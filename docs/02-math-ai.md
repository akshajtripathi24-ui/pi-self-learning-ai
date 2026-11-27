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

## Course 2: algebra and calculus
After course 1, the math AI moves on to **course 2** by itself (or pick it with **What it trains** on the Math AI tab). Course 2 has its **own, separate brain** (104,404 numbers), because course 1's brain only knows the 14 symbols of adding and subtracting. Course 2 needs more: `*`, `x`, `^` and `d/dx`. Course 1's progress is kept.

| Level | Example | Answer |
|---|---|---|
| 1. Multiplying 1-digit numbers | 7 × 8 | 56 |
| 2. Multiplying 2-digit × 1-digit | 47 × 8 | 376 |
| 3. Algebra: solve x + b = c | x + 7 = 15 | x = 8 |
| 4. Algebra: solve ax + b = c | 3x + 5 = 20 | x = 5 |
| 5. Calculus: derivative of one term | d/dx 4x³ | 12x² |
| 6. Calculus: derivative of two terms | d/dx 3x² − 5x | 6x − 5 |
| 7. Mixed: everything so far | any of the above | |

It works exactly like course 1: it writes its own questions, mostly about its weak spots, and a checker marks every answer. It needs **95%** on a test of new questions to move up a level (a bit less than course 1's 97%, because these are harder).

**Honest limits:** a brain this tiny can learn these exact kinds of question, but not "all of math". Even huge AIs find advanced math hard. It learns the *patterns* of these questions (like "multiply the number in front by the power, then take 1 off the power"), not a full understanding of algebra.

**How long it takes:** in a test on a fast computer, it mastered **all 7 levels in about 12½ minutes** (about 10,800 rounds):

| Level | Passed after |
|---|---|
| 1. Multiplying 1-digit numbers | 200 rounds |
| 2. Multiplying 2-digit × 1-digit | 2,200 rounds |
| 3. Solve x + b = c | 5,200 rounds |
| 4. Solve ax + b = c | 8,500 rounds |
| 5. Derivative of one term | 8,600 rounds (only 100 more!) |
| 6. Derivative of two terms | 9,300 rounds |
| 7. Mixed | mastered at about 10,800 rounds |

Course 1 took about 4 minutes on that computer and about an hour on a Pi 4, so expect course 2 to take **roughly 2 to 3 hours** on a Pi 4. Watch the test score chart: it climbs, drops each time it levels up (a new, harder kind of question), then climbs again. Interesting: derivatives were *easier* for it than solving ax + b = c, because the derivative rule is a simple pattern (multiply by the power, take 1 off the power), while solving needs division.

## Course 3: decimals and harder math
After course 2, it moves on to **course 3** by itself (or pick **Course 3 now** in **What it trains**). Course 3 has its **own brain too** (105,559 numbers), because it needs 3 new symbols: a **decimal point**, `S` (its way of writing the integral sign ∫) and a **comma** (to write two answers, like `2,3`). Courses 1 and 2 keep everything they learned.

| Level | Example | Answer |
|---|---|---|
| 1. Decimals: adding | 2.5 + 1.7 | 4.2 |
| 2. Decimals: subtracting | 38.6 − 12.9 | 25.7 |
| 3. Decimals: multiplying by a whole number | 4.5 × 6 | 27 |
| 4. Algebra: quadratic equations | x² − 5x + 6 = 0 | x = 2 or 3 |
| 5. Calculus: integrals | ∫ 6x² dx | 2x³ + C |
| 6. Calculus: derivatives of three terms | d/dx x³ − 4x² + 7x | 3x² − 8x + 7 |
| 7. Mixed: everything so far | any of the above | |

**Decimals are lined up, like on paper.** Inside, 2.5 + 1.7 is written `02.5+01.7=` and its answer 04.2 is written backward, `2.40`: tenths first, then the point, then the ones and tens, for the same reason as adding (you start with the tenths, then carry). Every number has 2 digits before the point and 1 after, so the tenths are always in the same column, just like you line up the decimal points in class. The web page shows them the normal way: 2.5 + 1.7 = 4.2. Quadratic answers are written smallest first, so `x^2-5x+6=0` always has the answer `2,3`, never `3,2`. The **+ C** of an integral is added by the web page, not the brain, because every integral has one.

**A new end mark.** Courses 1 and 2 end every answer with a `.`, which means "I've finished". In course 3, `.` is a decimal point, so it ends answers with `#` instead. Otherwise it couldn't tell "4." (finished) from "4.2" (not finished)!

**Every answer was checked:** 20,000 questions from each level were made and checked against the math engine, and none were wrong.

**How long it takes:** a test run on a fast computer is going now. Its results will be added here.

## The trick: it writes answers backward
Inside, it writes 47 + 38 = 85 as `047+038=5800.`: the answer is backward, ones digit first. That's how *you* add: you start with the ones, then carry to the tens. If it had to write the tens digit first, it would need to know about the carry before working out the ones! The web page shows the answer the normal way.

## Attention: where it looks
In **🙋 Ask it a question**, type any question one of the courses practices (`47+38`, `7*8`, `3x+5=20`, `d/dx 4x^3`, `2.5+1.7`, `x^2-5x+6=0`, `integral of 6x^2`). It goes to the course that practices that kind of question. If no course practices it, it tells you why, like "this course only practices a decimal up to 9.9 times a whole number from 2 to 9". The colored grid shows its **attention**: which digits of the question it "looked at" while writing each digit of the answer. A well-trained AI looks at the matching digits: the ones digits for the ones place, the tens digits for the tens place. Nobody programmed that. It figured it out.

**Next:** [3. The self-quizzing chatbot](03-chatbot.md)
