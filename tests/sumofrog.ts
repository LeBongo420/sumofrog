import * as anchor from "@coral-xyz/anchor";
import { Program, BN } from "@coral-xyz/anchor";
import { Keypair, PublicKey, LAMPORTS_PER_SOL, SystemProgram, SYSVAR_RENT_PUBKEY } from "@solana/web3.js";
import { getAssociatedTokenAddressSync, getMint, createMint, createAssociatedTokenAccount } from "@solana/spl-token";
import { createHash } from "crypto";
import { expect } from "chai";
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { Sumofrog } from "../target/types/sumofrog";

const UNIT = 1_000_000_000n; // 9 decimals
const METADATA_PROGRAM = new PublicKey("metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s");
const LOADER_V3 = new PublicKey("BPFLoaderUpgradeab1e11111111111111111111111");

// Small numbers so every rule is visible within a few blocks.
const PARAMS = {
  initialReward: new BN((50n * UNIT).toString()),
  halvingInterval: new BN(6),
  retargetInterval: new BN(4),
  targetBlockTime: new BN(60),
  initialTarget: new BN((1n << 56n).toString()), // ~8 bits: 1 in 256 hashes wins
  maxSupply: new BN((360n * UNIT).toString()), // 6x50 + 2x25 + a final 10
};

function powHash(challenge: Buffer, miner: PublicKey, nonce: bigint): Buffer {
  const n = Buffer.alloc(8);
  n.writeBigUInt64LE(nonce);
  return createHash("sha256").update(challenge).update(miner.toBuffer()).update(n).digest();
}
const workValue = (h: Buffer) => h.readBigUInt64BE(0);

function grind(challenge: Buffer, miner: PublicKey, target: bigint, ok = (_n: bigint) => true): bigint {
  for (let n = 0n; ; n++) if (workValue(powHash(challenge, miner, n)) <= target && ok(n)) return n;
}

async function expectError(p: Promise<unknown>, code: string) {
  try {
    await p;
  } catch (e: any) {
    // Anchor error code if the program returned one, else the message plus the program logs.
    const got = e?.error?.errorCode?.code ?? [String(e), ...(e?.logs ?? e?.transactionLogs ?? [])].join("\n");
    if (!got.includes(code)) console.log("      unexpected error:", got);
    expect(got).to.contain(code);
    return;
  }
  expect.fail(`expected ${code}`);
}

