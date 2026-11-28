"""Pi Self-Learning AI - three ways an AI can teach itself, running on a Raspberry Pi.

  Part 1: a tiny GPT that teaches itself math, checked by a calculator      (selfmath.py)
  Part 2: a chatbot that quizzes itself and keeps a notebook of mistakes     (chatbot.py, needs Ollama or llama.cpp)
  Part 3: the model-collapse experiment: an AI that learns from its own writing (collapse.py)

Run in the background:  bash setup-autostart.sh   (see README.md)
Run by hand:            python3 server.py
Then open http://<your-pi>.local:8100  (or http://<your-pi-ip>:8100)
Needs numpy (sudo apt install python3-numpy). Works with Python 3.9 and newer.
"""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")    # these tiny models are fastest on one core each
os.environ.setdefault("OMP_NUM_THREADS", "1")

import glob
import json
import re
import multiprocessing
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import accounts
import advmath
import collapse
import selfmath
from chat import Chat
from chatbot import KINDS, Chatbot, compare

PORT = int(os.environ.get("SELF_PORT", "8100"))      # stock tracker 8000, ISS tracker 8080, docking AI 8090
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RUNS = os.path.join(DATA, "collapse")
SETTINGS_FILE = os.path.join(HERE, "config.json")
DEFAULTS = {"math_paused": False, "math_course": "auto", "chatbot_running": False, "model": "qwen2.5:0.5b", "ollama_url": "http://localhost:11434", "llamacpp_url": "http://localhost:8099"}


AVATAR_PROMPT = """Pick one emoji and two background colors for a profile picture of: {description}
Reply with only this, like the example.
Example for "a happy cat that loves space": EMOJI: 🐱 COLORS: #1e3a8a #f472b6
Your answer for "{description}":"""
AVATAR_WORDS = [(("robot", "bot", "android"), "🤖"), (("astronaut", "space", "rocket"), "🚀"), (("cat", "kitten"), "🐱"),
                (("dog", "puppy"), "🐶"), (("planet", "saturn", "mars"), "🪐"), (("alien", "ufo"), "👽"), (("star",), "⭐"),
                (("fire", "flame"), "🔥"), (("game", "gaming"), "🎮"), (("code", "coding", "computer"), "💻"),
                (("dragon",), "🐉"), (("car", "race"), "🏎️"), (("soccer", "football"), "⚽"), (("basketball",), "🏀"),
                (("music", "guitar"), "🎸"), (("book", "read"), "📚"), (("ninja",), "🥷"), (("lion",), "🦁"), (("owl",), "🦉")]


