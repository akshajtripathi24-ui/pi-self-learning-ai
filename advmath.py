"""Courses 2 and 3 for the self-taught math AI.

  Course 2: multiplying, algebra (solve for x) and calculus (derivatives).
  Course 3: decimals, quadratic equations, integrals and longer derivatives.

They work just like course 1 (selfmath.py): a tiny GPT writes its own quiz, mostly about what it's worst at,
answers every question, a checker marks each answer, and it learns from the right answers. Each course has its
own brain, because a brain can only read and write the symbols it was built with: course 1 knows 14 symbols,
course 2 adds x, ^, * and "d/dx", and course 3 also needs a decimal point, "S" (for the integral sign ∫) and a comma.

Questions look like this (the answer comes after the last "="):
    course 2:  7*8=  -> 56 (written backward, "65")   3x+5=20 x=  -> 5      d/dx 3x^2-5x=  -> 6x-5
    course 3:  2.5+1.7= -> 4.2 (backward)   x^2-5x+6=0 x= -> 2,3   S 6x^2= -> 2x^3   d/dx x^3-4x^2+7x= -> 3x^2-8x+7
"""
import json
import os
import random
import re
import threading
import time
from collections import deque
from fractions import Fraction

import numpy as np

import mathengine
from tinygpt import TinyGPT

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


