"""Course 2 for the self-taught math AI: multiplying, algebra (solve for x) and calculus (derivatives).

It works just like course 1 (selfmath.py): a tiny GPT writes its own quiz, mostly about what it's worst at,
answers every question, a checker marks each answer, and it learns from the right answers. It's a new,
separate brain, because course 1's brain only knows the 14 symbols of adding and subtracting, and this
course needs more: x, ^, *, and "d/dx".

Questions look like this (the answer comes after the last "="):
    7*8=              ->  56          (written backward, "65", like course 1: ones digit first)
    x+7=15 x=         ->  8
    3x+5=20 x=        ->  5
    d/dx 4x^3=        ->  12x^2
    d/dx 3x^2-5x=     ->  6x-5
"""
import json
import os
import random
import re
import threading
import time
from collections import deque

import numpy as np

import mathengine
from tinygpt import TinyGPT

VOCAB = " 0123456789+-*=.x^d/"
TOK = {c: i for i, c in enumerate(VOCAB)}
Q_LEN, A_LEN = 16, 12          # longest question "d/dx 9x^5-9x^4=" (15), longest answer "45x^4-36x^3" + "."
PASS = 0.95                    # the test score needed to move up a level (a bit lower than course 1: these are harder)
BATCH, REVIEW = 48, 16


# ---------------------------------------------------------------- writing polynomials the same way every time
def term(c, n):
    """One term: (12, 2) -> '12x^2', (1, 1) -> 'x', (5, 0) -> '5'."""
    c = int(c)
    sign = "-" if c < 0 else ""
    c = abs(c)
    if n == 0:
        return sign + str(c)
    xs = "x" if n == 1 else "x^%d" % n
    return sign + ("" if c == 1 else str(c)) + xs


def poly_text(terms):
    """[(3, 2), (-5, 1)] -> '3x^2-5x' (biggest power first, zeros left out)."""
    out = ""
    for c, n in sorted([t for t in terms if t[0]], key=lambda t: -t[1]):
        s = term(c, n)
        out += s if not out or s.startswith("-") else "+" + s
    return out or "0"


def compact(poly):
    """A mathengine.Poly written the course's way (only for whole-number coefficients)."""
    return poly_text([(int(c), p) for p, c in poly.t.items()])


# ---------------------------------------------------------------- the levels: each makes (question, answer, kind of question)
def _mul1(r):
    a, b = r.randint(2, 9), r.randint(2, 9)
    return "%d*%d=" % (a, b), str(a * b)[::-1], "answer has %d digit%s" % (len(str(a * b)), "s" if a * b > 9 else "")


def _mul2(r):
    a, b = r.randint(10, 99), r.randint(2, 9)
    carries = sum(1 for d in str(a) if int(d) * b >= 10)
    return "%d*%d=" % (a, b), str(a * b)[::-1], "%d carr%s" % (carries, "y" if carries == 1 else "ies")


def _solve1(r):
    if r.random() < 0.5:
        x, b = r.randint(0, 30), r.randint(1, 20)
        return "x+%d=%d x=" % (b, x + b), str(x), "x + something"
    b = r.randint(1, 20)
    x = r.randint(b, b + 30)
    return "x-%d=%d x=" % (b, x - b), str(x), "x - something"


def _solve2(r):
    a, x, b = r.randint(2, 9), r.randint(0, 12), r.randint(0, 20)
    op = r.choice("+-")
    c = a * x + b if op == "+" else a * x - b
    if c < 0:
        op, c = "+", a * x + b
    q = "%dx%s%d=%d x=" % (a, op, b, c) if b else "%dx=%d x=" % (a, c)
    return q, str(x), "%s, a is %s" % ("ax + b" if op == "+" else "ax - b", "2 to 5" if a <= 5 else "6 to 9")


def _deriv1(r):
    a, n = r.randint(1, 9), r.randint(1, 5)
    return "d/dx %s=" % term(a, n), term(a * n, n - 1), "power %d" % n


def _deriv2(r):
    n1 = r.randint(2, 5)
    n2 = r.randint(0, n1 - 1)
    a, b = r.randint(1, 9), r.randint(1, 9) * r.choice([1, -1])
    q = "d/dx %s=" % poly_text([(a, n1), (b, n2)])
    return q, poly_text([(a * n1, n1 - 1), (b * n2, n2 - 1)] if n2 else [(a * n1, n1 - 1)]), \
        "highest power %d%s" % (n1, ", with a number on its own" if n2 == 0 else "")


