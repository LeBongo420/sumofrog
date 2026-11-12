# SUMO FROG ($SUMO)

### A small proof-of-work coin on Solana. The frog you mine.

**Draft, 1 November 2026; revised 12 November 2026.** Author: [lebongo420](https://x.com/lebongo420)

> **Test-network notice.** $SUMO currently lives only on a private test network and on Solana's
> public test networks. Test SUMO is a **worthless test token**. It cannot be bought or sold, and
> it will never carry over to any later network.

---

## 1. What it is

Sumo Frog is a hobby and learning project: a token that anyone can earn by doing a little work
with their own computer, under rules written down in advance. The idea is borrowed openly from
Bitcoin. The mascot is an 8-bit sumo frog.

There is no company, no team allocation, no sale and no roadmap of promises. There is a program,
a set of rules, and whoever chooses to mine.

## 2. How a block is found

The program keeps one **challenge**, a 32-byte random-looking value.

1. A miner picks a number, the **guess #**, and computes
   `sha256(challenge ‖ reward address ‖ guess #)`.
   The reward address is the miner's own wallet, or a payout address the miner chose (section 5).
2. The first 8 bytes of that hash, read as a number, must be at or below the current **target**.
   A lower target means more guesses are needed.
3. When a miner finds such a guess, they send it to the program. The program repeats the hash
   itself, and if it passes, mints the block reward to the reward address and replaces the
   challenge with a new one built from the winning hash.

Because the reward address is inside the hash, a winning guess found for one address is useless
for any other. Because the challenge changes after every block, each answer works exactly once.
If two miners find answers for the same challenge, the first to arrive wins and the other simply
starts on the new challenge.

**Honest note on "CPU mining".** SUMO is designed to be mined on an ordinary computer, and the
miner is a small program for home PCs. SHA-256 also runs on graphics cards and specialised chips
much faster than on a PC. Nothing in the rules stops that, so $SUMO is *CPU-mineable*, not
*CPU-only*.

## 3. Difficulty

The program aims for one block every **60 seconds**. Every **10 blocks** it compares how long
those blocks actually took with the 10 minutes planned, and moves the target in proportion:
faster blocks make the next ones harder, and slower blocks make them easier. A single adjustment
never moves difficulty by more than **4×**, as in Bitcoin. The network started at a difficulty of
**28 bits**, about 268 million guesses per block on average.

The program's clock is the network's clock. Nobody can set difficulty by hand.

## 4. Supply and halving

| Rule | Value |
|---|---|
| Reward | **20 SUMO** per block |
| Halving | **once a year**: every 525,600 blocks (365 days of 60-second blocks) |
| Maximum supply | **21,000,000 SUMO**, with 9 decimal places |
| Block time | 60 seconds target |
| Retarget | every 10 blocks, at most 4× per step |

The reward halves every 525,600 blocks: 20 SUMO in the first year, then 10, then 5, and so on.
The 21 million cap is checked by the program on every single block, so the total can never pass
it. The final block is trimmed so the cap is met exactly. After that, mining ends and no more
SUMO can exist.

**How the numbers add up.** The first 34 blocks on the test network paid 50 SUMO each (1,700 SUMO)
under the earlier draft rules. Everything after that pays 20 SUMO, halving yearly. Left
uncapped, that schedule would add up to about 21,025,020 SUMO, so the cap cuts in during the
tenth year: at 60-second blocks, mining ends after about **9.8 years**, at roughly block
5,141,088. If blocks come faster or slower than planned, difficulty moves to bring them back
towards 60 seconds, and the years stretch or shrink with them.

| Year | Reward per block | Total mined by the end of that year |
|---|---|---|
| 1 | 20 SUMO | 10,513,020 |
| 2 | 10 SUMO | 15,769,020 |
| 3 | 5 SUMO | 18,397,020 |
| 4 | 2.5 SUMO | 19,711,020 |
| 5 | 1.25 SUMO | 20,368,020 |
| 6 to 9 | 0.625 down to 0.078 SUMO | 20,983,957.5 |
| 10 | 0.039 SUMO | 21,000,000 (cap reached, mining ends) |

## 5. Payout address

A miner can send rewards to any wallet address they choose (a **payout address**) instead of the
wallet that runs the miner. The miner's own wallet still signs and pays the small transaction
fees. The payout address goes into the hash, so a guess found for one payout address can't be
redirected to another one. If the payout wallet has no SUMO account yet, the program creates it
in the same transaction.

A payout address is a **public** address only. The miner never asks for a seed phrase or a
private key, and refuses them if they are typed in.

## 6. Fair launch

- **No premine.** No SUMO exists before the first block on the launch network. The creator
  starts at zero, like everyone else. Test-network SUMO never carries over.
- **No liquidity from the creator.** The creator will not create or fund a trading pool. If
  others ever choose to make a market, that is their own decision and their own risk.
- **No sale, no allocation, no fees to the creator.** Every SUMO comes from a solved block.
- **No official social media.** There is no official Sumo Frog account. The author's personal
  X handle is [lebongo420](https://x.com/lebongo420). Any other account claiming to speak for
  Sumo Frog is not official. The project is found through a plain website, this paper and the
  open code.

## 7. Fixed rules

The program is upgradeable while it is being tested, so mistakes can be fixed. While it is
upgradeable, the holder of the upgrade key can also lower the block reward or move the next
halving later (never raise the reward, never move a halving into the past, never pass the
21 million cap). This is how the test network moved from the earlier draft schedule to the one
above.

Once testing is complete, the **upgrade key will be given up** on the launch network. After that,
nobody, including the creator, can change the program, its rules, its schedule or its supply. The
only power the program ever has is to mint SUMO for a valid solved block, up to the cap.

The name and logo of the token are held by the setup wallet, and whether to lock them at launch
is still being decided.

## 8. Paying for the network

Each solved block is an ordinary Solana transaction. On the launch network, miners pay their own
small transaction fees in SOL. There is no faucet there. On test networks, a small faucet hands
out free test SOL.

## 9. Risks and limits

- The code is a hobby project. It has been tested, including automated random-input testing,
  and reviewed by AI tools, but it has not had a paid professional audit. Bugs found after the
  upgrade key is given up can never be fixed.
- Faster hardware wins more often. Specialised hardware could dominate mining.
- Solana itself could change, stall or censor transactions. Sumo Frog has no control over that.
- SUMO is not an investment. This paper makes **no claim about price, value or returns**, and
  none should be inferred.

## 10. Summary

A frog, a few written-down rules and a 21 million cap. Anyone may mine. Nobody was given any in
advance. When the key is given up, the rules can no longer change.

---

*Program and tests: `programs/sumofrog/src/lib.rs`. The rules' maths is written out separately
in `scripts/gen_vectors.py`, and the program is checked against it.*
