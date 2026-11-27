"""Part 4: talk to the AI. Type any question, even with spelling or grammar mistakes.

For each message it:
  1. FIXES spelling and grammar (the same small AI rewrites your message), with a safety check
     that it only fixed it, and didn't change or answer it,
  2. SPLITS it into separate questions, if you asked more than one,
  3. CHECKS any math with Python (the "checker"), so the answer can't get the math wrong,
  4. ANSWERS each question, remembering this chat (for follow-ups) and anything related from your OTHER chats.
Chats are saved on the Pi (data/chats/), each with a title the AI writes, so you can go back to them any time.
While you chat, the self-quizzing practice pauses, so you get answers faster.
"""
import difflib
import json
import os
import re
import secrets
import threading
import time

import mathengine
from chatbot import similar

FIX_PROMPT = """Fix the spelling and grammar mistakes in the text. Keep the same meaning and the same questions.
Don't answer the questions. Reply with only the fixed text.

Text: wat is the bigest planet in are solar sistem
Fixed: What is the biggest planet in our solar system?

Text: how do rokets get to space and how fast do they go
Fixed: How do rockets get to space, and how fast do they go?

Text: {text}
Fixed:"""

ANSWER_SYSTEM = """You are a friendly helper for a student who loves robotics, space and coding.
Answer the question clearly in 2 to 4 short sentences. If you're not sure about something, say so."""

TITLE_PROMPT = """Write a short title (2 to 5 words) for a chat that starts with this question. Reply with only the title.

Question: How fast does the International Space Station go?
Title: Space station speed

Question: {question}
Title:"""

# words too common to tell chats apart, for finding related things in your other chats
COMMON = {"what", "when", "where", "which", "while", "with", "would", "could", "should", "there", "their", "them", "they",
          "this", "that", "these", "those", "have", "does", "about", "from", "into", "your", "much", "many", "more", "most",
          "some", "than", "then", "make", "made", "like", "just", "also", "very", "really", "work", "works", "tell", "explain",
          "please", "thanks", "know", "think", "want", "need", "help", "answer", "question"}
REMEMBER_CUES = re.compile(r"\b(before|earlier|last time|remember|previous|other chat|already asked|asked about)\b", re.I)

QUESTION_WORDS = ["what", "why", "how", "when", "where", "who", "which", "whose", "can", "could", "is", "are", "do",
                  "does", "did", "will", "would", "should", "was", "were", "have", "has", "explain", "tell"]
SMALL_WORDS = {"a", "an", "the", "is", "are", "am", "was", "were", "be", "do", "does", "did", "to", "of", "in", "on", "at",
               "and", "or", "it", "its", "it's", "our", "your", "my", "you", "i", "for", "with", "that", "this", "there", "s"}


def _words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def _close(a, b):
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.6


def _sentences(text):
    return [x for x in re.split(r"(?<=[?!.])\s+", text.strip()) if x.strip()]


def _is_question(sentence):
    """Ends with "?", or starts with a question word (a misspelled long one like "wat" counts; short ones like "is" must be exact)."""
    w = _words(sentence)
    if sentence.rstrip().endswith("?"):
        return True
    return bool(w) and any(w[0] == q or (len(q) >= 4 and difflib.SequenceMatcher(None, w[0], q).ratio() >= 0.75)
                           for q in QUESTION_WORDS)


