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
from decimal import Decimal
from fractions import Fraction

MAX_POWER = 8            # x^8 is plenty for school math, and keeps the work small
MAX_BITS = 3400          # numbers up to about 1,000 digits: bigger ones could keep a Pi busy for hours


class MathError(ValueError):
    pass


class Poly:
    """A polynomial: {power: coefficient}. 3x^2 - 4 is {2: 3, 0: -4}."""

    def __init__(self, terms=None):
        self.t = {p: Fraction(c) for p, c in (terms or {}).items() if c != 0}
        for c in self.t.values():
            if max(abs(c.numerator).bit_length(), c.denominator.bit_length()) > MAX_BITS:
                raise MathError("that number is too big for me (more than 1,000 digits)")

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
                body = xs if c == 1 else ("(%s)%s" % (cs, xs) if "/" in cs else cs + xs)
            parts.append((sign, body))
        first_sign, first = parts[0]
        out = ("-" if first_sign == "-" else "") + first
        for sign, body in parts[1:]:
            out += " %s %s" % (sign, body)
        return out


def fmt_number(f):
    """Whole numbers as they are, numbers that end as decimals as decimals (5/2 -> 2.5, 18/5 -> 3.6),
    and others as fractions (7/3), because 2.333... never ends."""
    f = Fraction(f)
    if f.denominator == 1:
        return str(f.numerator)
    d = f.denominator
    for p in (2, 5):
        while d % p == 0:
            d //= p
    if d == 1:                                        # only 2s and 5s underneath: it ends, so write it as a decimal
        text = format(Decimal(f.numerator) / Decimal(f.denominator), "f")     # "f": 0.0000001, not 1E-7
        if len(text) <= 14:
            return text
    return "%d/%d" % (f.numerator, f.denominator)


def is_decimal_text(text):
    return "/" not in text


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
            if base.is_number() and power.is_number() and power.value().denominator == 1:
                b, n = base.value(), int(power.value())         # a plain number, like 2^10 or 10^-2
                if b == 0 and n < 0:
                    raise MathError("I can only divide by a number that isn't 0")
                if b in (0, 1, -1):
                    return Poly.num(b ** (n % 2 + 2 if b == -1 and n else n))      # 1^1000000 is just 1
                if max(abs(b.numerator).bit_length(), b.denominator.bit_length()) * abs(n) > MAX_BITS + 64:
                    raise MathError("that number is too big for me (more than 1,000 digits)")   # (checked before working it out)
                return Poly.num(b ** n)
            if not power.is_number() or power.value().denominator != 1 or not 0 <= power.value() <= MAX_POWER:
                raise MathError("powers of x must be whole numbers from 0 to %d" % MAX_POWER)
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


# ---------------------------------------------------------------- showing the steps (for the Chat tab)
def _x(n):
    return "" if n == 0 else "x" if n == 1 else "x^%d" % n


def _term(c, n):
    """One term as text: (3, 2) -> '3x^2', (1, 1) -> 'x', (-5, 0) -> '-5'."""
    if n == 0:
        return fmt_number(c)
    if c == 1:
        return _x(n)
    if c == -1:
        return "-" + _x(n)
    return ("(%s)" % fmt_number(c) if "/" in fmt_number(c) else fmt_number(c)) + _x(n)


