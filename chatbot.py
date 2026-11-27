"""Part 2: the self-quizzing chatbot.

A small, ready-made AI language model runs on the Pi (with Ollama, or with llama.cpp on 32-bit Pi OS).
Over and over, it:
  1. TEACHER: writes its own math word problem about space or robots, plus the math that solves it,
  2. CHECKER: Python works out that math, so we know the true answer (bad questions are thrown away),
  3. STUDENT: the same AI answers the problem, without seeing the math,
  4. NOTEBOOK: wrong answers go into a notebook with the correct solution. Next time, it reads a few
     similar notebook examples before answering.
To find out honestly if the notebook helps, half the questions are answered WITH the notebook and half WITHOUT.

This doesn't change the AI's brain (training a real chatbot needs far more computer power than a Pi has).
It's like a student who keeps a notebook of solved problems and reads it before a test.
"""
import ast
import json
import math
import operator
import os
import random
import re
import threading
import time
import urllib.request
from collections import deque

TOPICS = ["a Mars rover", "astronauts on the space station", "a rocket launch", "satellites", "the Moon", "a robot arm",
          "solar panels", "a space telescope", "a robot car", "planets", "a drone", "a moon base", "a robot factory",
          "fuel for a spacecraft", "space food", "a weather station", "an ISS pass", "a Raspberry Pi"]

TEACHER_PROMPT = """Write one short math word problem for a 12-year-old about {topic}. Use small whole numbers.
Choose the numbers so the answer is a whole number.
Then write the math that solves it, using only numbers, + - * / and parentheses. Don't write the answer.
Use exactly this format, like this example:
PROBLEM: A robot picks 4 apples every minute. How many apples does it pick in 6 minutes?
MATH: 4 * 6

Now write a new one about {topic}.
PROBLEM: <the word problem>
MATH: <the math>"""

STUDENT_PROMPT = """{examples}Solve this math word problem. Think in one or two short steps, then finish with the line
ANSWER: <just the number>

PROBLEM: {problem}"""

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def clean_math(expr):
    """Small models often write more than the math: the answer ("12 * 5 = 60"), units ("30 liters * 8"),
    or formatting ("**MATH:** `4 * 6`"). Keep just the math part."""
    expr = expr.split("=")[0]                                   # "12 * 5 = 60" -> "12 * 5"
    expr = expr.replace("×", "*").replace("÷", "/").replace("`", " ").replace(",", "")
    expr = re.sub(r"(?<=[\d)\s])[xX](?=[\s\d(])", "*", expr)    # "120 x 4" -> "120 * 4"
    expr = re.sub(r"[A-Za-z$€£:]+", " ", expr)                  # units and words: "30 liters" -> "30"
    return " ".join(expr.split()).strip(" *.")                  # leftover "**" or a final period


def safe_math(expr, whole=True):
    """The checker: works out simple math like (3 + 4) * 12 safely. Anything else is refused.
    whole=True also refuses answers that aren't whole numbers (the practice problems need whole numbers)."""
    expr = clean_math(expr)
    if not expr or len(expr) > 80 or not re.fullmatch(r"[\d\s+\-*/().]+", expr):
        raise ValueError("not simple math")
    if not re.search(r"\d\s*[-+*/]\s*[\d(]", expr):           # "5 squared" would become just "5": refuse it
        raise ValueError("no + - * / in the math")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise ValueError("the math has a mistake in it")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -ev(n.operand)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if hasattr(ast, "Num") and isinstance(n, getattr(ast, "Num")):         # older Python
            return n.n
        raise ValueError("not simple math")
    try:
        value = ev(tree)
    except ZeroDivisionError:
        raise ValueError("it divides by zero")
    if abs(value) > 1e12 or (whole and (abs(value) > 1e7 or abs(value - round(value)) > 1e-9)):
        raise ValueError("the answer isn't a whole number")
    return int(round(value)) if abs(value - round(value)) < 1e-9 else round(value, 6)


