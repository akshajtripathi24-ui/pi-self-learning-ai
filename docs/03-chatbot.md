# 3. The self-quizzing chatbot

## What it is
A small, ready-made AI language model (**Qwen 2.5, 0.5 billion parameters**, made by Alibaba and free to use), running entirely on your Pi. It practices math word problems by quizzing itself:

1. **Teacher:** it writes its own word problem about space or robots, plus the math that solves it, like `MATH: 12 * 5`.
2. **Checker:** Python works out that math to get the true answer. If the AI didn't follow the format, or the math isn't simple whole-number math, the question is thrown away.
3. **Student:** the same AI answers the problem *without* seeing the math.
4. **Notebook:** wrong answers go into a notebook, together with the correct math and answer.

**The experiment:** in half the rounds, the AI first reads the 3 notebook pages most like the new problem. In the other half, it doesn't. Comparing the two scores shows honestly whether the notebook helps. It might not! Small models sometimes get *confused* by longer prompts. Either answer is a real result.

**Is this "training"?** Not quite. Changing a chatbot's brain (its 500 million numbers) needs far more computer power than a Pi has. This is more like a student who keeps a notebook of solved problems and reads it before a test. That's still a real technique, used by big AI systems too: it's called *few-shot prompting* or *retrieval*.

## Set it up
First, find out which kind of Raspberry Pi OS you have:
```bash
getconf LONG_BIT
```
Use this, not `uname -m`! Many Pi 4s run a **64-bit kernel** (the core of the system, so `uname -m` says `aarch64`) with **32-bit programs** (so `getconf LONG_BIT` says `32`). What matters for installing programs is the programs: the `getconf` answer.

### If it says 64: use Ollama (about 15 minutes)
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:0.5b
```
The first command installs [Ollama](https://ollama.com) (it runs AI models), and the second downloads the model (about 400 MB). Test it:
```bash
ollama run qwen2.5:0.5b "Say hi in five words."
```

### If it says 32: use llama.cpp (about 30 minutes)
Ollama only has 64-bit programs, so on 32-bit Pi OS we build [llama.cpp](https://github.com/ggml-org/llama.cpp) instead. One script does it all: it builds llama.cpp as a 32-bit program (the slow part), downloads the model (about 490 MB) and runs it in the background on port 8099.

Pause the Docking AI first, so the build gets all the memory and processor:
```bash
sudo systemctl stop dockingai
```
```bash
cd ~/selflearning && bash setup-llamacpp.sh
```
When it says `Done!`, test it (it should say `ok`), then start the Docking AI again:
```bash
curl http://127.0.0.1:8099/health
```
```bash
sudo systemctl start dockingai
```
*The build was tested for exactly this kind of Pi: 32-bit ARM, the Pi's GCC 10 compiler, and running in an ARM emulator. It hasn't run on a real Pi yet, so if anything gives an error, send it, and it'll go in the build log.*

### Then
Open the **💬 Chatbot** tab and press **▶ Start practicing**. The badge should say **● Practicing with …**.

The first round takes a while, so watch the line under the buttons. It shows what the AI is doing right now (✍️ the teacher writing a question, or 🤔 the student answering), how many seconds so far, and its **speed in tokens a second**. A *token* is a piece of a word: language models read and write in tokens, not letters or whole words.

## Experiments
The first experiment on our Pi found that **the notebook made it worse** (27% right with it, 45% without; see the [build log](06-build-log.md), problem 17). The **🧪 Experiments** card on the Chatbot tab lets you test *why*, by changing one thing at a time. Every experiment is saved in a table, with a verdict and the chance that the difference is just luck (using a statistics check called Fisher's exact test).

| # | Change | What it tests | Time |
|---|---|---|---|
| 2 | Turn on the **strict checker** | Does a *clean* notebook help? The strict checker also throws away questions with no question in them, or math using numbers that aren't in the question, so bad examples never get into the notebook. | About 1–2 hours |
| 3 | Strict checker on, **1 notebook page** | Were the long prompts the problem? The student sees 1 example instead of 3. | About 1–2 hours |
| 4 | A **bigger model** (1.5B, 3 times bigger) | Does a smarter model use the notebook better? Run `bash setup-llamacpp.sh 1.5b` on the Pi (a 1.1 GB download). When the chatbot notices the new model, it starts a new experiment by itself. It's about 3 times slower, so leave it overnight. To go back: `bash setup-llamacpp.sh 0.5b` | Overnight |

**Kinds of question:** each experiment can also choose what the AI practices: **arithmetic** (12 × 5), **algebra** ("solve for x" word problems) and **calculus** (derivatives). The math engine (`mathengine.py`) checks algebra and calculus: it solves the equation, or works out the derivative, exactly. Bad questions are thrown away, like an equation where x isn't one whole number, or a function it can't read (like sin(x)). Derivatives are compared *as math*, so `2x + 6x^2` counts the same as `6x^2 + 2x`. Every practice problem the student gets right (so Python and the AI agree) is also saved for the Chat tab to use as an example.

**How to run one:** pick the settings on the Chatbot tab, press **🧪 Start a new experiment with these settings**, and let it practice until both columns have **at least 30 rounds** (60 is better). Starting a new experiment saves the current one and empties the notebook, so each experiment starts fair.

## Good to know
- **It's slow:** each round takes about 15–60 seconds on a Pi 4. Let it run for an hour or more to get enough rounds for a fair comparison (at least 30 with and 30 without the notebook).
- **It uses all 4 processor cores.** Pause the Docking AI while the chatbot practices (`sudo systemctl stop dockingai`), and keep an eye on the Pi's temperature. If the Pi is too busy, the chatbot page warns you. Remember that the Docking AI starts again by itself whenever the Pi restarts.
- **It keeps practicing after a restart.** If the Pi loses power or restarts, the chatbot carries on by itself.
- **Click a thrown-away question** (🗑️) to see exactly what the AI wrote, and why the checker refused it.
- **The teacher can be wrong too!** Sometimes it writes a problem whose math doesn't match the words. Then the "correct" answer is wrong, and the student gets marked wrong unfairly. Look through the feed and see if you can spot one. That's a real problem in AI research: checking the checker.
- The download needs internet, but after that it all runs on your Pi. Nothing is sent anywhere.

**Next:** [4. The collapse experiment](04-collapse-experiment.md)
