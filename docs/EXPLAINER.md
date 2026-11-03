# qcal, explained simply

## What is a quantum computer?
An ordinary computer stores information as bits, tiny switches that are either off (0) or on (1). A quantum computer uses **qubits**, tiny physical objects that follow the strange rules of the very small. For some problems, like designing medicines, this could be far more powerful.

*Analogy:* an ordinary bit is a coin lying flat, heads or tails. A qubit is a coin spinning on the table, and the way it spins carries information.

## Why does it make mistakes?
Qubits are extremely delicate. Heat, vibration or tiny chip flaws nudge them, and today's machines slip up roughly once every few hundred steps.

*Analogy:* keeping that coin spinning while trucks drive past the house.

## What is error correction?
Instead of trusting one qubit, you spread the information over many qubits and keep checking them against each other. The checks show *where something looks wrong*; these warning signs are called the **syndrome**.

*Analogy:* a smoke alarm in every room.

## What is a decoder?
The **decoder** is a program that looks at the pattern of warning signs and guesses the most likely mistake, so it can be undone. We use a standard one called **PyMatching**.

*Analogy:* a detective who looks at muddy footprints and works out the most likely route the burglar took.

When the decoder's guess is wrong, that run's answer is corrupted: a **logical error**.

## What does qcal add?
Ordinary decoders give an answer but never say how sure they are. qcal adds two things.

**1. An honest "how sure am I" number.** For every run, qcal gives the chance that the decoder got it wrong, for example "2% chance of a mistake". It's honest (**calibrated**): of all the runs it labels "2%", about 2 in 100 really are wrong.

*Analogy:* a weather forecaster whose "70% chance of rain" days really are rainy about 70% of the time.

**2. A rule for throwing out risky runs, with a guaranteed limit.** You choose the most mistakes you'll accept among the runs you keep, say "at most 1 in 1,000". qcal sets a cut-off and discards runs that look too risky. A statistical method (**Learn-then-Test**) promises that, with 90% confidence, kept runs meet your limit, as long as future runs behave like the ones used to set the rule.

*Analogy:* a fruit inspector who throws out doubtful apples and can promise the crate you buy has at most 1 bad apple in 1,000.

## What did we measure?

**In computer simulations** (pretend machines with realistic noise):
- Throwing out only **7 to 14 out of every 100 runs** made mistakes among the kept runs **11 to 18 times rarer**. At the largest size we tested, the error rate fell from about 1 in 100 to under 1 in 1,000, while 93 of every 100 runs were kept.
- The promised limit held in 35 out of 36 tests. The one miss was tiny and within normal chance.

**On real data from Google's quantum chip** (300,000 real runs, shared publicly by Google):
- Real runs fail far more often (14 to 31 in 100), so we tested looser limits like "at most 5 in 100".
- The promise held in most cases, about 9 out of 10 points on held-back runs.
- **Where it fell short:** when we set the rule on earlier runs and used it on later runs, the strict limit was broken in about 15% of cases. Adding a small safety cushion (aiming for 80% of the limit) and using all past data fixed this: the limit then held in **97 out of 100** cases, and we still kept about 9 of every 10 runs we had kept before.
- For the hardest real experiments, qcal sometimes says "I can't promise that" and keeps nothing. That's the safe behaviour.
- A small neural-network decoder helped a little alongside the standard one, but alone it was worse on bigger setups.

## Honest limits
- The promise only covers runs that behave like the runs used to set the rule. If the machine changes, you must re-check it.
- Very strict limits, like 1 mistake in a million, need far more test runs than we have, so qcal refuses them.
- Discarded runs must be repeated, which costs time.
- The real data is from one Google chip from 2022. Newer machines may behave differently.
- It's too slow for use *inside* a running machine; it suits checking results afterwards.

## In one sentence
qcal makes a quantum error-correction decoder say how confident it is and lets you keep only the runs it can vouch for, with a stated, tested limit on mistakes.
