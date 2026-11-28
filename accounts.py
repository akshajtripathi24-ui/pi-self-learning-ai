"""Part 5: accounts, so every person has their own chats and settings, kept private.

Signing in has 2 layers (plus an optional 3rd):
  1. YOUR EMAIL: type it, and the Pi emails you a 6-digit code. That proves the email is yours,
     without the Pi ever seeing your email password (a website should never ask for that).
  2. YOUR ACCOUNT: you see every account on that email, pick one, and type its password.
  3. TWO-STEP VERIFICATION (optional, in Settings): a code from an authenticator app, your email, or your phone (ntfy).
Log out, and you go through it all again.

Keeping things private:
  - Passwords are never saved. Only a "fingerprint" of each one is, made with scrypt, which is slow on purpose,
    so guessing passwords takes forever even for someone who copies the files.
  - Everything personal (your profile, what you use the AI for, your chats) is locked with AES-GCM encryption.
    The key is itself locked with your password, so it only exists in memory while you're signed in.
  - Emails and usernames aren't saved as text either: emails become a fingerprint, and usernames are locked with a key
    made from the email, so you can only list the accounts on an email you've proved is yours.
Honest limits: whoever controls the Pi could change this code to copy passwords as they're typed, and the website uses
plain http on your home Wi-Fi (see docs/08-accounts.md). This keeps the saved files private, which is the main risk.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import ssl
import struct
import threading
import time
import urllib.request
from email.message import EmailMessage

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:                                    # sudo apt install -y python3-cryptography
    AESGCM = None

SCRYPT = dict(n=2 ** 14, r=8, p=1, maxmem=64 * 1024 * 1024)   # about 0.1 s on a Pi 4: fine for you, slow for guessers
CODE_MINUTES = 10                  # a code works for 10 minutes...
CODE_TRIES = 5                     # ...and for 5 tries
LOCK_AFTER, LOCK_MINUTES = 5, 5    # 5 wrong passwords in a row lock the account for 5 minutes
SESSION_DAYS = 7
USE_OPTIONS = ["School homework", "Math practice", "Robotics & building", "Coding", "Space & science",
               "Making videos", "Writing & ideas", "Just for fun"]
COMMON_PASSWORDS = {"password", "password1", "12345678", "123456789", "1234567890", "qwertyuiop", "qwerty123",
                    "11111111", "abcdefgh", "iloveyou", "letmein1", "welcome1", "football", "baseball", "sunshine"}


class AuthError(ValueError):
    """Something the person did (a wrong code, a taken username...). The message is shown on the page."""


def b64(b):
    return base64.b64encode(b).decode()


def unb64(s):
    return base64.b64decode(s)


def kdf(secret, salt, n=32):
    """Turns a password (or email) into a key. scrypt is slow and uses lots of memory on purpose."""
    return hashlib.scrypt(secret.encode() if isinstance(secret, str) else secret, salt=salt, dklen=n, **SCRYPT)


def seal(key, obj, aad=""):
    """Lock: AES-GCM encryption. It also detects tampering, and aad ties it to one account or chat,
    so a locked box can't be swapped into someone else's account."""
    nonce = os.urandom(12)
    return b64(nonce + AESGCM(key).encrypt(nonce, json.dumps(obj).encode(), aad.encode()))


def unseal(key, blob, aad=""):
    raw = unb64(blob)
    return json.loads(AESGCM(key).decrypt(raw[:12], raw[12:], aad.encode()))


def norm_email(email):
    email = str(email or "").strip().lower()
    if len(email) > 120 or not re.fullmatch(r"[^@\s]{1,64}@[^@\s]+\.[a-z]{2,24}", email):
        raise AuthError("That doesn't look like an email address.")
    return email


def mask_email(email):
    """akshaj@example.com -> a*****@example.com (for showing on the page and in logs)."""
    name, _, domain = email.partition("@")
    return name[:1] + "*" * max(1, len(name) - 1) + "@" + domain


def check_password(password, username=""):
    password = str(password or "")
    if len(password) < 8:
        raise AuthError("Your password needs at least 8 characters.")
    if len(password) > 128:
        raise AuthError("That password is too long (128 characters at most).")
    if password.lower() in COMMON_PASSWORDS or (username and password.lower() == username.lower()):
        raise AuthError("That password is too easy to guess. Try a few random words together.")
    return password


def check_username(username):
    username = str(username or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,20}", username):
        raise AuthError("Usernames are 3 to 20 letters, numbers, dots, dashes or underscores (no spaces).")
    return username


# ---------------------------------------------------------------- authenticator apps (TOTP, the 6 digits that change every 30 s)
def totp(secret_b32, at=None, step=0):
    """The 6-digit code an authenticator app shows right now (RFC 6238, the standard every app uses)."""
    key = base64.b32decode(secret_b32)
    counter = int((at or time.time()) // 30) + step
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = mac[-1] & 15
    return "%06d" % ((struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % 1000000)


def totp_ok(secret_b32, code):
    code = re.sub(r"\D", "", str(code or ""))
    return any(hmac.compare_digest(totp(secret_b32, step=s), code) for s in (-1, 0, 1))   # (allows a clock off by 30 s)


# ---------------------------------------------------------------- sending codes
class Sender:
    """Sends codes by email (if the Pi has an email account set up, see docs/08-accounts.md) or to a phone with ntfy.
    Without email set up it's in TEST MODE: the code goes in the Pi's log, which only someone with the Pi can read."""

    def __init__(self, cfg):
        self.cfg = cfg

    def email_ready(self):
        return all(self.cfg.get(k) for k in ("smtp_host", "smtp_user", "smtp_password"))

    def email(self, to, code, why):
        if not self.email_ready():
            print("[TEST MODE] %s code for %s: %s  (set up email sending: docs/08-accounts.md)" % (why, mask_email(to), code),
                  flush=True)
            return "log"
        msg = EmailMessage()
        msg["Subject"] = "Your Pi AI code: %s" % code
        msg["From"] = self.cfg.get("smtp_from") or self.cfg["smtp_user"]
        msg["To"] = to
        msg.set_content("Your code to %s is:\n\n    %s\n\nIt works for %d minutes. If you didn't ask for it, you can ignore "
                        "this email.\n\nPi Self-Learning AI" % (why, code, CODE_MINUTES))
        try:
            with smtplib.SMTP(self.cfg["smtp_host"], int(self.cfg.get("smtp_port", 587)), timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(self.cfg["smtp_user"], self.cfg["smtp_password"])
                s.send_message(msg)
        except Exception as e:
            print("email error:", e, flush=True)
            raise AuthError("The Pi couldn't send the email. Check its email settings (docs/08-accounts.md).")
        return "email"

    def phone(self, topic, code, why):
        url = self.cfg.get("ntfy_server", "https://ntfy.sh").rstrip("/") + "/" + topic
        req = urllib.request.Request(url, data=("Your code to %s: %s" % (why, code)).encode(),
                                     headers={"Title": "Pi AI code", "Tags": "lock"})
        try:
            urllib.request.urlopen(req, timeout=15).read()
        except Exception as e:
            print("ntfy error:", e, flush=True)
            raise AuthError("The Pi couldn't send the code to your phone (is the Pi online?).")
        return "phone"


# ---------------------------------------------------------------- the accounts
class Accounts:
    def __init__(self, folder, cfg, on_login=None, on_logout=None, on_delete=None):
        if AESGCM is None:
            raise RuntimeError("Accounts need the cryptography package. On the Pi: sudo apt install -y python3-cryptography")
        os.makedirs(folder, exist_ok=True)
        self.file = os.path.join(folder, "accounts.json")
        pepper_file = os.path.join(folder, "pepper.key")      # a random secret, made once, that never leaves the Pi
        if not os.path.exists(pepper_file):
            fd = os.open(pepper_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(os.urandom(32))
        with open(pepper_file, "rb") as f:
            self.pepper = f.read()
        try:
            with open(self.file) as f:
                self.accounts = json.load(f)
        except (OSError, ValueError):
            self.accounts = []
        self.lock = threading.Lock()
        self.pending = {}           # codes waiting to be typed in: token -> what it's for
        self.sessions = {}          # signed-in browsers: session id -> who (and their key, only in memory)
        self.sent = {}              # when codes were sent to each email (to stop spamming)
        self.send = Sender(cfg)
        self.on_login, self.on_logout, self.on_delete = on_login, on_logout, on_delete

    def _save(self):
        tmp = self.file + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self.accounts, f)
        os.replace(tmp, self.file)

    def _email_keys(self, email):
        """Email -> (its fingerprint, the key that locks its usernames). Both need the Pi's secret pepper."""
        out = kdf(email, self.pepper + b"email", 64)
        return out[:32].hex(), out[32:]

    def _code_hash(self, code):
        return hmac.new(self.pepper, code.encode(), hashlib.sha256).hexdigest()

    def _new_code(self):
        return "%06d" % secrets.randbelow(10 ** 6)

    def _tidy(self):
        """Forget codes that ran out."""
        now = time.time()
        for k in [k for k, v in self.pending.items() if v["expires"] < now]:
            self.pending.pop(k, None)

    def _expire(self):
        """Sign out sessions that ran out. Returns the accounts that are now fully signed out."""
        now = time.time()
        gone = {self.sessions.pop(k)["aid"] for k in [k for k, v in self.sessions.items() if v["expires"] < now]}
        return [aid for aid in gone if not any(x["aid"] == aid for x in self.sessions.values())]

    def _limit(self, eid):
        """At most 1 code every 30 seconds, and 6 an hour, for each email, and 20 every 10 minutes for the whole Pi
        (so nobody can use your Pi to spam lots of email addresses)."""
        now = time.time()
        everyone = [t for t in self.sent.get("*", []) if now - t < 600]
        if len(everyone) >= 20:
            raise AuthError("The Pi has sent a lot of codes just now. Please try again in a few minutes.")
        self.sent["*"] = everyone + [now]
        times = [t for t in self.sent.get(eid, []) if now - t < 3600]
        if times and now - times[-1] < 30:
            raise AuthError("Please wait %d seconds before asking for another code." % (30 - (now - times[-1])))
        if len(times) >= 6:
            raise AuthError("Too many codes for this email. Try again in an hour.")
        self.sent[eid] = times + [now]

    def _account(self, aid):
        a = next((a for a in self.accounts if a["id"] == aid), None)
        if not a:
            raise AuthError("That account doesn't exist any more.")
        return a

    def _check_code(self, p, code):
        if p["tries"] >= CODE_TRIES:
            raise AuthError("Too many wrong codes. Ask for a new one.")
        p["tries"] += 1
        if not hmac.compare_digest(p["code"], self._code_hash(re.sub(r"\D", "", str(code or "")))):
            left = CODE_TRIES - p["tries"]
            raise AuthError("That code isn't right. %d tr%s left." % (left, "y" if left == 1 else "ies") if left else
                            "That code isn't right. Ask for a new one.")

    def _pending(self, token, purpose):
        p = self.pending.get(str(token or ""))
        if not p or p["purpose"] != purpose or p["expires"] < time.time():
            raise AuthError("That took too long. Please start again.")
        return p

    # ------------------------------------------------------------ layer 1: prove the email is yours
    def start_email(self, email):
        email = norm_email(email)
        eid, ekey = self._email_keys(email)
        code = self._new_code()
        with self.lock:
            self._tidy()
            self._limit(eid)
            token = secrets.token_urlsafe(24)
            self.pending[token] = {"purpose": "email", "email": email, "eid": eid, "ekey": ekey, "code": self._code_hash(code),
                                   "tries": 0, "verified": False, "expires": time.time() + CODE_MINUTES * 60}
        how = self.send.email(email, code, "sign in")
        return {"token": token, "sent_to": mask_email(email), "how": how}

    def verify_email(self, token, code):
        with self.lock:
            p = self._pending(token, "email")
            if not p["verified"]:
                self._check_code(p, code)
                p["verified"], p["expires"] = True, time.time() + 15 * 60      # 15 minutes to pick an account
            return {"accounts": self._list(p)}

    def _list(self, p):
        out = []
        for a in self.accounts:
            if a["eid"] == p["eid"]:
                out.append({"id": a["id"], "username": unseal(p["ekey"], a["name"], a["id"])["u"]})
        return sorted(out, key=lambda x: x["username"].lower())

    # ------------------------------------------------------------ layer 2: the account and its password
    def signup(self, token, username, password):
        username = check_username(username)
        password = check_password(password, username)
        with self.lock:
            p = self._pending(token, "email")
            if not p["verified"]:
                raise AuthError("Check your email code first.")
            if any(x["username"].lower() == username.lower() for x in self._list(p)):
                raise AuthError("You already have an account called %s on this email." % username)
            first_ever = not self.accounts
        aid = secrets.token_hex(8)
        salt = os.urandom(16)
        derived = kdf(password, salt, 64)                    # half to check the password, half to unlock the key
        data_key = os.urandom(32)                            # locks everything personal in this account
        profile = {"name": username, "email": p["email"], "avatar": None, "uses": [], "about": "", "twofa": {"method": "off"}}
        acct = {"id": aid, "eid": p["eid"], "name": seal(p["ekey"], {"u": username}, aid), "salt": b64(salt),
                "check": b64(derived[:32]), "key": seal(derived[32:], {"k": b64(data_key)}, aid),
                "profile": seal(data_key, profile, aid), "created": time.time(), "fails": 0, "locked_until": 0}
        with self.lock:
            self.accounts.append(acct)
            self._save()
            self.pending.pop(token, None)
        return self._sign_in(aid, data_key, username, p["email"], first_ever=first_ever)

    def login(self, token, aid, password):
        with self.lock:
            p = self._pending(token, "email")
            if not p["verified"]:
                raise AuthError("Check your email code first.")
            a = self._account(aid)
            if a["eid"] != p["eid"]:
                raise AuthError("That account isn't on this email.")
            if a["locked_until"] > time.time():
                raise AuthError("Too many wrong passwords. Try again in %d minutes." % (1 + (a["locked_until"] - time.time()) // 60))
        derived = kdf(str(password or ""), unb64(a["salt"]), 64)
        with self.lock:
            if not hmac.compare_digest(derived[:32], unb64(a["check"])):
                a["fails"] += 1
                if a["fails"] >= LOCK_AFTER:
                    a["fails"], a["locked_until"] = 0, time.time() + LOCK_MINUTES * 60
                    self._save()
                    raise AuthError("Too many wrong passwords. The account is locked for %d minutes." % LOCK_MINUTES)
                self._save()
                raise AuthError("Wrong password. %d tries left before the account locks for a few minutes." % (LOCK_AFTER - a["fails"]))
            if a["fails"]:
                a["fails"] = 0
                self._save()
            data_key = unb64(unseal(derived[32:], a["key"], aid)["k"])
            profile = unseal(data_key, a["profile"], aid)
            username = unseal(p["ekey"], a["name"], aid)["u"]
            self.pending.pop(token, None)
        method = profile["twofa"]["method"]
        if method == "off":
            return self._sign_in(aid, data_key, username, p["email"])
        # layer 3: two-step verification
        code = self._new_code()
        token2 = secrets.token_urlsafe(24)
        with self.lock:
            self.pending[token2] = {"purpose": "2fa", "aid": aid, "key": data_key, "username": username, "email": p["email"],
                                    "method": method, "code": self._code_hash(code), "tries": 0,
                                    "expires": time.time() + CODE_MINUTES * 60}
        if method == "email":
            how = self.send.email(p["email"], code, "finish signing in")
        elif method == "phone":
            how = self.send.phone(profile["twofa"]["topic"], code, "finish signing in")
        else:
            how = "app"
        return {"need_2fa": method, "token": token2, "how": how}

    def verify_2fa(self, token, code):
        with self.lock:
            p = self._pending(token, "2fa")
            if p["method"] == "app":
                if p["tries"] >= CODE_TRIES:
                    raise AuthError("Too many wrong codes. Please start again.")
                p["tries"] += 1
                profile = unseal(p["key"], self._account(p["aid"])["profile"], p["aid"])
                if not totp_ok(profile["twofa"]["secret"], code):
                    raise AuthError("That code isn't right. Use the newest code in your authenticator app.")
            else:
                self._check_code(p, code)
            self.pending.pop(token, None)
        return self._sign_in(p["aid"], p["key"], p["username"], p["email"])

    def _sign_in(self, aid, data_key, username, email, first_ever=False):
        sid = secrets.token_urlsafe(32)
        with self.lock:
            self.sessions[sid] = {"aid": aid, "key": data_key, "username": username, "email": email,
                                  "expires": time.time() + SESSION_DAYS * 86400}
        if self.on_login:
            self.on_login(aid, data_key, self.profile(self.sessions[sid]), first_ever)
        return {"session": sid, "username": username}

    def session(self, sid):
        with self.lock:
            s = self.sessions.get(str(sid or ""))
            ended = self._expire() if s and s["expires"] <= time.time() else []
        for aid in ended:                                   # ran out: lock their chats again, like logging out
            if self.on_logout:
                self.on_logout(aid)
        return s if s and s["expires"] > time.time() else None

    def logout(self, sid):
        with self.lock:
            s = self.sessions.pop(str(sid or ""), None)
            still_in = s and any(x["aid"] == s["aid"] for x in self.sessions.values())
        if s and not still_in and self.on_logout:
            self.on_logout(s["aid"])                      # forget its key, so its chats are locked again

    # ------------------------------------------------------------ settings (you must be signed in)
    def profile(self, s):
        with self.lock:
            return unseal(s["key"], self._account(s["aid"])["profile"], s["aid"])

    def _put_profile(self, s, profile):
        a = self._account(s["aid"])
        a["profile"] = seal(s["key"], profile, s["aid"])
        self._save()

    def me(self, s):
        p = self.profile(s)
        twofa = p["twofa"]["method"]
        return {"username": s["username"], "email": p["email"], "name": p["name"], "avatar": p["avatar"], "uses": p["uses"],
                "about": p["about"], "twofa": twofa, "use_options": USE_OPTIONS, "email_ready": self.send.email_ready()}

    def update(self, s, changes):
        p = self.profile(s)
        if "name" in changes:
            name = " ".join(str(changes["name"]).split())[:40]
            if not name:
                raise AuthError("Your name can't be empty.")
            p["name"] = name
        if "uses" in changes:
            p["uses"] = [u for u in USE_OPTIONS if u in (changes["uses"] or [])]
        if "about" in changes:
            p["about"] = str(changes["about"] or "").strip()[:400]
        if "avatar" in changes:
            p["avatar"] = check_avatar(changes["avatar"])
        with self.lock:
            self._put_profile(s, p)
        return self.me(s)

    def change_password(self, s, old, new):
        new = check_password(new, s["username"])
        a = self._account(s["aid"])
        if not hmac.compare_digest(kdf(str(old or ""), unb64(a["salt"]), 64)[:32], unb64(a["check"])):
            raise AuthError("Your current password isn't right.")
        salt = os.urandom(16)
        derived = kdf(new, salt, 64)
        with self.lock:                                   # the same key, locked with the new password: nothing to re-lock
            a.update(salt=b64(salt), check=b64(derived[:32]), key=seal(derived[32:], {"k": b64(s["key"])}, s["aid"]))
            self._save()
        return {"ok": True}

    def start_email_change(self, s, new_email):
        email = norm_email(new_email)
        if email == s["email"]:
            raise AuthError("That's already your email.")
        eid, ekey = self._email_keys(email)
        code = self._new_code()
        with self.lock:
            self._tidy()
            self._limit(eid)
            token = secrets.token_urlsafe(24)
            self.pending[token] = {"purpose": "change", "aid": s["aid"], "email": email, "eid": eid, "ekey": ekey,
                                   "code": self._code_hash(code), "tries": 0, "expires": time.time() + CODE_MINUTES * 60}
        how = self.send.email(email, code, "change your email")
        return {"token": token, "sent_to": mask_email(email), "how": how}

    def finish_email_change(self, s, token, code):
        with self.lock:
            p = self._pending(token, "change")
            if p["aid"] != s["aid"]:
                raise AuthError("That code is for a different account.")
            self._check_code(p, code)
            if any(x["username"].lower() == s["username"].lower() for x in self._list(p)):
                raise AuthError("There's already an account called %s on that email." % s["username"])
            a = self._account(s["aid"])
            profile = unseal(s["key"], a["profile"], s["aid"])
            profile["email"] = p["email"]
            a.update(eid=p["eid"], name=seal(p["ekey"], {"u": s["username"]}, s["aid"]),
                     profile=seal(s["key"], profile, s["aid"]))
            self._save()
            for x in self.sessions.values():
                if x["aid"] == s["aid"]:
                    x["email"] = p["email"]
            self.pending.pop(token, None)
        return self.me(s)

    # ------------------------------------------------------------ two-step verification
    def start_2fa(self, s, method):
        """Turning it on: first we send (or show) a code, and you type it back, so we know it reaches you."""
        if method not in ("app", "email", "phone"):
            raise AuthError("Pick the authenticator app, email or phone.")
        code = self._new_code()
        setup = {"purpose": "setup", "aid": s["aid"], "method": method, "code": self._code_hash(code), "tries": 0,
                 "expires": time.time() + CODE_MINUTES * 60}
        out = {"method": method}
        if method == "app":
            setup["secret"] = base64.b32encode(os.urandom(20)).decode()
            out.update(secret=setup["secret"], link="otpauth://totp/Pi%%20AI:%s?secret=%s&issuer=Pi%%20AI" % (s["username"], setup["secret"]))
        elif method == "email":
            out["how"] = self.send.email(s["email"], code, "turn on two-step verification")
        else:
            setup["topic"] = "piai-" + secrets.token_hex(8)       # random, so nobody can guess it
            out["topic"] = setup["topic"]
        token = secrets.token_urlsafe(24)
        with self.lock:
            self._tidy()
            self.pending[token] = setup
        out["token"] = token
        return out

    def send_phone_test(self, s, token):
        """For the phone: once you've subscribed to the topic in the ntfy app, send the code there."""
        with self.lock:
            p = self._pending(token, "setup")
            if p["aid"] != s["aid"] or p["method"] != "phone":
                raise AuthError("Please start again.")
            code = self._new_code()
            p["code"], p["tries"] = self._code_hash(code), 0
        return {"how": self.send.phone(p["topic"], code, "turn on two-step verification")}

    def finish_2fa(self, s, token, code):
        with self.lock:
            p = self._pending(token, "setup")
            if p["aid"] != s["aid"]:
                raise AuthError("Please start again.")
            if p["method"] == "app":
                p["tries"] += 1
                if p["tries"] > CODE_TRIES or not totp_ok(p["secret"], code):
                    raise AuthError("That code isn't right. Type the 6 digits your app shows for Pi AI.")
                twofa = {"method": "app", "secret": p["secret"]}
            else:
                self._check_code(p, code)
                twofa = {"method": p["method"], "topic": p["topic"]} if p["method"] == "phone" else {"method": "email"}
            profile = unseal(s["key"], self._account(s["aid"])["profile"], s["aid"])
            profile["twofa"] = twofa
            self._put_profile(s, profile)
            self.pending.pop(token, None)
        return self.me(s)

    def turn_off_2fa(self, s, password):
        self._password_ok(s, password)
        p = self.profile(s)
        p["twofa"] = {"method": "off"}
        with self.lock:
            self._put_profile(s, p)
        return self.me(s)

    def _password_ok(self, s, password):
        a = self._account(s["aid"])
        if not hmac.compare_digest(kdf(str(password or ""), unb64(a["salt"]), 64)[:32], unb64(a["check"])):
            raise AuthError("That password isn't right.")

    def delete(self, s, password):
        self._password_ok(s, password)
        aid = s["aid"]
        with self.lock:
            self.accounts = [a for a in self.accounts if a["id"] != aid]
            self._save()
            for sid in [k for k, v in self.sessions.items() if v["aid"] == aid]:
                self.sessions.pop(sid)
        if self.on_delete:
            self.on_delete(aid)
        return {"ok": True}


def check_avatar(av):
    """A profile picture: an emoji on two colors, or a small picture you uploaded (shrunk by the page first)."""
    if not av:
        return None
    if av.get("kind") == "emoji":
        emoji = str(av.get("emoji", ""))[:8]
        colors = [str(av.get(k, "")) for k in ("c1", "c2")]
        if not emoji.strip() or not all(re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in colors):
            raise AuthError("That profile picture didn't work. Try another one.")
        return {"kind": "emoji", "emoji": emoji, "c1": colors[0], "c2": colors[1]}
    if av.get("kind") == "image":
        data = str(av.get("data", ""))
        if len(data) > 120000 or not re.fullmatch(r"data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+", data):
            raise AuthError("That picture is too big or isn't a PNG or JPG.")
        return {"kind": "image", "data": data}
    raise AuthError("That profile picture didn't work.")