LEVELS = [
    {"name": "Multiplying 1-digit numbers", "make": _mul1, "backward": True},
    {"name": "Multiplying 2-digit × 1-digit", "make": _mul2, "backward": True},
    {"name": "Algebra: solve x + b = c", "make": _solve1},
    {"name": "Algebra: solve ax + b = c", "make": _solve2},
    {"name": "Calculus: derivative of one term", "make": _deriv1},
    {"name": "Calculus: derivative of two terms", "make": _deriv2},
    {"name": "Mixed: everything so far", "make": None},
]


def make(level, r):
    if LEVELS[level]["make"] is None:                                # the mixed level picks any earlier level
        level = r.randrange(len(LEVELS) - 1)
    q, a, kind = LEVELS[level]["make"](r)
    return q, a, kind, LEVELS[level].get("backward", False)


def readable(q, a, backward):
    """For people: ('7*8=', '65') -> ('7 × 8', '56'), ('x-2=2 x=', '4') -> ('x − 2 = 2, x', '4')."""
    q = q.rstrip("=")
    solve = q.endswith(" x")
    if solve:
        q = q[:-2]
    q = q.replace("*", " × ")
    q = re.sub(r"(?<=[\dx])([+-])(?=[\dx])", lambda m: " − " if m.group(1) == "-" else " + ", q)
    q = " ".join(q.replace("=", " = ").split()) + (", x" if solve else "")
    return q, (a[::-1] if backward and a else a)


def encode(q, a=None):
    s = q.rjust(Q_LEN)                                               # questions are lined up on the right
    if a is not None:
        s += (a + ".").ljust(A_LEN)
    return [TOK[c] for c in s]


def decode(tokens):
    s = "".join(VOCAB[t] for t in tokens)
    return s.split(".")[0].strip() if "." in s else None            # no "." means it never finished


def pi_temperature():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except (OSError, ValueError):
        return None


