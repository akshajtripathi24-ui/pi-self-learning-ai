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
import http.client
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
Answer the question clearly in 2 to 4 short sentences. If you're not sure about something, say so.
If you can't help with something, say why in one sentence, and suggest something related you can help with."""

TITLE_PROMPT = """Write a short title (2 to 5 words) for a chat that starts with this question. Reply with only the title.

Question: How fast does the International Space Station go?
Title: Space station speed

Question: {question}
Title:"""

RETRY_SYSTEM = """You are a helpful teacher for a high school student. Answer the question clearly and simply in 2 to 4 sentences.
Only refuse if the question asks for something truly dangerous or harmful. If you do refuse, say why in one sentence,
and suggest a safe, related question you can answer instead."""

EXPLAIN_SYSTEM = """You are a friendly teacher for a high school student. An AI just refused to answer the student's question.
Don't answer the question itself. In 2 short sentences: first say why an AI might not answer it (for example, it could be
dangerous, it's about someone's private information, or it needs live information from the internet, which this AI
doesn't have). Then suggest a safe, related question the student could ask instead. Start with "I can't help with that because"."""

# words that show a refusal gives a reason ("...because it could hurt someone", "...I don't have internet access")
REASON = re.compile(r"\b(because|since|as it|due to|could|might|would|dangerous|unsafe|harm|harmful|hurt|illegal|against|"
                    r"private|personal|real-time|live|internet|online|access|don't have|do not have|not allowed|instead)\b", re.I)
LIVE = re.compile(r"\b(today|tonight|tomorrow|yesterday|right now|current|currently|latest|live|news|weather|score|scores|price|prices|"
                  r"stock|stocks|this week|this year)\b", re.I)

REFUSAL = re.compile(r"(i('m| am) sorry,? but i (can('|no)t|won't|am not able|am unable)|i can('|no)t (assist|help|provide|answer|do that|comply)|"
                     r"i('m| am) (not able|unable) to (assist|help|answer|provide)|as an ai( language model)?,? i (can('|no)t|don't))", re.I)


def has_reason(text):
    return bool(REASON.search(text or ""))


def fallback_reason(question):
    """If even the explanation fails, the Pi gives a reason itself."""
    if LIVE.search(question):
        return ("I can't help with that because I can't look things up on the internet, so I don't know what's happening "
                "right now. Try asking me how something works instead, like how weather forecasts are made.")
    return ("I can't help with that one. Small AIs like me are trained to say no to anything that sounds like it could be "
            "risky, and sometimes we're too careful with normal questions. If it's a normal question, try asking it a different way.")


def is_refusal(text):
    """Small models sometimes refuse harmless questions ("I'm sorry, but I can't assist with that.").
    Only short answers count: "I can't check live data, but the ISS goes about 28,000 km/h..." is a real answer."""
    text = (text or "").strip()
    return len(text) < 240 and bool(REFUSAL.search(text[:160]))


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


def math_bits(text):
    """The numbers and math symbols in order: 'whats 2.5+1,250?' -> ['2.5', '+', '1250']. (A '-' only counts
    between numbers or spaces, so the hyphen in "well-known" doesn't.)"""
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    return re.findall(r"\d+(?:\.\d+)?|[+*/^=%]|(?<=[\d\s])-(?=[\s\d.(x])", text)


def only_fixed(original, fixed):
    """The safety check: did the AI only fix the spelling and grammar? Small AIs sometimes answer the question
    instead ("...is Jupiter."), or add their own sentences. If so, we keep what you typed."""
    a, b = original.lower(), fixed.lower()
    if not 0.4 <= len(b) / max(1, len(a)) <= 2.5 or difflib.SequenceMatcher(None, a, b).ratio() < 0.5:
        return False
    # the math must stay exactly the same: "fixing" 2.5 into 25, or + into -, would solve the wrong problem
    if math_bits(a) != math_bits(b):
        return False
    # it mustn't add sentences that aren't questions (that's usually an answer)
    statements = lambda t: sum(not _is_question(x) for x in _sentences(t))
    if statements(fixed) > statements(original):
        return False
    # and it mustn't bring in many new words (fixing typos keeps the same words, spelled better)
    ow = _words(original)
    new = [w for w in _words(fixed) if w not in SMALL_WORDS and not any(_close(w, o) for o in ow)]
    return len(new) <= max(1, len(_words(fixed)) // 5)


QWORDS = r"(?:what|what's|whats|how|why|when|where|who|whose|which|can|could|is|are|was|were|do|does|did|should|will|would)"
ASKS = re.compile(r"^\W*(?:%s|solve|find|calculate|compute|work out|explain|tell me|describe|name|give)\b" % QWORDS, re.I)
JOIN = re.compile(r",?\s+(and then|and also|and|also|plus|then)\s+(?=%s\b)" % QWORDS, re.I)
ONE_THING = re.compile(r"\b(between|both|difference|compare|versus|vs)\b", re.I)


def split_and(sentence):
    """'what is 2.5 + 1.75 and how do I stop a program' -> two questions, even without a "?".
    Only if it starts like a question and both halves are at least 3 words: "how fast and how far can a rover go"
    is one question, and so is "what's the difference between what I eat and what I drink"."""
    if not ASKS.match(sentence) or ONE_THING.search(sentence):
        return [sentence]
    bits = JOIN.split(sentence)                                  # [part, joining word, part, joining word, part...]
    out = [bits[0].strip()]
    for joiner, part in zip(bits[1::2], bits[2::2]):
        part = part.strip()
        if len(out[-1].split()) < 3 or len(part.split()) < 3:
            out[-1] += " %s %s" % (joiner, part)                 # too short to be its own question: keep it joined
        else:
            out.append(part)
    return out


def split_questions(text, most=3):
    """'What is a robot? How do they move?' -> two questions. A sentence that isn't a question
    (like 'I have 3 robots.') stays with the question after it."""
    sentences = [s for s in re.split(r"(?<=[?!.])\s+", text.strip()) if s]
    questions, waiting = [], []
    for s in sentences:
        parts = split_and(s)
        if len(parts) > 1:                                       # "... and how ...": each part is a question
            questions.append(" ".join(waiting + [parts[0]]))
            questions += parts[1:]
            waiting = []
            continue
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
            "integral": "the integral of %s is %s" % (what, answer), "sqrt": "%s = %s" % (what, answer),
            "percent": "%s = %s" % (what, answer)}.get(kind, "%s = %s" % (what.replace("*", "×"), answer))


