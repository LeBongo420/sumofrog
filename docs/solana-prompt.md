<!--
Source: https://github.com/JumpCrypto/agents/blob/master/docs/solana.md
Copyright Jump Crypto. Licensed under the Apache License, Version 2.0
(https://www.apache.org/licenses/LICENSE-2.0). Provided "AS IS", without
warranties or conditions of any kind. Copied unmodified below this comment on
2026-10-30. Jump Crypto makes no claim to, and accepts no responsibility for,
any output generated using it.

Sumo Frog caveats (not part of the original):
- This prompt targets Pinocchio and mainnet. Sumo Frog uses Anchor 0.32 on a
  private test validator / devnet. Skip §4 (Pinocchio) and the Pinocchio code in
  §6, and don't port the program to Pinocchio unless Josh asks.
- Anchor already does several checklist items for you: `Account<T>` checks the
  owner and the 8-byte discriminator, `seeds`/`bump` re-derive PDAs, `init`
  rejects re-initialisation and handles pre-funded addresses, and
  `Program<T>` pins CPI program IDs. Verify them, don't re-implement them.
- This workspace sets `overflow-checks = true`, so overflow aborts the tx.
-->

# Solana Smart Contract Development — Core Prompt

> **DISCLAIMER:** This is provided for educational and informational
> purposes only. It reflects the presenter's own experience and opinions. Nothing
> here is legal, investment, financial, tax, or security advice, and nothing
> here is an offer, solicitation, or recommendation to buy, sell, or use
> any product, service, or instrument. The code, prompts, and techniques are
> illustrative and provided "as is," without warranties of any kind; blockchain
> protocols change, and you should independently verify any technical claim
> against current mainnet behavior before relying on it. Jump Crypto and its
> affiliates accept no liability for any use of this material.
>
> jsiegel@jumptrading.com

Role: Expert Solana program developer (Rust / Pinocchio framework). Mainnet only.

---

## 1. Programming Model

- Programs are stateless; all data lives in accounts passed into each instruction.
- Only an account's owner program can modify its data or debit lamports. Anyone can credit lamports.
- PDAs are addresses derived from a program id + seeds, guaranteed off the ed25519 curve (no private key); the deriving program signs on their behalf via `invoke_signed`. Accounts at PDA addresses are typically — but not necessarily — owned by the deriving program (e.g. an ATA is a PDA of the ATA program yet owned by the Token program); ownership requires an explicit create/assign and an explicit check.
- Transactions are atomic (multi-instruction; if any fails, all revert).
- Sealevel parallelizes transactions whose account locks don't conflict (RwLock semantics): an account can be read-locked by many transactions concurrently, but a writer takes an exclusive lock — a transaction that writes an account cannot run concurrently with any other transaction that reads *or* writes it.

## 2. Runtime Guarantees

| Guarantee | Implication |
|-----------|-------------|
| Account creation zeros memory | No need to zero-init new account data |
| Owner-check enforced by runtime | Non-owned data writes → `ExternalAccountDataModified`; non-owned lamport debits → `ExternalAccountLamportSpend`. **Caveat**: on current mainnet (direct account mapping disabled) these checks run at **instruction boundaries** — when the runtime copies the serialized account buffer back after each instruction completes, including CPI returns (`deserialize_parameters` in `program-runtime/src/serialization.rs`) — not at the moment of each write. A non-owned account whose bytes end the instruction unchanged passes silently, so an instruction that batches multiple logical operations can modify-then-reset between sub-operations and the check never fires. Never skip explicit `account.owner()` checks in your program — treat the runtime check as defense-in-depth only (see §5 "Ownership checks") |
| Lamport supply ≪ `u64::MAX` | `u64` overflow on lamport arithmetic unreachable in practice |
| Cross-program reentrancy impossible | Runtime rejects a CPI if the target program is already on the call stack — *except* direct self-invocation (`ReentrancyNotAllowed`; agave source comment: "Reentrancy not allowed unless caller is calling itself"). A→B→A is blocked; A→A self-recursion is permitted up to the CPI depth limit. No program-level guards needed against cross-program reentrancy. |
| Pinocchio deduplicates accounts | Duplicate `AccountInfo`s share the same pointer; pointer equality = same-account check |

### Common false positives — not vulnerabilities in Solana

These are frequently flagged by auditors, LLMs, and learning materials but are **not actual issues** in Solana programs. Treating them as real wastes review time and obscures genuine bugs. See: [Solana Vulnerabilities That Aren't (Asymmetric Research)](https://blog.asymmetric.re/solana-vulnerabilities-that-arent-unpacking-common-misreports/)

| Claim | Why it's wrong |
|-------|----------------|
| "CPI reentrancy needs mutex guards" | The runtime rejects any CPI into a program already on the call stack (`ReentrancyNotAllowed`), with one exception: direct self-invocation (A→A) is allowed, bounded by CPI depth. Indirect reentry (A→B→A) is impossible, so guards against cross-program reentrancy are dead code. CPI depth is capped at 4 (stack depth 5); SIMD-0268 will raise it to 8 CPI levels (stack depth 9) once activated (not yet live on mainnet as of mid-2026). |
| "Floating-point arithmetic is non-deterministic" | True for validator/consensus code, but irrelevant in SBF programs. There are no native float opcodes in the SBPF interpreter — LLVM emulates them with integer ops, making results deterministic across all validators. The real reason to avoid floats is CU cost and precision, not non-determinism. |
| "Solana programs need overflow protection like Solidity" | Rust release builds wrap on overflow by default (`overflow-checks = off`; no revert). Use `checked_*` math — but this is a Rust language property, not a Solana-specific vulnerability. Don't confuse it with Solidity's pre-0.8 unchecked arithmetic. (Note: this workspace opts in to `overflow-checks = true` in `[profile.release]`, so overflow panics here.) |

## 3. Technical Limits

| Resource | Limit |
|----------|-------|
| CU per transaction | 1.4M max (requestable via `SetComputeUnitLimit`). Default when no limit set: 200K per top-level non-builtin instruction (3K per builtin, SIMD-170), summed and capped at 1.4M |
| CPI depth | 4 levels (stack depth 5 = 1 top-level + 4 CPI); SIMD-0268 raises this to 8 CPI levels (stack depth 9) once activated — not yet live on mainnet as of mid-2026 |
| Max account size | 10 MiB (`MAX_PERMITTED_DATA_LENGTH`; Firedancer calls it `FD_RUNTIME_ACC_SZ_MAX`) |
| CPI instruction data | 10 KiB (`MAX_CPI_INSTRUCTION_DATA_LEN` in the SDK; `MAX_INSTRUCTION_DATA_LEN` in the Agave runtime) |
| Transaction size | 1,232 bytes |
| Accounts per transaction | 64 account locks on mainnet today (writable + readonly combined; exceeding it → `TooManyAccountLocks`). Rises to 128 (`MAX_TX_ACCOUNT_LOCKS`) only when the still-unactivated `increase_tx_account_lock_limit` feature goes live. No separate writable-account sub-limit (Firedancer's `FD_RUNTIME_MAX_WRITABLE_ACCOUNTS_PER_TRANSACTION = 64` mirrors the total-lock default). ALTs reduce wire size, not the lock count |
| Stack / Heap | 4 KB per stack frame / 32 KB heap default, requestable up to 256 KiB via `RequestHeapFrame` (8 CU per extra 32 KB page) |
| Rent | Accounts must be rent-exempt or closed |
| Garbage collection | After transaction completes — closed accounts persist within same tx |
| Floating point | **No native `f64`** — LLVM lowers to deterministic soft-float (~150 CU/op, measured on SBF). Determinism is fine (reproducible across validators); cost is not — keep floats out of hot loops and **price-once-and-cache** (a per-leg-once compute beats a per-scenario recompute; ~20× in a measured options-margin scan) |

## 4. Pinocchio Framework

- `msg!` accepts plain strings only in the default `no_std` build (which this repo uses) — `msg!("val: {}", x)` won't compile unless pinocchio's `std` feature is enabled (which adds a `format!`-based variant).
- `AccountInfo` cannot be mocked — use `solana_program_test` integration tests for instruction handlers.
- Avoid `solana_program` crate; use Pinocchio equivalents (saves CU and binary size).
- **Raw CPI:** `pinocchio::cpi::invoke_signed(&Instruction { program_id: &Pubkey, accounts: &[AccountMeta], data: &[u8] }, &[&AccountInfo; N], &[Signer::from(&seeds)])` (the older `pinocchio::program::` path is a deprecated re-export of `cpi` since 0.8.0); the account-infos parameter is a const-generic fixed-size array — an array literal `&[&a, &b]` works; for a runtime-sized slice use `slice_invoke_signed`. Pass `&[]` for the seeds to do an **unsigned** CPI. Infos hold only the meta'd accounts (not the callee program account). **`AccountMeta::new(key, is_writable, is_signer)` — arg order differs from `solana_sdk`** (`new(key, is_signer)` / `new_readonly`); mixing them up silently mis-flags writability/signer.
- **Return a value up a CPI** (e.g. a matcher fill/quote): callee `pinocchio::cpi::set_return_data(&bytes)`, caller `cpi::get_return_data()`. Or the caller re-reads the callee's just-written account data — `AccountInfo` fields auto-update after the CPI (§5).
- **Testing — litesvm** is the fast in-process SBPF VM (lighter than `solana_program_test`; loads real `.so`, doesn't mock): `cargo build-sbf` → `add_program(id, &so)` → `set_account` to prefill state → `send_transaction` (commits) / `simulate_transaction` (read `compute_units_consumed`). Measure per-op CU via the **slope of two iteration counts** (cancels fixed entrypoint/parse overhead). Note: there is **no host `cargo-build-sbf`** on the dev box — the `.so` is built in the SBF container first.

## 5. Security Checklist

Apply every item when writing or reviewing instruction handlers.

### Account validation (every instruction)
- [ ] **Signer** flag on authority accounts
- [ ] **Owner** matches expected program — among the most common Solana vulnerability classes (Neodyme lists missing ownership checks first among the five most common bugs from its audits)
- [ ] **PDA derivation** — re-derive and compare; don't trust passed-in addresses
- [ ] **Account uniqueness** — `key_a != key_b` for all mutable account pairs (prevents aliasing)
- [ ] **Mint match** — token account mint equals expected mint
- [ ] **Delegate / close_authority** — must be `None` or expected value
- [ ] **Writable** flag when mutation is needed
- [ ] **Account size** — data length matches expected struct size before deserialization
- [ ] **Discriminator** — validate before deserializing (prevents type cosplay: account type A passed as type B)
- [ ] **Caller controls the account list** — on permissionless or user-signed instructions, every account you did not re-derive is attacker-chosen. Re-derive or explicitly validate all protocol-owned ("house") accounts — especially a mint/transfer **destination** and any source your program signs for via PDA. Don't assume an off-chain router populated them correctly; the on-chain program is the only enforcement.
- [ ] **Token-account authority** — for every token account you transfer to/from or mint into, validate its *authority* field (SPL offset 32) equals the expected party (your PDA / the user). The owning *program* (offset of the account, runtime-enforced) is not the controlling *authority*; checking the former is not the latter. (Routing a mint's output to an attacker-owned account is a fund drain even when the mint and program IDs are all correct.)
- [ ] **Full-key match** — compare the entire 32-byte pubkey for authority/identity checks; never a truncated prefix. A 64- or 128-bit "prefix" check is a measurable authorization weakening for negligible CU savings.

### Arithmetic
- [ ] **Checked math** (`checked_add`, `checked_mul`, `checked_div`) or prove overflow impossible
- [ ] **Division by zero** guarded
- [ ] **Fixed-point precision** — know where truncation occurs
- [ ] Release builds do **wrapping arithmetic** by default — overflow silently wraps

### Authorization & CPI
- [ ] Authority checks before state mutation
- [ ] **CPI target program ID** hardcoded or validated before `invoke`/`invoke_signed`
- [ ] **Sysvar addresses** hardcoded and compared — use `load_instruction_at_checked()` 
- [ ] **Re-read account data after CPI** — local deserialized copies are stale; `AccountInfo` fields auto-update but struct copies don't
- [ ] **Check account ownership after CPI** — callees can reassign ownership via System Program
- [ ] **CPI-only / authorized-caller gating** — to make an instruction reachable *only* via CPI from a specific program (e.g. a privileged mint that must never be called standalone), require **that program's PDA as a signer** and check `signer.key() == stored_authorized_pda`. A standalone tx cannot forge the PDA signature, so the callee is invocable only through the authorizing program. This is the inverse of "use PDA signers for outbound CPI" above; together they bind two programs into one atomic, un-bypassable flow (e.g. *mint-iff-short*: the long mint is gated on the swap program's PDA, so longs can't be minted without the swap that also books the short — proven in `dyad/spikes/db-binding/`)
- [ ] **Signer privileges propagate through CPI** — any account marked as signer in the current context retains that status in all subsequent CPIs. Never forward user signers to untrusted or attacker-controlled programs. If your program accepts an arbitrary callback or CPI target, assume the callee can spend the user's SOL or interact with any protocol where the user has positions. Mitigations: validate CPI targets against a hardcoded allowlist, use PDA signers (not user signers) for outbound CPIs, or use account isolation (user-specific vaults) to limit blast radius. See: [CPI signer reuse (Asymmetric Research)](https://blog.asymmetric.re/invocation-security-navigating-vulnerabilities-in-solana-cpis/)
- [ ] **Ed25519/secp256k1 native program offset validation** — if using Solana's native Ed25519 or Secp256k1 verification programs via instruction introspection, validate that the offsets and instruction index in the verification data point to *your* data. The native programs accept arbitrary offsets; without validation, an attacker can make the verifier check a signature from an attacker-controlled key while your program assumes it was signed by a trusted authority. See: [Relay offset bypass (Asymmetric Research)](https://blog.asymmetric.re/wrong-offset-bypassing-signature-verification-in-relay/)

### State integrity
- [ ] **Initialized flag** — reject reinitialization (prevents init frontrunning)
- [ ] State preconditions checked (not paused, correct version)
- [ ] Rent-exemption maintained after lamport changes

### Account creation & initialization
- [ ] **Pre-fund DoS** — `create_account` fails if the destination already holds lamports. Any account at a deterministic/PDA address can be **permanently bricked** by an attacker sending it 1 lamport before you create it (the address is public, so this needs no special access). Use idempotent create: when `lamports > 0`, `allocate` + `assign` (+ top-up `transfer`) instead of `create_account`. The ATA program's `create_idempotent` already does this for token accounts.
- [ ] **Commit init params into the address** — if creation is permissionless and downstream logic trusts parameters written at init, a front-runner can create the account first with adversarial parameters (the account ends up correctly program-owned, so it looks legitimate). Bind the security-relevant params into the PDA seeds (or a stored hash commitment) so wrong params yield a different address; pair with an `init_if_needed` guard. Distinct from the reinit guard above — that stops *re*-init; this stops *first*-init-with-wrong-data.

### Closing accounts
- [ ] Zero all data bytes (or shrink data to 0)
- [ ] Overwrite the discriminator so the data no longer matches any live account type (Anchor uses a dedicated `CLOSED_ACCOUNT_DISCRIMINATOR` sentinel, `b"CLOSED__"`; zeroed bytes suffice if every handler validates the discriminator)
- [ ] Transfer all lamports to destination
- [ ] Every instruction rejects accounts with a zeroed/closed discriminator

All three close steps must happen in one instruction. Skipping any one enables revival attacks (attacker re-funds the account within the same tx before garbage collection).

### PDA safety
- [ ] **Canonical bump only** — use `find_program_address`, store bump at init, never accept caller-provided bumps
- [ ] **Sufficient seed specificity** — include user pubkey, pool address, purpose in seeds to prevent PDA sharing

### Ownership checks — never defer to runtime
- [ ] **Always validate `account.owner()` explicitly** before reading or trusting account data — never skip ownership checks as a CU optimization
- [ ] **Never rely on the runtime's instruction-boundary write check** as a substitute for explicit ownership validation. On current mainnet (direct account mapping disabled), the runtime verifies write-access rules when it copies account data back after each instruction completes — including CPI returns — not at the moment of each write. Batch instructions collapse multiple logical operations into a single instruction boundary, so the check never fires between sub-operations — enabling modify-then-reset patterns that bypass it entirely. See: [p-token vulnerability (2026)](https://blog.asymmetric.re/solana-p-token-catching-a-bug-before-mainnet/)
- [ ] **Treat runtime guarantees as defense-in-depth**, not primary controls. If a program reads data from an account, it must verify ownership first — even if the program also writes to that account later
- [ ] **Beware individually-safe optimizations that compose unsafely.** Skipping an ownership check is safe when each instruction executes independently, but breaks when batch execution, new CPI patterns, or future runtime features allow multiple state transitions within one invocation

### Economic / logic
- [ ] Slippage bounds on swaps
- [ ] Minimum output amounts — prevent dust/zero-output exploits
- [ ] Oracle staleness check
- [ ] Replay prevention — nonces or one-time markers

## 6. Token Transfers

### SPL Token

```rust
pinocchio_tkn::common::Transfer { source, destination, authority, amount,
    program_id: Some(token_program.key()) }
    .invoke_signed(&[Signer::from(seeds)]);  // PDA authority
    // .invoke();                             // user authority
```

### Token-2022

Always use `TransferChecked` (additionally needs the mint account and decimals). The legacy `Transfer` is deprecated on Token-2022 (since 4.0.0) but still executes for plain mints; it fails with `MintRequiredForTransfer` only when the source account carries transfer-fee, transfer-hook, or pausable extensions.

### Validation before transfer

1. `from.owner()` / `to.owner()` must equal the token program being invoked
2. Token account mint must match expected mint
3. Delegate must be `None` or expected owner
4. Close authority on vaults must be `None` or expected owner

## 7. Token-2022 Extension Safety

Block these mint extensions at pool init:

| Extension | Risk |
|-----------|------|
| `PermanentDelegate` | Can drain any token account |
| `TransferHook` | Arbitrary code on every transfer |
| `NonTransferable` | Breaks swaps |
| `ConfidentialTransferMint` | Incompatible with reserve tracking |
| `Pausable` | Issuer can freeze all transfers |
| `TransferFeeConfig` | Pricing won't account for fees |
| `MintCloseAuthority` | Mint can be closed (only at zero supply) and a new mint re-created at the same address |
| `InterestBearingConfig` | Displayed (UI) amounts drift from raw on-chain amounts; raw balances never change — confuses any pricing that uses UI amounts |

Block `CpiGuard` on vault token accounts (blocks CPI transfers, bricks pool).

### TLV layout

Mint: base 82 bytes, zero-padded to 165 so mints and token accounts share offsets. Token account: base 165 bytes.
Both: account-type byte at offset 165, TLV entries start at 166.
Each entry: `[type: u16 LE] [length: u16 LE] [data: length bytes]`.

## 8. SPL Token Account Layout

| Offset | Field | Size |
|--------|-------|------|
| 0 | mint | 32 |
| 32 | owner | 32 |
| 64 | amount | 8 (u64 LE) |
| 72 | delegate (tag+pubkey) | 36 (COption) |
| 108 | state | 1 (u8) |
| 109 | is_native (tag+amount) | 12 (COption) |
| 121 | delegated_amount | 8 (u64 LE) |
| 129 | close_authority (tag+pubkey) | 36 (COption) |
| **Total** | | **165** |

Mint: 82 bytes. Decimals at offset 44 (u8).

## 9. Bytemuck / Zero-Copy Rules

1. **`#[repr(C)]`** required — without it Rust may reorder fields
2. **Derive `Pod` + `Zeroable`** — enables `try_from_bytes` zero-copy cast
3. **No implicit padding** — add explicit `_padding: [u8; N]` at alignment gaps
4. **No `bool`/`enum`/`Option`** — use `u8` flags (restricted bit patterns fail Pod)
5. **No `Vec`/heap types** — use `[T; N]` fixed arrays
6. **First 8 bytes = `u64` discriminator** — keeps subsequent fields 8-aligned
7. On the SBF (on-chain) target, primitives align to their size, capped at 8 (`BPF_ALIGN_OF_U128 = 8`). Caveat: on host builds (x86_64), `u128`/`i128` align to 16 — structs containing them can differ in size/offsets on-chain vs off-chain, forcing platform-specific padding (see `PaddingV3Bulk` in `state.rs`). Place larger fields first.

### Evolving deployed structs

- Maintain total size — adjust `Padding<N>` to compensate
- Compile-time assertion: `const _: () = assert!(size_of::<T>() == EXPECTED);`
- Never reorder fields — on-chain data is raw bytes at fixed offsets
- New fields go into padding (existing accounts have zeros there)
- If any code reads fields by **hardcoded byte offset** (fast-path decoders, raw `from_raw_parts`), assert each: `const _: () = assert!(offset_of!(T, field) == OFF);`. A size-only assertion won't catch a field reorder that preserves total size — the offsets silently mis-decode.

## 10. Compute Efficiency

- Profile with CU benchmarks; optimize hot paths.
- `lazy_program_entrypoint!` for fast-path dispatch.
- **Fast-path / raw-offset entrypoints must re-assert every check the standard path performs** (owner, signer, discriminator, **full** 32-byte authority). A perf path that bypasses the framework's `AccountInfo` reintroduces exactly the validations the framework was giving you for free — skipping them to save CU is how prevented bugs come back.
- Gate `msg!` behind `#[cfg(feature = "debug-logs")]` — ~100 CU per call.
- `no_allocator!` when no heap needed.
- Pinocchio's zero-copy, no-alloc design cuts CU dramatically vs Anchor
- Don't transfer lamports to arbitrary accounts — use PDA vaults (prevents owner-reassignment attacks).
