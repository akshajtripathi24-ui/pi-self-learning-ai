# 7. Talk to the AI (the Chat tab)

The **🗨️ Chat** tab lets you type any question to the same AI model the Chatbot tab uses (Qwen 2.5, running on your Pi). You can make spelling and grammar mistakes, and ask more than one question at once.

## Your chats
**You need to sign in to chat** (see [8. Accounts and Settings](08-accounts.md)). Each account only sees its own chats, and they're saved locked (encrypted), so nobody can read them from the Pi's files.

Like other chatbots, you can have lots of separate chats:
- **➕ New chat** starts a fresh one. It's saved on the Pi when you send your first message (in `data/chats/`, one locked file per chat), so it's still there after a restart.
- **🏷️ Titles:** after your first question, the AI writes a short title for the chat, like "Mars rover speed". If its title is too long or looks like an answer, it uses the first few words of your question instead. **✏️ Rename** changes it.
- **🔍 Search** finds chats by their title, and **🗑️ Delete** removes a chat for good.
- **Memory in a chat:** it remembers the last 3 questions and answers in the same chat, so follow-ups like "and how heavy is it?" work.
- **🔗 Memory across chats:** before answering, it looks through your *other* chats for answers that share at least 2 important words with your question (or just 1 if you say something like "before", "earlier" or "remember"). It shows the AI up to 2 of them, and shows you where they came from: "🔗 Remembered from: Mars rover speed". Click the name to open that chat.

## Buttons
- **✍️ Live typing:** the answer appears word by word as the AI writes it, like other chatbots, so you don't wait 20–60 seconds for the whole thing.
- **⏹️ Stop:** while it's writing, the Send button turns into Stop. It keeps what's written so far, and the AI really stops (the Pi hangs up on it).
- **🔄 Try again:** under the last answer. It answers your last message again, a bit more creatively (a higher *temperature*: 0.85 instead of 0.4), so you get a different answer.
- **🔊 Read aloud:** under every answer. It uses your browser's own voice, so nothing is sent anywhere. Math is read the way you'd say it ("x squared", "the derivative of"). Press it again to stop.
- **📝 Show the steps:** for algebra and calculus, the math engine shows every step, like "Subtract 5 from both sides: 3x = 15", then "Divide both sides by 3: x = 5". The AI is given the steps too, so its explanation matches.
- **💡 Follow-up suggestions:** after each answer, it suggests 2 questions you might ask next, like "How do Mars rovers get their power?". Tap one to ask it. The AI writes them at the end of the same reply as the answer (they're hidden from the answer itself), so they pop up the moment the answer is done, with no extra waiting. Turn them off with the switch under your chats.
- **🆚 Two answers to pick from:** about 1 in 4 times, you get two answers side by side and pick the one you like better with 👍. One is written *carefully* (temperature 0.4) and one *creatively* (temperature 0.95), in a random order so you can't tell which is which. The one you pick becomes the answer (the other one is tucked away under "Show the other one"), and the sidebar counts which kind you pick more often: your own little experiment! It takes about twice as long on a Pi, so you can turn it off with the switch under your chats.
- **⬇️ Export:** downloads the whole chat as a text file (Markdown, `.md`), including the math engine's steps.

## What happens when you press Send
1. **✏️ It fixes your message.** The AI rewrites it with the spelling and grammar fixed, and shows you what it understood: "I read this as: What is the biggest planet?"
2. **🛡️ A safety check makes sure it *only* fixed it.** Small AIs sometimes answer the question instead of fixing it ("…is Jupiter."), or change it. The check refuses the fix if:
   - the letters changed too much,
   - it changed any number or math symbol (like 2.5 into 25, or + into −), which would make the math engine solve the wrong problem,
   - it added a sentence that isn't a question (that's usually an answer), or
   - it brought in lots of new words.
   Then it just uses what you typed.
3. **✂️ It splits your questions.** "What's 47 times 38? And why do robots need sensors?" gets two separate answers, up to 3 per message. Questions joined with "and" work too, even without a question mark: "whats 2.5 + 1.75 and how do i stop a stuck program". But "how fast and how far can a rover go" stays one question (both halves need at least 3 words), and so does "what's the difference between…".
4. **🧮 The math engine works out any math exactly.** Arithmetic ("47 times 38", "1,250 divided by 4", "7 squared", "-5 + 3"), **decimals** ("2.5 + 1.75", "10 divided by 4" is 2.5), **percentages** ("15% of 80"), **square roots** ("square root of 6.25"), algebra ("solve 3x + 5 = 20", "0.5x + 1.2 = 3", "x^2 - 5x + 6 = 0") and calculus ("derivative of 4x^3 + 2x", "integral of 6x^2"). The AI is told the exact answer, so it can't get the math wrong, and explains the steps.
   - Answers that end are shown as decimals (10 ÷ 4 = 2.5). Answers that never end are shown as a fraction *and* a rounded decimal: 10 ÷ 3 = 10/3 (about 3.33333). Dividing by 0 says you can't.
   - **🧠 Your trained math AI has a go too,** if it's the kind of question one of its courses practices (like `47+38`, `7*8`, `3x+5=20`, `d/dx 4x^3`, `2.5+1.7`, `x^2-5x+6=0` or `integral of 6x^2`). You'll see its answer with ✅ or ❌, and the level it's on, so you can watch it get better.
   - **📒 For word problems** (no equation to solve), it finds up to 2 similar problems from the Chatbot's practice that were **checked twice** (Python and the AI agreed), and shows them to the AI as examples.
