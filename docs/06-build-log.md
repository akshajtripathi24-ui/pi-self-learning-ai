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
**Results:** *will be added here after running them on the Pi.*

### 19. The collapse experiment said "Stopped." with no reason
**Problem:** The collapse experiment page just said "Stopped.", with no rounds done. Also, 60 rounds had been typed in, but the most it allowed was 10, and it cut it down without saying so.
**Cause:** Updating the Pi (`git pull` and restarting the program) stops a collapse run that's in progress, but the page didn't say why it stopped.
**Fix:** The page now says how many rounds were done and why it stopped ("because the program restarted" or "because you pressed Stop"). It allows up to 60 rounds, refuses numbers outside 2 to 60 with a message, and asks before starting a run longer than 20 rounds, since that takes a few hours.

### 20. Experiment 2 started without the strict checker (and accidentally repeated experiment 1)
**Problem:** Experiment 2 was meant to have the strict checker on, but the table showed it **off**, so it ran with the same settings as experiment 1.
**Cause:** The page refreshes every 3 seconds, and each refresh put the settings boxes back to the saved settings. If the strict checker box was ticked and then the page refreshed before ▶ was pressed (for example after clicking the text next to the box), it got unticked again. The same kind of bug happened in the Docking AI's experiments card.
**Fix:** Once you change a setting, the refresh leaves it alone until you start the experiment. The confirm box also says the exact settings you're about to start with ("strict checker ON"), so a mistake is easy to spot.
**A lucky result:** The accidental repeat got the same answer as experiment 1. It finished at **18% right with the notebook (9 of 49), 45% without (22 of 49)**, a 0.9% chance of luck on its own. Experiment 1 finished at 27% vs 46% (19 of 71 vs 33 of 71). Repeating an experiment and getting the same result is called **replication**, and it's how scientists check that a result is real. With both runs added together (28 of 120 vs 55 of 120), the chance that the difference is luck is only about **0.04%** (about 1 in 2,500). The notebook really does make this small model worse.
