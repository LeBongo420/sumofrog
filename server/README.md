# Sumo Frog private test network (Oracle server)

**Retired: old private Oracle test network, switched off 21 Nov 2026, not used for the public devnet launch.**

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
- serves the static website at `/` (home, guide, whitepaper; stats at `/stats/`) and the token metadata at `/metadata.json`.

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

When assembling `www/` or the public HTTPS site, never copy the real
`stats/sumo_config.js` (it may hold the private server address). Stage a
publishable copy with `python3 scripts/build_site.py --publish-dir DIR`
(example config, `YOUR_SERVER` placeholder) or
`python3 scripts/build_site.py --publish-dir DIR --stats-network devnet`
(official Solana devnet RPC only). The script copies tracked files only, and
refuses a publish folder that is (or is inside) the live `stats/` or `docs/`
trees, including via a symlink. It also refuses to publish any other stats
config. The miner zip is packed from git (`scripts/build_zips.py`), never from
gitignored working-tree copies.

## Turning it off / removing

```bash
$R 'sudo systemctl disable --now sumo-gateway sumo-validator'
$R 'sudo iptables -D INPUT -p tcp -m state --state NEW -m tcp --dport 8080 -m comment --comment sumo-gateway -j ACCEPT && sudo sh -c "iptables-save > /etc/iptables/rules.v4"'
```
Then delete the 8080 ingress rule in the Oracle console. `~/sumo/` can be deleted afterwards
(pre-change iptables file kept at `~/sumo/rules.v4.pre_sumo`). Wiping `~/sumo/ledger` resets the chain;
the program would then need redeploying and `scripts/setup.ts` rerunning.

## Public HTTPS for the website only (prepared, not yet live)

Josh said yes to this on 12 November 2026. It is **not live yet**: it needs a hostname and two
Oracle console rules (see below). Until those are in place, leave Caddy uninstalled and ports
80/443 closed.

The plan is the simplest free route: **Caddy** with automatic Let's Encrypt certificates.

| | |
|---|---|
| What is public on 443 (and 80 for the certificate check) | The static website only (home, guide, whitepaper, stats page) |
| What stays off 443 | The filtered JSON-RPC gateway, the validator, and every other service |
| JSON-RPC | Remains on port 8080 (HTTP), as today |
| Config templates | `Caddyfile.example`, `sumo-site.service` (YOUR_DOMAIN placeholder, no server address) |
| Site files on the server | `/home/ubuntu/sumo/site`. Publish into a fresh empty folder (for example `/home/ubuntu/sumo/site.new`) with `python3 scripts/build_site.py --publish-dir ...` so only the example or devnet stats config is included, never the real `stats/sumo_config.js`, then swap with `rm -rf /home/ubuntu/sumo/site.old` followed by `mv -T /home/ubuntu/sumo/site /home/ubuntu/sumo/site.old` and `mv -T /home/ubuntu/sumo/site.new /home/ubuntu/sumo/site`. The script refuses a non-empty folder, so a second publish cannot go straight into the live `site`. The `rm -rf` of `site.old` makes the swap safe to repeat. |
| Caddy process | `sumo-site.service` runs as a dedicated `sumo-site` user with only `CAP_NET_BIND_SERVICE`, `ProtectHome=tmpfs`, and read-only binds for `/home/ubuntu/sumo/site` and the Caddyfile only (template only; not installed) |

Caddy will refuse POST on 80/443, so the test-network RPC cannot be reached through the website.

### What has to come from Josh before this can go live

1. **A hostname** (a domain Josh already owns, or a free one such as a DuckDNS name) with an
   A record pointed at the same server that already serves the test site on port 8080.
   Let's Encrypt will not issue a certificate without a real hostname. An IP address is not enough,
   and we will not use an IP-based name.
2. **Two ingress rules in the Oracle console**, same place as the existing port 8080 rule:
   - TCP, source `0.0.0.0/0` (or Josh's home IP `/32`), destination port **80**
   - TCP, source `0.0.0.0/0` (or Josh's home IP `/32`), destination port **443**
   Without these, the cloud firewall drops 80 and 443 even if iptables on the machine allows them.

Once both are ready, the remaining work is: install Caddy, create a system
user `sumo-site` with home `/var/lib/caddy` (and `/var/log/caddy`), both owned
by that user, publish the website into a fresh empty folder (for example
`/home/ubuntu/sumo/site.new`) with
`python3 scripts/build_site.py --publish-dir ...` (never the real
`stats/sumo_config.js`; the script refuses a non-empty folder, including
the live `site` after the first publish), then swap it into place
(`rm -rf /home/ubuntu/sumo/site.old`, then
`mv -T /home/ubuntu/sumo/site /home/ubuntu/sumo/site.old &&
mv -T /home/ubuntu/sumo/site.new /home/ubuntu/sumo/site`), put a Caddyfile with the hostname in
`/home/ubuntu/sumo/Caddyfile`, allow 80 and 443 in iptables (saved to
`/etc/iptables/rules.v4`, comments `sumo-site-http` and `sumo-site-https`),
and start `sumo-site.service`. The unit binds ports 80 and 443 with only
`CAP_NET_BIND_SERVICE`, hides `/home` with `ProtectHome=tmpfs`, and bind-mounts
only the site folder and the Caddyfile. It must not run as root. No tunnel is used. The
validator stays bound as it is today; iptables continues to reject its ports.

Do not announce the site or turn on GitHub Pages as part of this step.
Do not install Caddy or open ports 80/443 until Josh has picked a hostname
and added the two Oracle rules.
