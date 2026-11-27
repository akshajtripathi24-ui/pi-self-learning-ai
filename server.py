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
import multiprocessing
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import collapse
import selfmath
from chatbot import Chatbot, compare

PORT = int(os.environ.get("SELF_PORT", "8100"))      # stock tracker 8000, ISS tracker 8080, docking AI 8090
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RUNS = os.path.join(DATA, "collapse")
SETTINGS_FILE = os.path.join(HERE, "config.json")
DEFAULTS = {"math_paused": False, "chatbot_running": False, "model": "qwen2.5:0.5b", "ollama_url": "http://localhost:11434", "llamacpp_url": "http://localhost:8099"}


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
        self.math = selfmath.MathAI(DATA)
        self.math.paused = cfg["math_paused"]
        self.bot = Chatbot(DATA, cfg)
        self.bot.running = cfg["chatbot_running"]           # keep practicing after the Pi restarts
        self.collapse_proc = None
        self.collapse_path = None
        for path in glob.glob(os.path.join(RUNS, "*.json")):          # runs that were cut off by a restart
            r = read_json(path)
            if r and r.get("status") == "running":
                r["status"] = "stopped"
                write_json(path, r)

    def save_settings(self):
        write_json(SETTINGS_FILE, self.cfg)

    # ------------------------------------------------------------ part 1
    def math_status(self):
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
            return {"level": lv, "levels": [l["name"] for l in selfmath.LEVELS], "mastered": st["mastered"], "round": st["round"],
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
        settings = {"rounds": max(2, min(10, int(body.get("rounds", 6)))), "keep_real": bool(body.get("keep_real", False)),
                    "temperature": max(0.3, min(1.5, float(body.get("temperature", 0.9)))), "steps": 1500}
        path = os.path.join(RUNS, time.strftime("run-%Y%m%d-%H%M%S") + ".json")
        self.collapse_proc = multiprocessing.get_context("spawn").Process(target=collapse_job, args=(settings, path), daemon=True)   # a fresh, separate process
        self.collapse_proc.start()
        self.collapse_path = path
        for old in sorted(glob.glob(os.path.join(RUNS, "*.json")))[:-8]:   # keep the last 8 runs
            os.remove(old)

    def stop_collapse(self):
        if self.collapse_proc is not None and self.collapse_proc.is_alive():
            self.collapse_proc.terminate()
            self.collapse_proc.join(5)
            r = read_json(self.collapse_path)
            if r:
                r["status"] = "stopped"
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
                    "load": round(os.getloadavg()[0], 1), "cores": os.cpu_count() or 4,
                    "settings": st["settings"], "result": compare(st["with"], st["without"]),
                    "runs": [dict(r, result=compare(r["with"], r["without"])) for r in st["runs"]]}


class Handler(BaseHTTPRequestHandler):
    lab = None

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        lab = self.lab
        try:
            if path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if path == "/api/math":
                return self._send(200, lab.math_status())
            if path == "/api/collapse":
                return self._send(200, lab.collapse_status())
            if path == "/api/chatbot":
                return self._send(200, lab.chatbot_status())
            return self._send(404, {"error": "not found"})
        except Exception as e:
            print("error on", path, e, flush=True)
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        path = urlparse(self.path).path
        lab = self.lab
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            if path in ("/api/math/pause", "/api/math/resume"):
                lab.math.paused = lab.cfg["math_paused"] = path.endswith("pause")
                lab.save_settings()
                return self._send(200, {"paused": lab.math.paused})
            if path == "/api/math/reset":
                lab.math.reset()
                lab.math.save()
                return self._send(200, {"ok": True})
            if path == "/api/math/ask":
                try:
                    return self._send(200, lab.math.ask(int(body.get("a", -1)), int(body.get("b", -1)), str(body.get("op", "+"))))
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
            if path == "/api/chatbot/experiment":
                pages = max(1, min(3, int(body.get("pages", 3))))
                lab.bot.new_experiment(pages, bool(body.get("strict", False)))
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
            lab.stop_collapse()
            print("saved. bye!", flush=True)
            os._exit(0)
        threading.Thread(target=finish, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    threading.Thread(target=lab.math.run, daemon=True).start()
    threading.Thread(target=lab.bot.run, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "Pi Self-Learning AI running on port", PORT, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
