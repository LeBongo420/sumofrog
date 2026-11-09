# Notes for AI agents working on Sumo Frog

Sumo Frog is a toy proof-of-work token on a **private Solana test validator / devnet only**.
It has no value. Never touch mainnet, real wallets, seed phrases or real SOL. Never print or
commit anything in `.keys/` or `.env`.

## Before you edit `programs/sumofrog/src/lib.rs`

1. **Load [`docs/solana-prompt.md`](docs/solana-prompt.md)** (Jump Crypto's core Solana prompt).
   It says how the Solana runtime actually behaves and lists common false alarms (reentrancy guards,
   "floats are non-deterministic", etc.). Don't add code to defend against those.
2. **Anchor, not Pinocchio.** The prompt targets Pinocchio; ignore its §4 and the Pinocchio
   snippets in §6. Anchor's `Account<T>`, `seeds`/`bump`, `has_one`, `init` and `Program<T>`
   already do the owner, discriminator, PDA, re-init and program-ID checks. Check they're
   present; don't hand-roll duplicates. Don't port to Pinocchio unless asked.
3. **The maths spec is `scripts/gen_vectors.py`.** If you change `work_value`, `block_reward`,
   `retarget` or the challenge hashes, change the Python first, run it, and review the diff in
   `tests/vectors/golden.json`. Never edit the JSON by hand to make a test pass.

## Rules for tests

- Run `scripts/test-local.sh`. It must end with `ALL OK`.
- Never delete, comment out or `.skip` a test to make the suite pass. The script counts passing
  tests against `tests/test-count-baseline.txt` and fails if the count drops. Only ever raise it.
- `tests/cu-baseline.json` holds the compute units for `mine`. If your change raises them more
  than 5%, say so and explain why instead of just bumping the baseline.

## Deploying

Changing the program means the Oracle validator runs old code until someone redeploys.
Don't redeploy or restart anything on the Oracle server yourself; say a redeploy is needed.