def parse_teacher(text):
    text = text.replace("**", "").replace("__", "")              # drop bold formatting like **PROBLEM:**
    p = re.search(r"PROBLEM:\s*(.+?)\s*(?:\n|MATH:)", text, re.S | re.I)
    m = re.search(r"MATH:\s*([^\n]+)", text, re.I)
    if not p or not m:
        raise ValueError("didn't follow the format")
    problem = " ".join(p.group(1).split())
    if len(problem) < 20:
        raise ValueError("the problem is too short")
    return problem, clean_math(m.group(1)), safe_math(m.group(1))


NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
                "hundred": 100, "thousand": 1000, "twice": 2, "double": 2, "half": 2, "triple": 3, "dozen": 12, "pair": 2}
CONVERSIONS = {2, 7, 12, 24, 60, 100, 365, 1000, 3600}      # days in a week, minutes in an hour, cm in a meter...


def makes_sense(problem, math_text):
    """The strict checker (an experiment setting). The normal checker only checks that the math works out.
    This one also throws away questions that don't make sense, so they never get into the notebook."""
    if "?" not in problem:
        raise ValueError("there's no question in it")
    low = problem.lower().replace(",", "")
    have = {float(x) for x in re.findall(r"\d+(?:\.\d+)?", low)}
    have |= {float(v) for w, v in NUMBER_WORDS.items() if re.search(r"\b%ss?\b" % w, low)}
    for x in re.findall(r"\d+(?:\.\d+)?", clean_math(math_text)):
        if float(x) not in have and float(x) not in CONVERSIONS:
            raise ValueError("the math uses %s, which isn't in the question" % x)


def compare(with_, without):
    """Is the difference between with and without the notebook real, or could it be luck? This works out the
    exact chance of a gap at least this big if the notebook made no difference at all ("Fisher's exact test")."""
    (a, n1), (b, n2) = with_, without
    if min(n1, n2) < 30:
        return {"verdict": "needs more rounds", "luck": None}
    right, total = a + b, n1 + n2
    chance = lambda k: math.comb(n1, k) * math.comb(n2, right - k) / math.comb(total, right)
    this = chance(a)
    luck = sum(chance(k) for k in range(max(0, right - n2), min(n1, right) + 1) if chance(k) <= this * (1 + 1e-9))
    luck = round(min(luck, 1) * 100, 1)                              # % chance of a gap this big by luck alone
    if luck >= 5:
        return {"verdict": "no clear difference", "luck": luck}
    return {"verdict": "the notebook helped" if a / n1 > b / n2 else "the notebook made it worse", "luck": luck}


def parse_answer(text):
    m = re.search(r"ANSWER:\s*\$?(-?[\d,]*\.?\d+)", text, re.I)
    nums = [m.group(1)] if m else re.findall(r"-?\d[\d,]*\.?\d*", text)
    if not nums:
        return None
    try:
        v = float(nums[-1].replace(",", ""))
        return int(v) if v == int(v) else v
    except ValueError:
        return None


def similar(problem, notebook, n=3):
    """The notebook pages most like this problem (the most words in common)."""
    words = set(re.findall(r"[a-z]+", problem.lower())) - {"the", "a", "an", "of", "and", "to", "in", "is", "each", "how", "many", "has"}
    scored = sorted(notebook, key=lambda e: -len(words & set(re.findall(r"[a-z]+", e["problem"].lower()))))
    return scored[:n]


