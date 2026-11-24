"""Part 3: the model-collapse experiment. What happens when an AI learns only from its own writing?

Round 0: a fresh tiny GPT learns to write from 100 real space and robot facts (facts.txt).
Round 1: a new tiny GPT learns ONLY from sentences that round 0 wrote.
Round 2: a new one learns ONLY from round 1's sentences... and so on.
Nothing checks the sentences, so mistakes pile up. Watch the sentences get stranger and more repetitive.
Turn on "keep real sentences" and half of each round's lessons are the real facts again, which is the fix.
"""
import os
import random
import re
import threading
import time
from collections import Counter

import numpy as np

from tinygpt import TinyGPT

HERE = os.path.dirname(os.path.abspath(__file__))
CHARS = "^abcdefghijklmnopqrstuvwxyz ,."       # ^ = the start of a sentence
TOK = {c: i for i, c in enumerate(CHARS)}
CONTEXT = 40


def real_sentences():
    with open(os.path.join(HERE, "facts.txt")) as f:
        return [l.strip() for l in f if l.strip()]


def words(text):
    return re.findall(r"[a-z]+", text)


class Collapse:
    def __init__(self, rounds=6, steps=1500, sentences=150, temperature=0.9, keep_real=False, seed=None, on_update=None):
        self.rounds, self.steps, self.n, self.temp, self.keep_real = rounds, steps, sentences, temperature, keep_real
        self.rng = random.Random(seed)
        self.real = real_sentences()
        self.vocab = set(w for s in self.real for w in words(s))
        self.results = []          # one entry per round
        self.status = "waiting"
        self.progress = 0.0
        self.stop = False
        self.on_update = on_update

    def train(self, sentences, round_no):
        """A brand-new tiny GPT learns from these sentences."""
        text = "".join("^" + s + " " for s in sentences)
        data = np.array([TOK[c] for c in text if c in TOK])
        m = TinyGPT(len(CHARS), CONTEXT, dim=64, heads=4, layers=2, seed=self.rng.randrange(10 ** 6))
        nrng = np.random.RandomState(self.rng.randrange(10 ** 6))
        for step in range(self.steps):
            if self.stop:
                return None
            starts = nrng.randint(0, len(data) - CONTEXT - 1, 32)
            x = np.stack([data[s:s + CONTEXT] for s in starts])
            y = np.stack([data[s + 1:s + CONTEXT + 1] for s in starts])
            m.learn(x, y, np.ones_like(x, np.float32), lr=3e-3 if step < self.steps * 0.7 else 1e-3)
            if step % 100 == 0:
                self.progress = (round_no + step / self.steps) / self.rounds
                if self.on_update:
                    self.on_update(self)
        return m

    def write(self, m, n):
        """The model writes n sentences, one letter at a time, starting from ^."""
        start = np.full((n, 1), TOK["^"])
        out = m.generate(start, 90, temperature=self.temp, rng=np.random.RandomState(self.rng.randrange(10 ** 6)))
        sents = []
        for row in out:
            s = "".join(CHARS[t] for t in row[1:])
            s = s.split("^")[0]
            s = s[:s.index(".") + 1] if "." in s else s
            sents.append(s.strip())
        return [s for s in sents if s]

    def surprise(self, m):
        """How surprised the model is by the REAL facts (lower = it still knows how real sentences look)."""
        text = "".join("^" + s + " " for s in self.real)
        data = np.array([TOK[c] for c in text])
        idx = np.arange(0, len(data) - CONTEXT - 1, CONTEXT)
        x = np.stack([data[s:s + CONTEXT] for s in idx])
        y = np.stack([data[s + 1:s + CONTEXT + 1] for s in idx])
        loss, _ = m.loss_and_grads(x, y, np.ones_like(x, np.float32))
        return loss

    def measure(self, sents):
        ws = [w for s in sents for w in words(s)]
        real = sum(w in self.vocab for w in ws)
        exact = sum(s in self.real for s in sents)
        return {"real_words": round(100 * real / max(1, len(ws)), 1),          # words that exist in the real facts
                "different_words": len(set(ws)),                                  # how big its vocabulary still is
                "different_sentences": round(100 * len(set(sents)) / max(1, len(sents)), 1),
                "copied_facts": round(100 * exact / max(1, len(sents)), 1),        # sentences exactly like a real fact
                "top_words": Counter(ws).most_common(6)}

    def run(self):
        self.status = "running"
        lessons = self.real
        for r in range(self.rounds):
            t0 = time.time()
            m = self.train(lessons, r)
            if m is None:
                self.status = "stopped"
                return
            sents = self.write(m, self.n)
            res = dict(self.measure(sents), round=r, surprise=round(self.surprise(m), 3),
                       samples=self.rng.sample(sents, min(10, len(sents))), seconds=round(time.time() - t0),
                       learned_from="the 100 real facts" if r == 0 else ("its own writing + the real facts" if self.keep_real else "only the last round's writing"))
            self.results.append(res)
            if self.on_update:
                self.on_update(self)
            lessons = sents + (self.real if self.keep_real else [])
        self.progress = 1.0
        self.status = "done"
