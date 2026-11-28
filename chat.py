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
import random
import re
import secrets
import threading
import time

import shutil

import mathengine
from accounts import seal, unseal
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
Don't make up facts about people, and don't guess someone's reasons or feelings as if you knew them.
If you can't help with something, say why in one sentence, and suggest something related you can help with."""

# questions where one confident answer would be a guess: why someone feels or does something, and opinions
WHY_PERSON = re.compile(r"\bwhy (?:do|does|did|is|are|was|were|would|wouldn'?t|won'?t|can'?t|doesn'?t|don'?t|didn'?t|isn'?t|aren'?t|wasn'?t)\b"
                        r"[^?]*?\b(?:like|likes|liked|love|loves|loved|hate|hates|hated|dislike|dislikes|enjoy|enjoys|want|wants|prefer|"
                        r"prefers|feel|feels|think|thinks|care|cares|scared|afraid|angry|mad|sad|happy|upset|annoyed|bored|jealous|"
                        r"eat|eats|watch|watches|play|plays|choose|chose|pick|picks|believe|believes|trust|trusts|act|acts|say|says|"
                        r"said|mean|rude|nice|quiet|shy|annoying|weird|lazy)\b", re.I)
OPINION = re.compile(r"\b(?:best|worst|better|worse|favou?rite|should i|should we|is it worth|worth it|overrated|underrated|"
                     r"good idea|bad idea|coolest|greatest|smartest|fairest|versus|vs\.?|do you think|your opinion|"
                     r"what do you think|is it ok(?:ay)? to|is it bad|is it good)\b", re.I)
WHY_NOTE = """
This question asks WHY a person (or people) feel or act a certain way. Unless there's a clear, well-known answer, you can't
know the real reason, especially for someone you don't know. Don't pick one reason, and don't state a guess as a fact. Say you can't know for sure, then give 3 or 4
common possible reasons as a short list, and end by asking what they think, or suggesting they ask the person."""
OPINION_NOTE = """
This is an opinion question, so there isn't one right answer. Don't state one opinion as a fact. Give the main things it
depends on as a short list, with a good point for each side. You can say what you'd lean toward and why, but say it depends
on the person."""
# words that show an answer isn't pretending to know for sure
HEDGE = re.compile(r"\b(might|may|maybe|could|possibly|perhaps|probably|some people|many people|others|depends|depending|"
                   r"not sure|don'?t know|do not know|can'?t know|cannot know|no way to know|hard to say|possible|reasons|factors|"
                   r"everyone|personal|preference|on the other hand|it varies|varies)\b", re.I)


WHY_SOMEONE = re.compile(r"\bwhy (?:do|does|did|is|are|was|were|would|won'?t|can'?t|doesn'?t|don'?t|didn'?t|isn'?t|aren'?t|wasn'?t)\s+"
                         r"(?:my|your|his|her|their|our|the|some|most|all)?\s*(?:mom|moms|dad|dads|mother|father|parents?|brother|"
                         r"sister|siblings?|friends?|best friend|teachers?|coach|boss|classmates?|cousins?|grandma|grandpa|"
                         r"grandparents|family|uncle|aunt|neighbou?rs?|kids|boys|girls|people|someone|somebody|everyone|he|she)\b", re.I)


def guess_kind(question):
    """"why" for why-someone-feels questions, "opinion" for opinions, else None."""
    if WHY_PERSON.search(question) or WHY_SOMEONE.search(question):
        return "why"
    if OPINION.search(question):
        return "opinion"
    return None

TITLE_PROMPT = """Write a short title (2 to 5 words) for a chat that starts with this question. Reply with only the title.

Question: How fast does the International Space Station go?
Title: Space station speed

Question: {question}
Title:"""

SUGGEST_PROMPT = """Write 2 short follow-up questions a curious student might ask next. Each one under 10 words, on its own line.
Reply with only the 2 questions.

Question: How fast does the ISS go?
Answer: About 28,000 km/h, so it goes around Earth about every 90 minutes.
Follow-ups:
How do astronauts sleep on the ISS?
Can I see the ISS from my house?

Question: {question}
Answer: {answer}
Follow-ups:"""

