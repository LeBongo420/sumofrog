#!/usr/bin/env bash
# Deploy Sumo Frog to Solana DEVNET, set it up, and mine a few demo blocks.
# Needs ~2 devnet SOL in .keys/deployer.json (free from https://faucet.solana.com, Devnet).
# Usage: scripts/deploy-devnet.sh [metadata-json-uri] [demo-blocks]
set -euo pipefail
cd "$(dirname "$0")/.."
source ~/.sumo_env
RPC="${SUMO_RPC:-https://api.devnet.solana.com}"   # SUMO_RPC=http://127.0.0.1:8899 for a local rehearsal
# Refuse \ or @ before the host check (5 Nov 2026, Ribbit): they can make Python and solana disagree on the host.
case "$RPC" in
  *\\*|*@*) echo "SUMO_RPC has a backslash or @, refusing."; exit 1 ;;
esac
# After the RPC refuse, before any network call: stop if the declared
# program addresses disagree (public addresses only).
python3 scripts/check_program_id.py >/dev/null
DEVNET_GENESIS=EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG
PRIVATE_GENESIS="${SUMO_PRIVATE_GENESIS:-9eDPpAG4RUei7HTciCEucnshXm6Rfo61d6KU8hyXwx6n}"  # private Sumo validator on the Oracle server
GH="$(solana genesis-hash -u "$RPC")"
# Exact host match (5 Nov 2026, Ribbit 02d Note 4): "https://localhost.example.com" is not local.
HOST="$(python3 -c 'import sys,urllib.parse; print((urllib.parse.urlsplit(sys.argv[1]).hostname or "").lower())' "$RPC")"
case "$HOST" in
  127.0.0.1|localhost|::1) [ "$GH" != 5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d ] || { echo "Mainnet, refusing."; exit 1; } ;;
  *) [ "$GH" = "$DEVNET_GENESIS" ] || [ "$GH" = "$PRIVATE_GENESIS" ] || { echo "Not devnet or the private Sumo network, refusing."; exit 1; } ;;
esac
URI="${1:-}"
BLOCKS="${2:-5}"
DEPLOYER=.keys/deployer.json
PROGRAM_KEY=.keys/program.json
PROGRAM_ID=$(solana-keygen pubkey "$PROGRAM_KEY")
echo "Deployer $(solana-keygen pubkey $DEPLOYER): $(solana balance -u $RPC $DEPLOYER)"

if solana program show -u "$RPC" "$PROGRAM_ID" >/dev/null 2>&1; then
  echo "Program already deployed: $PROGRAM_ID"
else
  solana program deploy -u "$RPC" --use-rpc --keypair "$DEPLOYER" --upgrade-authority "$DEPLOYER" \
    --program-id "$PROGRAM_KEY" target/deploy/sumofrog.so
fi

ANCHOR_PROVIDER_URL=$RPC ANCHOR_WALLET=$DEPLOYER npx ts-node --transpile-only scripts/setup.ts $URI
python3 scripts/write_config.py "$RPC"

# Demo: give the demo miner a little devnet SOL for fees, then mine.
MINER=.keys/miner.json
if [ "$(solana balance -u $RPC $MINER --lamports | cut -d' ' -f1)" -lt 20000000 ]; then
  solana transfer -u "$RPC" --keypair "$DEPLOYER" --allow-unfunded-recipient "$(solana-keygen pubkey $MINER)" 0.05 >/dev/null
fi
cd miner && python3 sumo_miner.py mine --blocks "$BLOCKS" --keypair ../$MINER --rpc "$RPC" && python3 sumo_miner.py status --rpc "$RPC"
