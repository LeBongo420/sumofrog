# Payout address for miners

**Status:** built and live on the private test network, 1 Nov 2026 (program upgrade + miner v0.5).
Design first written 31 Oct 2026.

## The question

> "To mine you connect your wallet, right?"

**No, and it stays that way.** "Connecting a wallet" (Phantom and so on) is something websites do.
The miner is a program on your PC, and it never needs your real wallet or its keys.

## How it works now

The miner signs with its own **throwaway fee key** (`sumo-devnet-key.json`, a small file holding a
little test SOL for fees). Rewards can mint either to that fee key (as before) or to **your own
wallet's public address**, which you give the miner once. You never type a seed phrase or private
key anywhere, and your real wallet never touches the mining PC. SUMO simply appears in your wallet
under that address.

```
py sumo_miner.py mine --payout <your wallet's PUBLIC address>
py sumo_miner.py set-payout <address>      (saves it in payout-address.txt; "none" clears it)
```

Or double-click **Set payout address.bat**. If the fee key file is lost or stolen, the loss is the
little test SOL in it. The SUMO is already in your wallet.

## Program side (`programs/sumofrog/src/lib.rs`)

1. A new instruction, **`mine_to(challenge, guess)`**, with a `payout` account (any address,
   read-only, not a signer). The token account is `associated_token::authority = payout` and is
   created if it doesn't exist yet (`init_if_needed`); the signer pays the fee and that one-off rent.
2. **The hash binds the payout address, not the signer:** `sha256(challenge ‖ payout ‖ guess #)`.
   If someone copies your winning guess and sends it with their own fee key, the reward still goes
   to *your* address. Anyone can relay your solution for you, which is harmless.
3. The old **`mine`** instruction is unchanged, so miners that haven't updated keep working and
   mining to yourself hashes exactly as before.
4. `BlockMined` / `last_miner` record the payout address, so the stats page shows who earned it.
5. No change to the `Config` account layout, so the private network took it as a normal program
   upgrade: no reset, all balances kept.

Tests: the reward lands at the payout address and creates its token account; a guess found for one
payout fails for another; a relayed solution still pays the original payout; someone else's token
account is refused.

## Cost (measured)

| | |
|---|---|
| Compute units | `mine_to` 44,544 the first time for a payout wallet (creates its token account), 20,622 after that; `mine` is 35,014 / 17,246 |
| Transaction size | +32 bytes (one more account) |
| Rent | ~0.002 SOL per payout wallet, once, for its SUMO token account (free test SOL on test networks) |

## How the miner protects you

- **Typo in the address:** the miner checks it's valid base58 and 32 bytes, prints it in full,
  and asks you to type YES before saving it. It shows the payout address every time it starts.
- **Someone pastes a seed phrase:** the miner refuses anything with spaces in it and says never to
  type a seed phrase or private key into anything.
- **Someone pastes a private key or key file:** anything longer than an address, or that looks like
  a key file (`[1,2,3...]`), is refused with the same warning. Nothing is saved.
- **System addresses** (the system, token and associated-token programs) are refused.
- **Sumo Frog's own addresses** (the program, its config and the SUMO mint) are refused.
- **Program-controlled addresses** (off the ed25519 curve), such as your SUMO *token account*
  (block explorers show it next to your wallet), are refused, because nobody can spend from them.
- **Token or program accounts:** when the miner can reach the network it also checks the address
  is a plain wallet, not an existing token or program account, and refuses it otherwise.
- These checks run on every payout path: `set-payout`, `--payout`, `payout-address.txt` and a
  `"payout"` entry in `sumo_config.json`, and again each time the miner starts.
- **Exchange deposit addresses:** the miner warns never to use one. Use a wallet you control.
