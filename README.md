# Sumo Frog ($SUMO)

A toy coin you can mine with your PC, living on a **private Solana test network** on Josh's
Oracle server (public devnet later, once the devnet faucet works for us).

- **Test networks only.** The private network and devnet are free test networks. Nothing on them has value.
- **$SUMO is worthless** and can't be bought, sold or swapped. It's a learning project.
- **No real money is involved.** Never put a real wallet, seed phrase or real SOL anywhere near it.

| | |
|---|---|
| Program ID | `6h1PqXArg2Ap1CJdR1hXXWhqSrzkeboqi5cx1y44NvTW` |
| Token mint | `7VNZhAWFCKjrZVKcbU2sXxT5mNAbzYh8qmtD7HfePabR` |
| Game state | `AjCSGvVNV2FcDxGjMQbc2QEuJMx144XpuivkDX4e4Pad` |
| Network | private Sumo test network (genesis `9eDPpAG4RUei7HTciCEucnshXm6Rfo61d6KU8hyXwx6n`); the RPC address is in `miner/sumo_config.json` (copy from `miner/sumo_config.example.json` — same for `stats/sumo_config.example.js` and `assets/metadata.example.json`) |
| Stats page | the gateway's front page (same address as the RPC, port 8080) |
| Encryption | none yet: the private test link is plain `http` until launch (Josh, 2 Nov 2026). The miner says so at startup and before any withdraw |

The public Solana Explorer can't see the private network, so there are no explorer links for now.

Mascot: an 8-bit sumo frog (v4 look: pixel art, synthwave sunset, high contrast). The art is made by
`mockups_8bit/v4/art.py`, `scripts/make_miner_art.py` and `scripts/build_site.py`.

Docs: [whitepaper](docs/whitepaper.md) · [mining guide](docs/mining-guide.md) · [payout address](docs/payout-address.md).

## Local config

This repo ships **example** configs only (no private server address):

```bash
cp miner/sumo_config.example.json miner/sumo_config.json
cp stats/sumo_config.example.js stats/sumo_config.js
cp assets/metadata.example.json assets/metadata.json
```

Then edit `YOUR_SERVER` in those files to your own test gateway. The real files are gitignored.


## The rules

| Rule | Value |
|---|---|
| Reward | 20 SUMO per block (the first 34 test blocks paid 50 under the old draft rules) |
| Halving | Once a year: every 525,600 blocks (365 days of 60-second blocks) |
| Max supply | 21,000,000 SUMO, with 9 decimals |
| Target block time | 60 seconds |
| Difficulty retarget | Every 10 blocks, never more than 4x in one go |
| Starting difficulty | 28 bits (about 268 million guesses per block) |