def only_fixed(original, fixed):
    """The safety check: did the AI only fix the spelling and grammar? Small AIs sometimes answer the question
    instead ("...is Jupiter."), or add their own sentences. If so, we keep what you typed."""
    a, b = original.lower(), fixed.lower()
    if not 0.4 <= len(b) / max(1, len(a)) <= 2.5 or difflib.SequenceMatcher(None, a, b).ratio() < 0.5:
        return False
    # it mustn't add sentences that aren't questions (that's usually an answer)
    statements = lambda t: sum(not _is_question(x) for x in _sentences(t))
    if statements(fixed) > statements(original):
        return False
    # and it mustn't bring in many new words (fixing typos keeps the same words, spelled better)
    ow = _words(original)
    new = [w for w in _words(fixed) if w not in SMALL_WORDS and not any(_close(w, o) for o in ow)]
    return len(new) <= max(1, len(_words(fixed)) // 5)


def split_questions(text, most=3):
    """'What is a robot? How do they move?' -> two questions. A sentence that isn't a question
    (like 'I have 3 robots.') stays with the question after it."""
    sentences = [s for s in re.split(r"(?<=[?!.])\s+", text.strip()) if s]
    questions, waiting = [], []
    for s in sentences:
        waiting.append(s)
        if s.endswith("?"):
            questions.append(" ".join(waiting))
            waiting = []
    if waiting:
        if questions:
            questions[-1] += " " + " ".join(waiting)
        else:
            questions.append(" ".join(waiting))
    return questions[:most], max(0, len(questions) - most)


def describe(kind, what, answer):
    """How the math engine's answer is shown, and told to the AI."""
    return {"solve": "%s, so %s" % (what, answer), "derivative": "d/dx (%s) = %s" % (what, answer),
            "integral": "the integral of %s is %s" % (what, answer)}.get(kind, "%s = %s" % (what.replace("*", "×"), answer))


def content_words(text):
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in COMMON}


def clean_title(text, fallback):
    """The AI's title, tidied up. If it's empty or looks like an answer, use the first words of the question."""
    t = (text or "").strip().split("\n")[0]
    t = re.sub(r"^\s*title\s*:\s*", "", t, flags=re.I).strip().strip('"\'*.!?: ')
    if not t or len(t) > 45 or len(t.split()) > 7:
        words = re.sub(r"[?!.,]", "", fallback).split()
        t = " ".join(words[:5]) + ("…" if len(words) > 5 else "")
    return t[:60] or "New chat"