# ---------------------------------------------------------------- course 3
def dec(n, width=2):
    """A number of tenths, lined up the way you line up decimals on paper: 23 -> '02.3', 5 -> '00.5', 50 -> '05.0'.
    Every number has the same shape, so the digits are always in the same columns (like course 1's 047+038)."""
    return "%0*d.%d" % (width, n // 10, n % 10)


def _count(word, n):
    return "no %sing" % word if n == 0 else "%d %s" % (n, word if n == 1 else word.replace("y", "ie") + "s")


def _dec_add(r):
    a, b = r.randint(1, 499), r.randint(1, 499)
    c1 = a % 10 + b % 10 >= 10                                      # carry from the tenths into the ones
    c2 = a // 10 % 10 + b // 10 % 10 + c1 >= 10                      # carry from the ones into the tens
    return "%s+%s=" % (dec(a), dec(b)), dec(a + b)[::-1], _count("carry", c1 + c2)


def _dec_sub(r):
    a, b = sorted((r.randint(1, 499), r.randint(1, 499)), reverse=True)
    b1 = a % 10 < b % 10                                            # borrow from the ones for the tenths
    b2 = a // 10 % 10 - b1 < b // 10 % 10                            # borrow from the tens for the ones
    return "%s-%s=" % (dec(a), dec(b)), dec(a - b)[::-1], _count("borrow", b1 + b2)


def _dec_mul(r):
    a, b = r.randint(1, 99), r.randint(2, 9)
    carries = sum(1 for d in "%02d" % a if int(d) * b >= 10)
    return "%s*%d=" % (dec(a, 1), b), dec(a * b)[::-1], "times, " + _count("carry", carries)    # (not mixed up with adding's)


def _quadratic(r):
    r1, r2 = sorted((r.randint(-9, 9), r.randint(-9, 9)))
    q = "%s=0 x=" % poly_text([(1, 2), (-(r1 + r2), 1), (r1 * r2, 0)])
    return q, ("%d" % r1 if r1 == r2 else "%d,%d" % (r1, r2)), \
        "one answer" if r1 == r2 else "a negative answer" if r1 < 0 else "two positive answers"


def _integral(r):
    n, k = r.randint(0, 4), r.randint(1, 9)
    return "S %s=" % term(k * (n + 1), n), term(k, n + 1), "power %d" % n


def _deriv3(r):
    powers = sorted(r.sample(range(0, 5), 3), reverse=True)
    terms = [(r.randint(1, 9) * (1 if i == 0 else r.choice([1, -1])), n) for i, n in enumerate(powers)]
    return "d/dx %s=" % poly_text(terms), poly_text([(c * n, n - 1) for c, n in terms if n]), "highest power %d" % powers[0]


LEVELS3 = [
    {"name": "Decimals: adding", "make": _dec_add, "backward": True},          # 02.5+01.7= -> 04.2, written 2.40
    {"name": "Decimals: subtracting", "make": _dec_sub, "backward": True},
    {"name": "Decimals: multiplying by a whole number", "make": _dec_mul, "backward": True},
    {"name": "Algebra: quadratic equations (x² …)", "make": _quadratic},
    {"name": "Calculus: integrals", "make": _integral},
    {"name": "Calculus: derivatives of three terms", "make": _deriv3},
    {"name": "Mixed: everything so far", "make": None},
]

COURSES = {
    2: {"n": 2, "name": "Course 2: Algebra & Calculus", "files": "math2", "vocab": " 0123456789+-*=.x^d/",
        "q_len": 16, "a_len": 12, "end": ".", "levels": LEVELS},
    3: {"n": 3, "name": "Course 3: Decimals & Harder Math", "files": "math3", "vocab": " 0123456789+-*=.x^d/S,#",
        "q_len": 22, "a_len": 18, "end": "#", "levels": LEVELS3},
}


def make(level, r, levels=LEVELS):
    if levels[level]["make"] is None:                                # the mixed level picks any earlier level
        level = r.randrange(len(levels) - 1)
    q, a, kind = levels[level]["make"](r)
    return q, a, kind, levels[level].get("backward", False)


def readable(q, a, backward):
    """For people: ('7*8=', '65') -> ('7 × 8', '56'), ('x-2=2 x=', '4') -> ('x − 2 = 2, x', '4')."""
    q = q.rstrip("=")
    solve = q.endswith(" x") and "=" in q              # "3x+5=20 x" is an equation; "d/dx x" isn't
    if solve:
        q = q[:-2]
    if q.startswith("S "):
        q = "∫ " + q[2:] + " dx"
    q = q.replace("*", " × ")
    q = re.sub(r"(?<=[\dx])([+-])(?=[\dx])", lambda m: " − " if m.group(1) == "-" else " + ", q)
    q = " ".join(q.replace("=", " = ").split()) + (", x" if solve else "")
    a = a[::-1] if backward and a else a
    if "." in q:                                     # course 3 lines decimals up with zeros: show 02.5 as 2.5, 27.0 as 27
        q = re.sub(r"\d+\.\d", lambda m: mathengine.fmt_number(Fraction(m.group())), q)
        if a and re.fullmatch(r"\d+\.\d", a):
            a = mathengine.fmt_number(Fraction(a))
    if a and q.startswith("∫"):
        a += " + C"
    return q, (a.replace(",", " or ") if solve and a else a)


def place_names(answer):
    """The places of an answer's digits, in the order the AI writes them (backward):
    '56' -> ones, tens; '04.2' -> tenths, point, ones, tens."""
    whole, _, frac = str(answer).partition(".")
    names = ["ones", "tens", "hundreds", "thousands", "ten thousands"]
    return ["tenths", "hundredths"][:len(frac)][::-1] + (["point"] if frac else []) + names[:len(whole)]


def pi_temperature():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except (OSError, ValueError):
        return None


class MathCourse:
    """One course of the self-taught math AI. Everything that's different between courses (its symbols, how long a
    question and answer can be, its levels and its files) comes from its entry in COURSES."""

    def __init__(self, data_dir, course=2, seed=None):
        spec = COURSES[course]
        self.n, self.name, self.levels = spec["n"], spec["name"], spec["levels"]
        self.vocab, self.end = spec["vocab"], spec["end"]
        self.tok = {c: i for i, c in enumerate(self.vocab)}
        self.q_len, self.a_len = spec["q_len"], spec["a_len"]
        self.dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.model_file = os.path.join(data_dir, spec["files"] + "_model.npz")
        self.state_file = os.path.join(data_dir, spec["files"] + "_state.json")
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
            self.model = TinyGPT(len(self.vocab), self.q_len + self.a_len - 1, dim=64, heads=4, layers=2,
                                 seed=self.rng.randrange(10 ** 6))
            self.state = {"round": 0, "questions": 0, "level": 0, "skills": {}, "notebook": [], "history": [],
                          "tests": [], "level_ups": [], "started": time.time(), "seconds": 0.0, "mastered": False}
            self.feed.clear()

    def make(self, level, r):
        return make(level, r, self.levels)

    # ------------------------------------------------------------ turning text into numbers for the brain, and back
    def encode(self, q, a=None):
        s = q.rjust(self.q_len)                                      # questions are lined up on the right
        if a is not None:
            s += (a + self.end).ljust(self.a_len)                    # the end mark says "my answer is finished"
        return [self.tok[c] for c in s]

    def decode(self, tokens):
        s = "".join(self.vocab[t] for t in tokens)
        return s.split(self.end)[0].strip() if self.end in s else None      # no end mark means it never finished

    # ------------------------------------------------------------ 1. writing its own quiz
    def skills_for(self, level):
        """The kinds of question at a level, found by making 2,000 random ones."""
        if level not in self._skills:
            r = random.Random(1)
            self._skills[level] = sorted({self.make(level, r)[2] for _ in range(2000)})
        return self._skills[level]

    def write_quiz(self, n):
        st, lv = self.state, self.state["level"]
        skills = self.skills_for(lv)
        weights = [1.05 - st["skills"].get("%d|%s" % (lv, k), 0.0) for k in skills]
        quiz = []
        for _ in range(n):
            x = self.rng.random()
            if lv > 0 and x < 0.2:
                quiz.append(self.make(self.rng.randrange(lv), self.rng))              # review an earlier level
            elif x < 0.45:
                quiz.append(self.make(lv, self.rng))
            else:
                want = self.rng.choices(skills, weights)[0]                           # its weak spots
                for _ in range(100):
                    q = self.make(lv, self.rng)
                    if q[2] == want:
                        break
                quiz.append(q)
        return quiz

    # ------------------------------------------------------------ 2. answering
    def answer(self, quiz):
        out = self.model.generate(np.array([self.encode(q[0]) for q in quiz]), self.a_len, stop=self.tok[self.end])
        return [self.decode(row[self.q_len:]) for row in out]

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
        seqs = np.array([self.encode(q, truth) for q, truth, _, _ in allq])
        w = np.zeros((len(allq), seqs.shape[1] - 1), np.float32)
        for i, (_, truth, _, _) in enumerate(allq):
            w[i, self.q_len - 1:self.q_len - 1 + len(truth) + 1] = 1.0              # the answer and its end mark
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
        qs = [self.make(lv, r) for _ in range(n)]
        with self.brain:
            got = self.answer(qs)
        acc = sum(g == q[1] for q, g in zip(qs, got)) / n
        with self.lock:
            st = self.state
            st["tests"].append([st["round"], lv, round(acc * 100, 1)])
            st["tests"] = st["tests"][-2000:]
            if acc >= PASS:
                if lv < len(self.levels) - 1:
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
    def to_question(self, text):
        """Your question -> the course's question form, its answer, and whether it's written backward.
        Raises ValueError if it's not something this course practices."""
        return (to_question2 if self.n == 2 else to_question3)(text)

    def ask(self, text):
        q, truth, backward = self.to_question(text)
        if len(q) > self.q_len or len(truth) >= self.a_len:
            raise ValueError("that question is too long for this tiny brain")
        with self.brain:
            ans = self.answer([(q, truth, "", backward)])[0]
            seq = np.array([self.encode(q, truth)])[:, :-1]
            self.model.forward(seq, keep=True)
            start = self.q_len - len(q)
            rows = range(self.q_len - 1, self.q_len - 1 + len(truth))
            attn = [[[round(float(v), 3) for v in A[0].mean(0)[r, start:self.q_len]] for r in rows] for A in self.model.attn]
        shown_q, shown_truth = readable(q, truth, backward)
        return {"question": shown_q, "answer": readable(q, ans, backward)[1] if ans else None, "truth": shown_truth,
                "attention": attn, "tokens": list(q), "rows": place_names(truth[::-1]) if backward else list(truth),
                "course": self.n}


def AdvancedMathAI(data_dir, seed=None):
    """Course 2 (the name it had before course 3 existed)."""
    return MathCourse(data_dir, 2, seed)


def HarderMathAI(data_dir, seed=None):
    """Course 3."""
    return MathCourse(data_dir, 3, seed)


# ---------------------------------------------------------------- reading your questions
def _tidy(text):
    return (str(text).lower().replace(" ", "").replace("×", "*").replace("−", "-").replace("÷", "/")
            .replace("∫", "integralof").rstrip("?=").rstrip("."))


def to_question2(text):
    """'7 x 8', '3x + 5 = 20' or 'derivative of 4x^3' -> course 2's question form."""
    t = _tidy(text)
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
        if xs[0].denominator != 1:
            raise ValueError("this course only practices equations where x is a whole number")
        return eq + " x=", mathengine.fmt_number(xs[0]), False
    m = re.fullmatch(r"(?:d/dx|derivativeof|thederivativeof|differentiate)(.+)", t)
    if m:
        p = mathengine.parse(m.group(1))
        if p.degree() > 5 or len(p.t) > 2 or any(c.denominator != 1 or abs(c) > 9 for c in p.t.values()):
            raise ValueError("this course only practices up to 2 terms, numbers up to 9 and powers up to 5")
        return "d/dx %s=" % compact(p), compact(p.derivative()), False
    raise ValueError("Course 2 practices questions like 7*8, 3x+5=20 or d/dx 4x^3")


DEC = r"(\d{1,2}(?:\.\d)?)"


def to_question3(text):
    """'2.5 + 1.7', 'x^2 - 5x + 6 = 0', 'integral of 6x^2' or 'd/dx x^3-4x^2+7x' -> course 3's question form."""
    t = _tidy(text)
    m = re.fullmatch(DEC + r"([+\-*x])" + DEC, t)
    if m:
        a, op, b = Fraction(m.group(1)), m.group(2).replace("x", "*"), Fraction(m.group(3))
        if op == "*":
            if a.denominator == 1 and b.denominator != 1:
                a, b = b, a                                 # it practices 2.5*3, not 3*2.5
            if b.denominator != 1 or not 2 <= b <= 9 or not 0 < a <= Fraction(99, 10):
                raise ValueError("this course only practices a decimal up to 9.9 times a whole number from 2 to 9")
            return "%s*%d=" % (dec(int(a * 10), 1), b), dec(int(a * b * 10))[::-1], True
        if not 0 < a <= Fraction(499, 10) or not 0 < b <= Fraction(499, 10):
            raise ValueError("this course only practices adding and subtracting decimals from 0.1 to 49.9")
        if op == "-" and b > a:
            raise ValueError("this course only practices subtracting a smaller number from a bigger one")
        truth = a + b if op == "+" else a - b
        return "%s%s%s=" % (dec(int(a * 10)), op, dec(int(b * 10))), dec(int(truth * 10))[::-1], True
    m = re.fullmatch(r"(?:solve)?(.*x\^2.*)=(.+?)(?:,x)?", t)
    if m:
        p = mathengine.parse(m.group(1)) - mathengine.parse(m.group(2))
        if p.degree() != 2:
            raise ValueError("that isn't a quadratic equation")
        if p.t[2] < 0:
            p = -p
        a, b, c = p.t.get(2, 0), p.t.get(1, 0), p.t.get(0, 0)
        if a != 1 or b.denominator != 1 or c.denominator != 1:
            raise ValueError("this course only practices quadratics that start with x^2 and have whole numbers")
        xs = [x for x in range(-9, 10) if x * x + b * x + c == 0]
        if not xs or (len(xs) == 1 and b * b != 4 * c):
            raise ValueError("this course only practices quadratics whose answers are whole numbers from -9 to 9")
        return "%s=0 x=" % compact(p), ",".join(str(x) for x in xs), False
    m = re.fullmatch(r"(?:theintegralof|integralof|integrate|antiderivativeof|s)(.+?)(?:dx)?", t)
    if m:
        p = mathengine.parse(m.group(1))
        if len(p.t) != 1:
            raise ValueError("this course only practices integrals of one term, like 6x^2")
        (n, c), = p.t.items()
        if n > 4 or c.denominator != 1 or c <= 0 or c % (n + 1) or c / (n + 1) > 9:
            raise ValueError("this course only practices integrals like 6x^2, where the answer has a whole number up to 9")
        return "S %s=" % compact(p), compact(p.integral()), False
    m = re.fullmatch(r"(?:d/dx|derivativeof|thederivativeof|differentiate)(.+)", t)
    if m:
        p = mathengine.parse(m.group(1))
        if p.degree() > 4 or len(p.t) != 3 or any(c.denominator != 1 or abs(c) > 9 for c in p.t.values()):
            raise ValueError("this course only practices 3 terms, numbers up to 9 and powers up to 4")
        return "d/dx %s=" % compact(p), compact(p.derivative()), False
    raise ValueError("Course 3 practices questions like 2.5+1.7, x^2-5x+6=0, integral of 6x^2 or d/dx x^3-4x^2+7x")