def steps(kind, what):
    """How to get the answer, step by step, the way you'd do it in class."""
    try:
        if kind == "solve":
            return _solve_steps(what)
        if kind == "derivative":
            p = parse(what)
            out = ["Use the power rule on each term: the derivative of ax^n is (a × n)x^(n−1)."]
            for n in sorted(p.t, reverse=True):
                c = p.t[n]
                if n == 0:
                    out.append("%s → 0 (a number on its own never changes, so its derivative is 0)" % fmt_number(c))
                elif n == 1:
                    out.append("%s → %s (the x goes away)" % (_term(c, 1), fmt_number(c)))
                else:
                    out.append("%s → %s × %d = %s, and the power goes down to %d: %s"
                               % (_term(c, n), fmt_number(c), n, fmt_number(c * n), n - 1, _term(c * n, n - 1)))
            out.append("So the derivative is %s" % p.derivative())
            return out
        if kind == "integral":
            p = parse(what)
            out = ["Use the power rule for integrals on each term: the integral of ax^n is (a ÷ (n+1))x^(n+1)."]
            for n in sorted(p.t, reverse=True):
                c = p.t[n]
                if n == 0:
                    out.append("%s → %s (a number on its own gets an x)" % (fmt_number(c), _term(c, 1)))
                else:
                    out.append("%s → %s ÷ %d = %s, and the power goes up to %d: %s"
                               % (_term(c, n), fmt_number(c), n + 1, fmt_number(c / (n + 1)), n + 1, _term(c / (n + 1), n + 1)))
            out.append("Add + C: any number's derivative is 0, so we can't tell which number was there.")
            out.append("So the integral is %s + C" % p.integral())
            return out
        if kind == "percent":
            pct, of = [Fraction(x) for x in re.findall(r"-?\d+(?:\.\d+)?", what)[:2]]
            return ["%s%% means %s out of 100: %s ÷ 100 = %s" % (fmt_number(pct), fmt_number(pct), fmt_number(pct), fmt_number(pct / 100)),
                    "Multiply: %s × %s = %s" % (fmt_number(pct / 100), fmt_number(of), fmt_number(pct / 100 * of))]
        if kind == "sqrt":
            n = Fraction(what.lstrip("√"))
            root = _exact_sqrt(n)
            if root is not None:
                return ["%s × %s = %s, so √%s = %s" % (fmt_number(root), fmt_number(root), fmt_number(n), fmt_number(n), fmt_number(root))]
            lo = math.isqrt(int(n))
            return ["%d × %d = %d and %d × %d = %d, so √%s is between %d and %d" % (lo, lo, lo * lo, lo + 1, lo + 1, (lo + 1) ** 2, fmt_number(n), lo, lo + 1),
                    "It doesn't come out exactly, so it's about %.6g" % math.sqrt(n)]
    except (MathError, ZeroDivisionError, ValueError):
        pass
    return []


def _solve_steps(equation):
    left, right = equation.split("=")
    L, R = parse(left), parse(right)
    out = ["Start with: %s = %s" % (L, R)]
    p = L - R
    if p.degree() == 1:
        if not L.t.get(1) and R.t.get(1):                         # the x is only on the right: swap the sides
            L, R = R, L
            out.append("Swap the sides: %s = %s" % (L, R))
        if R.t.get(1):                                            # x on the right: move it to the left
            k = R.t[1]
            L, R = L - Poly({1: k}), R - Poly({1: k})
            out.append("%s %s from both sides: %s = %s" % ("Subtract" if k > 0 else "Add", _term(abs(k), 1), L, R))
        if L.t.get(0):                                            # a number on the left: move it to the right
            k = L.t[0]
            L, R = L - Poly.num(k), R - Poly.num(k)
            out.append("%s %s %s both sides: %s = %s" % ("Subtract" if k > 0 else "Add", fmt_number(abs(k)),
                                                          "from" if k > 0 else "to", L, R))
        a = L.t.get(1, 0)
        if a != 1 and a.numerator == 1:                           # (1/3)x: multiply by 3
            out.append("Multiply both sides by %s: x = %s" % (fmt_number(1 / a), fmt_number(R.value() / a)))
        elif a != 1:
            out.append("Divide both sides by %s: x = %s" % (fmt_number(a), fmt_number(R.value() / a)))
        return out
    if p.degree() == 2:
        if R.t:
            out.append("Move everything to the left side: %s = 0" % p)
        a, b, c = p.t.get(2, 0), p.t.get(1, 0), p.t.get(0, 0)
        roots = solve(equation)
        if all(isinstance(r, Fraction) for r in roots):
            brackets = "".join("(x %s %s)" % ("-" if r >= 0 else "+", fmt_number(abs(r))) for r in roots)
            if len(roots) == 1:
                brackets = brackets + "^2"
            out.append("Factor it: %s%s = 0" % ("" if a == 1 else fmt_number(a), brackets))
            out.append("A product is 0 only if one bracket is 0, so " + " or ".join("x = %s" % fmt_number(r) for r in roots))
        else:
            out.append("It doesn't factor nicely, so use the quadratic formula: x = (−b ± √(b² − 4ac)) ÷ 2a, with a = %s, b = %s, c = %s"
                       % (fmt_number(a), fmt_number(b), fmt_number(c)))
            out.append("b² − 4ac = %s, so x = %s" % (fmt_number(b * b - 4 * a * c), " or ".join("%g" % r for r in roots)))
        return out
    return []


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
    x_times = False
    if not re.search(r"=|deriv|d/dx|integra|differentiat|solve|x\s*\^|\dx", t):   # no algebra: "5 x 4" means times
        t, x_times = re.subn(r"(?<=[\d)])\s+x\s+(?=[\d(])", " * ", t)
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
    t = t.replace(",", "")
    # percentages: "15% of 80", "what is 20 percent of 45.5"
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:%|percent)\s*of\s*(-?\d+(?:\.\d+)?)", t)
    if m:
        return "percent", "%s%% of %s" % (m.group(1), m.group(2)), show_value(Fraction(m.group(1)) / 100 * Fraction(m.group(2)))
    # square roots: "square root of 50", "sqrt(16)", "√2"
    m = re.search(r"(?:square root of|sqrt|√)\s*\(?\s*(\d{1,30}(?:\.\d{1,10})?)(?![\d.])", t)
    if m:
        n = Fraction(m.group(1))
        root = _exact_sqrt(n)
        return "sqrt", "√" + m.group(1), fmt_number(root) if root is not None else "about %.6g" % math.sqrt(n)
    # plain arithmetic: the longest piece of math with an operator in it (a minus at the start counts: -5 + 3)
    found = re.finditer(r"(?:(?<![\d)])-)?[\d(][\d\s+\-*/^().]*[\d)]", t)
    for m in sorted(found, key=lambda m: len(m.group()), reverse=True):
        piece = m.group()
        if not re.search(r"[\d)]\s*[-+*/^]\s*[-\d(]", piece):       # an operator between numbers: 2+3, (-1)^7
            continue
        if not clearly_math(piece, t[:m.start()], t[m.end():], x_times):
            continue
        try:
            p = parse(piece)
            if p.is_number():
                return "arithmetic", " ".join(piece.split()), show_value(p.value())
        except MathError as e:
            if "divide" in str(e):
                return "arithmetic", " ".join(piece.split()), "nothing: you can't divide by 0"
            if "too big" in str(e):
                return "arithmetic", " ".join(piece.split()), "too big to work out (more than 1,000 digits)"
            continue
    return None


