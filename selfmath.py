"""Part 1: the self-taught math AI.

A tiny GPT starts knowing nothing. Over and over, it:
  1. writes its own quiz, choosing more questions about the skills it's worst at,
  2. answers every question, one digit at a time,
  3. has a calculator check each answer (the "checker", so it can't fool itself),
  4. learns from the right answers, and saves its mistakes in a notebook to practice again later.
When it scores 97% on a test it has never seen, it moves up a level.
"""
import json
import os
import random
import threading
import time
from collections import deque

import numpy as np

from tinygpt import TinyGPT

VOCAB = "0123456789+-=."
TOK = {c: i for i, c in enumerate(VOCAB)}
Q_LEN, A_LEN = 8, 5           # "047+038=" and the answer written backward, "5800." (see why in docs/02)
LEVELS = [
    {"name": "Adding 1-digit numbers", "ops": "+", "a": (0, 9), "b": (0, 9)},
    {"name": "2-digit + 1-digit", "ops": "+", "a": (10, 99), "b": (0, 9)},
    {"name": "2-digit + 2-digit", "ops": "+", "a": (10, 99), "b": (10, 99)},
    {"name": "3-digit + 3-digit", "ops": "+", "a": (100, 999), "b": (100, 999)},
    {"name": "Subtracting 2-digit numbers", "ops": "-", "a": (10, 99), "b": (0, 99)},
    {"name": "Subtracting 3-digit numbers", "ops": "-", "a": (100, 999), "b": (0, 999)},
    {"name": "Adding and subtracting", "ops": "+-", "a": (0, 999), "b": (0, 999)},
]
PASS = 0.97          # the test score needed to move up a level
BATCH, REVIEW = 48, 16   # new questions per round, and old mistakes to practice again


def carries(a, b, op):
    """How many times you'd "carry" (adding) or "borrow" (subtracting). These are the hard parts."""
    n, c = 0, 0
    for _ in range(3):
        da, db = a % 10, b % 10
        if op == "+":
            c = 1 if da + db + c >= 10 else 0
        else:
            c = 1 if da - db - c < 0 else 0
        n += c
        a //= 10
        b //= 10
    return n


def pi_temperature():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except (OSError, ValueError):
        return None


def calculator(a, b, op):
    return a + b if op == "+" else a - b


def encode(a, b, op, answer=None):
    s = "%03d%s%03d=" % (a, op, b)
    if answer is not None:
        s += ("%04d" % answer)[::-1] + "."      # written backward: ones digit first, like when you add by hand
    return [TOK[c] for c in s]


def decode_answer(tokens):
    s = "".join(VOCAB[t] for t in tokens[:4])
    return int(s[::-1]) if s.isdigit() else None


