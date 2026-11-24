# 2. The self-taught math AI

## What it is
A **tiny GPT**: the same kind of AI as ChatGPT (a *transformer*), just about a million times smaller. Its brain is **102,670 numbers**. When it starts, those numbers are random, so it knows nothing, not even what a digit is.

## How it teaches itself
Every round, it:
1. **Writes its own quiz** of 48 questions. It keeps a score for each *kind* of question (like "adding with 2 carries") and writes more questions about the kinds it's worst at. A quarter of the questions are random, and a fifth review earlier levels so it doesn't forget them.
2. **Practices old mistakes:** 16 questions come from its **notebook of mistakes**. When it gets one right, the question leaves the notebook.
3. **Answers** every question, one digit at a time, just like ChatGPT writes one word at a time.
4. **Checks** each answer with a **calculator**. This is the most important part: without a checker, it could teach itself wrong answers and never know (see [the collapse experiment](04-collapse-experiment.md)).
5. **Learns:** for every question, it compares its guesses with the right answer and nudges its 102,670 numbers a tiny bit toward the right answer. This is called *backpropagation*.

Every 100 rounds it takes a **test of 300 brand-new questions**, which it doesn't learn from. If it scores **97%** or more, it moves up a level.

## The 7 levels
| Level | Example |
|---|---|
| 1. Adding 1-digit numbers | 7 + 5 |
| 2. 2-digit + 1-digit | 47 + 8 |
| 3. 2-digit + 2-digit | 47 + 38 |
| 4. 3-digit + 3-digit | 472 + 389 |
| 5. Subtracting 2-digit numbers | 92 − 47 |
| 6. Subtracting 3-digit numbers | 702 − 389 |
| 7. Adding and subtracting | both, up to 999 |

On a fast computer it learned all 7 levels in about 4 minutes. A Pi 4 is slower, so expect roughly 45 minutes to an hour.

## The trick: it writes answers backward
Inside, it writes 47 + 38 = 85 as `047+038=5800.`: the answer is backward, ones digit first. That's how *you* add: you start with the ones, then carry to the tens. If it had to write the tens digit first, it would need to know about the carry before working out the ones! The web page shows the answer the normal way.

## Attention: where it looks
In **🙋 Ask it a question**, the colored grid shows its **attention**: which digits of the question it "looked at" while writing each digit of the answer. A well-trained AI looks at the matching digits: the ones digits for the ones place, the tens digits for the tens place. Nobody programmed that. It figured it out.

**Next:** [3. The self-quizzing chatbot](03-chatbot.md)