FOLLOWUPS = """
After your answer, on a new line, write "Next questions:" and then 2 short follow-up questions the student might ask
next, separated by " | ". For example:
Next questions: How do astronauts sleep in space? | Can I see the ISS from my house?"""
NEXT_MARK = re.compile(r"(?:^|\n|(?<=[.!?)])\s)[\s*#_]*(?:next questions?|follow[- ]?up questions?|follow[- ]?ups?)[\s*_]*:", re.I)
MARK_WORDS = ("next questions:", "follow-up questions:", "follow up questions:", "followups:")


def split_next(raw):
    """The answer and its follow-up questions are written together: "...the answer. Next questions: A? | B?".
    Returns (the answer to show, the follow-up part or None). While it's still writing "Next qu...", that bit is hidden."""
    m = NEXT_MARK.search(raw)
    if m:
        return raw[:m.start()].rstrip(), raw[m.end():].lstrip("*_ ")
    frag = re.split(r"(?<=[.!?)])\s+|\n", raw)[-1]
    t = frag.strip(" *#_").lower()
    if len(t) >= 2 and any(w.startswith(t) for w in MARK_WORDS):
        return raw[:len(raw) - len(frag)].rstrip(), None                 # maybe the start of "Next questions:"
    return raw, None


COMPARE_CHANCE = float(os.environ.get("CHAT_COMPARE_CHANCE", "0.25"))   # about 1 in 4 single questions also gets a
                                                                          # second answer, so you can pick the one you like
CAREFUL, CREATIVE = 0.4, 0.95  # the two answers' temperatures: careful (sticks to the likeliest words) and creative


def clean_suggestions(text, question):
    """The AI's follow-up questions, tidied: no numbers or bullets, not too short or long, not your own question again."""
    out = []
    for line in (text or "").split("\n"):
        t = re.sub(r"^\s*(?:[-*•]|\d+[.)]|follow-?ups?:)\s*", "", line, flags=re.I).strip().strip('"\'*_ ')
        if not 3 <= len(t.split()) <= 14 or is_refusal(t) or t.lower().rstrip("?") == question.lower().rstrip("?"):
            continue
        t = t.rstrip(" |").strip()
        if not t.endswith("?") and _is_question(t):
            t += "?"
        if t.lower() not in [o.lower() for o in out]:
            out.append(t)
    return out[:2]


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


def names(text):
    """Words you typed with a capital letter in the middle of a sentence, like "Akshaj" or "Micro Center"."""
    out = []
    for sentence in _sentences(text):
        out += [w for w in re.findall(r"[A-Za-z']+", sentence)[1:] if w[0].isupper() and w != "I" and not w.startswith("I'")]
    return out


