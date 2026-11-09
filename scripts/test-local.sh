#!/usr/bin/env bash
# Full local test run:
#   1. golden vectors: regenerate from the Python spec and check the JSON is unchanged
#   2. Rust unit tests (maths + golden vectors)
#   3. build the program, then the TS integration tests on a throwaway local validator
#      (our program is loaded as *upgradeable* with a fresh throwaway key as upgrade
#      authority, made for this run and deleted after; never the real deployer key.
#      anchor test's default genesis load has no authority)
#   4. test-count guard: fail if the number of passing tests ever drops below
#      tests/test-count-baseline.txt (stops tests being quietly deleted or skipped)
# Local only. Never points at the Oracle validator, devnet or mainnet.
# Its validator runs on its own ports (RPC 18999, not the default 8899) with its own ledger, and
# only that validator is stopped afterwards: other validators on this machine are left alone.
# A trap removes the temp files and the throwaway key however the run ends (2 Nov 2026, Ribbit).
# Note: --bind-address only covers gossip. This validator version has no option to keep its RPC and
# faucet ports on 127.0.0.1, so while the run lasts they listen on all of this machine's network
# interfaces (0.0.0.0). It's a throwaway test chain with nothing of value, deleted afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."
source ~/.sumo_env
RPC_PORT=18999
FAUCET_PORT=19900
GOSSIP_PORT=18000
DYN_PORTS=18010-18060
RPC="http://127.0.0.1:$RPC_PORT"
LEDGER=.anchor/test-ledger-local
VPID=""
TMPDIR_RUN=$(mktemp -d /tmp/sumo-test-XXXXXX)
chmod 700 "$TMPDIR_RUN"
cleanup() {
  if [ -n "$VPID" ]; then kill "$VPID" 2>/dev/null || true; wait "$VPID" 2>/dev/null || true; fi
  rm -rf "$TMPDIR_RUN"
}
trap cleanup EXIT
trap "exit 130" INT TERM  # exit (which runs cleanup) instead of carrying on
LOG="$TMPDIR_RUN/log"
TESTKEY="$TMPDIR_RUN/test-authority.json"
(umask 077; solana-keygen new --no-bip39-passphrase --silent --outfile "$TESTKEY" >/dev/null)
if curl -s -m 2 "$RPC" >/dev/null 2>&1; then
  echo "FAIL: something is already listening on port $RPC_PORT; not touching it"
  exit 1
fi

echo "== golden vectors"
cp tests/vectors/golden.json "$LOG.golden"
python3 scripts/gen_vectors.py
if ! cmp -s tests/vectors/golden.json "$LOG.golden"; then
  echo "FAIL: tests/vectors/golden.json was out of date with scripts/gen_vectors.py (now regenerated; review and commit it)"
  exit 1
fi

echo "== miner checks (offline)"
python3 tests/miner_checks.py | grep -v '^Address:'

echo "== deploy-devnet SUMO_RPC guard (offline)"
python3 tests/deploy_devnet_guard.py

echo "== rust unit tests"
cargo test -p sumofrog --lib 2>&1 | tee -a "$LOG"

echo "== build"
anchor build 2>&1 | grep -v "overflows the maximum allowed frame space" | tail -3 || true
test -f target/deploy/sumofrog.so

echo "== integration tests (own validator on this machine's port $RPC_PORT)"
mkdir -p .anchor  # a fresh clone has no .anchor/, and the validator can't start without it
rm -rf "$LEDGER"
PID=$(solana-keygen pubkey target/deploy/sumofrog-keypair.json)
solana-test-validator --reset --quiet --ledger "$LEDGER" --bind-address 127.0.0.1 \
  --rpc-port "$RPC_PORT" --faucet-port "$FAUCET_PORT" --gossip-port "$GOSSIP_PORT" --dynamic-port-range "$DYN_PORTS" \
  --upgradeable-program "$PID" target/deploy/sumofrog.so "$TESTKEY" \
  --bpf-program metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s tests/fixtures/mpl_token_metadata.so \
  > "$TMPDIR_RUN/validator.log" 2>&1 &
VPID=$!
UP=""
for i in $(seq 1 90); do solana -u "$RPC" cluster-version >/dev/null 2>&1 && { UP=1; break; }; sleep 1; done
if [ -z "$UP" ]; then
  echo "FAIL: the local test validator didn't start within 90 seconds. Its log:"
  cat "$TMPDIR_RUN/validator.log" || true
  exit 1
fi
solana -u "$RPC" airdrop 100 "$(solana-keygen pubkey "$TESTKEY")" >/dev/null
anchor test --skip-local-validator --skip-deploy --skip-build \
  --provider.cluster "$RPC" --provider.wallet "$TESTKEY" 2>&1 | tee -a "$LOG"

echo "== test-count guard"
CLEAN=$(sed 's/\x1b\[[0-9;]*m//g' "$LOG")
RUST=$(awk '/^test result: ok\. [0-9]+ passed/ {s+=$4} END {print s+0}' <<<"$CLEAN")
TS=$(awk '/^ *[0-9]+ passing/ {s=$1} END {print s+0}' <<<"$CLEAN")
FAILING=$(awk '/^ *[0-9]+ (failing|pending)/ {s+=$1} END {print s+0}' <<<"$CLEAN")
TOTAL=$((RUST + TS))
BASE=$(grep -oE '^[0-9]+' tests/test-count-baseline.txt | head -1)
echo "passing tests: $TOTAL (rust $RUST + ts $TS), baseline $BASE, failing/pending $FAILING"
if [ "$FAILING" -gt 0 ] || [ "$TOTAL" -lt "$BASE" ]; then
  echo "FAIL: test count dropped below baseline or tests failing/skipped"
  exit 1
fi
if [ "$TOTAL" -gt "$BASE" ]; then
  echo "note: $TOTAL > baseline $BASE. Raise tests/test-count-baseline.txt to $TOTAL when you commit."
fi
echo "ALL OK"
