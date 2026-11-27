# 6. Build log: problems we hit

Every problem that came up while building Pi Self-Learning AI, what caused it, and how it was fixed.

## Part 1: Building it

### 1. The gradient check failed everywhere
**Problem:** Writing an AI's learning code by hand is easy to get wrong, so we tested it with a *gradient check*. We nudged each of the AI's numbers a tiny bit and measured how the loss changed, then compared that with what the backpropagation code said. **Every single number disagreed**, even for the very last layer, which is the simplest part.
**Cause:** The loss used `log(probability + 0.000000001)`, a common trick to avoid `log(0)`. The test used big weights, so some probabilities were far smaller than 0.000000001, and the added bit took over.
**Fix:** The loss now uses **log-softmax**, the exact and stable way to work out log-probabilities. After the fix, backpropagation and the nudge test agreed to within 0.0000002.
**Lesson:** Test your math code with a method you trust, like the nudge test, before trusting the AI's results.

### 2. "Subtracting, 2 borrows: 0%"
**Problem:** On level 5 (subtracting 2-digit numbers), the "weak spots" chart showed 0% for "2 borrows" and "3 borrows". Worse, the AI kept trying to write those questions, because 0% looked like a weak spot.
**Cause:** Those questions can't happen! With 2-digit numbers (and the first number bigger), you can only borrow once.
**Fix:** For each level, it now tries 4,000 random questions to find out which kinds of question are actually possible, and only tracks those.

### 3. It forgot how to add while learning to subtract
**Problem:** On level 5, it answered "47 + 38 = 84". It used to get that right.
**Cause:** Only 10% of its questions reviewed earlier levels. Practicing one thing all the time can make an AI forget others. Scientists call it *catastrophic forgetting*.
**Fix:** A fifth of its questions now review earlier levels.

### 4. Asking a question while it trains could scramble its memory
**Problem:** Found by reading the code. Your question on the web page and the training loop both use the AI's brain. Answering your question saves some numbers the training was in the middle of using.
**Fix:** A lock makes them take turns. It's only a few milliseconds each.

### 5. The collapse experiment would slow down the math AI
**Problem:** Python can only really do one calculation at a time per program. Running the collapse experiment in the same program as the math AI would make both slower.
**Fix:** The experiment runs as a separate program (a *process*), on its own processor core.

### 6. The chatbot couldn't be tested with a real AI model here
**Problem:** The computer used to build this can't download AI models (its network blocks those sites).
**Fix:** We built a **pretend** Ollama server and a pretend llama.cpp server that answer like the real ones. The whole loop was tested with both: teacher, checker, student, notebook, and throwing away a bad question. The real thing gets tested on the Pi.

### 7. The Pi's numpy is about twice as slow
**Problem:** Raspberry Pi OS Bullseye comes with Python 3.9 and numpy 1.19, which are older than the computer this was built on.
**Fix:** Everything was tested on exactly Python 3.9 and numpy 1.19.5. It all works. Training is about twice as slow (65 ms per round instead of 34 ms), and a Pi is slower again, so the math AI takes roughly 45–60 minutes to learn all 7 levels, not 4.

### 8. The Pi is half 64-bit and half 32-bit
**Problem:** The Pi said `aarch64` for `uname -m` (64-bit) but `32` for `getconf LONG_BIT`.
**Cause:** Raspberry Pi OS often runs a **64-bit kernel** (the core of the system) with **32-bit programs**. Ollama only comes as a 64-bit program, so it can't run there.
**Fix:** Use llama.cpp, built from source as a 32-bit program. The guide now says to check with `getconf LONG_BIT`, not `uname -m`.

### 9. The llama.cpp script was out of date, and probably would have failed
**Problem:** Before you ran it, the script was tested by compiling llama.cpp for a 32-bit Pi on the build computer (this is called *cross-compiling*), and by reading llama.cpp's build files. That turned up two things:
1. The script turned off an option called `LLAMA_CURL`, but newer llama.cpp doesn't have it any more (it's now `LLAMA_OPENSSL`). That would only have caused a warning, but it showed the script was out of date.
2. llama.cpp's build decides what kind of processor it's building for by asking the system, and on a Pi with a 64-bit kernel the answer is `aarch64`. So it would most likely pick 64-bit settings, which the Pi's 32-bit compiler can't use.

