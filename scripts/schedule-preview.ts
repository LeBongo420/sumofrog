// What a set_schedule change would do, worked out before anything is sent (2 Nov 2026, after
// Ribbit's second review: a typo such as 41 for 525,600 would end issuance in about a day).
// Same maths as the program's block_reward / capped_reward, in BigInt. No network, no keys.

export const BLOCK_SECONDS = 60; // target block time the dates assume
export const UNIT = 1_000_000_000n; // 9 decimals

export interface Schedule {
  initialReward: bigint; // base units
  halvingInterval: bigint; // blocks
}

/** The program's MIN_HALVING_INTERVAL (2 Nov 2026, Ribbit's third review): no change can set a
 *  halving interval below this (or below the current one, if that's already shorter). */
export const MIN_HALVING_INTERVAL = 262_800n;
/** The schedule the private network launched its yearly halving with (1 Nov 2026). On the private
 *  network the preview also compares against this, so a run of small cuts can't each look harmless
 *  on its own. Other networks (local test chains, devnet) pass null: it doesn't apply to them. */
export const ORIGINAL_SCHEDULE: Schedule = { initialReward: 20n * 1_000_000_000n, halvingInterval: 525_600n };

/** The program's block_reward: initial >> era, 0 from era 64. */
export function blockReward(s: Schedule, block: bigint): bigint {
  const era = block / s.halvingInterval;
  return era >= 64n ? 0n : s.initialReward >> era;
}

/** The first block (counting blocks mined) that pays less than now, under schedule s. */
export function nextHalvingBlock(s: Schedule, blocksMined: bigint): bigint {
  return (blocksMined / s.halvingInterval + 1n) * s.halvingInterval;
}

/** Total ever minted if every block from blocksMined on follows s, with the same cap trim as
 *  the program, plus the block count at which issuance ends (null if it never reaches 0 or the cap,
 *  which can't happen: era 64 always pays 0). */
export function projectSupply(s: Schedule, blocksMined: bigint, totalMinted: bigint, maxSupply: bigint) {
  let total = totalMinted;
  let b = blocksMined;
  while (total < maxSupply) {
    const r = blockReward(s, b);
    if (r === 0n) break;
    const eraEnd = nextHalvingBlock(s, b);
    const n = eraEnd - b;
    const left = maxSupply - total;
    if (r * n >= left) {
      b += (left + r - 1n) / r; // the last block is trimmed to what's left
      total = maxSupply;
      break;
    }
    total += r * n;
    b = eraEnd;
  }
  return { total, endBlock: b };
}

export function fmtSumo(base: bigint): string {
  const whole = base / UNIT;
  const frac = (base % UNIT).toString().padStart(9, "0").replace(/0+$/, "");
  return whole.toLocaleString("en-GB") + (frac ? "." + frac : "");
}

/** Approximate UK date for a block, assuming BLOCK_SECONDS per block from now. */
export function ukDate(blocksFromNow: bigint, now = new Date()): string {
  const secs = Number(blocksFromNow) * BLOCK_SECONDS;
  if (!Number.isFinite(secs) || secs > 8.64e15 / 1000 - now.getTime() / 1000) return "never (far beyond any calendar)";
  const d = new Date(now.getTime() + secs * 1000);
  return d.toLocaleString("en-GB", { timeZone: "Europe/London", dateStyle: "medium", timeStyle: "short" }) + " UK";
}

/** Block number as the miner shows it: blocks are counted from #1, so the block mined after
 *  `blocksMined` blocks is #blocksMined+1 (the first halved block of the yearly schedule is #525,601). */
const blockNo = (count: bigint) => "#" + (count + 1n).toLocaleString("en-GB");

/** "Issuance ends" wording: the last block that pays anything, and why it stops. */
function endText(p: { total: bigint; endBlock: bigint }, maxSupply: bigint, blocksMined: bigint, now: Date): string {
  const why = p.total >= maxSupply ? "(cap reached)" : "(reward reaches zero)";
  return `last paying block #${p.endBlock.toLocaleString("en-GB")} (~${ukDate(p.endBlock - blocksMined, now)}) ${why}`;
}

/** The text shown before asking for YES. */
export function previewText(
  cur: Schedule,
  next: Schedule,
  blocksMined: bigint,
  totalMinted: bigint,
  maxSupply: bigint,
  now = new Date(),
  original: Schedule | null = null
): string {
  const half = nextHalvingBlock(next, blocksMined);
  const curHalf = nextHalvingBlock(cur, blocksMined);
  const p = projectSupply(next, blocksMined, totalMinted, maxSupply);
  const pc = projectSupply(cur, blocksMined, totalMinted, maxSupply);
  const po = original ? projectSupply(original, blocksMined, totalMinted, maxSupply) : null;
  const floor = cur.halvingInterval < MIN_HALVING_INTERVAL ? cur.halvingInterval : MIN_HALVING_INTERVAL;
  const lines = [
    `Blocks mined so far:   ${blocksMined.toLocaleString("en-GB")}   (minted ${fmtSumo(totalMinted)} SUMO)`,
    `Reward per block:      now ${fmtSumo(blockReward(cur, blocksMined))} SUMO  ->  new ${fmtSumo(blockReward(next, blocksMined))} SUMO`,
    `Halving interval:      now ${cur.halvingInterval.toLocaleString("en-GB")} blocks  ->  new ${next.halvingInterval.toLocaleString("en-GB")} blocks`,
    `First halved block:    now block ${blockNo(curHalf)} (~${ukDate(curHalf - blocksMined, now)})`,
    `                       new block ${blockNo(half)} (~${ukDate(half - blocksMined, now)})`,
    `Projected total supply: now ${fmtSumo(pc.total)} SUMO  ->  new ${fmtSumo(p.total)} SUMO (cap ${fmtSumo(maxSupply)})`,
    ...(original && po
      ? [`                       original schedule (${fmtSumo(original.initialReward)} SUMO, halving every ${original.halvingInterval.toLocaleString("en-GB")}): ${fmtSumo(po.total)} SUMO`]
      : []),
    `Issuance ends:         now ${endText(pc, maxSupply, blocksMined, now)}`,
    `                       new ${endText(p, maxSupply, blocksMined, now)}`,
    `Block numbers count from #1, as the miner shows them. Dates assume one block every ${BLOCK_SECONDS} seconds.`,
    `These numbers are as of the moment they were read; the program re-checks everything when the change is sent.`,
  ];
  if (next.halvingInterval < floor)
    lines.push(`WARNING: the program will refuse this: the halving interval can't go below ${floor.toLocaleString("en-GB")} blocks.`);
  if (next.halvingInterval * 2n < cur.halvingInterval)
    lines.push(`WARNING: the program will refuse this: the halving interval can't go below half the current one (${((cur.halvingInterval + 1n) / 2n).toLocaleString("en-GB")} blocks).`);
  if (p.total * 2n < pc.total)
    lines.push("WARNING: this change cuts total supply by more than half. Check the numbers you typed.");
  else if (po && p.total * 2n < po.total)
    lines.push("WARNING: together with earlier changes, this cuts total supply to less than half the original schedule.");
  lines.push("This can't be undone: after the first halving the program refuses every schedule change.");
  return lines.join("\n");
}

/** Only an exact typed YES goes ahead. */
export const confirmed = (answer: string | null | undefined) => (answer ?? "").trim() === "YES";
