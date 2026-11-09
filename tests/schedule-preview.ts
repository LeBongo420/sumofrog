// Offline tests for scripts/schedule-preview.ts (what set-schedule.ts shows before asking YES).
import { expect } from "chai";
import { blockReward, nextHalvingBlock, projectSupply, previewText, confirmed, fmtSumo, UNIT, MIN_HALVING_INTERVAL, ORIGINAL_SCHEDULE } from "../scripts/schedule-preview";

const CAP = 21_000_000n * UNIT;
const YEARLY = { initialReward: 20n * UNIT, halvingInterval: 525_600n };
const NOW = new Date("2026-11-02T16:30:00Z");

describe("set-schedule preview (offline)", () => {
  it("matches the program's reward maths and finds the next halving", () => {
    expect(blockReward(YEARLY, 49n)).to.eq(20n * UNIT);
    expect(blockReward(YEARLY, 525_600n)).to.eq(10n * UNIT);
    expect(blockReward({ initialReward: 1n, halvingInterval: 1n }, 64n)).to.eq(0n);
    expect(nextHalvingBlock(YEARLY, 49n)).to.eq(525_600n);
    expect(nextHalvingBlock(YEARLY, 525_600n)).to.eq(1_051_200n);
  });

  it("projects the yearly schedule to the 21M cap", () => {
    const p = projectSupply(YEARLY, 49n, 1_700n * UNIT + 15n * 20n * UNIT, CAP);
    expect(p.total).to.eq(CAP);
    expect(p.endBlock > 9n * 525_600n).to.eq(true);
  });

  it("shows the 41-for-525,600 typo for what it is", () => {
    const typo = { initialReward: 20n * UNIT, halvingInterval: 41n };
    const p = projectSupply(typo, 40n, 0n, CAP);
    expect(p.total < 2_000n * UNIT).to.eq(true);
    expect(p.endBlock < 2_000n).to.eq(true); // about a day of 60-second blocks
    const text = previewText(YEARLY, typo, 40n, 0n, CAP, NOW);
    expect(text).to.contain("new block #42 "); // the miner numbers blocks from #1
    expect(text).to.contain("(reward reaches zero)");
    expect(text).to.contain("can't go below 262,800");
    expect(text).to.contain("WARNING");
    expect(text).to.contain("3 Nov 2026"); // issuance would end the next day
    expect(text).to.contain(" UK");
  });

  it("dates the next halving about a year out for the yearly schedule", () => {
    const text = previewText(YEARLY, YEARLY, 49n, 0n, CAP, NOW, ORIGINAL_SCHEDULE);
    expect(text).to.contain("new block #525,601"); // the first halved block, as the miner numbers it
    expect(text).to.contain("(cap reached)");
    expect(text).to.contain("original schedule (20 SUMO, halving every 525,600): 21,000,000 SUMO");
    expect(text).to.contain("2027");
    expect(text).to.not.contain("WARNING");
    expect(text.toLowerCase()).to.not.contain("nonce");
  });

  it("compares with the original schedule, so a run of small cuts is flagged (Ribbit, 2 Nov c)", () => {
    // From a schedule already at the floor (262,800), a further step to 131,400 looks like "just
    // under half" of the current one, but the preview flags the floor and the original schedule.
    const atFloor = { initialReward: 20n * UNIT, halvingInterval: MIN_HALVING_INTERVAL };
    const step = { initialReward: 20n * UNIT, halvingInterval: 131_400n };
    const text = previewText(atFloor, step, 40n, 800n * UNIT, CAP, NOW, ORIGINAL_SCHEDULE);
    expect(text).to.contain("can't go below 262,800");
    expect(text).to.contain("less than half the original schedule");
    expect(text).to.not.contain("by more than half"); // vs the current one alone it isn't
    // One allowed change, 525,600 -> 262,800: no floor warning, ends by reward reaching zero.
    const ok = previewText(YEARLY, atFloor, 40n, 800n * UNIT, CAP, NOW, ORIGINAL_SCHEDULE);
    expect(ok).to.not.contain("will refuse");
    expect(ok).to.contain("new last paying block");
    expect(ok).to.contain("(reward reaches zero)");
  });

  it("skips the original-schedule comparison off the private network (Ribbit, 2 Nov d, Note 3)", () => {
    // A local test chain halving every 6 blocks: no change, so no warning at all.
    const local = { initialReward: 20n * UNIT, halvingInterval: 6n };
    const text = previewText(local, local, 3n, 60n * UNIT, CAP, NOW);
    expect(text).to.not.contain("original schedule");
    expect(text).to.not.contain("WARNING");
  });

  it("warns about the can't-go-below-half rule (Ribbit, 2 Nov d, Note 3)", () => {
    const big = { initialReward: 20n * UNIT, halvingInterval: 600_000n };
    const tooShort = previewText(big, { initialReward: 20n * UNIT, halvingInterval: 280_000n }, 40n, 800n * UNIT, CAP, NOW);
    expect(tooShort).to.contain("can't go below half the current one (300,000 blocks)");
    const half = previewText(big, { initialReward: 20n * UNIT, halvingInterval: 300_000n }, 40n, 800n * UNIT, CAP, NOW);
    expect(half).to.not.contain("will refuse");
    expect((tooShort + half).toLowerCase()).to.not.contain("nonce");
  });

  it("only an exact YES confirms", () => {
    expect(confirmed("YES")).to.eq(true);
    expect(confirmed(" YES\n")).to.eq(true);
    for (const a of ["yes", "Y", "y", "", "YES!", "no", null, undefined]) expect(confirmed(a as any)).to.eq(false);
  });

  it("formats SUMO amounts", () => {
    expect(fmtSumo(21_000_000n * UNIT)).to.eq("21,000,000");
    expect(fmtSumo(12n * UNIT + UNIT / 2n)).to.eq("12.5");
  });
});
