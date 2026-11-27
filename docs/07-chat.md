# 7. Talk to the AI (the Chat tab)

The **🗨️ Chat** tab lets you type any question to the same AI model the Chatbot tab uses (Qwen 2.5, running on your Pi). You can make spelling and grammar mistakes, and ask more than one question at once.

## Your chats
Like other chatbots, you can have lots of separate chats:
- **➕ New chat** starts a fresh one. It's saved on the Pi when you send your first message (in `data/chats/`, one file per chat), so it's still there after a restart.
- **🏷️ Titles:** after your first question, the AI writes a short title for the chat, like "Mars rover speed". If its title is too long or looks like an answer, it uses the first few words of your question instead. **✏️ Rename** changes it.
- **🔍 Search** finds chats by their title, and **🗑️ Delete** removes a chat for good.
- **Memory in a chat:** it remembers the last 3 questions and answers in the same chat, so follow-ups like "and how heavy is it?" work.
- **🔗 Memory across chats:** before answering, it looks through your *other* chats for answers that share at least 2 important words with your question (or just 1 if you say something like "before", "earlier" or "remember"). It shows the AI up to 2 of them, and shows you where they came from: "🔗 Remembered from: Mars rover speed". Click the name to open that chat.

## What happens when you press Send
1. **✏️ It fixes your message.** The AI rewrites it with the spelling and grammar fixed, and shows you what it understood: "I read this as: What is the biggest planet?"
2. **🛡️ A safety check makes sure it *only* fixed it.** Small AIs sometimes answer the question instead of fixing it ("…is Jupiter."), or change it. The check refuses the fix if:
   - the letters changed too much,
   - it added a sentence that isn't a question (that's usually an answer), or
   - it brought in lots of new words.
   Then it just uses what you typed.
3. **✂️ It splits your questions.** "What's 47 times 38? And why do robots need sensors?" gets two separate answers, up to 3 per message.
4. **🧮 The math engine works out any math exactly.** Arithmetic ("47 times 38", "1,250 divided by 4", "7 squared"), algebra ("solve 3x + 5 = 20", "x^2 - 5x + 6 = 0") and calculus ("derivative of 4x^3 + 2x", "integral of 6x^2"). The AI is told the exact answer, so it can't get the math wrong, and explains the steps.
   - **🧠 Your trained math AI has a go too,** if it's the kind of question one of its courses practices (like `47+38`, `7*8`, `3x+5=20` or `d/dx 4x^3`). You'll see its answer with ✅ or ❌, and the level it's on, so you can watch it get better.
   - **📒 For word problems** (no equation to solve), it finds up to 2 similar problems from the Chatbot's practice that were **checked twice** (Python and the AI agreed), and shows them to the AI as examples.
5. **🤔 It answers,** remembering your last two questions, so you can ask follow-ups like "and how big is it?"

While you chat, the Chatbot's practice **pauses**, so your answers come faster. It carries on by itself about 20 seconds after your last answer.

## Good to know
- **It's a small AI, so it can be wrong about facts,** especially dates, names and numbers that Python didn't check. Double-check anything important.
- **How the training helps the chat, honestly:** the chat AI (Qwen) doesn't change its brain. Training a 500-million-number model needs far more than a Pi 4 has (see [3. The chatbot](03-chatbot.md)). What *does* carry over: your math AI really is trained on the Pi, and it answers next to Qwen; and the Chatbot's checked practice problems become examples Qwen reads before answering (*in-context learning*). The math itself comes from the math engine, which is always exact.
- Each answer takes about 20–60 seconds on a Pi 4.
- Chats are saved in `data/chats/` on the Pi, which never goes to GitHub.

**Tested:** the safety check with 16 typical "fixes" (good fixes, answers pretending to be fixes, and fixes that changed the question): all 16 handled correctly. The whole chat was tested with a pretend model server: fixing, splitting into 2 questions, Python's math (47 × 38 = 1,786), refusing an answer that pretended to be a fix, and pausing the practice.
