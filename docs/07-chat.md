# 7. Talk to the AI (the Chat tab)

The **🗨️ Chat** tab lets you type any question to the same AI model the Chatbot tab uses (Qwen 2.5, running on your Pi). You can make spelling and grammar mistakes, and ask more than one question at once.

## Your chats
Like other chatbots, you can have lots of separate chats:
- **➕ New chat** starts a fresh one. It's saved on the Pi when you send your first message (in `data/chats/`, one file per chat), so it's still there after a restart.
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
7. **💬 If it still says no, it always tells you why.** Its instructions ask it to give a reason and suggest a related question it *can* answer. If it just says "I can't assist with that" anyway, it's asked one more short question: why might an AI not answer this, and what could you ask instead? (While it does that, you'll see "It said no, so it's working out why…".) If even that fails, the Pi writes a reason itself. For example, for "what's the weather today?" it explains that it can't look things up on the internet.

While you chat, the Chatbot's practice **pauses**, so your answers come faster. It carries on by itself about 20 seconds after your last answer.

## If something goes wrong
- **If the Pi restarts while it's writing,** the part it already wrote is kept and marked "interrupted". If it restarted before it wrote anything, the chat says so. Either way, press 🔄 Try again.
- **If the model takes too long or crashes,** you get a clear message (like "the model took too long") and a 🔄 Try again button, and your chat still gets a title.
- **If sending fails,** what you typed is put back in the box, so you don't have to type it again.

## Good to know
- **It's a small AI, so it can be wrong about facts,** especially dates, names and numbers that Python didn't check. Double-check anything important.
- **How the training helps the chat, honestly:** the chat AI (Qwen) doesn't change its brain. Training a 500-million-number model needs far more than a Pi 4 has (see [3. The chatbot](03-chatbot.md)). What *does* carry over: your math AI really is trained on the Pi, and it answers next to Qwen; and the Chatbot's checked practice problems become examples Qwen reads before answering (*in-context learning*). The math itself comes from the math engine, which is always exact.
- Each answer takes about 20–60 seconds on a Pi 4.
- Chats are saved in `data/chats/` on the Pi, which never goes to GitHub.

**Tested (again, after the bug hunt):** with a pretend model that refuses on purpose (it said no, then answered on the retry), a model that refuses every time (marked), a restart halfway through an answer (the half answer was kept), pressing Stop while it was still fixing the spelling, two questions in one message (the second one saw the first), sending an empty message, and 30 kinds of math with decimals, percentages, square roots and negative numbers.

**Tested before:** the safety check with 16 typical "fixes" (good fixes, answers pretending to be fixes, and fixes that changed the question): all 16 handled correctly. The whole chat was tested with a pretend model server: fixing, splitting into 2 questions, Python's math (47 × 38 = 1,786), refusing an answer that pretended to be a fix, and pausing the practice.
