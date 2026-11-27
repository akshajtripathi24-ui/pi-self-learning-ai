"""A small, exact math engine for algebra and calculus with one letter, x.

It understands polynomials like 3x^2 - 4x + 1, (x+2)(x-3) or 2(x+1)^2, and can:
  - solve equations:            3x + 5 = 20        ->  x = 5
  - take derivatives:           d/dx 4x^3 + 2x     ->  12x^2 + 2
  - take integrals:             integral of 6x^2   ->  2x^3 + C
  - work out plain arithmetic:  (12 + 8) * 3       ->  60
Every number is kept as an exact fraction, so 1/3 stays 1/3 and nothing gets rounded by mistake.

It never runs the text it's given as code: it reads it one symbol at a time, and refuses anything
that isn't numbers, x, + - * / ^ and brackets. That makes it safe to use on what an AI writes.
"""
import math
import re
from fractions import Fraction

MAX_POWER = 8            # x^8 is plenty for school math, and keeps the work small


class MathError(ValueError):
    pass


class Poly:
    """A polynomial: {power: coefficient}. 3x^2 - 4 is {2: 3, 0: -4}."""

    def __init__(self, terms=None):
        self.t = {p: Fraction(c) for p, c in (terms or {}).items() if c != 0}

    @staticmethod
    def num(n):
        return Poly({0: Fraction(n)})

    def degree(self):
        return max(self.t) if self.t else 0

    def __add__(self, o):
        out = dict(self.t)
        for p, c in o.t.items():
            out[p] = out.get(p, 0) + c
        return Poly(out)

    def __neg__(self):
        return Poly({p: -c for p, c in self.t.items()})

    def __sub__(self, o):
        return self + (-o)

    def __mul__(self, o):
        out = {}
        for p1, c1 in self.t.items():
            for p2, c2 in o.t.items():
                if p1 + p2 > MAX_POWER:
                    raise MathError("the power gets too big")
                out[p1 + p2] = out.get(p1 + p2, 0) + c1 * c2
        return Poly(out)

    def __eq__(self, o):
        return isinstance(o, Poly) and self.t == o.t

    def is_number(self):
        return all(p == 0 for p in self.t)

    def value(self, x=0):
        return sum(c * Fraction(x) ** p for p, c in self.t.items()) if self.t else Fraction(0)

    def derivative(self):
        return Poly({p - 1: c * p for p, c in self.t.items() if p > 0})

    def integral(self):
        return Poly({p + 1: c / (p + 1) for p, c in self.t.items()})

    def __str__(self):
        if not self.t:
            return "0"
        parts = []
        for p in sorted(self.t, reverse=True):
            c = self.t[p]
            sign = "-" if c < 0 else "+"
            c = abs(c)
            cs = fmt_number(c)
            if p == 0:
                body = cs
            else:
                xs = "x" if p == 1 else "x^%d" % p
                body = xs if c == 1 else ("(%s)%s" % (cs, xs) if c.denominator != 1 else cs + xs)
            parts.append((sign, body))
        first_sign, first = parts[0]
        out = ("-" if first_sign == "-" else "") + first
        for sign, body in parts[1:]:
            out += " %s %s" % (sign, body)
        return out


def fmt_number(f):
    f = Fraction(f)
    return str(f.numerator) if f.denominator == 1 else "%d/%d" % (f.numerator, f.denominator)


# ---------------------------------------------------------------- reading math text, one symbol at a time
def _tokens(text):
    t = text.lower().replace("×", "*").replace("·", "*").replace("÷", "/").replace("−", "-").replace("²", "^2").replace("³", "^3")
    t = t.replace("**", "^").replace(" ", "")
    if not t or len(t) > 120 or not re.fullmatch(r"[0-9x+\-*/^().]+", t):
        raise MathError("that isn't math I can read")
    out = re.findall(r"\d+(?:\.\d+)?|[x+\-*/^()]", t)
    if "".join(out) != t:
        raise MathError("that isn't math I can read")
    return out


class _Reader:
    """Reads +, -, *, /, ^, brackets, and 'implied' multiplication like 3x, 2(x+1) or (x+1)(x-1)."""

    def __init__(self, tokens):
        self.k, self.i = tokens, 0

    def peek(self):
        return self.k[self.i] if self.i < len(self.k) else None

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expr(self):
        out = self.term()
        while self.peek() in ("+", "-"):
            out = out + self.term() if self.take() == "+" else out - self.term()
        return out

    def term(self):
        out = self.factor()
        while self.peek() is not None and (self.peek() in ("*", "/") or self.peek() == "x" or self.peek() == "("
                                           or re.match(r"\d", self.peek())):
            op = self.take() if self.peek() in ("*", "/") else "*"          # "3x" means 3 * x
            right = self.factor()
            if op == "*":
                out = out * right
            else:
                if not right.is_number() or right.value() == 0:
                    raise MathError("I can only divide by a number that isn't 0")
                out = out * Poly.num(1 / right.value())
        return out

    def factor(self):
        if self.peek() == "-":
            self.take()
            return -self.factor()
        if self.peek() == "+":
            self.take()
            return self.factor()
        base = self.atom()
        if self.peek() == "^":
            self.take()
            power = self.factor()
            if not power.is_number() or power.value().denominator != 1 or not 0 <= power.value() <= MAX_POWER:
                raise MathError("powers must be whole numbers from 0 to %d" % MAX_POWER)
            out = Poly.num(1)
            for _ in range(int(power.value())):
                out = out * base
            return out
        return base

    def atom(self):
        tok = self.take()
        if tok is None:
            raise MathError("the math stops too early")
        if tok == "x":
            return Poly({1: 1})
        if tok == "(":
            inside = self.expr()
            if self.take() != ")":
                raise MathError("a bracket isn't closed")
            return inside
        if re.match(r"\d", tok):
            return Poly.num(Fraction(tok))
        raise MathError("I didn't expect '%s' there" % tok)


