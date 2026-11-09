// One-time setup after deploy: initialize the game rules and attach token metadata.
// Run: ANCHOR_PROVIDER_URL=<rpc> ANCHOR_WALLET=.keys/deployer.json npx ts-node scripts/setup.ts [metadata-uri]
import * as anchor from "@coral-xyz/anchor";
import { BN, Program } from "@coral-xyz/anchor";
import { PublicKey } from "@solana/web3.js";
import { Sumofrog } from "../target/types/sumofrog";
import idl from "../target/idl/sumofrog.json";

const UNIT = 1_000_000_000n;
const LOADER_V3 = new PublicKey("BPFLoaderUpgradeab1e11111111111111111111111");
const MAINNET_GENESIS = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d";

async function main() {
  const provider = anchor.AnchorProvider.env();
  if ((await provider.connection.getGenesisHash()) === MAINNET_GENESIS) throw new Error("Refusing to run on mainnet");
  anchor.setProvider(provider);
  const program = new Program(idl as Sumofrog, provider);
  const [config] = PublicKey.findProgramAddressSync([Buffer.from("config")], program.programId);
  const [mint] = PublicKey.findProgramAddressSync([Buffer.from("mint")], program.programId);
  const [programData] = PublicKey.findProgramAddressSync([program.programId.toBuffer()], LOADER_V3);

  // SUMO_EASY_TARGET=1 starts with an easy target (16 bits). Local test validators only, for rehearsals.
  const local = /127\.0\.0\.1|localhost/.test(provider.connection.rpcEndpoint);
  if (process.env.SUMO_EASY_TARGET && !local) throw new Error("SUMO_EASY_TARGET is for local test validators only");
  const initialTarget = process.env.SUMO_EASY_TARGET ? 1n << 48n : 1n << 36n;

  if (!(await provider.connection.getAccountInfo(config))) {
    const sig = await program.methods
      .initialize({
        initialReward: new BN((20n * UNIT).toString()), // 20 SUMO per block
        halvingInterval: new BN(525_600), // one year of 60-second blocks: the reward halves yearly
        retargetInterval: new BN(10), // like ToyCoin
        targetBlockTime: new BN(60), // seconds
        initialTarget: new BN(initialTarget.toString()), // default ~268M guesses per block to start (28 bits)
        maxSupply: new BN((21_000_000n * UNIT).toString()),
      })
      .accounts({ programData })
      .rpc();
    console.log("initialized:", sig);
  } else console.log("already initialized");

  const uri = process.argv[2];
  if (uri) {
    const sig = await program.methods.createMetadata("Sumo Frog", "SUMO", uri).accounts({ mint }).rpc();
    console.log("metadata:", sig);
  }
  console.log("program", program.programId.toBase58(), "\nconfig ", config.toBase58(), "\nmint   ", mint.toBase58());
}
main().catch((e) => {
  console.error(e);
  process.exit(1);
});