class MathAI:
    def __init__(self, data_dir, seed=None):
        self.dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.model_file = os.path.join(data_dir, "math_model.npz")
        self.state_file = os.path.join(data_dir, "math_state.json")
        self.rng = random.Random(seed)
        self.lock = threading.Lock()             # protects the numbers the web page reads
        self.brain = threading.Lock()            # only one thing uses the model at a time (training, or your question)
        self.paused = False
        self.hot = False
        self.feed = deque(maxlen=40)             # the latest questions it asked itself, for the web page
        self.speed = deque(maxlen=20)
        if os.path.exists(self.model_file) and os.path.exists(self.state_file):
            self.model, _ = TinyGPT.load(self.model_file)
            with open(self.state_file) as f:
                self.state = json.load(f)
        else:
            self.reset()
        self.saved_at = time.time()

    def reset(self):
        with self.brain, self.lock:
            self.model = TinyGPT(len(VOCAB), Q_LEN + A_LEN - 1, dim=64, heads=4, layers=2, seed=self.rng.randrange(10 ** 6))
            self.state = {"round": 0, "questions": 0, "level": 0, "skills": {}, "notebook": [], "history": [],
                          "tests": [], "level_ups": [], "started": time.time(), "seconds": 0.0, "mastered": False}
            self.feed.clear()

    # ------------------------------------------------------------ 1. writing its own quiz
    def skill_of(self, a, b, op, level):
        return "%d%s%d" % (level, op, carries(a, b, op))

    def skills_for(self, level):
        """The kinds of question that can happen at a level, like "adding with 2 carries"."""
        if not hasattr(self, "_skills"):
            self._skills = {}
        if level not in self._skills:
            r, L = random.Random(1), LEVELS[level]
            found = set()
            for _ in range(4000):
                o = r.choice(L["ops"])
                a, b = r.randint(*L["a"]), r.randint(*L["b"])
                if o == "-" and b > a:
                    a, b = b, a
                found.add((o, carries(a, b, o)))
            self._skills[level] = sorted(found)
        return self._skills[level]

    def make_question(self, level, op=None, want_carries=None):
        L = LEVELS[level]
        for _ in range(200):
            o = op or self.rng.choice(L["ops"])
            a, b = self.rng.randint(*L["a"]), self.rng.randint(*L["b"])
            if o == "-" and b > a:
                a, b = b, a
            if want_carries is None or carries(a, b, o) == want_carries:
                return a, b, o
        return a, b, o

    def write_quiz(self, n):
        """Most questions practice its weakest skills. A quarter are random, and a fifth review earlier levels (so it doesn't forget them)."""
        st, lv = self.state, self.state["level"]
        skills = self.skills_for(lv)
        weights = [1.05 - st["skills"].get("%d%s%d" % (lv, o, c), 0.0) for o, c in skills]
        quiz = []
        for i in range(n):
            r = self.rng.random()
            if lv > 0 and r < 0.2:
                quiz.append(self.make_question(self.rng.randrange(lv)))          # review an earlier level
            elif r < 0.45:
                quiz.append(self.make_question(lv))                              # anything at this level
            else:
                o, c = self.rng.choices(skills, weights)[0]                      # its weak spots
                quiz.append(self.make_question(lv, o, c))
        return quiz

    # ------------------------------------------------------------ 2. answering, one digit at a time
    def answer(self, quiz):
        q = np.array([encode(a, b, o) for a, b, o in quiz])
        out = self.model.generate(q, A_LEN)
        return [decode_answer(row[Q_LEN:]) for row in out]

    # ------------------------------------------------------------ one round of self-teaching
    def round(self):
        t0 = time.time()
        st = self.state
        lv = st["level"]
        quiz = self.write_quiz(BATCH)
        review = [tuple(x) for x in self.rng.sample(st["notebook"], min(REVIEW, len(st["notebook"])))]
        allq = quiz + review
        with self.brain:
            answers = self.answer(allq)
        right = 0
        with self.lock:
            for (a, b, o), ans in zip(allq, answers):
                truth = calculator(a, b, o)                                      # 3. the checker
                ok = ans == truth
                key = self.skill_of(a, b, o, lv)
                st["skills"][key] = 0.97 * st["skills"].get(key, 0.0) + 0.03 * ok
                if (a, b, o) in review:
                    if ok and [a, b, o] in st["notebook"]:
                        st["notebook"].remove([a, b, o])                         # learned it: out of the notebook
                elif not ok:
                    st["notebook"].append([a, b, o])                             # a mistake: into the notebook
                right += ok
            st["notebook"] = st["notebook"][-500:]
            for (a, b, o), ans in list(zip(allq, answers))[:6]:
                self.feed.appendleft({"q": "%d %s %d" % (a, o.replace("-", "−"), b), "answer": ans, "truth": calculator(a, b, o),
                                      "ok": ans == calculator(a, b, o), "review": (a, b, o) in review})
        # 4. learn from the right answers (the calculator's), for every question
        seqs = np.array([encode(a, b, o, calculator(a, b, o)) for a, b, o in allq])
        w = np.zeros((len(allq), seqs.shape[1] - 1), np.float32)
        w[:, Q_LEN - 1:] = 1.0                                                   # only the answer digits count
        with self.brain:
            loss = self.model.learn(seqs[:, :-1], seqs[:, 1:], w, lr=2e-3)
        with self.lock:
            st["round"] += 1
            st["questions"] += len(allq)
            st["seconds"] += time.time() - t0
            if st["round"] % 10 == 0:
                st["history"].append([st["round"], lv, round(right / len(allq) * 100, 1), round(loss, 4)])
                st["history"] = st["history"][-5000:]
        self.speed.append(time.time() - t0)
        if st["round"] % 100 == 0:
            self.test()
        return right / len(allq), loss

    def test(self, n=300):
        """A test of brand-new questions at its level (it doesn't learn from these)."""
        lv = self.state["level"]
        qs = [self.make_question(lv) for _ in range(n)]
        with self.brain:
            got = self.answer(qs)
        acc = sum(ans == calculator(a, b, o) for (a, b, o), ans in zip(qs, got)) / n
        with self.lock:
            st = self.state
            st["tests"].append([st["round"], lv, round(acc * 100, 1)])
            st["tests"] = st["tests"][-2000:]
            if acc >= PASS:
                if lv < len(LEVELS) - 1:
                    st["level"] = lv + 1
                    st["level_ups"].append([st["round"], lv + 1, st["questions"]])
                else:
                    st["mastered"] = True
        return acc

    def run(self):
        hot = False
        while True:
            temp = pi_temperature()
            if temp is not None:                  # rest if the Pi gets hot, until it's 8 °C cooler
                hot = temp >= 78 or (hot and temp > 70)
            self.hot = hot
            if self.paused or hot:
                time.sleep(2)
                continue
            try:
                self.round()
                if time.time() - self.saved_at > 300:
                    self.save()
            except Exception as e:
                print("math training error:", e, flush=True)
                time.sleep(5)

    def save(self):
        with self.brain, self.lock:
            self.model.save(self.model_file)
            tmp = self.state_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.state, f)
            os.replace(tmp, self.state_file)
            self.saved_at = time.time()

    def ask(self, a, b, op):
        """You ask it a question on the web page."""
        if op not in "+-" or not (0 <= a <= 999 and 0 <= b <= 999) or (op == "-" and b > a):
            raise ValueError("Use two numbers from 0 to 999 (and for −, the first must be bigger).")
        with self.brain:
            ans = self.answer([(a, b, op)])[0]
            self.model.forward(np.array([encode(a, b, op, calculator(a, b, op))])[:, :-1], keep=True)
            attn = [A[0].mean(0)[Q_LEN - 1:Q_LEN + 3, :Q_LEN].round(3).tolist() for A in self.model.attn]
        return {"answer": ans, "truth": calculator(a, b, op), "attention": attn}