**Fix:** The script now tells the build exactly what it's making: a 32-bit ARM program (`armv7l`), with the Pi 4's NEON math instructions turned on. It also downloads the exact llama.cpp version that was tested. That build was checked with the same compiler version as the Pi (GCC 10), and the finished program started correctly in an ARM emulator.

### 10. Building could run out of memory
**Problem:** Building with 4 files at a time uses a lot of memory, and the Pi has 3.7 GB with almost no swap (99 MB), while also running the Docking AI.
**Fix:** The script builds 2 files at a time, and the guide says to pause the Docking AI during the build.

## Part 2: Running it on the real Pi
What happened when it was installed on a real Raspberry Pi 4 (32-bit Pi OS, with a 64-bit kernel).

### 11. Building llama.cpp on the real Pi worked the first time
**What happened:** The tested build settings from problem 9 worked on the real Pi with no errors. It took **about 30 minutes**, faster than the 45–90 minutes we'd guessed, and the Pi stayed cool (about 40 °C at the start) thanks to a small fan. The Docking AI was paused during the build, as the guide says.
**Fix:** The guide and the script now say about 30 minutes.
**Lesson:** Testing the build on another computer first (cross-compiling plus an ARM emulator) meant the real install just worked.

### 12. The chatbot looked like it wasn't doing anything
**Problem:** After pressing **▶ Start practicing**, the badge said "Practicing with llama.cpp server", but there were 0 rounds, and the feed said "Press ▶ Start practicing", the same message as when it's stopped. It looked stuck, but it was working. A little later, the first question showed up.
**Cause:** A round has two slow steps: the teacher writes a question, then the student answers it. The page only showed something once a whole round was finished. Also, if talking to the model failed, the error only showed on the badge for about 10 seconds before it was replaced.
**Fix:** A new line under the buttons shows what it's doing right now (✍️ teacher writing, or 🤔 student answering), how many seconds so far, and its speed in tokens a second. Before the first round finishes, it says it's working on the first question. Errors now go into the feed, so they stay on the page. Tested with a pretend llama.cpp server that answers slowly, and one that never answers.

