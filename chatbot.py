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
Then write the math that solves it, using only numbers, + - * / and parentheses.
Use exactly this format:
PROBLEM: <the word problem>
MATH: <the math>"""

STUDENT_PROMPT = """{examples}Solve this math word problem. Think in one or two short steps, then finish with the line
ANSWER: <just the number>

PROBLEM: {problem}"""

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def safe_math(expr):
    """The checker: works out simple math like (3 + 4) * 12 safely. Anything else is refused."""
    expr = expr.replace("×", "*").replace("÷", "/").replace("x", "*").replace(",", "").strip().rstrip("=").strip()
    if not expr or len(expr) > 80 or not re.fullmatch(r"[\d\s+\-*/().]+", expr):
        raise ValueError("not simple math")

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
    value = ev(ast.parse(expr, mode="eval"))
    if abs(value) > 1e7 or abs(value - round(value)) > 1e-9:
        raise ValueError("the answer isn't a whole number")
    return int(round(value))


def parse_teacher(text):
    p = re.search(r"PROBLEM:\s*(.+?)\s*(?:\n|MATH:)", text, re.S | re.I)
    m = re.search(r"MATH:\s*([^\n]+)", text, re.I)
    if not p or not m:
        raise ValueError("didn't follow the format")
    problem = " ".join(p.group(1).split())
    if len(problem) < 20:
        raise ValueError("the problem is too short")
    return problem, m.group(1).strip(), safe_math(m.group(1))


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
            return True, "Ollama with %s" % self.cfg["model"]
        except Exception:
            pass
        try:
            with urllib.request.urlopen(self.cfg["llamacpp_url"].rstrip("/") + "/health", timeout=3) as r:
                r.read()
            self.backend = "llamacpp"
            return True, "llama.cpp server"
        except Exception:
            return False, "No language model found. Start Ollama or the llama.cpp server (see docs/03-chatbot.md)."

    def ask(self, prompt, max_tokens=160, temperature=0.7):
        if getattr(self, "backend", "ollama") == "ollama":
            r = self._post(self.cfg["ollama_url"].rstrip("/") + "/api/generate",
                           {"model": self.cfg["model"], "prompt": prompt, "stream": False,
                            "options": {"temperature": temperature, "num_predict": max_tokens}})
            return r.get("response", "")
        r = self._post(self.cfg["llamacpp_url"].rstrip("/") + "/v1/chat/completions",       # (uses the model's chat format)
                       {"messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature})
        return r["choices"][0]["message"]["content"]


class Chatbot:
    def __init__(self, data_dir, cfg):
        self.file = os.path.join(data_dir, "chatbot.json")
        self.cfg = cfg
        self.llm = LLM(cfg)
        self.lock = threading.Lock()
        self.running = False
        self.connection = (False, "Not checked yet")
        self.feed = deque(maxlen=30)
        self.rng = random.Random()
        try:
            with open(self.file) as f:
                self.state = json.load(f)
        except (OSError, ValueError):
            self.reset()

    def reset(self):
        with self.lock:
            self.state = {"rounds": 0, "bad_questions": 0, "with": [0, 0], "without": [0, 0], "notebook": [], "history": []}
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
        teacher = self.llm.ask(TEACHER_PROMPT.format(topic=topic), max_tokens=150, temperature=0.9)       # 1. teacher
        try:
            problem, math, truth = parse_teacher(teacher)                                                 # 2. checker
        except ValueError as e:
            with self.lock:
                st["bad_questions"] += 1
                self.feed.appendleft({"kind": "bad", "topic": topic, "why": str(e), "text": teacher.strip()[:300]})
            return
        use_notebook = st["rounds"] % 2 == 0 and len(st["notebook"]) >= 3                                 # half with, half without
        examples = ""
        if use_notebook:
            examples = "Here are some solved examples from your notebook:\n\n" + "\n\n".join(
                "PROBLEM: %s\nMATH: %s\nANSWER: %s" % (e["problem"], e["math"], e["answer"]) for e in similar(problem, st["notebook"])) + "\n\n"
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
            if not self.running:
                time.sleep(1)
                continue
            self.connection = self.llm.check()
            if not self.connection[0]:
                time.sleep(10)
                continue
            try:
                self.practice_round()
            except Exception as e:
                self.connection = (False, "Error talking to the model: %s" % e)
                time.sleep(10)