describe("sumofrog", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.sumofrog as Program<Sumofrog>;
  const [config] = PublicKey.findProgramAddressSync([Buffer.from("config")], program.programId);
  const [mint] = PublicKey.findProgramAddressSync([Buffer.from("mint")], program.programId);
  const [programData] = PublicKey.findProgramAddressSync([program.programId.toBuffer()], LOADER_V3);
  // Fixed test keys (local validator only) so CU numbers repeat run to run: Anchor finds
  // each ATA address with find_program_address, which costs ~1.5k CU per bump it tries.
  const testKey = (name: string) => Keypair.fromSeed(createHash("sha256").update(`sumo-test-${name}`).digest());
  const alice = testKey("alice");
  const bob = testKey("bob");

  const state = () => program.account.config.fetch(config);
  const balance = async (owner: PublicKey) =>
    BigInt((await provider.connection.getTokenAccountBalance(getAssociatedTokenAddressSync(mint, owner))).value.amount);

  async function mineWith(kp: Keypair, nonce: bigint, challenge?: number[]) {
    const s = await state();
    return program.methods
      .mine(challenge ?? s.challenge, new BN(nonce.toString()))
      .accounts({ miner: kp.publicKey })
      .signers([kp])
      .rpc();
  }
  async function mineBlock(kp: Keypair) {
    const s = await state();
    const nonce = grind(Buffer.from(s.challenge), kp.publicKey, BigInt(s.target.toString()));
    return mineWith(kp, nonce, s.challenge);
  }

  // Compute units used by `mine`, read from the confirmed transaction's metadata.
  const cu: Record<string, number> = {};
  async function recordCu(label: string, sig: string) {
    await provider.connection.confirmTransaction(sig, "confirmed");
    const tx = await provider.connection.getTransaction(sig, { commitment: "confirmed", maxSupportedTransactionVersion: 0 });
    cu[label] = tx!.meta!.computeUnitsConsumed!;
  }

  before(async () => {
    for (const kp of [alice, bob]) {
      const sig = await provider.connection.requestAirdrop(kp.publicKey, 5 * LAMPORTS_PER_SOL);
      await provider.connection.confirmTransaction(sig, "confirmed");
    }
  });

  it("initialize refuses a retarget window big enough to overflow the maths", async () => {
    // Guard added 31 Oct 2026: retarget_interval * target_block_time must fit i64::MAX / 4.
    const absurd = { ...PARAMS, retargetInterval: new BN("18446744073709551615") };
    await expectError(program.methods.initialize(absurd).accounts({ programData }).rpc(), "BadParams");
  });

  it("only the upgrade authority can initialize", async () => {
    await expectError(
      program.methods.initialize(PARAMS).accounts({ authority: bob.publicKey, programData }).signers([bob]).rpc(),
      "NotUpgradeAuthority"
    );
    await program.methods.initialize(PARAMS).accounts({ programData }).rpc();
    const s = await state();
    expect(s.blocksMined.toNumber()).to.eq(0);
    expect(s.mint.toBase58()).to.eq(mint.toBase58());
    const m = await getMint(provider.connection, mint);
    expect(m.decimals).to.eq(9);
    expect(m.mintAuthority!.toBase58()).to.eq(config.toBase58());
    expect(m.freezeAuthority).to.eq(null);
  });

  it("attaches Metaplex metadata", async () => {
    await program.methods
      .createMetadata("Sumo Frog", "SUMO", "https://example.com/sumo.json")
      .accounts({ mint })
      .rpc();
    const [md] = PublicKey.findProgramAddressSync(
      [Buffer.from("metadata"), METADATA_PROGRAM.toBuffer(), mint.toBuffer()],
      METADATA_PROGRAM
    );
    const info = await provider.connection.getAccountInfo(md);
    expect(info!.owner.toBase58()).to.eq(METADATA_PROGRAM.toBase58());
    expect(info!.data.includes(Buffer.from("Sumo Frog"))).to.eq(true);
  });

  // ---- set_schedule (yearly halving), added 1 Nov 2026, tightened 2 Nov 2026 ----
  // Here at block 0 (era 0, 50 SUMO, halving every 6) a change may only make things meaner.
  it("set_schedule: the reward can't go up, halving can't move later or more than 2x sooner, the interval must be past blocks mined", async () => {
    const set = (reward: bigint, halving: string | number) =>
      program.methods.setSchedule(new BN(reward.toString()), new BN(halving)).accounts({ programData }).rpc();
    await expectError(set(51n * UNIT, 6), "BadParams"); // reward up
    await expectError(set(50n * UNIT, 7), "BadParams"); // halving later
    await expectError(set(20n * UNIT, 1000), "BadParams"); // lower now, but more than 50/6 pays from block 12
    await expectError(set(50n * UNIT, "18446744073709551615"), "BadParams"); // "never halve"
    await expectError(set(0n, 6), "BadParams");
    // More than 2x sooner (Ribbit, 2 Nov b: a typo like 41 for 525,600 would end issuance in a day)
    await expectError(set(50n * UNIT, 2), "BadParams");
    await expectError(set(50n * UNIT, 1), "BadParams");
    await expectError(set(50n * UNIT, 0), "BadParams");
  });

  it("set_schedule: fixed floor, so the interval can't be halved again and again (Ribbit, 2 Nov c)", async () => {
    // This chain halves every 6 blocks, under MIN_HALVING_INTERVAL (262,800), so only 6 itself
    // passes: even exactly half (3), which the "at most half" rule alone would allow, is refused.
    const set = (halving: number) =>
      program.methods.setSchedule(new BN((50n * UNIT).toString()), new BN(halving)).accounts({ programData }).rpc();
    for (const iv of [5, 4, 3]) await expectError(set(iv), "BadParams");
    expect((await state()).halvingInterval.toNumber()).to.eq(6);
  });

  it("set_schedule: an allowed change applies and keeps everything else", async () => {
    // Same schedule (the meanest change that keeps the later tests' numbers): accepted.
    const before = await state();
    await program.methods.setSchedule(new BN((50n * UNIT).toString()), new BN(6)).accounts({ programData }).rpc();
    const s = await state();
    expect(s.initialReward.toString()).to.eq((50n * UNIT).toString());
    expect(s.halvingInterval.toNumber()).to.eq(6);
    expect(s.maxSupply.toString()).to.eq(before.maxSupply.toString());
    expect(s.totalMinted.toString()).to.eq(before.totalMinted.toString());
    expect(s.blocksMined.toNumber()).to.eq(before.blocksMined.toNumber());
    expect(Buffer.from(s.challenge).equals(Buffer.from(before.challenge))).to.eq(true);
    expect(s.target.toString()).to.eq(before.target.toString());
  });

  it("rejects a nonce that doesn't meet the target", async () => {
    const s = await state();
    const target = BigInt(s.target.toString());
    let bad = 0n;
    while (workValue(powHash(Buffer.from(s.challenge), alice.publicKey, bad)) <= target) bad++;
    await expectError(mineWith(alice, bad), "InsufficientWork");
  });

  it("rejects substituted accounts (fake mint, someone else's token account)", async () => {
    const s = await state();
    const nonce = grind(Buffer.from(s.challenge), bob.publicKey, BigInt(s.target.toString()));
    // A look-alike mint that bob controls: fails the mint PDA seeds check.
    const fake = await createMint(provider.connection, bob, bob.publicKey, null, 9);
    await expectError(
      program.methods.mine(s.challenge, new BN(nonce.toString()))
        .accountsPartial({ miner: bob.publicKey, mint: fake, minerAta: getAssociatedTokenAddressSync(fake, bob.publicKey) })
        .signers([bob]).rpc(),
      "Constraint"
    );
    // Bob's valid solution, but paid into carol's (real, existing) token account: refused.
    const carol = testKey("carol");
    const carolAta = await createAssociatedTokenAccount(provider.connection, bob, mint, carol.publicKey);
    await expectError(
      program.methods.mine(s.challenge, new BN(nonce.toString()))
        .accountsPartial({ miner: bob.publicKey, minerAta: carolAta })
        .signers([bob]).rpc(),
      "Constraint"
    );
    expect((await state()).blocksMined.toNumber()).to.eq(0);
  });

  it("accepts a valid solution and mints 50 SUMO", async () => {
    const before = await state();
    await recordCu("mine_first_creates_ata", await mineBlock(alice));
    const s = await state();
    expect(s.blocksMined.toNumber()).to.eq(1);
    expect(await balance(alice.publicKey)).to.eq(50n * UNIT);
    expect(Buffer.from(s.challenge).equals(Buffer.from(before.challenge))).to.eq(false);
    expect(s.lastMiner.toBase58()).to.eq(alice.publicKey.toBase58());
  });

  it("solutions are single-use (replay fails)", async () => {
    const s = await state();
    const c = Buffer.from(s.challenge);
    const nonce = grind(c, alice.publicKey, BigInt(s.target.toString()));
    await recordCu("mine_existing_ata", await mineWith(alice, nonce, s.challenge));
    await expectError(mineWith(alice, nonce, s.challenge), "StaleChallenge");
    expect((await state()).blocksMined.toNumber()).to.eq(2);
  });

  it("a nonce is bound to the miner's key (can't steal someone else's)", async () => {
    const s = await state();
    const c = Buffer.from(s.challenge);
    const target = BigInt(s.target.toString());
    const stolen = grind(c, alice.publicKey, target, (n) => workValue(powHash(c, bob.publicKey, n)) > target);
    await expectError(mineWith(bob, stolen, s.challenge), "InsufficientWork");
  });

  it("retargets after 4 fast blocks (difficulty up, max 4x)", async () => {
    const t0 = BigInt((await state()).target.toString());
    await mineBlock(bob); // block 3
    expect(BigInt((await state()).target.toString())).to.eq(t0);
    await recordCu("mine_with_retarget", await mineBlock(bob)); // block 4 -> retarget; blocks took seconds, not 4 minutes
    const t1 = BigInt((await state()).target.toString());
    expect(t1).to.eq(t0 / 4n);
  });

  // ---- payout address (mine_to), added 1 Nov 2026 ----
  const dave = testKey("dave"); // a wallet that never signs anything
  const erin = testKey("erin");
  async function mineTo(feeKey: Keypair, payout: PublicKey, nonce: bigint, challenge: number[], payoutAta?: PublicKey) {
    const accts: any = { miner: feeKey.publicKey, payout };
    if (payoutAta) accts.payoutAta = payoutAta;
    return program.methods.mineTo(challenge, new BN(nonce.toString())).accountsPartial(accts).signers([feeKey]).rpc();
  }

  it("mine_to pays the payout address and creates its token account; the signer only pays fees", async () => {
    const s = await state();
    const nonce = grind(Buffer.from(s.challenge), dave.publicKey, BigInt(s.target.toString()));
    const bobBefore = await balance(bob.publicKey);
    expect(await provider.connection.getAccountInfo(getAssociatedTokenAddressSync(mint, dave.publicKey))).to.eq(null);
    await recordCu("mine_to_first_creates_ata", await mineTo(bob, dave.publicKey, nonce, s.challenge)); // block 5
    expect(await balance(dave.publicKey)).to.eq(50n * UNIT);
    expect(await balance(bob.publicKey)).to.eq(bobBefore);
    const after = await state();
    expect(after.blocksMined.toNumber()).to.eq(5);
    expect(after.lastMiner.toBase58()).to.eq(dave.publicKey.toBase58());
  });

  it("mine_to: an answer found for one payout address fails for another", async () => {
    const s = await state();
    const c = Buffer.from(s.challenge);
    const target = BigInt(s.target.toString());
    const n = grind(c, dave.publicKey, target, (x) => workValue(powHash(c, erin.publicKey, x)) > target);
    await expectError(mineTo(bob, erin.publicKey, n, s.challenge), "InsufficientWork");
    // and someone else's token account can't stand in for the payout wallet's
    const carolAta = getAssociatedTokenAddressSync(mint, testKey("carol").publicKey);
    await expectError(mineTo(bob, dave.publicKey, n, s.challenge, carolAta), "Constraint");
    expect((await state()).blocksMined.toNumber()).to.eq(5);
  });

  it("mine_to: a relayed answer still pays the wallet it was found for", async () => {
    const s = await state();
    const nonce = grind(Buffer.from(s.challenge), dave.publicKey, BigInt(s.target.toString()));
    await recordCu("mine_to_existing_ata", await mineTo(alice, dave.publicKey, nonce, s.challenge)); // block 6 (last 50)
    expect(await balance(dave.publicKey)).to.eq(100n * UNIT);
  });

  it("halves the reward after 6 blocks", async () => {
    expect((await state()).blocksMined.toNumber()).to.eq(6);
    const before = await balance(alice.publicKey);
    await mineBlock(alice); // 7 -> 25
    expect((await balance(alice.publicKey)) - before).to.eq(25n * UNIT);
    expect((await state()).lastReward.toString()).to.eq((25n * UNIT).toString());
  });

  it("set_schedule can't undo the halving or turn halving off (Ribbit, 2 Nov 2026)", async () => {
    const s = await state(); // block 7, era 1, paying 25
    const set = (reward: bigint, halving: string | number) =>
      program.methods.setSchedule(new BN(reward.toString()), new BN(halving)).accounts({ programData }).rpc();
    await expectError(set(50n * UNIT, s.blocksMined.toNumber() + 1), "BadParams"); // back to 50, halving pushed ahead
    await expectError(set(25n * UNIT, s.blocksMined.toNumber() + 1), "BadParams"); // today's 25, restarted at era 0
    await expectError(set(50n * UNIT, "18446744073709551615"), "BadParams"); // never halve
    await expectError(set(25n * UNIT, "18446744073709551615"), "BadParams");
    const after = await state();
    expect(after.initialReward.toString()).to.eq(PARAMS.initialReward.toString());
    expect(after.halvingInterval.toNumber()).to.eq(6);
  });

  it("stops at max supply", async () => {
    await mineBlock(bob); // 8 -> 25, total 350; retarget again
    await mineBlock(bob); // 9 -> only 10 left
    const s = await state();
    expect(s.lastReward.toString()).to.eq((10n * UNIT).toString());
    expect(s.totalMinted.toString()).to.eq(PARAMS.maxSupply.toString());
    const m = await getMint(provider.connection, mint);
    expect(m.supply.toString()).to.eq(PARAMS.maxSupply.toString());
    const nonce = grind(Buffer.from(s.challenge), bob.publicKey, BigInt(s.target.toString()));
    await expectError(mineWith(bob, nonce, s.challenge), "SupplyExhausted");
    expect((await balance(alice.publicKey)) + (await balance(bob.publicKey)) + (await balance(dave.publicKey))).to.eq(360n * UNIT);
  });

  it("set_schedule: only the upgrade authority can change the schedule", async () => {
    await expectError(
      program.methods.setSchedule(new BN((20n * UNIT).toString()), new BN(1000))
        .accounts({ authority: bob.publicKey, programData }).signers([bob]).rpc(),
      "NotUpgradeAuthority"
    );
  });

  // Baseline lives in tests/cu-baseline.json. If a change makes `mine` more than 5% more
  // expensive this fails; if you meant it (or made it cheaper), update the baseline file.
  it("mine compute units stay within the recorded baseline", async () => {
    mkdirSync("target", { recursive: true });
    writeFileSync("target/cu-report.json", JSON.stringify(cu, null, 2) + "\n");
    console.log("      mine CU:", JSON.stringify(cu));
    const base = JSON.parse(readFileSync("tests/cu-baseline.json", "utf8")).mine as Record<string, number>;
    for (const [k, limit] of Object.entries(base)) {
      expect(cu[k], `missing CU sample ${k}`).to.be.a("number");
      expect(cu[k], `${k} used ${cu[k]} CU, baseline ${limit}`).to.be.at.most(Math.ceil(limit * 1.05));
    }
  });
});
