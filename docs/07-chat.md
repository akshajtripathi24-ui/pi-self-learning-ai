# 7. Talk to the AI (the Chat tab)

The **🗨️ Chat** tab lets you type any question to the same AI model the Chatbot tab uses (Qwen 2.5, running on your Pi). You can make spelling and grammar mistakes, and ask more than one question at once.

## What happens when you press Send
1. **✏️ It fixes your message.** The AI rewrites it with the spelling and grammar fixed, and shows you what it understood: "I read this as: What is the biggest planet?"
2. **🛡️ A safety check makes sure it *only* fixed it.** Small AIs sometimes answer the question instead of fixing it ("…is Jupiter."), or change it. The check refuses the fix if:
   - the letters changed too much,
   - it added a sentence that isn't a question (that's usually an answer), or
   - it brought in lots of new words.
   Then it just uses what you typed.
3. **✂️ It splits your questions.** "What's 47 times 38? And why do robots need sensors?" gets two separate answers, up to 3 per message.
4. **🧮 Python checks the math.** If a question has math in it ("47 times 38", "1,250 divided by 4", "(12 + 8) x 3"), Python works out the exact answer, the same checker idea as the rest of this project. The AI is told the right number, so it can't get the math wrong.
5. **🤔 It answers,** remembering your last two questions, so you can ask follow-ups like "and how big is it?"

While you chat, the Chatbot's practice **pauses**, so your answers come faster. It carries on by itself about 20 seconds after your last answer.

## Good to know
- **It's a small AI, so it can be wrong about facts,** especially dates, names and numbers that Python didn't check. Double-check anything important.
- **It doesn't learn from your chat.** Its brain stays the same. See [3. The chatbot](03-chatbot.md) for why.
- Each answer takes about 20–60 seconds on a Pi 4.
- The chat is kept in memory only. It's cleared when the Pi or the program restarts, or when you press 🧹 Clear the chat.

**Tested:** the safety check with 16 typical "fixes" (good fixes, answers pretending to be fixes, and fixes that changed the question): all 16 handled correctly. The whole chat was tested with a pretend model server: fixing, splitting into 2 questions, Python's math (47 × 38 = 1,786), refusing an answer that pretended to be a fix, and pausing the practice.