def parse(text):
    """'3x^2 - 4x + 1' -> Poly. Raises MathError for anything it can't read."""
    r = _Reader(_tokens(text))
    out = r.expr()
    if r.peek() is not None:
        raise MathError("I didn't expect '%s' there" % r.peek())
    return out


# ---------------------------------------------------------------- solving
def solve(equation):
    """'3x + 5 = 20' -> [5]. Works for equations up to x^2. Answers are exact fractions,
    or rounded decimals when the answer is a square root that isn't whole."""
    if equation.count("=") != 1:
        raise MathError("an equation needs exactly one =")
    left, right = equation.split("=")
    p = parse(left) - parse(right)
    d = p.degree()
    a, b, c = p.t.get(2, 0), p.t.get(1, 0), p.t.get(0, 0)
    if d == 0:
        raise MathError("every x is true" if c == 0 else "no x makes this true")
    if d == 1:
        return [-c / b]
    if d == 2:
        disc = b * b - 4 * a * c
        if disc < 0:
            raise MathError("no real x makes this true")
        root = _exact_sqrt(disc)
        if root is not None:
            xs = {(-b + root) / (2 * a), (-b - root) / (2 * a)}
        else:
            s = math.sqrt(disc)
            xs = {round((-float(b) + s) / (2 * float(a)), 4), round((-float(b) - s) / (2 * float(a)), 4)}
        return sorted(xs)
    raise MathError("I can only solve equations up to x^2")


def _exact_sqrt(f):
    n, d = math.isqrt(f.numerator), math.isqrt(f.denominator)
    return Fraction(n, d) if n * n == f.numerator and d * d == f.denominator else None


def show_x(values):
    return ", ".join("x = " + (fmt_number(v) if isinstance(v, Fraction) else ("%g" % v)) for v in values)


# ---------------------------------------------------------------- finding math in a question (for the Chat tab)
def find_problem(text):
    """Look for algebra, calculus or arithmetic in a question. Returns (kind, what, answer) or None,
    e.g. ("solve", "3x + 5 = 20", "x = 5") or ("derivative", "4x^3 + 2x", "12x^2 + 2")."""
    t = text.lower().replace("’", "'")
    t = re.sub(r"\bsquared\b", "^2", t)
    t = re.sub(r"\bcubed\b", "^3", t)
    t = re.sub(r"\bto the power of\b", "^", t)
    t = re.sub(r"\bmultiplied by\b|\btimes\b", "*", t)
    t = re.sub(r"\bdivided by\b", "/", t)
    t = re.sub(r"\bplus\b", "+", t)
    t = re.sub(r"\bminus\b", "-", t)
    if not re.search(r"=|deriv|d/dx|integra|differentiat|solve|x\s*\^|\dx", t):   # no algebra: "5 x 4" means times
        t = re.sub(r"(?<=[\d)])\s+x\s+(?=[\d(])", " * ", t)
    math_chars = r"[0-9x+\-*/^(). ×÷²³]"
    # derivatives: "derivative of 4x^3", "d/dx 4x^3", "differentiate 4x^3"
    m = re.search(r"(?:derivative of|differentiate|d/dx)\s*(?:of\s*)?(%s+)" % math_chars, t)
    if m:
        what = m.group(1).strip(" .")
        try:
            return "derivative", str(parse(what)), str(parse(what).derivative())
        except MathError:
            pass
    # integrals: "integral of 6x^2", "integrate 6x^2"
    m = re.search(r"(?:integral of|integrate|antiderivative of)\s*(%s+)" % math_chars, t)
    if m:
        what = m.group(1).strip(" .")
        try:
            return "integral", str(parse(what)), str(parse(what).integral()) + " + C"
        except MathError:
            pass
    # equations: "solve 3x + 5 = 20", "what is x if 2x - 4 = 10"
    m = re.search(r"(%s+=%s+)" % (math_chars, math_chars), t)
    if m and "x" in m.group(1):
        eq = m.group(1).strip(" .")
        try:
            return "solve", eq.replace(" ", ""), show_x(solve(eq))
        except MathError as e:
            return "solve", eq.replace(" ", ""), str(e)
    # plain arithmetic: the longest piece of math with an operator in it
    for piece in sorted(re.findall(r"[\d(][\d\s+\-*/^().]*[\d)]", t.replace(",", "")), key=len, reverse=True):
        if not re.search(r"\d\s*[-+*/^]\s*[\d(]", piece):
            continue
        try:
            p = parse(piece)
            if p.is_number():
                v = p.value()
                return "arithmetic", " ".join(piece.split()), fmt_number(v) if v.denominator == 1 else "%s (about %.6g)" % (fmt_number(v), float(v))
        except MathError:
            continue
    return None
