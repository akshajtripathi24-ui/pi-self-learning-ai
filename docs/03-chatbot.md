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

### If it says 64: use Ollama (about 15 minutes)
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:0.5b
```
The first command installs [Ollama](https://ollama.com) (it runs AI models), and the second downloads the model (about 400 MB). Test it:
```bash
ollama run qwen2.5:0.5b "Say hi in five words."
```

### If it says 32: use llama.cpp (30–60 minutes)
Ollama only works on 64-bit Pi OS, so on 32-bit we build [llama.cpp](https://github.com/ggml-org/llama.cpp) instead. One script does it all: it builds llama.cpp (the slow part), downloads the model (about 490 MB) and runs it in the background on port 8099:
```bash
cd ~/selflearning && bash setup-llamacpp.sh
```
Test it with `curl http://127.0.0.1:8099/health`. It should say `ok`. *This way hasn't been tested on a real 32-bit Pi yet. If it gives an error, send it, and it'll go in the build log.*

### Then
Open the **💬 Chatbot** tab and press **▶ Start practicing**. The badge should say **● Practicing with …**.

## Good to know
- **It's slow:** each round takes about 15–60 seconds on a Pi 4. Let it run for an hour or more to get enough rounds for a fair comparison (at least 30 with and 30 without the notebook).
- **It uses all 4 processor cores.** Pause the Docking AI while the chatbot practices, and keep an eye on the Pi's temperature.
- **The teacher can be wrong too!** Sometimes it writes a problem whose math doesn't match the words. Then the "correct" answer is wrong, and the student gets marked wrong unfairly. Look through the feed and see if you can spot one. That's a real problem in AI research: checking the checker.
- The download needs internet, but after that it all runs on your Pi. Nothing is sent anywhere.

**Next:** [4. The collapse experiment](04-collapse-experiment.md)