The 21M cap is checked on every block, so the total can never pass it. With the 1,700 SUMO already
mined at 50 a block, mining ends after about 9.8 years (see the whitepaper's table).

## How mining works

1. The program stores a random **challenge**.
2. Your PC tries guess numbers (guess #1, #2, ...) and hashes `sha256(challenge + reward address + guess #)`.
   The reward address is the miner's wallet, or your payout address if you set one.
3. If the hash starts with enough zeros, that's a block. The miner sends it to the program.
4. The program checks the hash itself, mints 20 SUMO to the reward address, and picks a new challenge.

The reward address is part of the hash, so nobody can steal your answer or redirect its reward. The challenge changes
after every block, so an answer only works once. If someone else finds the block first, your
miner notices and moves on to the new one.

## Mining on Windows

**Easiest way (no Python knowledge needed):** unzip `sumo_miner_win.zip` into the miner folder and double-click
`Mine SUMO.bat`. It reuses `.venv` if one is there (or makes one), installs `solders` only if it's missing,
makes a test wallet only if `sumo-devnet-key.json` doesn't exist, gets test SOL for a new wallet, then mines.
`Check balance.bat`, `Get test SOL.bat`, `Set payout address.bat` and `Withdraw SOL.bat` do what they say. Plain steps are in `miner/HOW TO MINE.txt`.
Build the zips with: `python3 scripts/build_zips.py` (writes `dist/sumo_miner_win.zip` and `dist/sumo_miner_friends.zip`).

The manual way:

1. **Install Python** 3.10 or newer from https://www.python.org/downloads/.
   Tick **"Add python.exe to PATH"** in the installer.
2. **Unzip** this folder, then open a Command Prompt in the `miner` folder.
   An easy way is to type `cmd` in the File Explorer address bar.
3. **Install the one dependency:**
   ```
   py -m pip install -r requirements.txt
   ```
4. **Make a test-only wallet:**
   ```
   py sumo_miner.py new-key
   ```
   This saves `sumo-devnet-key.json` and prints your address. Keep the file to yourself.
   It's only for test networks, so never send real SOL to it.
5. **Get free test SOL for fees:**
   ```
   py sumo_miner.py faucet
   ```
   That gives you 1 test SOL (worthless), which is enough for thousands of blocks. Each block
   costs about 0.000005 SOL in fees, plus 0.002 SOL once to open your SUMO account. The faucet
   allows one request every 10 minutes and 5 a day.
6. **Mine:**
   ```
   py sumo_miner.py mine
   ```
   Press Ctrl+C to stop. Other commands:
   - `py sumo_miner.py mine --blocks 5` stops after 5 blocks.
   - `py sumo_miner.py mine --workers 8` uses 8 CPU threads. The default is all of them.
   - `py sumo_miner.py balance` shows your SUMO and test SOL.
   - `py sumo_miner.py status` shows blocks mined, difficulty, reward and supply.
   - `py sumo_miner.py mine --payout <your PUBLIC address>` sends rewards to your own wallet.
     `py sumo_miner.py set-payout <address>` saves it for next time (`set-payout none` clears it).
     The miner's own test wallet still pays the fees. Never type a seed phrase or private key: the miner refuses them.
   - `py sumo_miner.py mine --plain` turns off the colours and pixel art.
   - `py sumo_miner.py withdraw [<your PUBLIC address>]` sends the miner wallet's leftover test SOL
     to your wallet (default: your payout address, confirmed on screen). It shows the amount, the
     address and the fee, and asks y/N first (`--yes` skips that). It sends everything minus the fee,
     so the miner's wallet closes. `--sumo` also sends the miner wallet's SUMO (and closes its SUMO
     account). Same address checks as `set-payout`, plus it refuses program addresses and the
     miner's own address.

The miner refuses to run on any network except the private Sumo network (its genesis hash is
pinned in `miner/sumo_config.json` as `private_genesis`), devnet, or a local test validator.
It always refuses mainnet. To use devnet later: `py sumo_miner.py mine --rpc https://api.devnet.solana.com`.

## Stats page

Open the gateway's front page (the RPC address from `miner/sumo_config.json`, in a browser), or `stats/index.html` from the zip. It shows:

- blocks mined
- difficulty
- reward
- supply
- top miners
- recent activity

It reads the network directly and refreshes every 20 seconds. Add `?rpc=<url>` to point it
somewhere else, e.g. `?rpc=https://api.devnet.solana.com`.

## For developers

- **Program:** `programs/sumofrog/src/lib.rs`, written in Rust with Anchor 0.32. It has 5 instructions:
  - `initialize`: one-time setup. Only the upgrade authority can run it.
  - `create_metadata`: adds the Metaplex name, symbol and image.
  - `mine(challenge, guess)`: checks a solution and mints the reward to the signer.
  - `mine_to(challenge, guess)`: same, but pays a `payout` wallet (bound into the hash); the signer
    only pays fees, and the payout's token account is created if needed.
  - `set_schedule(reward, halving)`: upgrade authority only. Can only make the schedule meaner
    (see below), never raise the reward, delay halving or pass the cap. Dead once the upgrade key is given up.
    Used once on 1 Nov 2026 (`scripts/set-schedule.ts`) to move to 20 SUMO, yearly halving.
- **Mint authority** is the program's config PDA, so SUMO can only be minted by a valid solution.
  There's no freeze authority.
- **Tests:** `scripts/test-local.sh` runs everything, all on the box (never the Oracle server).
  It starts its own local validator on its own ports on this machine (RPC port 18999, not the default 8899),
  stops only that one when it ends, and cleans up its temp files and throwaway key with a `trap`
  even if a step fails. It refuses to start if something already uses port 18999.
  While it runs, the validator's RPC and faucet ports listen on all of this machine's network
  interfaces, not only 127.0.0.1 (this validator version has no option to limit them). It's a
  throwaway test chain with nothing of value, and it's deleted when the run ends.
  1. **Golden vectors.** `scripts/gen_vectors.py` is a Python copy of the program's maths
     (`work_value`, halving, retarget with the 4x clamp, and the three challenge hashes).
     It writes `tests/vectors/golden.json`, and the script fails if that file is out of date.
  2. **Rust unit tests** (`cargo test -p sumofrog --lib`) check the Rust against those vectors,
     plus **property/fuzz tests** (proptest, 4,096 random cases each per run): retarget never
     panics or returns 0, matches exact maths, moves at most 4x and never gets harder when blocks
     are slower; the supply cap always holds; work value orders like the hash; a guess is bound to
     its reward address and challenge; the yearly 20 SUMO schedule never passes 21M.
  3. **Anchor build**, then the **TS integration tests** on a throwaway local validator. They cover:
     upgrade-authority-only init, the retarget-window limit, metadata, invalid solutions,
     substituted accounts (fake mint, someone else's token account), valid solutions, replays,
     miner binding, payout addresses (`mine_to`), `set_schedule` permissions and limits, retargeting,
     halving, the supply cap, and the compute units of `mine` and `mine_to`.
  4. **Test-count guard.** It fails if fewer tests pass than `tests/test-count-baseline.txt`
     (currently 57: 30 Rust + 27 TS, of which 7 are the offline preview tests), or if any test fails or is skipped. This stops tests being
     quietly deleted. Only ever raise the number.
- **Compute units for `mine`** (baseline in `tests/cu-baseline.json`, measured 30 Oct 2026 and re-measured
  31 Oct after the overflow guard and 1 Nov after `mine_to`, on a local validator; the test fails if a sample goes more than 5% over):

  | Case | CU |
  |---|---|
  | First block for a wallet (creates its token account) | 35,014 |
  | Normal block | 17,246 |
  | Block that also retargets difficulty | 19,796 |
  | `mine_to`, first block for a payout wallet | 44,544 |
  | `mine_to`, normal block | 20,622 |

- **Using AI on this code:** read [`AGENTS.md`](AGENTS.md) first. Agents load
  [`docs/solana-prompt.md`](docs/solana-prompt.md) (Jump Crypto's Solana prompt, Apache 2.0)
  before editing the program. It is written for Pinocchio; this program uses Anchor, so skip
  the Pinocchio parts.
- **Private network:** `server/` holds the server side: `sumo-validator.service` (Agave 4.1.1
  `solana-test-validator`, localhost, capped CPU/memory/ledger) and `sumo-gateway.service`
  (`sumo_gateway.py`: allowlisted JSON-RPC, rate-limited faucet, stats page on port 8080).
  See `server/README.md`.
- **Deploy:** run `scripts/deploy-devnet.sh [metadata-uri] [demo-blocks]` (set `SUMO_RPC`).
  It needs about 2.1 devnet SOL in the deployer key, which is mostly program rent.
  You can get that back later with `solana program close`.
- **Keys** live in `.keys/` and are git-ignored. They're test-network-only throwaway keys.
- **Default wallet (`Anchor.toml`)** is `.keys/test-wallet.json`, a local test key, never the
  upgrade key, so a stray `anchor deploy` or `anchor upgrade` can't use the upgrade key by
  accident. Make it once with `solana-keygen new --no-bip39-passphrase -o .keys/test-wallet.json`.
  Only deploys pass the upgrade key, and they pass it explicitly:
  `scripts/deploy-devnet.sh` uses `--keypair .keys/deployer.json`, and `scripts/setup.ts` /
  `scripts/set-schedule.ts` take it through `ANCHOR_WALLET=.keys/deployer.json`.
- **Upgrade key (`.keys/deployer.json`)** is the program's upgrade authority: whoever holds it
  can replace the program and call `set_schedule`. It must be its own throwaway test wallet,
  used for nothing else, and never a wallet with real funds. Local test runs
  (`scripts/test-local.sh`) make a fresh throwaway authority each run instead of using it.
  Giving it up (and locking the token name and logo with `is_mutable = false`) is a launch-day
  step that needs Josh's yes.
- **`set_schedule` (tightened 2 Nov 2026):** a change can only make the schedule meaner. No block,
  now or later, may pay more than the current schedule, and halving can't be delayed or turned
  off. The new halving interval can't be less than half the current one, and never less than a
  fixed floor of 262,800 blocks (`MIN_HALVING_INTERVAL`, half the yearly 525,600), so neither a typo
  (41 for 525,600) nor a run of repeated halvings can end issuance early. A schedule already
  shorter than the floor (local test chains) can only keep its interval. Once the first halving has
  happened, no change passes at all. `scripts/set-schedule.ts` shows the first halved block (numbered
  like the miner, e.g. #525,601) and its UK date, the projected total supply against both the
  current and the original schedule (20 SUMO, yearly halving), and when issuance ends and why
  ("cap reached" or "reward reaches zero"). It only sends after a typed `YES`.
- **Miner safety checks (2 Nov 2026):** every payout path (`--payout`, `set-payout`,
  `payout-address.txt`, `"payout"` in `sumo_config.json`) refuses the program, config and mint
  addresses, token accounts and other program-controlled addresses. Network links must be
  `https`, except this computer (`localhost`, `127.0.0.1`, `::1`) and the private network link
  shipped in `sumo_config.json`, which stays `http` until launch. Whenever the miner uses that
  link it shows, at startup and again before any withdraw: "Note: the
  private test link isn't encrypted. Fine for test coins with no value. Always check the payout
  address you type." The colour mining screen pins a short version to its footer ("Note: test
  link isn't encrypted. Check your payout address."); `--plain` shows the full note. Someone on the same network could fake the miner's screens, so the program,
  not the miner, is the real safety net. New wallet
  files are owner-only (600). Offline checks: `python3 tests/miner_checks.py`.