def content_words(text):
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in COMMON}


def clean_title(text, fallback):
    """The AI's title, tidied up. If it's empty or looks like an answer, use the first words of the question."""
    t = (text or "").strip().split("\n")[0]
    t = re.sub(r"^\s*title\s*:\s*", "", t, flags=re.I).strip().strip('"\'*.!?: ')
    if not t or len(t) > 45 or len(t.split()) > 7 or is_refusal(t):
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
                    self._tidy(c)
                    self.chats[c["id"]] = c
                except (OSError, ValueError, KeyError):
                    pass
        self.busy, self.busy_chat = False, None
        self.stage, self.stage_since = None, 0
        self.stop_asked = False

    @staticmethod
    def _tidy(c):
        """An answer that was being written when the Pi restarted would otherwise say "writing" forever."""
        for m in c["messages"]:
            for a in m.get("answers", []):
                if a.get("writing"):
                    a["writing"], a["stopped"], a["interrupted"] = False, True, True
        if c["messages"]:
            last = c["messages"][-1]
            if not last.get("answers") and not last.get("error") and not last.get("stopped"):
                last["error"] = "The Pi restarted before it answered. Press 🔄 Try again."

    # ------------------------------------------------------------ saving and listing chats
    def save_all(self):
        """When the program is shut down (like for an update), save what's been written so far."""
        with self.lock:
            for c in self.chats.values():
                if c["id"] == self.busy_chat:
                    self._save(c)

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
            chat = json.loads(json.dumps({"id": c["id"], "title": c["title"], "messages": c["messages"][-60:]})) if c else None
            return {"chats": self._list(), "chat": chat,      # (a copy: the answer keeps changing while it's written)
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
        if not text:
            raise ValueError("Type a question first.")
        with self.lock:
            if self.busy:
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
            msg["answers"], msg["error"], msg["stopped"] = [], None, False
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
                        if not a.get("a") or a.get("refused") or is_refusal(a["a"]):
                            continue
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
            # 2. split it into questions
            questions, extra = split_questions(fixed)
            with self.lock:
                msg["fixed"], msg["skipped"] = fixed, extra
                # this chat's last 3 answered messages (not refusals: a small AI copies those)
                history = [m for m in chat["messages"] if m is not msg and m["answers"]
                           and not all(a.get("refused") or is_refusal(a["a"]) for a in m["answers"])][-3:]
            if self.stop_asked:
                with self.lock:
                    msg["stopped"] = True
                return
            # 3 and 4. check the math, then answer each question
            for q in questions:
                if self.stop_asked:
                    break
                self._set("answering")
                found = mathengine.find_problem(q)                       # 3. the math engine works out any math exactly
                engine = tutor = None
                examples = []
                math_note = ""
                if found:
                    kind, what, answer = found
                    engine = {"kind": kind, "what": what, "answer": answer, "text": describe(kind, what, answer),
                              "steps": mathengine.steps(kind, what)}
                    math_note = "\nA math engine worked this out exactly: %s. Use this answer, and explain the steps simply." % engine["text"]
                    if engine["steps"]:
                        math_note += "\nThe steps: " + " ".join("%d) %s." % (i + 1, st.rstrip(".")) for i, st in enumerate(engine["steps"]))
                    tutor = self.tutor(kind, what) if self.tutor else None   # ...and your trained math AI has a go too
                elif re.search(r"\d", q):                                # a word problem: use checked practice problems
                    examples = self._examples(q)
                system = ANSWER_SYSTEM + math_note
                if examples:
                    system += "\nHere are similar problems that were solved and checked:\n" + "\n".join(
                        "PROBLEM: %s MATH: %s ANSWER: %s" % (e["problem"], e["math"], e["answer"]) for e in examples)
                memories = self._memories(q, chat)                     # related things from your other chats
                if memories:
                    system += "\nFrom the student's other chats (use only if it helps):\n" + "\n".join(
                        '- In the chat "%s", they asked: %s You answered: %s' % (t, mq, ma[:200]) for _, _, _, t, mq, ma in memories)
                convo = [{"role": "system", "content": system}]
                for m in history:
                    convo.append({"role": "user", "content": (m["fixed"] or m["you"])[:300]})
                    convo.append({"role": "assistant", "content": " ".join(a["a"] for a in m["answers"])[:400]})
                with self.lock:
                    earlier = [(a["q"], a["a"]) for a in msg["answers"] if a["a"]]   # questions answered earlier in this message
                for eq, ea in earlier:
                    convo += [{"role": "user", "content": eq}, {"role": "assistant", "content": ea[:400]}]
                convo.append({"role": "user", "content": q})
                entry = {"q": q, "a": "", "engine": engine, "tutor": tutor, "examples": len(examples), "writing": True,
                         "memories": list({cid: {"chat": cid, "title": t} for _, _, cid, t, _, _ in memories}.values())}
                with self.lock:
                    msg["answers"].append(entry)
                stopped = self._write(entry, convo, 0.85 if again else 0.4)
                if not stopped and is_refusal(entry["a"]):
                    # small models sometimes refuse harmless questions: try once more, simply, without the extras
                    first = entry["a"]
                    with self.lock:
                        entry["a"], entry["writing"], entry["retried"] = "", True, True
                    simple = [{"role": "system", "content": RETRY_SYSTEM + math_note}, {"role": "user", "content": q}]
                    stopped = self._write(entry, simple, 0.7)
                    if not stopped and is_refusal(entry["a"]):
                        with self.lock:
                            entry["refused"] = True
                        if not has_reason(entry["a"]):           # a bare "I can't assist with that": find out why
                            if has_reason(first):
                                with self.lock:
                                    entry["a"] = first
                            else:
                                stopped = self._explain(entry, q)
                with self.lock:
                    chat["updated"] = time.time()
                    self._save(chat)
                if stopped:
                    break
            # 5. a title for a new chat (after its first answered message)
            answered = [m for m in chat["messages"] if m["answers"]]
            if not chat.get("titled") and answered == [msg] and questions and not self.stop_asked:
                self._set("titling")
                title = llm.ask(TITLE_PROMPT.format(question=questions[0]), max_tokens=16, temperature=0.3)
                with self.lock:
                    if not chat.get("titled"):                         # (unless you renamed it in the meantime)
                        chat["title"], chat["titled"] = clean_title(title, fixed), True
        except Exception as e:
            why = str(e)
            if "timed out" in why:
                why = "the model took too long to answer"
            elif "HTTP Error 400" in why:
                why = "the model couldn't take a message that long. Try a shorter question, or start a new chat."
            elif "refused" in why.lower() or "Errno 111" in why:
                why = ("the AI model isn't running. Wait a minute if the Pi just started, or restart it on the Pi with: "
                       "sudo systemctl restart llamaserver")
            elif isinstance(e, (ConnectionError, http.client.HTTPException)):
                why = ("the model stopped in the middle of answering (on a Pi this usually means it ran out of memory). "
                       "Press 🔄 Try again")
            with self.lock:
                msg["error"] = why
        finally:
            with self.lock:
                self.busy, self.busy_chat = False, None
                self.stage = None
                if chat["id"] in self.chats:
                    self._save(chat)
            self.bot.hold_until = time.time() + 20             # carry on practicing soon, unless you ask again

    def _explain(self, entry, q):
        """It said no without saying why. Ask for the reason (and a safer question to ask instead).
        If even that's a bare refusal, the Pi writes a reason itself. Returns True if you pressed Stop."""
        with self.lock:
            entry["a"], entry["writing"], entry["explained"] = "", True, True
        stopped = self._write(entry, [{"role": "system", "content": EXPLAIN_SYSTEM},
                                      {"role": "user", "content": "The student's question: " + q}], 0.5, stage="explaining")
        if not stopped and (not has_reason(entry["a"]) or len(entry["a"]) < 25):
            with self.lock:
                entry["a"] = fallback_reason(q)
        return stopped

    def _write(self, entry, convo, temperature, stage="writing"):
        """Live typing: stream the answer into entry. Returns True if you pressed Stop."""
        self._set(stage)

        def add(piece):
            with self.lock:
                entry["a"] += piece
        stopped = False
        try:
            stopped = self.bot.llm.chat_stream(convo, add, stop=lambda: self.stop_asked, max_tokens=260, temperature=temperature)
        finally:                                    # even if the model crashes halfway, it's not "writing" any more
            with self.lock:
                entry["a"] = entry["a"].strip()
                entry["writing"] = False
                entry["stopped"] = stopped
        return stopped