### 13. Three out of four questions were thrown away
**Problem:** After the first night, the chatbot had done 15 practice rounds, but it had thrown away **51** of the questions it wrote, all as "not simple math".
**Cause:** We tested the checker on the kinds of answers small AI models usually write, and it refused all six. The model often writes the answer as well (`MATH: 12 * 5 = 60`), adds units (`30 liters * 8 minutes`), or adds formatting like **bold** or `backticks`. The checker only accepted pure math. Two of them were even worse: a leftover `**` or a missing bracket caused a different kind of error, which made the program think the model's connection had broken, so it waited 10 seconds before trying again.
**Fix:** The checker now keeps just the math part: everything before the `=`, without words, units or formatting. To stay safe, it refuses math with no + − × ÷ in it (so "5 squared" can't turn into just "5" and give a wrong answer). The teacher's instructions now include an example, and you can click a thrown-away question to see exactly what the AI wrote. Tested with 11 typical answers: real math gets through, and broken math, dividing by zero, answers that aren't whole numbers and anything that isn't math are still thrown away.
**Lesson:** When an AI's answers go into another program, expect it to not follow the format exactly, and make the checker forgiving where it's safe.

### 14. It slowed down to 0.9 tokens a second
**Problem:** After the Pi was moved and restarted, the chatbot wrote just 0.9 tokens a second, so one question took more than a minute.
**Cause (most likely):** When the Pi starts, every project starts by itself, including the Docking AI, even though it had been paused. The Docking AI uses 3 of the 4 processor cores, and llama.cpp slows down a lot when it has to share them.
**Fix:** The chatbot page now warns you when the Pi is very busy and tells you the command to pause the Docking AI. After pausing the Docking AI, the speed went from **0.9 to 4.9 tokens a second**, more than 5 times faster, and a round took 17 to 50 seconds.

### 15. Practice stopped when the Pi restarted
**Problem:** After the Pi restarted, the math AI carried on by itself, but the chatbot didn't, and you had to press ▶ Start practicing again.
**Fix:** The chatbot now remembers whether it was practicing, and starts again by itself after a restart. Tested by restarting the program in the middle of practice.

### 16. The teacher got its own math wrong
**Problem:** With the new checker, most thrown-away questions were real mistakes: "the answer isn't a whole number" (like 9 robots ÷ 2). One question was worse. The AI wrote "A space telescope sends a message every 5 seconds. How many messages will it send in 3 minutes?" with the math `5 * 3`, so the checker worked out 15. The right answer is 3 minutes = 180 seconds, and 180 ÷ 5 = **36**.
**Cause:** The checker can only check that the math *adds up*. It can't check that the math *matches the words*. A small model can write a sensible question and then the wrong math for it.
**Fix:** The teacher is now asked to choose numbers that give a whole-number answer, so fewer rounds are wasted. The wrong-math problem has no easy fix. It's a real AI research problem, and the guide already warns about it ("checking the checker"). When you spot one in the feed, it's a good example of why AI answers still need a person to check them.

### 17. The result: the notebook made it worse
**What happened:** After the checker fix, the chatbot practiced for 134 rounds: 64 with the notebook and 64 without (the first few rounds don't count, because the notebook needs 3 pages first). Only 50 of 184 questions were thrown away (27%, down from 77% before the fix).

| | Right answers |
|---|---|
| 📒 With the notebook | **27%** (17 of 64) |
| Without the notebook | **45%** (29 of 64) |

**Is it real or luck?** A statistics check (Fisher's exact test) says there's about a **4% chance** of a gap this big happening by luck alone, so it's very likely real.
**Why (our best guesses):**
1. **The notebook has the teacher's mistakes in it.** If the teacher writes the wrong math, the "correct" answer is wrong, the student is marked wrong, and that wrong answer goes into the notebook. One page said "The ISS pass lasted for 12 hours." (not even a question) with a "correct" answer of 720. Learning from pages like that teaches wrong things: *garbage in, garbage out*.
2. **A small model copies what it just read.** With the notebook, the student sometimes repeated a number from the question or the examples instead of working it out (it answered 50 for "50 stars every minute, how many in 10 minutes?"). Longer prompts can confuse a model this small.

**Lesson:** Showing an AI examples only helps if the examples are right. A checker that checks the math, but not whether the question makes sense, lets bad examples in. This is the same problem as the collapse experiment: an AI learning from unchecked AI writing gets worse.

### 18. Three experiments to find out why
**Plan:** Result 17 gave two possible reasons, so the chatbot now has experiment settings to test them one at a time: a **strict checker** that keeps bad questions out of the notebook, the number of **notebook pages** shown (1 to 3), and a **bigger model** (Qwen 2.5 1.5B, switched with `bash setup-llamacpp.sh 1.5b`). Every experiment is saved in a table on the Chatbot tab, so they can be compared. The first experiment (27% vs 45%) was kept as experiment 1.
**Tested:** with a pretend model server: the old result was saved as experiment 1 with the model that produced it, the strict checker threw away "no question" and "numbers not in the question" problems, and switching the model started a new experiment by itself. The bigger model's download hasn't been tested yet (the computer used to build this can't download models).
**Results so far:**

| Experiment | Settings | 📒 With the notebook | Without | Result |
|---|---|---|---|---|
| 1 | 0.5B, 3 pages, normal checker | 27% (19/71) | 46% (33/71) | the notebook made it worse (2.3% chance it's luck) |
| 2 | same as 1 (an accidental repeat, see 20) | 18% (9/49) | 45% (22/49) | the notebook made it worse (0.9%) |
| 3 | 0.5B, 3 pages, **strict checker** | 37% (11/30) | 43% (13/30) | **no clear difference** (79% chance it's luck) |

With the strict checker keeping bad examples out, the big gap (about 23% vs 46%) **closed to 37% vs 43%**, and the difference is no longer clear. So the bad examples were most of the problem: *garbage in, garbage out*. But a clean notebook didn't clearly *help* either, at least not after 30 rounds each. More rounds, the 1-page setting and the bigger model are the next things to test.

### 19. The collapse experiment said "Stopped." with no reason
**Problem:** The collapse experiment page just said "Stopped.", with no rounds done. Also, 60 rounds had been typed in, but the most it allowed was 10, and it cut it down without saying so.
**Cause:** Updating the Pi (`git pull` and restarting the program) stops a collapse run that's in progress, but the page didn't say why it stopped.
**Fix:** The page now says how many rounds were done and why it stopped ("because the program restarted" or "because you pressed Stop"). It allows up to 60 rounds, refuses numbers outside 2 to 60 with a message, and asks before starting a run longer than 20 rounds, since that takes a few hours.

### 20. Experiment 2 started without the strict checker (and accidentally repeated experiment 1)
**Problem:** Experiment 2 was meant to have the strict checker on, but the table showed it **off**, so it ran with the same settings as experiment 1.
**Cause:** The page refreshes every 3 seconds, and each refresh put the settings boxes back to the saved settings. If the strict checker box was ticked and then the page refreshed before ▶ was pressed (for example after clicking the text next to the box), it got unticked again. The same kind of bug happened in the Docking AI's experiments card.
**Fix:** Once you change a setting, the refresh leaves it alone until you start the experiment. The confirm box also says the exact settings you're about to start with ("strict checker ON"), so a mistake is easy to spot.
**A lucky result:** The accidental repeat got the same answer as experiment 1. It finished at **18% right with the notebook (9 of 49), 45% without (22 of 49)**, a 0.9% chance of luck on its own. Experiment 1 finished at 27% vs 46% (19 of 71 vs 33 of 71). Repeating an experiment and getting the same result is called **replication**, and it's how scientists check that a result is real. With both runs added together (28 of 120 vs 55 of 120), the chance that the difference is luck is only about **0.04%** (about 1 in 2,500). The notebook really does make this small model worse.

### 21. The Chat tab, and the AI that answered instead of fixing
**What it is:** A new tab to type any question to the AI. It fixes your spelling and grammar first, splits several questions into separate answers, and has Python check any math so the numbers are right ([7. Chat with it](07-chat.md)).
**Problem:** Asking the small AI to "fix the spelling" doesn't always work. Sometimes it *answers* the question instead: asked to fix "wat is the bigest planet", it can reply "The biggest planet in our solar system is Jupiter." Then the chat would try to answer an answer.
**Fix:** A safety check compares the fix with what you typed, and keeps what you typed if the fix doesn't look like a fix. The first version only compared the letters, and it let "…is Jupiter." through, because that sentence uses mostly the same words. It now also checks that the AI didn't add any sentence that isn't a question, and didn't bring in many new words.
**Another bug found while testing:** "What is the biggest planet? It's Jupiter." still got through, because the check thought "It's" was the question word "is" spelled wrong. Short question words (is, do, can, how…) now have to match exactly; only longer ones can be misspelled ("wat" for "what").
**Tested:** 16 typical fixes, all handled correctly, plus the whole chat with a pretend model server.

### 22. Harder math: course 2 needed a new brain
**Goal:** Teach the math AI harder math: multiplying, algebra (solve for x) and calculus (derivatives).
**Problem:** The math AI's brain can only read and write the 14 symbols it was built with (`0`–`9`, `+`, `-`, `=`, `.`), and questions exactly 8 symbols long. Algebra and calculus need `x`, `^`, `*` and `d/dx`, and longer questions. You can't add new symbols to a trained brain without starting it over.
**Fix:** Course 2 is a **second, separate brain** (`advmath.py`) with 20 symbols and room for questions up to 16 symbols long, like `d/dx 9x^4-9x^3=`. Course 1's progress is kept, and course 2 starts by itself once course 1 is mastered (or straight away, with **What it trains → Course 2 now**).
**Checking the checker:** before training, every answer the course writes was checked against the math engine (problem 23): 21,000 questions across all 7 levels, 0 wrong.
**Tested:** a training run on the build computer: it **mastered all 7 levels in about 12½ minutes** (about 10,800 rounds). Level 1 passed after 200 rounds, level 2 after 2,200, level 3 (solve x + b = c) after 5,200, level 4 (solve ax + b = c) after 8,500, level 5 (derivative of one term) after just 100 more, level 6 (two terms) after 9,300, and the mixed level at about 10,800. So the tiny brain really can teach itself algebra and calculus patterns. The surprise: derivatives were *easier* than solving ax + b = c. The derivative rule is a simple pattern, while solving needs division. On a Pi 4, expect roughly 2 to 3 hours.

### 23. A math engine that never runs text as code
**Goal:** Check algebra and calculus, both in the chatbot's practice questions and in the Chat tab.
**Problem:** Python's usual shortcut for working out math from text, `eval`, runs the text as a program. With text written by an AI (or typed by anyone), that could run something harmful. A ready-made math library (SymPy) also uses `eval` inside, and would need installing.
**Fix:** `mathengine.py` reads the math one symbol at a time and refuses anything that isn't numbers, `x`, `+ - * / ^` and brackets. It knows polynomials (like `3x^2 - 4x + 1`, `(x+2)(x-3)` or `2(x+1)^2`), keeps every number as an exact fraction, and can solve equations up to x², take derivatives and integrals, and do plain arithmetic. Tested on 8 equations, derivatives, integrals and 8 kinds of bad input (like `__import__('os')`, `1/0`, `2^x` and a 200-digit number), which it all refused safely.

### 24. Connecting everything to the Chat tab
**Goal:** Make the training help the Chat tab.
**What's possible on a Pi 4:** the chat AI (Qwen, 500 million numbers) can't be retrained on a Pi 4 (see [3. The chatbot](03-chatbot.md)), so its brain stays the same. Three things do carry over:
1. **The math engine** works out any arithmetic, algebra or calculus in your question exactly, and tells Qwen the answer.
2. **Your trained math AI answers too**, when the question is something one of its courses practices. The chat shows its answer with ✅ or ❌, and its level.
3. **Checked practice problems:** every practice problem the chatbot gets right (Python and the AI agree) is saved, and the chat shows up to 2 similar ones to Qwen as examples for word problems.

**Problems found while testing:**
- **"x" can mean *times* or the letter x.** In "5 x 4" it's times, and in "3x + 5 = 20" it's a letter. Now: if the question looks like algebra or calculus (an `=`, "derivative", "solve", `x^`, or a number stuck to an x like `3x`), x is the letter; otherwise "5 x 4" means times.
- **The math AI was asked things it never practiced,** like 47 × 38 (course 2 only practices multiplying by a 1-digit number), and gave nonsense. Now it only answers questions inside what its courses practice, and says which level it's on.
- **Algebra questions looked messy** on the Math AI tab ("x-2 = 2, x"). They now read "x − 2 = 2, x = 4".

**Tested:** with a pretend model server: course 2 training and its feed, asking both courses, algebra and calculus practice (checked by the engine), and the chat using the engine, the math AI and checked examples.

### 25. Saved chats, titles and memory across chats
**Goal:** Make the Chat tab work like other chatbots: separate chats you can go back to, with titles, and memory.
**How:** each chat is saved as its own file in `data/chats/`. After the first question, the AI writes a title. When answering, it uses the last 3 questions and answers in the same chat, plus up to 2 related answers from your other chats, found by looking for shared important words (like "rover" or "jupiter", not "what" or "about").
**Problems found while testing:**
- **The AI's titles came out messy,** like `Title: "Jupiter facts"`. They're now cleaned up, and if a title is too long or looks like an answer, the first words of your question are used instead.
- **"What did I ask about the rover before?"** shares only 1 important word ("rover") with the old chat, and the search needed 2. Now, if you say "before", "earlier", "remember" or "already asked", 1 shared word is enough.
- **The same chat was linked twice** when 2 memories came from it. Now each chat is linked once.

**Tested:** with a pretend model server: new chats, AI titles, a follow-up seeing the earlier message, memory found across chats, rename, delete, sending while it's still busy (refused), and chats still there after a restart.

### 26. Live typing, Stop, Try again, Read aloud, math steps and Export
**Goal:** Make the chat feel like other chatbots, and show *how* math is solved.
**How:**
- **Live typing** asks the model to *stream* its answer: it sends each piece as soon as it's written, and the page shows it every 0.6 seconds. **Stop** works by hanging up on the model, which makes llama.cpp stop writing.
- **Math steps:** the math engine now explains its work the way you'd do it in class: moving terms to one side, dividing, factoring, or using the quadratic formula, and the power rule for derivatives and integrals.
- **Read aloud** uses the browser's built-in voice. **Export** builds the file in the browser, so nothing extra runs on the Pi.

**Problems found while testing:**
- **`5 = 2x - 7`** was solved by moving 2x across, which works but is awkward. Now it swaps the sides first, like you would: `2x - 7 = 5`.
- **`x/3 = 7`** said "divide both sides by 1/3". Now it says "multiply both sides by 3".
- **Exported chats said "null"** when the math AI gave no answer. Now they say "no answer".

**Tested:** the steps for 12 kinds of equations, derivatives and integrals, and, with a pretend model that streams slowly: text appearing while it's written, stopping halfway (the model saw the hang-up), Try again giving a new answer, and Export downloading the chat with its steps.
