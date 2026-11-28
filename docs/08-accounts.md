# 8. Accounts and Settings

Everyone who uses your Pi's Chat tab can have their **own account**: their own chats, their own profile picture, and their own settings, kept private from everyone else (even from whoever owns the Pi).

The **Chat** and **⚙️ Settings** tabs need you to sign in. The Math AI, Chatbot and Collapse tabs don't, because they're experiments everyone can watch.

## First: install the lock library
Accounts lock (encrypt) your data with a library called **cryptography**. On the Pi, run this once, then restart:

```bash
sudo apt install -y python3-cryptography
```

```bash
sudo systemctl restart selflearning
```

Without it, everything else still works, but signing in shows a message telling you to install it.

## Signing in: 2 layers
1. **Your email.** Type your email, and the Pi sends you a **6-digit code**. Typing the code proves the email is yours.
   - **The website never asks for your email's password.** That's on purpose: a website that asks for your email password is almost always a scam ("phishing"). Real websites send you a code instead.
2. **Your account.** You see every account on that email (one email can have several, like one for school and one for fun). Pick one and type its password, or make a new account.
3. **Two-step verification** (optional, turn it on in Settings). After your password, you also type a code.

**Log out** (top right, or in Settings), and next time you go through all of it again.

### Test mode (before email is set up)
Until the Pi has an email account to send from, it's in **test mode**: instead of emailing the code, it writes it in the Pi's log. To see it, run this on the Pi:

```bash
journalctl -u selflearning -n 5
```

That's fine for testing, because only someone with the Pi can read its log.

### Setting up email (ask a parent to help)
The Pi needs an email account to send codes *from*. With Gmail, that's an **app password**: a special 16-letter password just for the Pi, which can't be used to sign in to the account itself.

1. Use a Google account for the Pi, with **2-Step Verification** turned on (a parent's account, or a new one they make).
2. Go to **myaccount.google.com/apppasswords**, make an app password called "Pi AI", and copy the 16 letters.
3. On the Pi, open the settings file:

   ```bash
   nano ~/selflearning/config.json
   ```

   Add these lines inside the `{ }` (with your email and app password, and a comma after the line before):

   ```json
   "smtp_host": "smtp.gmail.com",
   "smtp_port": 587,
   "smtp_user": "the.pi.email@gmail.com",
   "smtp_password": "abcdefghijklmnop",
   "smtp_from": "Pi AI <the.pi.email@gmail.com>"
   ```

4. Save (Ctrl + O, Enter, Ctrl + X), then restart:

   ```bash
   sudo systemctl restart selflearning
   ```

`config.json` never goes to GitHub, and the Pi makes it readable only by you. **Never put the app password in a video or screenshot.**

## Two-step verification
In **⚙️ Settings → Two-step verification**, pick one:

| Option | How it works | What you need |
|---|---|---|
| 📱 **Authenticator app** (safest) | An app on your phone shows a new 6-digit code every 30 seconds | An app like Google Authenticator or Microsoft Authenticator (ask a parent first). You type the key the page shows into the app. |
| ✉️ **Email code** | A second code is emailed to you | Email set up on the Pi (or test mode) |
| 🔔 **Phone (ntfy)** | The code pops up on your phone | The free **ntfy** app (the same one the ISS tracker uses). Subscribe to the secret topic the page shows. |

Real text messages (SMS) would need a paid service, so the phone option uses ntfy instead.

## ⚙️ Settings
- **👤 Profile:** your name (the AI uses it) and a profile picture. You can:
  - **📷 Upload one** (the page shrinks it to 128 × 128 first),
  - **😀 Pick an emoji** and two colors, or
  - **✨ Describe one and let the AI make it**, like "a robot astronaut". A small language model can't draw pictures, but it *can* choose: it picks the emoji and colors that match your description.
- **🤖 What I use the AI for:** pick what you use it for (school homework, robotics, coding, space…) and tell it more in your own words, like "I'm building a Mars rover with an Arduino". **The AI reads this before every answer**, so it can give you examples that fit you.
- **✉️ Email:** change it (the new email gets a code first, to prove it's yours).
- **🔑 Password:** change it (you need the current one).
- **🛡️ Two-step verification:** turn it on or off.
- **🚪 Log out, or delete your account** (and all its chats, for good).

## How your data is kept private
| What | How it's kept | Can the Pi's owner read it from the files? |
|---|---|---|
| Your password | Never saved. Only a "fingerprint" made with **scrypt**, which is slow on purpose, so guessing passwords takes forever | No |
| Your email | Saved as a fingerprint too (with a secret only the Pi has) | No (only check a guess) |
| Your username | Locked with a key made from your email | Only if they already know your email |
| Your profile, settings and chats | Locked with **AES-GCM** encryption, using a key that's locked with your password | No |

The key that unlocks your chats only exists in the Pi's memory while you're signed in. That's why you need to sign in again after the Pi restarts (like after an update).

### Honest limits
- **If you forget your password, your chats can't be unlocked**, not even by the Pi's owner. That's the price of real encryption. You can make a new account on the same email.
- **Whoever controls the Pi could change this code** to copy passwords as they're typed. Encryption protects the saved files (like if someone copies the SD card), not against the person who runs the Pi.
- **The website uses plain `http`** on your home Wi-Fi, so someone on the same Wi-Fi could, with special tools, see what's sent. It's fine at home. If you ever open it from outside your home, use Tailscale (which encrypts everything).
- It's a learning project: great for understanding how real logins work, but don't use the same password you use anywhere else.

## Safety built in
- A code works for **10 minutes** and **5 tries**.
- At most **1 code every 30 seconds** and **6 an hour** for each email, and **20 every 10 minutes** for the whole Pi, so nobody can use your Pi to spam email addresses.
- **5 wrong passwords** lock the account for **5 minutes**.
- The sign-in cookie can't be read by the page's code (**HttpOnly**) and is never sent to other websites (**SameSite=Strict**).
- Each person only ever sees their own chats, even if they know another chat's ID.

**Tested:** a 28-step test through the real server (signing up, logging out and in, two accounts on one email, the second account trying to read and delete the first one's chat, wrong codes, weak passwords, the code spam limit, two-step verification by email and by authenticator app, changing the password and email, 5 wrong passwords, a restart, deleting the account, and checking the saved files for any readable personal info): **28 of 28 passed**. Plus a click-through of every screen in a browser, at computer and phone sizes.