5. **🤔 It answers,** remembering your last 3 questions and answers, so you can ask follow-ups like "and how big is it?"
6. **🙅 If it wrongly says "I can't assist with that",** it tries once more with simpler instructions. Small AIs sometimes refuse normal questions, often because the instructions were long and confusing. Refusals are never used as memories or as earlier messages, so one refusal can't cause more.
7. **⚖️ It doesn't guess reasons as if it knew them.** "Why does Akshaj not like tacos?" has no answer the AI could know, so it shouldn't make one up ("because they're unhealthy"). For questions about why someone feels or does something ("why does my teacher…", "why do people like…") it's told to say it can't know for sure and give 3 or 4 possible reasons. For opinion questions ("which is better", "should I", "best"), it gives what it depends on, not one opinion as a fact. If its answer still sounds like it knows for sure (no "might", "could", "some people", "depends"…), it's asked once more for the different possibilities, and you'll see "⚖️ It first gave one reason as if it knew for sure". Science questions like "why is the sky blue" still get a normal answer.
8. **💬 If it still says no, it always tells you why.** Its instructions ask it to give a reason and suggest a related question it *can* answer. If it just says "I can't assist with that" anyway, it's asked one more short question: why might an AI not answer this, and what could you ask instead? (While it does that, you'll see "It said no, so it's working out why…".) If even that fails, the Pi writes a reason itself. For example, for "what's the weather today?" it explains that it can't look things up on the internet.

While you chat, the Chatbot's practice **pauses**, so your answers come faster. It carries on by itself about 20 seconds after your last answer.

## If something goes wrong
- **If the Pi restarts while it's writing,** the part it already wrote is kept and marked "interrupted". If it restarted before it wrote anything, the chat says so. Either way, press 🔄 Try again.
- **If the model takes too long or crashes,** you get a clear message (like "the model took too long") and a 🔄 Try again button, and your chat still gets a title.
- **If sending fails,** what you typed is put back in the box, so you don't have to type it again.

## ⚡ Making it fast on a Pi
A Pi 4 writes about 5 words a second, so every step counts. What it does to save time:
- **It cuts in line.** When you press Send, the Chatbot practice hangs up on the AI model straight away (the question it was on is dropped and doesn't count), instead of making you wait up to a minute for it to finish.
- **It skips the spelling fix when nothing's misspelled.** It asks the model's tokenizer how it splits each word: common words are one piece (" planet"), but misspelled ones get chopped up (" big" + "est"). If every word is one piece, it skips the fixing step, which saves a whole AI step.
- **Tapped suggestions skip the fix too,** because the AI wrote them, so they're already spelled right.
- **Suggestions come with the answer,** instead of a separate step afterwards.
- **You never wait for extras.** While it names a new chat, you can already send your next question (it then just keeps the first words of your question as the title).
- **The math AI's training rests while the chat answers,** so the chat gets the whole Pi.
- **The page checks for new words 3 times a second** while it's writing, so the live typing is smooth (and only every 1.5 seconds when it's idle).

How fast the words themselves come out depends on the Pi's processor. A Pi 5 is about 2 to 3 times faster.

## Good to know
- **It's a small AI, so it can be wrong about facts,** especially dates, names and numbers that Python didn't check. Double-check anything important.
- **How the training helps the chat, honestly:** the chat AI (Qwen) doesn't change its brain. Training a 500-million-number model needs far more than a Pi 4 has (see [3. The chatbot](03-chatbot.md)). What *does* carry over: your math AI really is trained on the Pi, and it answers next to Qwen; and the Chatbot's checked practice problems become examples Qwen reads before answering (*in-context learning*). The math itself comes from the math engine, which is always exact.
- Each answer takes about 20–60 seconds on a Pi 4.
- Chats are saved in `data/chats/` on the Pi, which never goes to GitHub.

**Tested (again, after the bug hunt):** with a pretend model that refuses on purpose (it said no, then answered on the retry), a model that refuses every time (marked), a restart halfway through an answer (the half answer was kept), pressing Stop while it was still fixing the spelling, two questions in one message (the second one saw the first), sending an empty message, and 30 kinds of math with decimals, percentages, square roots and negative numbers.

**Tested before:** the safety check with 16 typical "fixes" (good fixes, answers pretending to be fixes, and fixes that changed the question): all 16 handled correctly. The whole chat was tested with a pretend model server: fixing, splitting into 2 questions, Python's math (47 × 38 = 1,786), refusing an answer that pretended to be a fix, and pausing the practice.
