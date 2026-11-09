# Adversarial review of the Sumo program, 31 Oct 2026

Reviewer: an AI agent working as a second reviewer (not a paid audit). Scope:
`programs/sumofrog/src/lib.rs` (3 instructions), with Anchor 0.32.2 semantics per `AGENTS.md`.
Method: read line by line against each attack below, then wrote tests that try the attack
(TS on a local validator) or throw random inputs at the maths (proptest, 4,096 cases each).

## Bugs found and fixed

| # | Problem | Impact | Fix | Test |
|---|---|---|---|---|
| 1 | `retarget` cast `interval as i64`. For `retarget_interval > i64::MAX` it wrapped negative, the window collapsed to 1 s, and a **fast** epoch made mining **4x easier** instead of harder. | Only with absurd setup values (the live network uses 10 × 60 s), so no live impact. | Window computed in `u128` and capped; `initialize` now refuses any window over `i64::MAX / 4` s (`params_ok`, `MAX_RETARGET_WINDOW`). Python spec and golden vectors updated. | `retarget_huge_interval_no_longer_wraps`, `params_ok_rules`, TS `initialize refuses a retarget window...`, `fuzz_retarget_*` |
| 2 | `blocks_mined += 1`, `total_minted += reward` and `now - epoch_start_ts` used plain maths. With `overflow-checks = true` an overflow would abort the block. | Unreachable in practice (supply cap and real clocks keep them far from limits). | `checked_add` (new `MathOverflow` error) and `saturating_sub`. | `fuzz_supply_cap_holds` |

Compute units moved by ±4 (17,232 → 17,236 normal block; 19,788 → 19,784 retarget block).
The private test network still runs the old build; for its settings the two builds behave
identically, so no redeploy is needed for safety. It can take the new build with the next upgrade.

## Checked and fine

- **Signers:** `initialize` needs the program's upgrade authority (checked through `ProgramData`),
  so nobody can front-run setup. `create_metadata` needs `config.authority` (`has_one`). `mine`
  needs the miner's signature. TS tests cover the first and last.
- **Owners / account types:** `Account<Config>`, `Account<Mint>`, `Account<TokenAccount>`,
  `Program<Token>` etc. check owner and discriminator. Config and mint are PDAs with stored bumps.
- **Account substitution:** fake mint → seeds check fails; someone else's token account →
  associated-token constraint fails (TS test `rejects substituted accounts`). `has_one = mint`
  ties config to the real mint.
- **Replay / reuse of a solved hash:** the challenge must equal the stored one, and it's replaced
  by `sha256(solution ‖ slot ‖ blocks_mined)` after every block. Resending fails
  (`StaleChallenge`, TS test). Two `mine` instructions with the same answer in one transaction fail the same way (the first
  changes the challenge), though that case has no separate test.
- **Stealing a winning guess:** the reward address is in the hash (TS tests, plus the PoW-binding fuzz test in `lib.rs`).
- **Difficulty bypass:** `work_value` is the first 8 bytes big-endian, compared `<= target`. Its
  order always matches the hash prefix order (`fuzz_work_value_orders_like_the_hash`). The target
  can never reach 0 (`fuzz_retarget_any_input_is_safe`), and the only way to change it is the
  retarget rule.
- **Supply cap:** the reward is trimmed to what's left, so the total never passes `max_supply`
  and hits it exactly (`fuzz_supply_cap_holds`, TS `stops at max supply`). The live schedule pays
  just under 21M (`live_schedule_stays_under_cap`). The config PDA is the only mint authority, and
  there is no freeze authority. No instruction can mint any other way.
- **Integer maths:** `block_reward` handles era ≥ 64; retarget products fit in `u128`;
  proptest found no panics on fully random `u64`/`i64` inputs.
- **No admin back door:** there is no instruction to change rules after setup. Only the upgrade
  key can, which is why giving it up matters. *(Update 1 Nov 2026: `set_schedule` now lets the
  upgrade-key holder lower the reward or move the halving later, never raise the reward, never pass
  the cap. It checks the upgrade authority through ProgramData, so it dies with the upgrade key.)*

## Theory only (no fix made; listed so Josh can weigh them)

1. **SHA-256 isn't CPU-only.** GPUs and ASICs hash far faster than PCs. Fairness, not a bug; the
   whitepaper says "CPU-mineable, not CPU-only". A memory-hard hash would be a big redesign.
2. **The clock comes from validators.** Retarget uses `Clock::unix_timestamp`. On the private
   network the validator is ours. On mainnet it's a stake-weighted estimate with bounded drift,
   so validators could nudge difficulty slightly, never more than the 4x clamp.
3. **Leaders can censor or reorder.** A Solana leader could drop other miners' transactions or put
   its own first. It still can't steal a winning guess or mint without work.
4. **Batching blocks.** Because the next challenge includes the slot, a miner who predicts the
   slot their transaction lands in could pre-solve the next block and send two `mine`
   instructions together. They still do all the work, and a wrong guess wastes it. Low impact.
5. **Rounding on the hard side.** The 4x-harder limit uses `floor(window / 4)`, so a single step
   can be up to 3/window stronger than 4x (0.5% on the 600 s window). Always against the miner,
   never easier.
6. **Hashrate drop.** If miners leave, difficulty only eases at the next 10-block boundary, so a
   sudden drop could stall blocks for a while (same as Bitcoin, on a much shorter cycle).
7. **64-bit target.** Only the first 8 bytes count, so the hardest possible target is about
   2^64 hashes per block. That's far beyond any hobby network.
8. **Name and logo** can still be changed by the setup wallet until that's locked (roadmap item).
9. **Halving every 210,000 one-minute blocks** is about 146 days, not 4 years. Rule choice for Josh,
   not a bug; unchanged here. *(Update 1 Nov 2026: changed on the private network to 20 SUMO a block,
   halving every 525,600 blocks, about a year. Total still capped at 21M.)*
