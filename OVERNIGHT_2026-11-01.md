# Overnight work, 1 Nov 2026

Everything stayed on test networks. Nothing went to mainnet, nothing was minted for sale, and no liquidity was added.
No new ports or tunnels were opened. The admin tunnel used for the upgrade is closed. All commits are local only, as LeBongo420, and nothing was pushed.

## What changed

1. **Miner v0.5, in the 8-bit synthwave look (v4)** (`miner/sumo_miner.py`, `miner/sumo_art.py`)
   - It uses ANSI colours, and turns on VT mode on Windows 10/11 cmd.
   - It draws a half-block pixel frog and a navy HUD panel. The layout goes wide at 94 columns or more.
   - Every status has a word and a symbol (`***`, `>>`, `!!`), so nothing depends on colour alone.
   - It says "guess #" everywhere and never "nonce". The scroll and ink wording is gone.
   - `--plain` (or NO_COLOR) gives a plain text screen. Old consoles fall back to plain on their own.
   - New options: `--payout <address>`, `set-payout`, `Set payout address.bat` and `--yes`.
   - The miner refuses seed phrases, private keys, key files and system addresses.
   - It shows a clear message for the program's overflow error (6005).
2. **Program upgrade on the private network** (`programs/sumofrog/src/lib.rs`)
   - New `mine_to`: rewards go to a payout address, and that address is part of the hash.
   - New `set_schedule`: upgrade key only. It can only lower the reward and can never pass the cap.
   - The old `mine` is unchanged, so old miners still work.
   - First rehearsed on a local validator with old blocks, upgrade, schedule change and new blocks. Balances were kept.
   - Then applied to the private network. The schedule is now **20 SUMO a block, halving every 525,600 blocks (yearly)**. The cap stays 21,000,000, counting the 1,700 SUMO mined before.
   - Checked by mining from the box after the upgrade:
     - block #35 to the box test wallet;
     - block #36 to a payout address;
     - block #37 during the Python 3.14 zip test.
   - All earlier holders' balances are unchanged.
3. **Whitepaper** (`docs/whitepaper.md` / `.html`)
   - Rewritten in v4. Author: lebongo420.
   - Covers yearly halving at 20 SUMO, the 21M cap with a year-by-year table, and the payout address.
   - No country's laws are mentioned.
4. **Mining guide** (`docs/mining-guide.md` / `.html` / `.png`)
   - In v4, with real-looking miner screenshots (`docs/screens/`).
   - Adds a HUD explainer, a payout section and "guess #" wording.
   - The `[DOWNLOAD LINK]` placeholder is kept.
5. **Stats page** (`stats/index.html`)
   - Moved to v4, with the header, logo and frog images.
   - Live on the gateway. The old files are backed up on the server with the suffix `.20261101_pre_v4`.
6. **Metadata logo**: `assets/metadata.json` and `sumo_frog.png` now use the v4 frog, live on the gateway.
7. **Zips**: `python3 scripts/build_zips.py` builds `dist/sumo_miner_win.zip` and `dist/sumo_miner_friends.zip`.
   - The zips are flat, with no usernames, keys or payout files.
   - Tested by unzipping into a clean folder and running under Python 3.14.
8. **Fixed**: the server address was in the README and server/README. It's gone from both.
   - It now appears only in `miner/sumo_config.json`, `stats/sumo_config.js` and `assets/metadata.json`.

## Tests

- `anchor test`: 40 passing (22 Rust + 18 TS).
- Compute units: `mine` 35,014 / 17,246 / 19,796; `mine_to` 44,544 / 20,622.
- Local upgrade rehearsal: passed.
- Private-network upgrade: passed. Blocks were mined at about 20–27 MH/s on the box.
- Python 3.14: imports with no warnings, `status` works, and mining found a block.
- Every page and image was rendered and checked by eye.

## For the morning

- Not checked on a real Windows cmd window, only simulated. Please double-click `Mine SUMO.bat` once.
- The whitepaper and guide are **not** on the gateway yet. The guide still has `[DOWNLOAD LINK]`.
- The server backup files (`*.20261101_pre_v4`) can be downloaded by anyone who knows their names. Delete them once you're happy with the new look.
- The upgrade script printed websocket errors, because the admin tunnel has no websocket. The transactions landed anyway, and I checked the program's state afterwards.

## Added later (about 21:00 UK time): Withdraw SOL

- **New `withdraw` command** (`py sumo_miner.py withdraw [ADDRESS] [--sumo] [--yes]`) and a **Withdraw SOL.bat** double-click file.
- It sends the miner wallet's leftover test SOL to a PUBLIC address. With no address it uses the saved payout address, after showing it and asking y/N.
- It sends everything minus the fee, so the miner's wallet ends at 0 and the account closes. Before asking y/N, it shows the amount, the destination and the fee.
- `--sumo` (or answering y to the prompt) also sends the miner wallet's SUMO. It opens the destination's SUMO account if needed and closes the miner's own SUMO account, which gets its rent back.
- It uses the same address checks as set-payout: seed phrases, key files, private keys, invalid addresses and system addresses are all refused. It also refuses Sumo Frog program addresses, off-curve (program-controlled) addresses, accounts owned by a program and the miner's own address. It never asks for or prints a key.
- It uses the same network guard as the other commands: it refuses mainnet and only runs on devnet, a local validator or the private network.
- **Tests:**
  - **Local validator:**
    - all 11 refusal cases;
    - no terminal and no --yes, so nothing was sent;
    - interactive runs: declined, then a seed phrase was pasted and refused, then a full send with SUMO;
    - a SOL-only send where the SUMO stayed behind;
    - an empty wallet, which reported "nothing to withdraw".
    - After the send, the miner wallet and its SUMO account were both gone. The destination had 0.99795 SOL and 20 SUMO.
  - **Private network:** a throwaway box wallet got test SOL from the faucet and mined 1 block. It then withdrew SOL + 20 SUMO to a second throwaway box wallet. The sender ended at 0 / 0 and the destination had 0.998 SOL / 20 SUMO. No real wallet was used.
  - **Python 3.14:** the zip imports with no warnings and the help text lists withdraw.
- Updated HOW TO MINE.txt, the mining guide (new section 7 and screenshot `docs/screens/miner_withdraw.png`, which uses example addresses) and README. Both zips were rebuilt and now hold 11 files.