# "-", "/" and "x" often aren't math: "a 2-3 hour drive", "$300-400", "on 11/27", "Windows 10/11", "a 2 x 4", "open 24/7"
MATH_CUE = re.compile(r"(?:^|\b(?:what is|what's|whats|wats|wat is|what are|how much is|calculate|compute|work out|"
                      r"solve|evaluate|simplify|find)\s*)$")


def clearly_math(piece, before, after, x_times=False):
    """Is this piece of the question really math to work out? Pieces with only "-" or "/" in them (or an "x" that
    was turned into "*") count only straight after words like "what is" or "calculate" (or if the question is just
    math), and not when a word comes right after them, like "2-3 hours"."""
    ops = set(re.findall(r"(?<=[\d)\s])[-+*/^](?=[\s\d(.-])", piece))
    if ops - {"-", "/"} and not (ops == {"*"} and x_times):
        return True                                          # + or ^ (or a typed *) means math: 47*38, 2+2, 2^10
    before = before.strip()
    if re.search(r"[$£€#]$|\b(?:windows|ios|android|version|v|ages?|grades?|from|between|on|open|score|scored|ended|won|lost|"
                 r"rated|room|page|pages|chapter|route|highway|interstate|i)$", before):
        return False
    if re.match(r"\s*[a-z]", after):                          # "2-3 hours", "10/11 laptops"
        return False
    return bool(MATH_CUE.search(before))


def show_value(v):
    """2.5 stays 2.5; 7/3 becomes '7/3 (about 2.33333)'."""
    text = fmt_number(v)
    return text if "/" not in text else "%s (about %s)" % (text, about(v))


def about(v):
    """A rounded value for people: 2.33333, or 1.23457e+400 for numbers too big for a normal float."""
    try:
        return "%.6g" % float(v)
    except OverflowError:
        return format(Decimal(v.numerator) / Decimal(v.denominator), ".6g").replace("E", "e")