def load_settings():
    cfg = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------- part 3 runs in its own process (so it doesn't slow part 1)
def collapse_job(settings, path):
    os.nice(5)
    run = {"id": os.path.basename(path)[:-5], "started": time.time(), "settings": settings, "status": "running", "progress": 0, "results": []}

    def update(c):
        run.update(status=c.status, progress=round(c.progress, 3), results=c.results)
        write_json(path, run)
    c = collapse.Collapse(rounds=settings["rounds"], steps=settings["steps"], temperature=settings["temperature"],
                          keep_real=settings["keep_real"], on_update=update)
    update(c)
    c.run()
    update(c)


class Lab:
    def __init__(self, cfg):
        self.cfg = cfg
        os.makedirs(RUNS, exist_ok=True)
        self.math = selfmath.MathAI(DATA)                    # course 1: adding and subtracting
        self.math2 = advmath.AdvancedMathAI(DATA)            # course 2: multiplying, algebra and calculus
        self.math3 = advmath.HarderMathAI(DATA)              # course 3: decimals, quadratics, integrals
        self.all_courses = [self.math, self.math2, self.math3]
        for c in self.all_courses:
            c.paused = cfg["math_paused"]
        self.bot = Chatbot(DATA, cfg)
        self.bot.running = cfg["chatbot_running"]           # keep practicing after the Pi restarts
        self.chat = Chat(self.bot, os.path.join(DATA, "chats"), tutor=self.math_ai_try)   # part 4: talk to the AI
        try:                                                                                 # part 5: accounts
            self.accounts = accounts.Accounts(os.path.join(DATA, "accounts"), cfg, on_login=self.chat.load_user,
                                              on_logout=self.chat.unload_user, on_delete=self.chat.delete_user)
            self.accounts_error = None
        except RuntimeError as e:
            self.accounts, self.accounts_error = None, str(e)
            print(e, flush=True)
        self.collapse_proc = None
        self.collapse_path = None
        for path in glob.glob(os.path.join(RUNS, "*.json")):          # runs that were cut off by a restart
            r = read_json(path)
            if r and r.get("status") == "running":
                r["status"] = "stopped"
                r["why"] = "the program restarted (for example after an update or a power cut)"
                write_json(path, r)

    def math_ask(self, text):
        """You ask the math AI a question. Whole-number adding and subtracting go to course 1, then whichever of
        course 2 or 3 practices that kind of question."""
        m = re.fullmatch(r"\s*(\d{1,3})\s*([+\-−])\s*(\d{1,3})\s*=?\s*\??\s*", str(text))
        if m:
            a, op, b = int(m.group(1)), "-" if m.group(2) in "-−" else "+", int(m.group(3))
            r = self.math.ask(a, b, op)
            r.update(question="%d %s %d" % (a, "+" if op == "+" else "−", b), course=1,
                     tokens=list("%03d" % a) + ["+" if op == "+" else "−"] + list("%03d" % b) + ["="],
                     rows=["ones", "tens", "hundreds", "thousands"])
            return r
        why = []
        for course in (self.math2, self.math3):
            try:
                r = course.ask(text)
            except ValueError as e:
                why.append(str(e))
                continue
            return r
        exact = [w for w in why if not w.startswith("Course ")]        # "only up to 9.9" beats "it practices..."
        raise ValueError(exact[0] if exact else "The math AI practices questions like 47+38, 7*8, 3x+5=20, d/dx 4x^3, "
                         "2.5+1.7, x^2-5x+6=0 or integral of 6x^2")

    def math_ai_try(self, kind, what):
        """For the Chat tab: let your trained math AI answer, if it's the kind of question it practices."""
        text = {"arithmetic": what, "solve": what, "derivative": "d/dx " + what, "integral": "integral of " + what}.get(kind)
        if not text:
            return None
        try:
            r = self.math_ask(text.replace(" ", ""))
        except Exception:
            return None                                       # not something any course practices
        course = self.all_courses[r["course"] - 1]
        return {"course": r["course"], "question": r["question"], "answer": r["answer"], "truth": r["truth"],
                "ok": str(r["answer"]) == str(r["truth"]), "level": course.state["level"] + 1,
                "levels": len(self.levels_of(course)), "mastered": course.state["mastered"]}

    def levels_of(self, course):
        return selfmath.LEVELS if course is self.math else course.levels

    def ai_avatar(self, description):
        """Profile pictures "made by the AI": it picks an emoji and two colors that match your description.
        (A small language model can't draw, but it can choose!)"""
        description = " ".join(str(description or "").split())[:80]
        if not description:
            raise accounts.AuthError("Describe the picture you want first, like: a robot astronaut.")
        self.bot.hold_until = time.time() + 60                    # the practice gets out of the way
        reply = ""
        try:
            reply = self.bot.llm.ask(AVATAR_PROMPT.format(description=description), max_tokens=24, temperature=0.8)
        except Exception as e:
            print("avatar error:", e, flush=True)
        emoji = re.search(r"EMOJI:\s*(\S{1,8})", reply)
        colors = re.findall(r"#[0-9a-fA-F]{6}", reply)
        emoji = emoji.group(1) if emoji and not re.search(r"[A-Za-z0-9]", emoji.group(1)) else None
        if not emoji:                                             # the AI didn't follow the format: pick by keyword
            low = description.lower()
            emoji = next((e for words, e in AVATAR_WORDS if any(w in low for w in words)), "🤖")
        while len(colors) < 2:
            colors.append(["#22d3ee", "#6366f1", "#f472b6", "#facc15", "#34d399"][len(colors) + len(description) % 3])
        return {"kind": "emoji", "emoji": emoji, "c1": colors[0], "c2": colors[1]}

    def save_settings(self):
        write_json(SETTINGS_FILE, self.cfg)
        try:
            os.chmod(SETTINGS_FILE, 0o600)              # it can hold the email app password: only you can read it
        except OSError:
            pass

    # ------------------------------------------------------------ part 1
    def training(self):
        """Which course the math AI is learning right now. "auto" means the first course it hasn't mastered yet."""
        mode = self.cfg.get("math_course", "auto")
        if mode in ("1", "2", "3"):
            return self.all_courses[int(mode) - 1]
        return next((c for c in self.all_courses if not c.state["mastered"]), self.math3)

    def math_loop(self):
        hot = False
        while True:
            temp = selfmath.pi_temperature()
            if temp is not None:                  # rest if the Pi gets hot, until it's 8 °C cooler
                hot = temp >= 78 or (hot and temp > 70)
            for c in self.all_courses:
                c.hot = hot
            if self.math.paused or hot or self.chat.busy:     # (it rests while the chat answers, so the chat gets the whole Pi)
                time.sleep(0.5 if self.chat.busy else 2)
                continue
            course = self.training()
            try:
                course.round()
                if time.time() - course.saved_at > 300:
                    course.save()
            except Exception as e:
                print("math training error:", e, flush=True)
                time.sleep(5)

    def courses(self):
        out = []
        for n, c in enumerate(self.all_courses, 1):
            out.append({"n": n, "name": "Course 1: Adding & subtracting" if n == 1 else c.name,
                        "level": c.state["level"], "levels": len(self.levels_of(c)), "mastered": c.state["mastered"],
                        "training": self.training() is c})
        return out

    def math_status(self, course=None):
        course = course or self.all_courses.index(self.training()) + 1
        if course in (2, 3):
            m = self.all_courses[course - 1]
            with m.lock:
                st = m.state
                hist = st["history"]
                step = max(1, len(hist) // 400)
                per = sum(m.speed) / len(m.speed) if m.speed else None
                return {"course": course, "courses": self.courses(), "mode": self.cfg.get("math_course", "auto"), "pass": round(advmath.PASS * 100),
                        "level": st["level"], "levels": [l["name"] for l in m.levels], "mastered": st["mastered"], "round": st["round"],
                        "questions": st["questions"], "notebook": len(st["notebook"]), "tests": st["tests"][-300:],
                        "history": hist[::step], "level_ups": st["level_ups"], "seconds": round(st["seconds"]),
                        "paused": m.paused, "hot": m.hot, "temp": selfmath.pi_temperature(), "feed": list(m.feed)[:24],
                        "skills": m.skill_rows(), "size": m.model.size(),
                        "per_minute": round(60 / per * (advmath.BATCH + advmath.REVIEW)) if per else None}
        m = self.math
        with m.lock:
            st = m.state
            lv = st["level"]
            skills = [{"label": ("%s, %s" % ("adding" if o == "+" else "subtracting", ["no carrying", "1 carry", "2 carries", "3 carries"][c]
                                              if o == "+" else ["no borrowing", "1 borrow", "2 borrows", "3 borrows"][c])),
                       "acc": round(100 * st["skills"].get("%d%s%d" % (lv, o, c), 0.0))}
                      for o, c in m.skills_for(lv)]
            hist = st["history"]
            step = max(1, len(hist) // 400)
            per = sum(m.speed) / len(m.speed) if m.speed else None
            return {"course": 1, "courses": self.courses(), "mode": self.cfg.get("math_course", "auto"), "pass": round(selfmath.PASS * 100),
                    "level": lv, "levels": [l["name"] for l in selfmath.LEVELS], "mastered": st["mastered"], "round": st["round"],
                    "questions": st["questions"], "notebook": len(st["notebook"]), "tests": st["tests"][-300:],
                    "history": hist[::step], "level_ups": st["level_ups"], "seconds": round(st["seconds"]),
                    "paused": m.paused, "hot": m.hot, "temp": selfmath.pi_temperature(), "feed": list(m.feed)[:24], "skills": skills, "size": m.model.size(),
                    "per_minute": round(60 / per * (selfmath.BATCH + selfmath.REVIEW)) if per else None}

    # ------------------------------------------------------------ part 3
    def collapse_status(self):
        running = self.collapse_proc is not None and self.collapse_proc.is_alive()
        runs = []
        for path in sorted(glob.glob(os.path.join(RUNS, "*.json")), reverse=True)[:8]:
            r = read_json(path)
            if r:
                runs.append(r)
        return {"running": running, "runs": runs}

    def start_collapse(self, body):
        if self.collapse_proc is not None and self.collapse_proc.is_alive():
            raise ValueError("An experiment is already running.")
        settings = {"rounds": max(2, min(60, int(body.get("rounds", 6)))), "keep_real": bool(body.get("keep_real", False)),
                    "temperature": max(0.3, min(1.5, float(body.get("temperature", 0.9)))), "steps": 1500}
        path = os.path.join(RUNS, time.strftime("run-%Y%m%d-%H%M%S") + ".json")
        self.collapse_proc = multiprocessing.get_context("spawn").Process(target=collapse_job, args=(settings, path), daemon=True)   # a fresh, separate process
        self.collapse_proc.start()
        self.collapse_path = path
        for old in sorted(glob.glob(os.path.join(RUNS, "*.json")))[:-8]:   # keep the last 8 runs
            os.remove(old)

    def stop_collapse(self, why="you pressed Stop"):
        if self.collapse_proc is not None and self.collapse_proc.is_alive():
            self.collapse_proc.terminate()
            self.collapse_proc.join(5)
            r = read_json(self.collapse_path)
            if r:
                r["status"] = "stopped"
                r["why"] = why
                write_json(self.collapse_path, r)

    # ------------------------------------------------------------ part 2
    def chatbot_status(self):
        b = self.bot
        with b.lock:
            st = b.state
            return {"running": b.running, "connection": list(b.connection), "rounds": st["rounds"], "bad_questions": st["bad_questions"],
                    "with": st["with"], "without": st["without"], "history": st["history"][-300:], "feed": list(b.feed)[:15],
                    "notebook": st["notebook"][-8:][::-1], "notebook_size": len(st["notebook"]), "model": self.cfg["model"],
                    "stage": b.stage, "stage_seconds": round(time.time() - b.stage_since) if b.stage else None, "speed": b.llm.speed,
                    "paused_for_chat": time.time() < b.hold_until,
                    "load": round(os.getloadavg()[0], 1), "cores": os.cpu_count() or 4,
                    "settings": st["settings"], "result": compare(st["with"], st["without"]),
                    "runs": [dict(r, result=compare(r["with"], r["without"])) for r in st["runs"]]}


class Handler(BaseHTTPRequestHandler):
    lab = None

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", cookie=None):
        data = body if isinstance(body, bytes) else json.dumps(body, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        if cookie is not None:              # the sign-in cookie: hidden from the page's code (HttpOnly), never sent to other sites
            self.send_header("Set-Cookie", "sid=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=%d"
                             % (cookie, accounts.SESSION_DAYS * 86400 if cookie else 0))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _sid(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "sid":
                return v
        return None

    def _who(self):
        """The signed-in account, or None."""
        lab = self.lab
        return lab.accounts.session(self._sid()) if lab.accounts else None

    def _need_login(self):
        return self._send(401, {"error": "Please sign in first.", "login": True})

    def do_GET(self):
        path = urlparse(self.path).path
        lab = self.lab
        try:
            if path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if path == "/api/math":
                c = parse_qs(urlparse(self.path).query).get("course", [""])[0]
                return self._send(200, lab.math_status(int(c) if c in ("1", "2", "3") else None))
            if path == "/api/collapse":
                return self._send(200, lab.collapse_status())
            if path == "/api/chatbot":
                return self._send(200, lab.chatbot_status())
            if path == "/api/me":
                if not lab.accounts:
                    return self._send(200, {"signed_in": False, "error": lab.accounts_error})
                s = self._who()
                return self._send(200, dict(lab.accounts.me(s), signed_in=True) if s else
                                  {"signed_in": False, "email_ready": lab.accounts.send.email_ready()})
            if path == "/api/chat":
                s = self._who()
                if not s:
                    return self._need_login()
                cid = parse_qs(urlparse(self.path).query).get("id", [""])[0]
                return self._send(200, lab.chat.status(s["aid"], cid or None))
            return self._send(404, {"error": "not found"})
        except Exception as e:
            print("error on", path, e, flush=True)
            return self._send(500, {"error": str(e)})

    def _account_post(self, path, body):
        """Signing in and out, and Settings. Errors a person caused (a wrong code...) come back as 400 with a message."""
        lab, A = self.lab, self.lab.accounts
        if not A:
            return self._send(503, {"error": lab.accounts_error})
        try:
            if path == "/api/auth/email":                          # layer 1: send a code to your email
                return self._send(200, A.start_email(body.get("email")))
            if path == "/api/auth/email/verify":                   # ...type it in: see your accounts
                return self._send(200, A.verify_email(body.get("token"), body.get("code")))
            if path in ("/api/auth/signup", "/api/auth/login", "/api/auth/2fa"):
                if path == "/api/auth/signup":
                    r = A.signup(body.get("token"), body.get("username"), body.get("password"))
                elif path == "/api/auth/login":                    # layer 2: the account's password
                    r = A.login(body.get("token"), str(body.get("account", "")), body.get("password"))
                else:                                              # layer 3 (if it's on): two-step verification
                    r = A.verify_2fa(body.get("token"), body.get("code"))
                if "session" in r:
                    return self._send(200, {"signed_in": True, "username": r["username"]}, cookie=r["session"])
                return self._send(200, r)
            if path == "/api/auth/logout":
                A.logout(self._sid())
                return self._send(200, {"signed_in": False}, cookie="")
            s = self._who()
            if not s:
                return self._need_login()
            if path == "/api/me/update":
                me = A.update(s, body)
                lab.chat.set_profile(s["aid"], A.profile(s))      # the AI now knows what you told it
                return self._send(200, me)
            if path == "/api/me/avatar/ai":
                return self._send(200, lab.ai_avatar(body.get("description")))
            if path == "/api/me/password":
                return self._send(200, A.change_password(s, body.get("old"), body.get("new")))
            if path == "/api/me/email":
                return self._send(200, A.start_email_change(s, body.get("email")))
            if path == "/api/me/email/verify":
                return self._send(200, A.finish_email_change(s, body.get("token"), body.get("code")))
            if path == "/api/me/2fa":
                return self._send(200, A.start_2fa(s, body.get("method")))
            if path == "/api/me/2fa/phone":
                return self._send(200, A.send_phone_test(s, body.get("token")))
            if path == "/api/me/2fa/verify":
                return self._send(200, A.finish_2fa(s, body.get("token"), body.get("code")))
            if path == "/api/me/2fa/off":
                return self._send(200, A.turn_off_2fa(s, body.get("password")))
            if path == "/api/me/delete":
                A.delete(s, body.get("password"))
                return self._send(200, {"signed_in": False}, cookie="")
            return self._send(404, {"error": "not found"})
        except accounts.AuthError as e:
            return self._send(400, {"error": str(e)})

    def do_POST(self):
        path = urlparse(self.path).path
        lab = self.lab
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 300000:                                   # (a profile picture is about 60 KB; nothing needs more)
                return self._send(413, {"error": "That's too big to send."})
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            if not isinstance(body, dict):
                body = {}
            if path in ("/api/math/pause", "/api/math/resume"):
                lab.cfg["math_paused"] = path.endswith("pause")
                for c in lab.all_courses:
                    c.paused = lab.cfg["math_paused"]
                lab.save_settings()
                return self._send(200, {"paused": lab.math.paused})
            if path == "/api/math/reset":
                n = body.get("course")
                course = lab.all_courses[n - 1] if n in (1, 2, 3) else lab.math
                course.reset()
                course.save()
                return self._send(200, {"ok": True})
            if path == "/api/math/mode":
                mode = str(body.get("mode", "auto"))
                lab.cfg["math_course"] = mode if mode in ("auto", "1", "2", "3") else "auto"
                lab.save_settings()
                return self._send(200, {"ok": True})
            if path == "/api/math/ask":
                try:
                    text = body.get("text")
                    if text is None:                                  # the old way: two numbers and + or -
                        text = "%s %s %s" % (body.get("a", ""), body.get("op", "+"), body.get("b", ""))
                    return self._send(200, lab.math_ask(str(text)[:60]))
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
            if path == "/api/collapse/start":
                try:
                    lab.start_collapse(body)
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                return self._send(200, {"ok": True})
            if path == "/api/collapse/stop":
                lab.stop_collapse()
                return self._send(200, {"ok": True})
            if path in ("/api/chatbot/start", "/api/chatbot/stop"):
                lab.bot.running = lab.cfg["chatbot_running"] = path.endswith("start")
                lab.save_settings()
                if lab.bot.running:
                    lab.bot.connection = lab.bot.llm.check()
                return self._send(200, lab.chatbot_status())
            if path.startswith("/api/auth/") or path.startswith("/api/me/"):
                return self._account_post(path, body)
            if path.startswith("/api/chat/"):
                s = self._who()
                if not s:
                    return self._need_login()
                me = s["aid"]
            if path == "/api/chat/send":
                try:
                    cid = lab.chat.send(me, body.get("text", ""), body.get("chat") or None,
                                        compare=body.get("compare", True) is not False, suggest=body.get("suggest", True) is not False,
                                        fix=body.get("fix", True) is not False)
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                if not cid:
                    return self._send(409, {"error": "It's still answering your last message."})
                return self._send(200, lab.chat.status(me, cid))
            if path == "/api/chat/stop":
                lab.chat.stop(me)
                return self._send(200, {"ok": True})
            if path == "/api/chat/regenerate":
                cid = lab.chat.regenerate(me, str(body.get("chat", "")))
                if not cid:
                    return self._send(409, {"error": "Wait until it finishes answering."})
                return self._send(200, lab.chat.status(me, cid))
            if path == "/api/chat/pick":
                try:
                    ok = lab.chat.pick(me, str(body.get("chat", "")), float(body.get("time", 0)), int(body.get("index", -1)), str(body.get("which", "")))
                except (TypeError, ValueError):
                    ok = False
                if not ok:
                    return self._send(409, {"error": "That answer can't be picked (it may still be writing, or you already picked one)."})
                return self._send(200, lab.chat.status(me, str(body.get("chat", ""))))
            if path == "/api/chat/rename":
                return self._send(200, {"ok": lab.chat.rename(me, str(body.get("chat", "")), body.get("title", ""))})
            if path == "/api/chat/delete":
                if not lab.chat.delete(me, str(body.get("chat", ""))):
                    return self._send(409, {"error": "Wait until it finishes answering in that chat."})
                return self._send(200, {"ok": True})
            if path == "/api/chatbot/experiment":
                pages = max(1, min(3, int(body.get("pages", 3))))
                topics = [t for t in body.get("topics", []) if t in KINDS] or ["arithmetic"]
                lab.bot.new_experiment(pages, bool(body.get("strict", False)), topics=topics)
                return self._send(200, lab.chatbot_status())
            if path == "/api/chatbot/reset":
                lab.bot.reset()
                return self._send(200, {"ok": True})
            if path == "/api/chatbot/settings":
                model = "".join(c for c in str(body.get("model", lab.cfg["model"])) if c.isalnum() or c in ".:-_/")[:60]
                if model:
                    lab.cfg["model"] = model
                lab.save_settings()
                lab.bot.connection = lab.bot.llm.check()
                return self._send(200, lab.chatbot_status())
            return self._send(404, {"error": "not found"})
        except Exception as e:
            print("error on", path, e, flush=True)
            return self._send(500, {"error": str(e)})


def main():
    try:
        os.nice(5)          # a little lower priority, so the Pi's other projects stay quick
    except OSError:
        pass
    cfg = load_settings()
    lab = Lab(cfg)
    Handler.lab = lab

    def stop(*_):
        def finish():
            lab.math.save()
            lab.math2.save()
            lab.math3.save()
            lab.chat.save_all()
            lab.stop_collapse("the program restarted (for example after an update)")
            print("saved. bye!", flush=True)
            os._exit(0)
        threading.Thread(target=finish, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    threading.Thread(target=lab.math_loop, daemon=True).start()
    threading.Thread(target=lab.bot.run, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "Pi Self-Learning AI running on port", PORT, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
