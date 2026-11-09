// Change the reward schedule on an existing Sumo Frog deployment (upgrade authority only).
// Default: 20 SUMO per block, halving every 525,600 blocks (one year of 60-second blocks), which is
// what the private network already runs, so the default is now a no-op.
// The program refuses any change that would make a block (now or later) pay more than the current
// schedule, a later or switched-off halving, a zero reward, a halving point at or below the blocks
// already mined (so once the first halving has happened, no change passes), or a halving interval
// below half the current one or below the fixed floor of 262,800 blocks. The 21M cap holds regardless.
// Run: ANCHOR_PROVIDER_URL=<test rpc> ANCHOR_WALLET=.keys/deployer.json npx ts-node scripts/set-schedule.ts [reward_sumo] [halving_blocks]
// Before sending it prints what the change would do (first halved block, numbered like the miner, and
// its UK date; projected total supply against the current and the original schedule; when issuance
// ends and why) and only goes ahead if you type YES. Anything else sends nothing.
// Test networks only: refuses mainnet, and refuses any network that isn't localhost, devnet or the private Sumo network.
import * as anchor from "@coral-xyz/anchor";
import { BN, Program } from "@coral-xyz/anchor";
import { PublicKey } from "@solana/web3.js";
import { Sumofrog } from "../target/types/sumofrog";
import idl from "../target/idl/sumofrog.json";
import settings from "../miner/sumo_config.json";
import { createInterface } from "readline";
import { previewText, confirmed, ORIGINAL_SCHEDULE } from "./schedule-preview";

const LOADER_V3 = new PublicKey("BPFLoaderUpgradeab1e11111111111111111111111");
const MAINNET_GENESIS = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d";
const DEVNET_GENESIS = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG";

async function main() {
  const provider = anchor.AnchorProvider.env();
  const genesis = await provider.connection.getGenesisHash();
  // Exact host match (2 Nov 2026): "localhost.example.com" or "?localhost" no longer count as local.
  const host = new URL(provider.connection.rpcEndpoint).hostname.toLowerCase();
  const local = ["localhost", "127.0.0.1", "[::1]", "::1"].includes(host);
  if (genesis === MAINNET_GENESIS) throw new Error("Refusing to run on mainnet");
  if (!local && genesis !== DEVNET_GENESIS && genesis !== (settings as any).private_genesis)
    throw new Error("Not a known test network, refusing");
  anchor.setProvider(provider);
  const program = new Program(idl as Sumofrog, provider) as Program<Sumofrog>;
  const [config] = PublicKey.findProgramAddressSync([Buffer.from("config")], program.programId);
  const [programData] = PublicKey.findProgramAddressSync([program.programId.toBuffer()], LOADER_V3);

  const reward = BigInt(Math.round(Number(process.argv[2] ?? "20") * 1e9));
  const halving = BigInt(process.argv[3] ?? "525600");
  const before = await program.account.config.fetch(config);
  console.log(`before: reward ${before.initialReward.toString()} halving ${before.halvingInterval.toString()} blocks ${before.blocksMined.toString()} minted ${before.totalMinted.toString()}`);
  if (halving <= 0n || reward <= 0n) throw new Error("Reward and halving interval must be positive. Nothing sent.");
  console.log(
    "\n" +
      previewText(
        { initialReward: BigInt(before.initialReward.toString()), halvingInterval: BigInt(before.halvingInterval.toString()) },
        { initialReward: reward, halvingInterval: halving },
        BigInt(before.blocksMined.toString()),
        BigInt(before.totalMinted.toString()),
        BigInt(before.maxSupply.toString()),
        new Date(),
        // Compare with the original yearly schedule only on the private network (Ribbit 02d Note 3).
        genesis === (settings as any).private_genesis ? ORIGINAL_SCHEDULE : null
      ) +
      "\n"
  );
  if (!process.stdin.isTTY) throw new Error("Needs a person at the keyboard to type YES. Nothing sent.");
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const answer = await new Promise<string>((res) => rl.question("Type YES to send this change (anything else cancels): ", res));
  rl.close();
  if (!confirmed(answer)) {
    console.log("Cancelled. Nothing was sent.");
    return;
  }
  const sig = await program.methods
    .setSchedule(new BN(reward.toString()), new BN(halving.toString()))
    .accounts({ authority: provider.wallet.publicKey, config, programData } as any)
    .rpc();
  const after = await program.account.config.fetch(config);
  console.log("set_schedule:", sig);
  console.log(`after:  reward ${after.initialReward.toString()} halving ${after.halvingInterval.toString()} blocks ${after.blocksMined.toString()} minted ${after.totalMinted.toString()}`);
  if (after.initialReward.toString() !== reward.toString() || after.halvingInterval.toString() !== halving.toString())
    throw new Error("schedule didn't change");
}
main().catch((e) => {
  console.error(e);
  process.exit(1);
});
