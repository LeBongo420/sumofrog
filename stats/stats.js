// Sumo Frog stats: reads Solana devnet directly, no server, no libraries.
const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function b58encode(bytes) {
  let n = 0n;
  for (const b of bytes) n = n * 256n + BigInt(b);
  let s = "";
  while (n > 0n) { s = B58[Number(n % 58n)] + s; n /= 58n; }
  for (const b of bytes) { if (b === 0) s = "1" + s; else break; }
  return s;
}
function b58decode(str) {
  let n = 0n;
  for (const c of str) n = n * 58n + BigInt(B58.indexOf(c));
  const out = [];
  while (n > 0n) { out.unshift(Number(n % 256n)); n /= 256n; }
  for (const c of str) { if (c === "1") out.unshift(0); else break; }
  return new Uint8Array(out);
}
function b64bytes(b64) {
  if (typeof Buffer !== "undefined") return new Uint8Array(Buffer.from(b64, "base64"));
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}
async function rpc(url, method, params) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) });
  const j = await r.json();
  if (j.error) throw new Error(method + ": " + j.error.message);
  return j.result;
}
function decodeConfig(d) {
  const v = new DataView(d.buffer, d.byteOffset, d.byteLength);
  let o = 8;
  const pk = () => { const s = b58encode(d.slice(o, o + 32)); o += 32; return s; };
  const u64 = () => { const x = v.getBigUint64(o, true); o += 8; return x; };
  const i64 = () => { const x = v.getBigInt64(o, true); o += 8; return x; };
  const authority = pk(), mint = pk(); o += 2;
  const challenge = d.slice(o, o + 32); o += 32;
  const c = { authority, mint, challenge, target: u64(), initialReward: u64(), halvingInterval: u64(),
    retargetInterval: u64(), targetBlockTime: i64(), maxSupply: u64(), blocksMined: u64(),
    totalMinted: u64(), epochStartTs: i64(), lastSolveTs: i64() };
  c.lastMiner = pk(); c.lastReward = u64();
  const era = c.blocksMined / c.halvingInterval;
  c.nextReward = era >= 64n ? 0n : c.initialReward >> era;
  if (c.nextReward > c.maxSupply - c.totalMinted) c.nextReward = c.maxSupply - c.totalMinted;
  c.difficultyBits = 64 - Math.log2(Number(c.target) + 1);
  return c;
}
async function loadStats(url, cfg) {
  const info = await rpc(url, "getAccountInfo", [cfg.config, { encoding: "base64", commitment: "confirmed" }]);
  if (!info.value) throw new Error("Config account not found: is Sumo Frog deployed on this network?");
  const c = decodeConfig(b64bytes(info.value.data[0]));
  const largest = await rpc(url, "getTokenLargestAccounts", [cfg.mint, { commitment: "confirmed" }]);
  const accs = largest.value.filter((a) => a.amount !== "0");
  let top = [];
  if (accs.length) {
    const parsed = await rpc(url, "getMultipleAccounts", [accs.map((a) => a.address), { encoding: "jsonParsed" }]);
    top = accs.map((a, i) => ({ owner: parsed.value[i]?.data?.parsed?.info?.owner ?? a.address,
      amount: Number(BigInt(a.amount)) / 1e9 }));
  }
  const sigs = await rpc(url, "getSignaturesForAddress", [cfg.config, { limit: 15, commitment: "confirmed" }]);
  const recent = sigs.filter((s) => !s.err).map((s) => ({ sig: s.signature, time: s.blockTime }));
  return { config: c, top, recent };
}
if (typeof module !== "undefined") module.exports = { loadStats, decodeConfig, b58encode, b58decode };
