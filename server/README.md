# Sumo Frog private test network (Oracle server)

Worthless test network. No mainnet, no real funds, no keys on the server.

| | |
|---|---|
| Validator | `sumo-validator.service`: Agave `solana-test-validator` 4.1.1 (arm64), `/home/ubuntu/sumo/bin`, ledger `/home/ubuntu/sumo/ledger`, RPC 127.0.0.1:8899 (+ws 8900), built-in faucet 9900 |
| Limits | `--limit-ledger-size 1000000` shreds, `Nice=10`, `CPUQuota=60%`, `MemoryMax=3G` |
| Gateway | `sumo-gateway.service`: `/home/ubuntu/sumo/gateway/sumo_gateway.py` on 0.0.0.0:8080, `CPUQuota=25%`, `MemoryMax=256M` |
| Genesis hash | `9eDPpAG4RUei7HTciCEucnshXm6Rfo61d6KU8hyXwx6n` |
| Program / mint | `6h1PqXArg2Ap1CJdR1hXXWhqSrzkeboqi5cx1y44NvTW` / `7VNZhAWFCKjrZVKcbU2sXxT5mNAbzYh8qmtD7HfePabR` |

Validator binary: Anza publishes no aarch64-Linux release, so the binaries come from the arm64 layer of
`ghcr.io/beeman/solana-test-validator:latest` (Agave 4.1.1 built from source, image 2026-07-06; layer
`sha256:9fa722a8...e57`). Only `solana` and `solana-test-validator` were extracted; no Docker is installed.

The gateway is the only thing reachable from outside (once the Oracle rule below exists). It:
- forwards only allowlisted JSON-RPC methods (account/balance/token reads, blockhash, sendTransaction,
  simulateTransaction, signature status/history, slot, genesis hash, health, version, requestAirdrop);
  no getProgramAccounts, no batches, no websockets, bodies max 16 KB;
- rate-limits each IP (10 req/s, sendTransaction 2/s);
- faucet (`requestAirdrop`): max 1 test SOL per request, 1 per IP per 10 min, 5 per IP per day, 200 per day total;
- serves the stats page at `/` and the token metadata at `/metadata.json`.

Ports 8899/8900/9900 bind 0.0.0.0 but the server's iptables REJECTs everything except 22 and 8080,
and the Oracle security list allows only 22 and 8080 (Josh added the 8080 rule on 31 Oct 2026:
TCP, source 0.0.0.0/0; checked from outside the same day, the gateway answers).

## Port 8080 in the Oracle console (done 31 Oct 2026; steps kept for a rebuild)

iptables allows 8080 (rule saved in `/etc/iptables/rules.v4`) and the Oracle Security List rule is in
place, so nothing needs doing now. If the instance is ever rebuilt, Oracle's cloud firewall blocks 8080
again until this one ingress rule is re-added:

1. Sign in at https://cloud.oracle.com.
2. Menu (top left) -> **Compute** -> **Instances** -> click **instance-20261021-1011**.
3. Under **Instance details** / **Primary VNIC**, click the **Subnet** link.
4. Open the **Security** tab (older console: **Security Lists** on the left) and click the
   **Default Security List for ...** (the one already holding the port 22 rule).
5. **Security rules** tab -> **Add Ingress Rules**, then fill in:
   - Stateless: **unticked**
   - Source Type: **CIDR**
   - Source CIDR: **0.0.0.0/0** (anyone; the gateway is filtered and the coin is worthless), or your home IP
     followed by `/32` to allow only your house (find it at https://ifconfig.me; it can change)
   - IP Protocol: **TCP**
   - Source Port Range: leave blank
   - Destination Port Range: **8080**
   - Description: `Sumo Frog gateway`
6. Click **Add Ingress Rules**.
7. Check: open http://<server address>:8080/ in a browser. You should see the Sumo Frog stats page.

If the instance's VNIC uses a **Network Security Group** instead, add the same rule to that NSG.

## Validator log rotation (added 31 Oct 2026)

The validator writes a very chatty log (`~/sumo/ledger/validator-<id>.log`, ~2.7 GB/day; `validator.log`
is a symlink to it). Without a cap it would fill the 45 GB disk in about 12 days. It is capped by logrotate,
run every hour by a systemd timer (Ubuntu's own logrotate only runs once a day, too slow for this):

- `/etc/logrotate-sumo.conf` (copy: `logrotate-sumo.conf`): daily, or sooner once the live log passes
  200M at an hourly check; keep 2 gzip copies; `copytruncate`, so the validator keeps writing to the same
  file (it opens it O_APPEND) and is **never restarted**. Kept outside `/etc/logrotate.d/` so the daily
  system run doesn't also touch it.
- `/etc/systemd/system/sumo-logrotate.{service,timer}` (copies here): hourly, Nice 19, idle IO,
  own state file `/var/lib/logrotate/sumo-status`.

Steady state: live log under ~320 MB plus two ~30-40 MB `.gz` files. First forced run on 31 Oct shrank
the 2.3 GB log to a 308 MB `.1.gz` (ages out after two more rotations); disk went 34G -> 36G free.
No RUST_LOG change was made (that would need a validator restart).

```bash
$R 'systemctl list-timers sumo-logrotate.timer --no-pager; ls -la ~/sumo/ledger/*.log*'
$R 'sudo logrotate -d --state /var/lib/logrotate/sumo-status /etc/logrotate-sumo.conf'   # dry run
```
Remove: `sudo systemctl disable --now sumo-logrotate.timer` and delete the three files.

## Admin (from the box)

```bash
R="$HOME/.venvs/ssh/bin/python /workspace/oracle/rx.py"
$R 'systemctl status sumo-validator sumo-gateway --no-pager | head -20'
$R 'journalctl -u sumo-gateway -n 30 --no-pager'          # airdrop log lines
$R 'du -sh ~/sumo/ledger'
# Tunnels for admin work (deploy/upgrade/setup), box only:
~/.venvs/ssh/bin/python /workspace/oracle/tunnel.py 18899 8899 &   # RPC
~/.venvs/ssh/bin/python /workspace/oracle/tunnel.py 18900 8900 &   # websocket (anchor/ts-node needs it)
```

Program upgrades: `solana program deploy -u http://127.0.0.1:18899 --use-rpc --keypair .keys/deployer.json
--upgrade-authority .keys/deployer.json --program-id .keys/program.json target/deploy/sumofrog.so`.
Gateway/page changes: copy files with `/workspace/oracle/put.py` into `/home/ubuntu/sumo/gateway/`
(`www/` for the page), then `sudo systemctl restart sumo-gateway`.

## Turning it off / removing

```bash
$R 'sudo systemctl disable --now sumo-gateway sumo-validator'
$R 'sudo iptables -D INPUT -p tcp -m state --state NEW -m tcp --dport 8080 -m comment --comment sumo-gateway -j ACCEPT && sudo sh -c "iptables-save > /etc/iptables/rules.v4"'
```
Then delete the 8080 ingress rule in the Oracle console. `~/sumo/` can be deleted afterwards
(pre-change iptables file kept at `~/sumo/rules.v4.pre_sumo`). Wiping `~/sumo/ledger` resets the chain;
the program would then need redeploying and `scripts/setup.ts` rerunning.
