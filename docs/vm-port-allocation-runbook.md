# VM Operations Runbook: Port Allocation and Caddy Routing

Operational rules for running multiple stacks side by side on the shared Oracle
Cloud VM (`vcn-20260908-1519`, Ubuntu, E2.1.Micro, IP `147.15.76.139`) without
port conflicts and without Caddy routing breakage.

Background: the 2026-10-18 Caddy 502 incident
([contexto-2026-10-18-incidente-caddy-502.md](contexto-2026-10-18-incidente-caddy-502.md))
was caused by a duplicated site definition (an inline block in the ApitaCerto
Caddyfile plus `condo.caddy` in `/opt/caddy-sites/`) and by single-file bind-mount
traps. This runbook codifies the rules that prevent a repeat.

## Stacks on the VM

| Stack | Path | Role | Domains | Internal ports | Host ports |
|---|---|---|---|---|---|
| ApitaCerto | `/opt/apitacerto` (`compose.prod.yaml`) | Production. Runs the Caddy entrypoint for ALL sites | `apitacerto.com.br`, `147-15-76-139.sslip.io`, `stats.…` (goatcounter) | app 8000, postgres 5432, goatcounter 8080 | 80, 443 (Caddy only) |
| Luas Social | `/opt/luas` | Production | `luas.147-15-76-139.sslip.io` | api 8010 | none |
| Soutes (Luas AI.S) | `/opt/soutes` | Production | `luasai.com.br`, `soutes.147-15-76-139.sslip.io` | 8787 | none |
| LuasCondo | `/opt/luas-condo` (git clone) | Dev/demo | `condo.147-15-76-139.sslip.io` | frontend 5173 (Vite dev) / 80 (nginx prod), backend 8000, db 5432, mock-bitrix 8080, prometheus 9090, grafana 3000 | loopback only: 5432, 8000, 8080, 5173, 9090, 3001 |

Site routing lives in `/opt/caddy-sites/*.caddy` (one file per site), imported by
`import /etc/caddy/sites/*.caddy` inside `/opt/apitacerto/Caddyfile`.

## Golden rules

1. **Only the ApitaCerto Caddy publishes host ports** (80/443). Every other
   service is reached by container name over the shared docker network `web`,
   never by a published host port.
2. **One site = one block, in one file** at `/opt/caddy-sites/{domain}.caddy`.
   Never define site blocks inline in `/opt/apitacerto/Caddyfile`. Duplicated
   blocks make `caddy validate` fail with `ambiguous site definition`, and a
   failing validation silently blocks every reload.
3. **Never `sed -i` / `docker cp` / `cat >` the mounted `/opt/apitacerto/Caddyfile`.**
   It is a single-file bind mount mounted read-only: `sed -i` creates a new inode
   the container never sees, `docker cp` fails with `device or resource busy`,
   and in-container writes fail with `read-only file system`.
   The supported path is: edit on host -> `caddy validate` -> `caddy reload`.
4. **A new stack must join the external `web` network** (declare it as
   `external: true` in its compose file). Caddy reaches upstreams by container
   name on that network.
5. **Internal port is not the published port.** Caddy talks to the internal
   container port (Vite 5173, backend 8000). Published ports are host-side
   conveniences and default to loopback binding via `.env` overrides
   (`*_HOST_IP` / `*_HOST_PORT`, see `.env.example`).
6. **Frontend internal port differs per mode**: Vite dev = 5173, nginx prod = 80.
   `deploy/condo.caddy` upstream must match the mode that is actually running.

## Change procedures

### Reload Caddy (zero downtime, preferred)

```bash
# 1. Edit the site file on the host, then validate the full boot config:
sudo cp /opt/apitacerto/Caddyfile /opt/caddy-sites/validate-boot.txt
docker exec apitacerto-caddy-1 caddy validate --config /etc/caddy/sites/validate-boot.txt --adapter caddyfile
sudo rm -f /opt/caddy-sites/validate-boot.txt

# 2. Apply gracefully (all sites stay up):
docker exec apitacerto-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

`--adapter caddyfile` is required for files with arbitrary names: Caddy only
auto-adapts files literally named `Caddyfile`.

### Restart Caddy (seconds of downtime for ALL sites)

Restart re-reads `/etc/caddy/Caddyfile` from the host path, flushing any stale
inode seen inside the container. Validate the boot config first (procedure
above), agree the window with the stack owners (ApitaCerto is production), then:

```bash
docker restart apitacerto-caddy-1
docker exec apitacerto-caddy-1 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

### Verify everything after a change

```bash
for u in "https://apitacerto.com.br/" \
         "https://luas.147-15-76-139.sslip.io/api/v1/health" \
         "https://condo.147-15-76-139.sslip.io/api/health" \
         "https://condo.147-15-76-139.sslip.io/" \
         "https://soutes.147-15-76-139.sslip.io/" \
         "https://luasai.com.br/"; do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 10 "$u")
  echo "$code  $u"
done
sudo ss -tlnp | grep docker-proxy   # confirm only expected host ports
```

Expected: all `200`; only `80` and `443` bound by Caddy's docker-proxy, plus the
condo loopback bindings.

## Deploying LuasCondo changes

```bash
# VM:
cd /opt/luas-condo && git pull --ff-only
docker compose up -d            # recreates only services whose config changed
docker compose ps               # confirm healthy before calling it done
```

Keep the VM clone in sync with the repository: local edits made directly on the
VM tend to drift and caused part of the incident (the deployed `condo.caddy` was
older than the committed one). Prefer committing in the repo, pushing, then
pulling on the VM.