class LLM:
    """Talks to the language model. Ollama (port 11434) or a llama.cpp server (port 8099)."""
    def __init__(self, cfg):
        self.cfg = cfg
        self.speed = None          # how fast it writes, in tokens per second (a token is a piece of a word)
        self.model_name = None

    def _post(self, url, body, timeout=300):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def check(self):
        """Is a model running? Returns (ok, message)."""
        try:
            with urllib.request.urlopen(self.cfg["ollama_url"].rstrip("/") + "/api/tags", timeout=3) as r:
                names = [m["name"] for m in json.loads(r.read().decode()).get("models", [])]
            if not any(n.split(":")[0] == self.cfg["model"].split(":")[0] and (":" not in self.cfg["model"] or n == self.cfg["model"]) for n in names):
                return False, "Ollama is running, but the model %s isn't downloaded. Run: ollama pull %s" % (self.cfg["model"], self.cfg["model"])
            self.backend = "ollama"
            self.model_name = self.cfg["model"]
            return True, "Ollama with %s" % self.cfg["model"]
        except Exception:
            pass
        try:
            with urllib.request.urlopen(self.cfg["llamacpp_url"].rstrip("/") + "/health", timeout=3) as r:
                r.read()
            self.backend = "llamacpp"
            try:                                     # which model file the llama.cpp server is running
                with urllib.request.urlopen(self.cfg["llamacpp_url"].rstrip("/") + "/v1/models", timeout=3) as r:
                    mid = json.loads(r.read().decode())["data"][0]["id"]
                self.model_name = os.path.basename(mid).replace(".gguf", "").replace("-instruct", "").replace("-q4_k_m", "")
            except Exception:
                self.model_name = "llama.cpp model"
            return True, "llama.cpp server (%s)" % self.model_name
        except Exception:
            return False, "No language model found. Start Ollama or the llama.cpp server (see docs/03-chatbot.md)."

    def chat(self, messages, max_tokens=200, temperature=0.4):
        """A whole conversation: [{"role": "system" / "user" / "assistant", "content": ...}, ...]."""
        if getattr(self, "backend", "ollama") == "ollama":
            r = self._post(self.cfg["ollama_url"].rstrip("/") + "/api/chat",
                           {"model": self.cfg["model"], "messages": messages, "stream": False,
                            "options": {"temperature": temperature, "num_predict": max_tokens}})
            return r.get("message", {}).get("content", "")
        r = self._post(self.cfg["llamacpp_url"].rstrip("/") + "/v1/chat/completions",
                       {"messages": messages, "max_tokens": max_tokens, "temperature": temperature})
        if r.get("timings", {}).get("predicted_per_second"):
            self.speed = round(r["timings"]["predicted_per_second"], 1)
        return r["choices"][0]["message"]["content"]

    def ask(self, prompt, max_tokens=160, temperature=0.7):
        if getattr(self, "backend", "ollama") == "ollama":
            r = self._post(self.cfg["ollama_url"].rstrip("/") + "/api/generate",
                           {"model": self.cfg["model"], "prompt": prompt, "stream": False,
                            "options": {"temperature": temperature, "num_predict": max_tokens}})
            if r.get("eval_count") and r.get("eval_duration"):
                self.speed = round(r["eval_count"] / (r["eval_duration"] / 1e9), 1)
            return r.get("response", "")
        r = self._post(self.cfg["llamacpp_url"].rstrip("/") + "/v1/chat/completions",       # (uses the model's chat format)
                       {"messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature})
        if r.get("timings", {}).get("predicted_per_second"):
            self.speed = round(r["timings"]["predicted_per_second"], 1)
        return r["choices"][0]["message"]["content"]


DEFAULT_SETTINGS = {"pages": 3, "strict": False, "model": None}   # notebook pages shown, strict checker, which model


class Chatbot:
    def __init__(self, data_dir, cfg):
        self.file = os.path.join(data_dir, "chatbot.json")
        self.cfg = cfg
        self.llm = LLM(cfg)
        self.lock = threading.Lock()
        self.running = False
        self.connection = (False, "Not checked yet")
        self.feed = deque(maxlen=30)
        self.stage, self.stage_since = None, 0      # what it's doing right now, for the web page
        self.hold_until = 0                         # the Chat tab pauses practice until this time
        self.rng = random.Random()
        try:
            with open(self.file) as f:
                self.state = json.load(f)
            self.state.setdefault("settings", dict(DEFAULT_SETTINGS))
            self.state.setdefault("runs", [])
        except (OSError, ValueError):
            self.state = {}
            self.reset()

    def _fresh(self, settings, runs):
        return {"rounds": 0, "bad_questions": 0, "with": [0, 0], "without": [0, 0], "notebook": [], "history": [],
                "settings": settings, "runs": runs, "started": time.time()}

    def _archive(self):
        """Save the experiment that's finishing into the list of past experiments."""
        st = self.state
        if st.get("rounds"):
            st["runs"].append({"settings": dict(st["settings"]), "rounds": st["rounds"], "bad_questions": st["bad_questions"],
                               "with": st["with"][:], "without": st["without"][:], "started": st.get("started"),
                               "ended": time.time()})

    def reset(self):
        """Clear the notebook and scores, but keep the settings and the past experiments."""
        with self.lock:
            self.state = self._fresh(self.state.get("settings", dict(DEFAULT_SETTINGS)), self.state.get("runs", []))
            self.feed.clear()
            self._save()

    def new_experiment(self, pages, strict, model=None):
        """Save the current experiment, then start a new one with an empty notebook and these settings."""
        with self.lock:
            self._archive()
            settings = dict(self.state["settings"], pages=pages, strict=strict)
            if model:
                settings["model"] = model
            self.state = self._fresh(settings, self.state["runs"])
            self.feed.clear()
            self._save()

    def _save(self):
        tmp = self.file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f)
        os.replace(tmp, self.file)

    def practice_round(self):
        st = self.state
        topic = self.rng.choice(TOPICS)
        t0 = time.time()
        self.stage, self.stage_since = "teacher", time.time()
        teacher = self.llm.ask(TEACHER_PROMPT.format(topic=topic), max_tokens=150, temperature=0.9)       # 1. teacher
        try:
            problem, math, truth = parse_teacher(teacher)                                                 # 2. checker
            if st["settings"].get("strict"):
                makes_sense(problem, math)
        except ValueError as e:
            with self.lock:
                st["bad_questions"] += 1
                self.feed.appendleft({"kind": "bad", "topic": topic, "why": str(e), "text": teacher.strip()[:300]})
            return
        use_notebook = st["rounds"] % 2 == 0 and len(st["notebook"]) >= 3                                 # half with, half without
        examples = ""
        if use_notebook:
            examples = "Here are some solved examples from your notebook:\n\n" + "\n\n".join(
                "PROBLEM: %s\nMATH: %s\nANSWER: %s" % (e["problem"], e["math"], e["answer"])
                for e in similar(problem, st["notebook"], st["settings"].get("pages", 3))) + "\n\n"
        self.stage, self.stage_since = "student", time.time()
        reply = self.llm.ask(STUDENT_PROMPT.format(examples=examples, problem=problem), max_tokens=180, temperature=0.2)   # 3. student
        answer = parse_answer(reply)
        ok = answer is not None and abs(answer - truth) < 1e-9
        with self.lock:
            key = "with" if use_notebook else "without"
            if len(st["notebook"]) >= 3:            # (only count fair comparisons, once the notebook has pages)
                st[key][0] += ok
                st[key][1] += 1
            if not ok:                                                                                     # 4. notebook
                st["notebook"].append({"problem": problem, "math": math, "answer": truth})
                st["notebook"] = st["notebook"][-200:]
            st["rounds"] += 1
            if st["rounds"] % 5 == 0:
                st["history"].append([st["rounds"], st["with"][:], st["without"][:]])
            self.feed.appendleft({"kind": "quiz", "topic": topic, "problem": problem, "math": math, "truth": truth,
                                  "answer": answer, "ok": ok, "notebook": use_notebook, "reply": reply.strip()[-400:],
                                  "seconds": round(time.time() - t0)})
            self._save()

    def run(self):
        while True:
            if not self.running or time.time() < self.hold_until:     # stopped, or paused while you chat
                time.sleep(1)
                continue
            self.connection = self.llm.check()
            if not self.connection[0]:
                time.sleep(10)
                continue
            model = self.llm.model_name
            if model and self.state["settings"].get("model") != model:
                if self.state["settings"].get("model") is None:          # first time: just note which model this is
                    with self.lock:
                        self.state["settings"]["model"] = model
                        self._save()
                else:                                                    # you switched models: that's a new experiment
                    s = self.state["settings"]
                    self.new_experiment(s.get("pages", 3), s.get("strict", False), model)
            try:
                self.practice_round()
            except Exception as e:
                self.stage = None
                why = "the model took more than 5 minutes to answer. Is the Pi busy with something else, like the Docking AI?" \
                    if "timed out" in str(e) else str(e)
                with self.lock:                     # (it goes in the feed, so it stays on the page)
                    self.feed.appendleft({"kind": "error", "why": why})
                self.connection = (False, "Error talking to the model: %s" % why)
                time.sleep(10)
            finally:
                self.stage = None