class Chat:
    def __init__(self, bot, folder, tutor=None):
        self.bot = bot                     # the self-quizzing chatbot: we share its connection to the model
        self.tutor = tutor                 # asks your trained math AI, if the question is something it practices
        self.folder = folder               # one file per chat, so they're kept after a restart
        os.makedirs(folder, exist_ok=True)
        self.lock = threading.Lock()
        self.chats = {}
        for name in os.listdir(folder):
            if name.endswith(".json"):
                try:
                    with open(os.path.join(folder, name)) as f:
                        c = json.load(f)
                    self.chats[c["id"]] = c
                except (OSError, ValueError, KeyError):
                    pass
        self.busy, self.busy_chat = False, None
        self.stage, self.stage_since = None, 0
        self.stop_asked = False

    # ------------------------------------------------------------ saving and listing chats
    def _save(self, chat):
        path = os.path.join(self.folder, chat["id"] + ".json")
        with open(path + ".tmp", "w") as f:
            json.dump(chat, f)
        os.replace(path + ".tmp", path)

    def _list(self):
        rows = sorted(self.chats.values(), key=lambda c: -c["updated"])
        return [{"id": c["id"], "title": c["title"], "updated": c["updated"], "count": len(c["messages"])} for c in rows]

    def status(self, chat_id=None):
        with self.lock:
            c = self.chats.get(chat_id)
            return {"chats": self._list(),
                    "chat": {"id": c["id"], "title": c["title"], "messages": c["messages"][-60:]} if c else None,
                    "busy": self.busy, "busy_chat": self.busy_chat, "stage": self.stage,
                    "stage_seconds": round(time.time() - self.stage_since) if self.stage else None,
                    "speed": self.bot.llm.speed, "model": self.bot.llm.model_name}

    def _new(self):
        cid = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
        c = {"id": cid, "title": "New chat", "titled": False, "created": time.time(), "updated": time.time(), "messages": []}
        self.chats[cid] = c
        return c

    def rename(self, chat_id, title):
        title = " ".join(str(title).split())[:60]
        with self.lock:
            c = self.chats.get(chat_id)
            if c and title:
                c["title"], c["titled"] = title, True
                self._save(c)
                return True
        return False

    def delete(self, chat_id):
        with self.lock:
            if chat_id not in self.chats or (self.busy and self.busy_chat == chat_id):
                return False
            del self.chats[chat_id]
        try:
            os.remove(os.path.join(self.folder, chat_id + ".json"))
        except OSError:
            pass
        return True

    def send(self, text, chat_id=None):
        """Returns the chat's id (a new chat if chat_id is empty), or None if it's still busy."""
        text = " ".join(str(text).split())[:600]
        with self.lock:
            if self.busy or not text:
                return None
            c = self.chats.get(chat_id) or self._new()
            msg = {"you": text, "fixed": None, "answers": [], "error": None, "time": time.time()}
            c["messages"].append(msg)
            c["updated"] = time.time()
            if not c["titled"] and len(c["messages"]) == 1:
                c["title"] = clean_title("", text)            # a first title right away; the AI writes a better one
            self.busy, self.busy_chat, self.stop_asked = True, c["id"], False
            self._save(c)
        threading.Thread(target=self._work, args=(c, msg), daemon=True).start()
        return c["id"]

    def stop(self):
        """The ⏹️ button: stop writing the answer."""
        self.stop_asked = True

    def regenerate(self, chat_id):
        """The 🔄 button: answer your last message again, a bit differently."""
        with self.lock:
            c = self.chats.get(chat_id)
            if self.busy or not c or not c["messages"]:
                return None
            msg = c["messages"][-1]
            msg["answers"], msg["error"] = [], None
            self.busy, self.busy_chat, self.stop_asked = True, c["id"], False
        threading.Thread(target=self._work, args=(c, msg, True), daemon=True).start()
        return c["id"]

    # ------------------------------------------------------------ what it can use to answer
    def _examples(self, q, n=2):
        """Up to 2 practice problems like this one that the Chatbot got right (so Python and the AI agreed)."""
        solved = list(self.bot.state.get("solved", []))
        words = set(re.findall(r"[a-z]{4,}", q.lower()))
        return [e for e in similar(q, solved, n) if len(words & set(re.findall(r"[a-z]{4,}", e["problem"].lower()))) >= 2]

    def _memories(self, q, chat, n=2):
        """Answers from your OTHER chats that share important words with this question
        (2 or more, or just 1 if you say something like "before" or "remember")."""
        words = content_words(q)
        need = 1 if REMEMBER_CUES.search(q) else 2
        found = []
        with self.lock:
            others = [c for c in self.chats.values() if c["id"] != chat["id"]]
            for c in others:
                for m in c["messages"]:
                    for a in m.get("answers", []):
                        overlap = len(words & content_words(a["q"] + " " + a["a"]))
                        if overlap >= need:
                            found.append((overlap, m.get("time", 0), c["id"], c["title"], a["q"], a["a"]))
        found.sort(key=lambda x: (-x[0], -x[1]))
        return found[:n]

    def _set(self, stage):
        self.stage, self.stage_since = stage, time.time()
        self.bot.hold_until = time.time() + 120               # pause the practice while we chat

    # ------------------------------------------------------------ answering
    def _work(self, chat, msg, again=False):
        llm = self.bot.llm
        try:
            ok, why = llm.check()
            if not ok:
                raise RuntimeError(why)
            # 1. fix spelling and grammar (not again, if you asked for a different answer)
            if again and msg.get("fixed"):
                fixed = msg["fixed"]
            else:
                self._set("fixing")
                fixed = llm.ask(FIX_PROMPT.format(text=msg["you"]), max_tokens=len(msg["you"]) // 2 + 40, temperature=0)
                fixed = fixed.strip().split("\n")[0].strip().strip('"').strip()
                fixed = re.sub(r"^(fixed|text)\s*:\s*", "", fixed, flags=re.I)
                if not fixed or not only_fixed(msg["you"], fixed):
                    fixed = msg["you"]                         # the safety check: keep what you typed
                msg["fixed"] = fixed
            # 2. split it into questions
            questions, extra = split_questions(fixed)
            msg["skipped"] = extra
            # 3 and 4. check the math, then answer each question
            with self.lock:
                history = [m for m in chat["messages"] if m is not msg and m["answers"]][-3:]   # this chat: the last 3
            for q in questions:
                self._set("answering")
                found = mathengine.find_problem(q)                       # 3. the math engine works out any math exactly
                system = ANSWER_SYSTEM
                engine = tutor = None
                examples = []
                if found:
                    kind, what, answer = found
                    engine = {"kind": kind, "what": what, "answer": answer, "text": describe(kind, what, answer),
                              "steps": mathengine.steps(kind, what)}
                    system += "\nA math engine worked this out exactly: %s. Use this answer, and explain the steps simply." % engine["text"]
                    if engine["steps"]:
                        system += "\nThe steps: " + " ".join("%d) %s." % (i + 1, st.rstrip(".")) for i, st in enumerate(engine["steps"]))
                    tutor = self.tutor(kind, what) if self.tutor else None   # ...and your trained math AI has a go too
                elif re.search(r"\d", q):                                # a word problem: use checked practice problems
                    examples = self._examples(q)
                    if examples:
                        system += "\nHere are similar problems that were solved and checked:\n" + "\n".join(
                            "PROBLEM: %s MATH: %s ANSWER: %s" % (e["problem"], e["math"], e["answer"]) for e in examples)
                memories = self._memories(q, chat)                     # related things from your other chats
                if memories:
                    system += "\nFrom the student's other chats (use only if it helps):\n" + "\n".join(
                        '- In the chat "%s", they asked: %s You answered: %s' % (t, mq, ma[:220]) for _, _, _, t, mq, ma in memories)
                convo = [{"role": "system", "content": system}]
                for m in history:
                    convo.append({"role": "user", "content": m["fixed"] or m["you"]})
                    convo.append({"role": "assistant", "content": " ".join(a["a"] for a in m["answers"])[:600]})
                convo.append({"role": "user", "content": q})
                entry = {"q": q, "a": "", "engine": engine, "tutor": tutor, "examples": len(examples), "writing": True,
                         "memories": list({cid: {"chat": cid, "title": t} for _, _, cid, t, _, _ in memories}.values())}
                with self.lock:
                    msg["answers"].append(entry)
                self._set("writing")

                def add(piece):                                        # live typing: each piece as it's written
                    with self.lock:
                        entry["a"] += piece
                stopped = llm.chat_stream(convo, add, stop=lambda: self.stop_asked, max_tokens=260,
                                          temperature=0.85 if again else 0.4)
                with self.lock:
                    entry["a"] = entry["a"].strip()
                    entry["writing"] = False
                    entry["stopped"] = stopped
                    chat["updated"] = time.time()
                    self._save(chat)
                if stopped:
                    break
            # 5. a title for a new chat
            if not chat.get("titled") and len(chat["messages"]) == 1 and questions and not self.stop_asked:
                self._set("titling")
                title = llm.ask(TITLE_PROMPT.format(question=questions[0]), max_tokens=16, temperature=0.3)
                with self.lock:
                    if not chat.get("titled"):                         # (unless you renamed it in the meantime)
                        chat["title"], chat["titled"] = clean_title(title, fixed), True
        except Exception as e:
            msg["error"] = "the model took too long to answer" if "timed out" in str(e) else str(e)
        finally:
            with self.lock:
                self.busy, self.busy_chat = False, None
                self.stage = None
                if chat["id"] in self.chats:
                    self._save(chat)
            self.bot.hold_until = time.time() + 20             # carry on practicing soon, unless you ask again