def only_fixed(original, fixed):
    """The safety check: did the AI only fix the spelling and grammar? Small AIs sometimes answer the question
    instead ("...is Jupiter."), or add their own sentences. If so, we keep what you typed."""
    a, b = original.lower(), fixed.lower()
    if not 0.4 <= len(b) / max(1, len(a)) <= 2.5 or difflib.SequenceMatcher(None, a, b).ratio() < 0.5:
        return False
    # the math must stay exactly the same: "fixing" 2.5 into 25, or + into -, would solve the wrong problem
    if math_bits(a) != math_bits(b):
        return False
    # and names must stay exactly the same: "Akshaj" isn't a misspelling of "Akash"
    fixed_words = set(re.findall(r"[A-Za-z']+", fixed))
    if any(name not in fixed_words for name in names(original)):
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
        self.folder = folder               # data/chats/<account>/: one locked (encrypted) file per chat
        os.makedirs(folder, exist_ok=True)
        self.lock = threading.Lock()
        self.chats = {}                    # the chats of everyone signed in right now
        self.keys = {}                     # account -> its key (only in memory, only while it's signed in)
        self.notes = {}                    # account -> what its settings tell the AI about them
        self.leaving = set()               # accounts that signed out while their answer was still being written
        self.busy, self.busy_chat = False, None
        self.stage, self.stage_since = None, 0
        self.stop_asked = False
        self.known = {}                    # word -> is it one token? (so each word is only checked once)

    @staticmethod
    def _tidy(c):
        """An answer that was being written when the Pi restarted would otherwise say "writing" forever."""
        for m in c["messages"]:
            for a in m.get("answers", []):
                if a.get("writing"):
                    a["writing"], a["stopped"], a["interrupted"] = False, True, True
                if a.get("writing_b"):                         # the second answer was cut off: just keep the first
                    a.pop("b", None), a.pop("temps", None)
                    a["writing_b"] = False
        if c["messages"]:
            last = c["messages"][-1]
            if not last.get("answers") and not last.get("error") and not last.get("stopped"):
                last["error"] = "The Pi restarted before it answered. Press 🔄 Try again."

    # ------------------------------------------------------------ accounts: unlocking and locking their chats
    def load_user(self, owner, key, profile=None, first_ever=False):
        """Someone signed in: unlock their chats with their key."""
        folder = os.path.join(self.folder, owner)
        os.makedirs(folder, exist_ok=True)
        loaded = {}
        for name in os.listdir(folder):
            if name.endswith(".json"):
                try:
                    with open(os.path.join(folder, name)) as f:
                        c = unseal(key, json.load(f)["blob"], name[:-5])
                    c["owner"] = owner
                    self._tidy(c)
                    loaded[c["id"]] = c
                except Exception:
                    pass                                   # (a damaged file is skipped, not fatal)
        with self.lock:
            self.keys[owner] = key
            self.leaving.discard(owner)
            for cid, c in loaded.items():
                if cid not in self.chats:                  # (already open from another browser: keep that copy)
                    self.chats[cid] = c
            if first_ever:
                self._adopt_old_chats(owner)
        if profile is not None:
            self.set_profile(owner, profile)

    def _adopt_old_chats(self, owner):
        """Chats from before accounts existed (not locked) go to the first account made on this Pi, and get locked."""
        for name in os.listdir(self.folder):
            path = os.path.join(self.folder, name)
            if name.endswith(".json") and os.path.isfile(path):
                try:
                    with open(path) as f:
                        c = json.load(f)
                    c["owner"] = owner
                    self._tidy(c)
                    self.chats[c["id"]] = c
                    self._save(c)
                    os.remove(path)
                except (OSError, ValueError, KeyError):
                    pass

    def unload_user(self, owner):
        """They signed out: forget their key and close their chats (after any answer still being written is saved)."""
        with self.lock:
            if self.busy and self.chats.get(self.busy_chat, {}).get("owner") == owner:
                self.leaving.add(owner)                    # _work finishes it off
                return
            self._unload(owner)

    def _unload(self, owner):
        for cid in [cid for cid, c in self.chats.items() if c.get("owner") == owner]:
            del self.chats[cid]
        self.keys.pop(owner, None)
        self.notes.pop(owner, None)
        self.leaving.discard(owner)

    def delete_user(self, owner):
        with self.lock:
            self._unload(owner)
        shutil.rmtree(os.path.join(self.folder, owner), ignore_errors=True)

    def set_profile(self, owner, profile):
        """What the AI is told about you, from Settings: your name, what you use it for, and anything you wrote."""
        bits = []
        if profile.get("name"):
            bits.append("Their name is %s." % profile["name"])
        if profile.get("uses"):
            bits.append("They use this AI for: %s." % ", ".join(profile["uses"]))
        if profile.get("about"):
            bits.append("In their own words: %s" % profile["about"][:400])
        self.notes[owner] = ("\nAbout the student, from their settings (use it to help them, but don't repeat it back): "
                             + " ".join(bits)) if bits else ""

    # ------------------------------------------------------------ saving and listing chats
    def save_all(self):
        """When the program is shut down (like for an update), save what's been written so far."""
        with self.lock:
            for c in self.chats.values():
                if c["id"] == self.busy_chat:
                    self._save(c)

    def _save(self, chat):
        """Locked with its owner's key, so nobody can read it without signing in (not even with the SD card)."""
        key = self.keys.get(chat.get("owner"))
        if not key:
            return
        folder = os.path.join(self.folder, chat["owner"])
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, chat["id"] + ".json")
        with open(path + ".tmp", "w") as f:
            json.dump({"v": 1, "blob": seal(key, chat, chat["id"])}, f)
        os.replace(path + ".tmp", path)

    def _mine(self, owner, chat_id):
        c = self.chats.get(chat_id)
        return c if c and c.get("owner") == owner else None

    def _list(self, owner):
        rows = sorted((c for c in self.chats.values() if c.get("owner") == owner), key=lambda c: -c["updated"])
        return [{"id": c["id"], "title": c["title"], "updated": c["updated"], "count": len(c["messages"])} for c in rows]

    def status(self, owner, chat_id=None):
        with self.lock:
            c = self._mine(owner, chat_id)
            chat = json.loads(json.dumps({"id": c["id"], "title": c["title"], "messages": c["messages"][-60:]})) if c else None
            mine = self.busy and self.chats.get(self.busy_chat, {}).get("owner") == owner
            return {"chats": self._list(owner), "chat": chat,      # (a copy: the answer keeps changing while it's written)
                    "busy": self.busy, "busy_chat": self.busy_chat if mine else None, "someone_else": self.busy and not mine,
                    "stage": self.stage if mine else None,
                    "stage_seconds": round(time.time() - self.stage_since) if self.stage and mine else None,
                    "speed": self.bot.llm.speed, "model": self.bot.llm.model_name, "picks": self.picks(owner)}

    def _new(self, owner):
        cid = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
        c = {"id": cid, "owner": owner, "title": "New chat", "titled": False, "created": time.time(), "updated": time.time(),
             "messages": []}
        self.chats[cid] = c
        return c

    def rename(self, owner, chat_id, title):
        title = " ".join(str(title).split())[:60]
        with self.lock:
            c = self._mine(owner, chat_id)
            if c and title:
                c["title"], c["titled"] = title, True
                self._save(c)
                return True
        return False

    def delete(self, owner, chat_id):
        with self.lock:
            if not self._mine(owner, chat_id) or (self.busy and self.busy_chat == chat_id):
                return False
            del self.chats[chat_id]
        try:
            os.remove(os.path.join(self.folder, owner, os.path.basename(chat_id) + ".json"))
        except OSError:
            pass
        return True

    def send(self, owner, text, chat_id=None, compare=True, suggest=True, fix=True):
        """Returns the chat's id (a new chat if chat_id is empty), or None if it's still busy.
        compare: sometimes write a second answer to choose from. suggest: suggest follow-up questions afterwards.
        fix: fix the spelling first (not needed for a suggestion you tapped: the AI wrote it, so it's spelled right)."""
        text = " ".join(str(text).split())[:600]
        if not text:
            raise ValueError("Type a question first.")
        self.bot.hold_until = time.time() + 120               # the practice hangs up on the model right away
        if self.busy and self.stage in ("suggesting", "titling"):   # you asked something new: skip these
            self.stop_asked = True
            for _ in range(100):
                if not self.busy:
                    break
                time.sleep(0.05)
        with self.lock:
            if self.busy:
                return None
            if owner not in self.keys:
                raise ValueError("Please sign in again.")
            c = self._mine(owner, chat_id) or self._new(owner)
            msg = {"you": text, "fixed": None if fix else text, "answers": [], "error": None, "time": time.time()}
            c["messages"].append(msg)
            c["updated"] = time.time()
            if not c["titled"] and len(c["messages"]) == 1:
                c["title"] = clean_title("", text)            # a first title right away; the AI writes a better one
            self.busy, self.busy_chat, self.stop_asked = True, c["id"], False
            self._save(c)
        threading.Thread(target=self._work, args=(c, msg, False, compare, suggest), daemon=True).start()
        return c["id"]

    def stop(self, owner):
        """The ⏹️ button: stop writing the answer (only your own)."""
        with self.lock:
            if self.busy and self.chats.get(self.busy_chat, {}).get("owner") == owner:
                self.stop_asked = True

    def regenerate(self, owner, chat_id):
        """The 🔄 button: answer your last message again, a bit differently."""
        with self.lock:
            c = self._mine(owner, chat_id)
            if self.busy or not c or not c["messages"]:
                return None
            msg = c["messages"][-1]
            msg["answers"], msg["error"], msg["stopped"], msg["suggestions"] = [], None, False, []
            self.busy, self.busy_chat, self.stop_asked = True, c["id"], False
        self.bot.hold_until = time.time() + 120               # the practice hangs up on the model right away
        threading.Thread(target=self._work, args=(c, msg, True, False, True), daemon=True).start()
        return c["id"]

    def pick(self, owner, chat_id, msg_time, index, which):
        """You chose the answer you like better (which = "a" or "b"). The one you chose becomes the answer."""
        with self.lock:
            c = self._mine(owner, chat_id)
            m = next((m for m in (c["messages"] if c else []) if abs(m.get("time", 0) - float(msg_time)) < 1e-3), None)
            if not m or not 0 <= index < len(m["answers"]) or which not in ("a", "b"):
                return False
            e = m["answers"][index]
            if not e.get("b") or e.get("pick") or e.get("writing") or e.get("writing_b"):
                return False
            if which == "b":
                e["a"], e["b"] = e["b"], e["a"]
                e["temps"] = e["temps"][::-1]
            e["pick"] = which
            self._save(c)
            return True

    def picks(self, owner):
        """How often you chose the careful answer or the creative one (a tiny experiment of your own)."""
        out = {"careful": 0, "creative": 0}
        for c in self.chats.values():
            if c.get("owner") != owner:
                continue
            for m in c["messages"]:
                for e in m.get("answers", []):
                    if e.get("pick") and e.get("temps"):
                        out["careful" if e["temps"][0] <= CAREFUL else "creative"] += 1
        return out

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
            others = [c for c in self.chats.values() if c["id"] != chat["id"] and c.get("owner") == chat.get("owner")]
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

    def spelled_right(self, text):
        """Every word (3 letters or more) is one of the model's tokens, so it's a common, correctly spelled word.
        Misspelled words get chopped into pieces ("bigest" -> " big" + "est"), and then it runs the spelling fix."""
        words = {w.split("'")[0].lower() for w in re.findall(r"[A-Za-z]+(?:'[a-z]+)?", text)}
        for w in sorted(words):
            if len(w) < 3:
                continue
            if w not in self.known:
                n = self.bot.llm.count_tokens(" " + w)
                if n is None:
                    return False                               # can't tell (like with Ollama): fix it to be safe
                self.known[w] = n == 1
                if len(self.known) > 5000:
                    self.known.clear()
            if not self.known[w]:
                return False
        return True

    def _set(self, stage):
        self.stage, self.stage_since = stage, time.time()
        self.bot.hold_until = time.time() + 120               # pause the practice while we chat

    # ------------------------------------------------------------ answering
    def _work(self, chat, msg, again=False, compare=False, suggest=True):
        llm = self.bot.llm
        try:
            ok, why = llm.check()
            if not ok:
                raise RuntimeError(why)
            # 1. fix spelling and grammar (not again, if you asked for a different answer, or tapped a suggestion)
            if msg.get("fixed"):
                fixed = msg["fixed"]
            elif self.spelled_right(msg["you"]):
                fixed = msg["you"]                             # nothing misspelled: skip the fixing step (saves 5-8 s)
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
                history = [m for m in chat["messages"] if m is not msg and any(a["a"] for a in m["answers"])
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
                guess = None if found else guess_kind(q)          # would one confident answer just be a guess?
                guess_note = {"why": WHY_NOTE, "opinion": OPINION_NOTE}.get(guess, "")
                wants_next = suggest and q is questions[-1]          # follow-ups come with the last answer
                system = (ANSWER_SYSTEM + self.notes.get(chat.get("owner"), "") + math_note + guess_note
                          + (FOLLOWUPS if wants_next else ""))
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
                entry = {"q": q, "a": "", "engine": engine, "tutor": tutor, "examples": len(examples), "writing": True, "guess": guess,
                         "memories": list({cid: {"chat": cid, "title": t} for _, _, cid, t, _, _ in memories}.values())}
                with self.lock:
                    msg["answers"].append(entry)
                stopped = self._write(entry, convo, 0.85 if again else 0.4, ends_message=wants_next)
                if wants_next and entry.get("next_q"):
                    with self.lock:
                        msg["suggestions"] = entry["next_q"]        # shown the moment the answer is done
                if not stopped and not self.stop_asked and is_refusal(entry["a"]):
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
                elif not stopped and not self.stop_asked and guess and entry["a"] and not HEDGE.search(entry["a"]):
                    # it answered as if it knew for sure ("because it's unhealthy"): ask for the different possible reasons
                    with self.lock:
                        entry["a"], entry["writing"], entry["balanced"] = "", True, True
                    simple = [{"role": "system", "content": ANSWER_SYSTEM + guess_note}, {"role": "user", "content": q}]
                    stopped = self._write(entry, simple, 0.6, stage="balancing")
                if (compare and len(questions) == 1 and not found and not stopped and not self.stop_asked and entry["a"] and not entry.get("retried")
                        and not entry.get("balanced") and random.random() < COMPARE_CHANCE):
                    stopped = self._second(entry, convo)                  # sometimes: a second answer to choose from
                with self.lock:
                    chat["updated"] = time.time()
                    self._save(chat)
                if stopped:
                    break
            # 5. a title for a new chat (after its first answered message)
            answered = [m for m in chat["messages"] if m["answers"]]
            if not chat.get("titled") and answered == [msg] and questions and not self.stop_asked:
                self._set("titling")
                try:
                    title = llm.ask(TITLE_PROMPT.format(question=questions[0]), max_tokens=16, temperature=0.3,
                                    stop=lambda: self.stop_asked)      # (you can send your next question while it does this)
                except Exception:
                    title = ""                                         # keep the answer; the title is just the first words
                with self.lock:
                    if not chat.get("titled"):                         # (unless you renamed it in the meantime)
                        chat["title"], chat["titled"] = clean_title(title, fixed), True
            # 6. follow-up questions you might ask next
            if suggest and not self.stop_asked and not msg.get("suggestions"):
                last = next((a for a in reversed(msg["answers"]) if a["a"] and not a.get("refused") and not a.get("stopped")), None)
                if last:
                    self._set("suggesting")
                    try:
                        text = []
                        llm.chat_stream([{"role": "user", "content": SUGGEST_PROMPT.format(question=last["q"], answer=last["a"][:400])}],
                                        text.append, stop=lambda: self.stop_asked, max_tokens=48, temperature=0.7)
                        if not self.stop_asked:
                            with self.lock:
                                msg["suggestions"] = clean_suggestions("".join(text), last["q"])
                    except Exception:
                        pass                                       # no suggestions this time; the answer is still fine
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
                if chat.get("owner") in self.leaving:          # they signed out while it was writing: lock it all now
                    self._unload(chat["owner"])
            self.bot.hold_until = time.time() + 20             # carry on practicing soon, unless you ask again

    def _second(self, entry, convo):
        """Write a second, more creative answer, and show the two in a random order (so you can't tell which is which).
        Returns True if you pressed Stop (then only the first answer is kept)."""
        with self.lock:
            entry["b"], entry["writing_b"] = "", True
        stopped = self._write(entry, convo, CREATIVE, stage="second", field="b")
        with self.lock:
            if stopped or not entry["b"] or is_refusal(entry["b"]):
                entry.pop("b", None)
                return stopped
            entry["temps"] = [CAREFUL, CREATIVE]
            if random.random() < 0.5:
                entry["a"], entry["b"], entry["temps"] = entry["b"], entry["a"], [CREATIVE, CAREFUL]
        return False

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

    def _write(self, entry, convo, temperature, stage="writing", field="a", ends_message=False):
        """Live typing: stream the answer into entry[field]. Returns True if you pressed Stop."""
        self._set(stage)
        flag = "writing" if field == "a" else "writing_b"
        raw = [""]

        def add(piece):
            raw[0] += piece
            shown, nxt = split_next(raw[0])
            with self.lock:
                entry[field] = shown
                if nxt is not None and field == "a":
                    if "next" not in entry and ends_message:
                        self._set("suggesting")         # the answer is done: you can already send your next question
                    entry["next"] = nxt
        stopped = False
        try:
            stopped = self.bot.llm.chat_stream(convo, add, stop=lambda: self.stop_asked, max_tokens=300, temperature=temperature)
        finally:                                    # even if the model crashes halfway, it's not "writing" any more
            with self.lock:
                entry[field] = entry[field].strip()
                entry[flag] = False
                if field == "a":
                    if "next" in entry:              # the follow-ups came after the answer, so the answer is complete
                        entry["next_q"] = clean_suggestions(entry.pop("next").replace("|", "\n"), entry["q"])
                        stopped = False
                    entry["stopped"] = stopped
        return stopped