class AdvancedMathAI:
    name = "Course 2: Algebra & Calculus"

    def __init__(self, data_dir, seed=None):
        self.dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.model_file = os.path.join(data_dir, "math2_model.npz")
        self.state_file = os.path.join(data_dir, "math2_state.json")
        self.rng = random.Random(seed)
        self.lock = threading.Lock()
        self.brain = threading.Lock()
        self.paused = False
        self.hot = False
        self.feed = deque(maxlen=40)
        self.speed = deque(maxlen=20)
        self._skills = {}
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
    def skills_for(self, level):
        """The kinds of question at a level, found by making 2,000 random ones."""
        if level not in self._skills:
            r = random.Random(1)
            self._skills[level] = sorted({make(level, r)[2] for _ in range(2000)})
        return self._skills[level]

    def write_quiz(self, n):
        st, lv = self.state, self.state["level"]
        skills = self.skills_for(lv)
        weights = [1.05 - st["skills"].get("%d|%s" % (lv, k), 0.0) for k in skills]
        quiz = []
        for _ in range(n):
            x = self.rng.random()
            if lv > 0 and x < 0.2:
                quiz.append(make(self.rng.randrange(lv), self.rng))                  # review an earlier level
            elif x < 0.45:
                quiz.append(make(lv, self.rng))
            else:
                want = self.rng.choices(skills, weights)[0]                           # its weak spots
                for _ in range(100):
                    q = make(lv, self.rng)
                    if q[2] == want:
                        break
                quiz.append(q)
        return quiz

    # ------------------------------------------------------------ 2. answering
    def answer(self, quiz):
        out = self.model.generate(np.array([encode(q[0]) for q in quiz]), A_LEN, stop=TOK["."])
        return [decode(row[Q_LEN:]) for row in out]

    # ------------------------------------------------------------ one round of self-teaching
    def round(self):
        t0 = time.time()
        st, lv = self.state, self.state["level"]
        quiz = self.write_quiz(BATCH)
        review = [tuple(x) for x in self.rng.sample(st["notebook"], min(REVIEW, len(st["notebook"])))]
        allq = quiz + review
        with self.brain:
            answers = self.answer(allq)
        right = 0
        with self.lock:
            for item, ans in zip(allq, answers):
                q, truth, kind, backward = item
                ok = ans == truth                                                     # 3. the checker
                key = "%d|%s" % (lv, kind)
                if item in review:
                    if ok and list(item) in st["notebook"]:
                        st["notebook"].remove(list(item))
                else:
                    st["skills"][key] = 0.97 * st["skills"].get(key, 0.0) + 0.03 * ok
                    if not ok:
                        st["notebook"].append(list(item))
                right += ok
            st["notebook"] = st["notebook"][-500:]
            for item, ans in list(zip(allq, answers))[:6]:
                q, truth, kind, backward = item
                shown_q, shown_truth = readable(q, truth, backward)
                self.feed.appendleft({"q": shown_q, "answer": readable(q, ans, backward)[1] if ans else None,
                                      "truth": shown_truth, "ok": ans == truth, "review": item in review})
        # 4. learn from the right answers
        seqs = np.array([encode(q, truth) for q, truth, _, _ in allq])
        w = np.zeros((len(allq), seqs.shape[1] - 1), np.float32)
        for i, (_, truth, _, _) in enumerate(allq):
            w[i, Q_LEN - 1:Q_LEN - 1 + len(truth) + 1] = 1.0                          # the answer and its "."
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
        lv = self.state["level"]
        r = random.Random()
        qs = [make(lv, r) for _ in range(n)]
        with self.brain:
            got = self.answer(qs)
        acc = sum(g == q[1] for q, g in zip(qs, got)) / n
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

    def save(self):
        with self.brain, self.lock:
            self.model.save(self.model_file)
            tmp = self.state_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.state, f)
            os.replace(tmp, self.state_file)
            self.saved_at = time.time()

    def skill_rows(self):
        lv = self.state["level"]
        return [{"label": k, "acc": round(100 * self.state["skills"].get("%d|%s" % (lv, k), 0.0))} for k in self.skills_for(lv)]

    # ------------------------------------------------------------ you ask it a question
    @staticmethod
    def to_question(text):
        """'7 x 8', '3x + 5 = 20' or 'derivative of 4x^3' -> the course's question form, its answer, and whether
        it's written backward. Raises ValueError if it's not something this course practices."""
        t = text.lower().replace(" ", "").replace("×", "*").replace("−", "-").rstrip("?=.")
        m = re.fullmatch(r"(\d{1,2})[*x](\d{1,2})", t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a < 10 and b >= 10:
                a, b = b, a                                     # it practices 47*8, not 8*47
            if b > 9:
                raise ValueError("this course only practices multiplying by a 1-digit number")
            return "%d*%d=" % (a, b), str(a * b)[::-1], True
        m = re.fullmatch(r"(?:solve)?(\d?x[+-]\d{1,3}|\d?x)=(\d{1,3})(?:,?x)?", t)
        if m:
            eq = m.group(1) + "=" + m.group(2)
            xs = mathengine.solve(eq)
            return eq + " x=", mathengine.fmt_number(xs[0]), False
        m = re.fullmatch(r"(?:d/dx|derivativeof|thederivativeof|differentiate)(.+)", t)
        if m:
            p = mathengine.parse(m.group(1))
            if p.degree() > 5 or len(p.t) > 2 or any(c.denominator != 1 or abs(c) > 9 for c in p.t.values()):
                raise ValueError("this course only practices up to 2 terms, numbers up to 9 and powers up to 5")
            return "d/dx %s=" % compact(p), compact(p.derivative()), False
        raise ValueError("Course 2 practices questions like 7*8, 3x+5=20 or d/dx 4x^3")

    def ask(self, text):
        q, truth, backward = self.to_question(text)
        if len(q) > Q_LEN or len(truth) >= A_LEN:
            raise ValueError("that question is too long for this tiny brain")
        with self.brain:
            ans = self.answer([(q, truth, "", backward)])[0]
            seq = np.array([encode(q, truth)])[:, :-1]
            self.model.forward(seq, keep=True)
            start = Q_LEN - len(q)
            rows = range(Q_LEN - 1, Q_LEN - 1 + len(truth))
            attn = [[[round(float(v), 3) for v in A[0].mean(0)[r, start:Q_LEN]] for r in rows] for A in self.model.attn]
        shown_q, shown_truth = readable(q, truth, backward)
        return {"question": shown_q, "answer": readable(q, ans, backward)[1] if ans else None, "truth": shown_truth,
                "attention": attn, "tokens": list(q), "rows": list(truth if not backward else truth),
                "course": 2}
