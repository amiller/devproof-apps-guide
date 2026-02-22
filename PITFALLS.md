# Pitfalls & Debugging Reference

> The stuff that wastes your afternoon. For people who've done the tutorial and are now shipping something real.

**Main guide:** [README.md](./README.md)

---

## 1. KMS: You're Probably on the Wrong One

**The default KMS (Pha) has no public upgrade log.** This means:
- Trust Center shows current state only, not history
- An operator could deploy malicious code, exfiltrate, redeploy clean — no evidence
- Every single audit in devproof-audits-guide found this

**Use Base KMS for anything claiming transparency:**
```bash
phala deploy --kms-id kms-base-prod5 --private-key "$PRIVATE_KEY"
```

Base KMS emits an on-chain event for every `phala cvms upgrade`, queryable retroactively at any block height. Pha KMS is invisible to auditors.

If you don't set a KMS explicitly, you get Pha. You won't realize the difference until an auditor asks for your upgrade history and you can't produce it.

---

## 2. Image Tags Don't Do What You Think

**Phala does NOT update when you push a new image to the same tag.** Tags like `:latest` or `:staging` are mutable pointers — useless for TEE deployment.

Always pin by digest in your deploy docker-compose.yml:
```yaml
# BAD
image: ghcr.io/you/app:latest

# GOOD
image: ghcr.io/you/app@sha256:abc123...
```

**Deployment workflow:**
```bash
docker build -t ghcr.io/you/app:staging .
docker push ghcr.io/you/app:staging
# Get the digest:
docker inspect ghcr.io/you/app:staging --format '{{index .RepoDigests 0}}'
# Update docker-compose.yml with the sha256 digest
# Then deploy
```

Also: old digests get deleted upstream. If your deploy compose references a stale digest, it'll fail silently. Always `docker pull` before referencing.

**GHCR packages default to private.** When you push a new container image to `ghcr.io`, it's private. The CVM will silently fail to pull it. You must make it public via the GitHub web UI at `https://github.com/users/<you>/packages/container/<pkg>/settings` — the REST API for changing package visibility returns 404 despite correct auth. This bites you on every new package.

---

## 3. Gateway URLs: The Three Patterns

```
<app-id>-<port>.dstack-pha-prodN.phala.network    # HTTP (gateway terminates TLS)
<app-id>-<port>s.dstack-pha-prodN.phala.network   # TLS passthrough (note the "s")
<app-id>-8090.dstack-pha-prodN.phala.network      # Attestation metadata endpoint
```

The `s` suffix is subtle and easy to miss. Without it, the gateway decrypts TLS and forwards HTTP. With it, TLS passes through to your app.

**Know which gateway your CVM is on.** Check with `phala cvms list`. If your CVM is on prod7 but you're hitting prod9 URLs, nothing will route.

**The simulator has no gateway.** Local dev doesn't test TLS behavior. You need a real deployment (or ngrok/stunnel) to test gateway routing.

**Custom domain routing (TXT records) only works on prod9.** If you deploy to prod5/prod7 expecting custom domain support via TXT records, it won't work.

---

## 4. SSH Access: Dev Image for Staging, No SSH in Prod

Use the **dev base image** (`dstack-dev-0.5.x`) for staging. It includes SSH built-in. Deploy with `--dev-os` and provide your public key:

```bash
# Initial deploy — key MUST be provided at creation time
ssh-keygen -t ed25519 -f deploy_key -N "" -C "staging"
phala deploy -n my-app -c docker-compose.staging.yaml --dev-os --ssh-pubkey deploy_key.pub

# Connect with your key
phala ssh my-app -- -i deploy_key echo "it works"
phala ssh my-app -- -i deploy_key -L 8080:localhost:80  # port forward
```

For production, use the **prod base image** (`dstack-0.5.x`) which intentionally has no SSH. No one can access the CVM remotely — that's the point.

| | Staging | Production |
|---|---|---|
| Base image | `dstack-dev-0.5.x` | `dstack-0.5.x` |
| SSH | `phala ssh` (built-in) | None (by design) |
| Debugging | Direct shell | Logs only, or redeploy with dev image |

**SSH auth uses env vars under the hood.** The `--ssh-pubkey` flag sets `DSTACK_AUTHORIZED_KEYS` (added to `allowed_envs` automatically). You can also set `DSTACK_ROOT_PASSWORD` for password auth. Both are dev images only. See [Phala docs](https://docs.phala.com/phala-cloud/networking/specifications#ssh-access).

**Critical gotcha: `--ssh-pubkey` only works on initial creation.** If you upgrade/redeploy an existing CVM with a new key, the old key stays. You must delete and recreate the CVM to change SSH keys.

```bash
# Useful phala ssh options
phala ssh my-app -v                     # verbose (shows connection details)
phala ssh my-app --dry-run              # print the SSH command without running it
phala ssh my-app -g dstack-pha-prod7.phala.network  # offline mode (skip API lookup)
```

---

## 5. dstack-ingress: Custom Domains and TLS

If you want a custom domain (not the `<app-id>-<port>` URL), you need dstack-ingress running as a sidecar.

**Common failure: exit code 7** — certbot gets the cert successfully, then nginx fails to start. Check logs via SSH:
```bash
docker logs dstack-dstack-ingress-1
```

**Required DNS records:**
```
CNAME  app.yourdomain.com                        → _.dstack-pha-prodN.phala.network
TXT    _dstack-app-address.app.yourdomain.com    → <app-id>:443
```

Both records must exist. If either is wrong, routing fails silently.

**You may also need a CAA record:**
```
CAA 0 issue "letsencrypt.org"
```

**GATEWAY_DOMAIN must match your actual cluster:**
```yaml
environment:
  - GATEWAY_DOMAIN=_.dstack-pha-prod7.phala.network  # match your CVM's cluster!
```

**Cloudflare:** Wildcard domains must be "DNS Only" mode, not proxied (orange cloud off).

---

## 6. Simulator Socket Version Mismatch

```bash
docker compose run --rm -p 8080:8080 \
  -v ~/.phala-cloud/simulator/0.5.3/dstack.sock:/var/run/dstack.sock \
  app
```

The `0.5.3` must match your installed `phala` CLI version. If it doesn't, `getKey()` calls hang or fail silently. The app starts fine but can't reach KMS.

Check your version: `phala --version`. Match that in the socket path.

**Simulator API format quirks (undocumented):**
- `GetKey`: `purpose` must be a **string** (`"signing"`), not an integer. Returns `key` as hex, not base64.
- `GetQuote`: `report_data` must be **hex-encoded**, not base64. Sending base64 gives a cryptic error: `"Invalid character 'G' at position 1"`.

```bash
# Correct GetKey call
curl --unix-socket ~/.phala-cloud/simulator/0.5.3/dstack.sock \
  http://localhost/GetKey -X POST -H 'Content-Type: application/json' \
  -d '{"path":"/my-app","purpose":"signing"}'

# Correct GetQuote call (report_data is hex)
curl --unix-socket ~/.phala-cloud/simulator/0.5.3/dstack.sock \
  http://localhost/GetQuote -X POST -H 'Content-Type: application/json' \
  -d '{"report_data":"74657374"}'
```

---

## 7. allowed_envs: The #1 Vulnerability

**If a URL handles user data, it must be hardcoded in docker-compose.yml, never in allowed_envs.**

```yaml
# BAD — operator can redirect to their server and steal tokens
allowed_envs:
  - API_URL
environment:
  - API_URL=${API_URL}

# GOOD — hardcoded, included in compose hash
environment:
  - API_URL=https://api.trusted-service.com/v1
```

Every audit in devproof-audits-guide found this pattern. It's the most common way to make a TEE app ruggable.

Same applies to image references — don't put `${IMAGE_VAR}` in allowed_envs. Hardcode the digest.

---

## 8. Compose Hash ≠ docker-compose.yml Hash

The attested `compose_hash` is `sha256(app_compose_json_string)`, which includes:
- `docker_compose_file` (your YAML)
- `allowed_envs` array
- `features` array
- `pre_launch_script`
- `kms_enabled`, `gateway_enabled`, etc.

You cannot reproduce it from just the docker-compose.yml in your repo. Use:
```bash
curl -s "https://<app-id>-8090.<cluster>.phala.network/"
```
to fetch the full app-compose JSON and verify.

**The 8090 endpoint returns HTML, not JSON.** The response is an HTML page with JSON data embedded using HTML entities (`&#34;` for `"`). To extract the `app_compose` and `compose_hash` fields, you need to decode HTML entities first:
```python
import html, re, hashlib
decoded = html.unescape(raw_html)
m = re.search(r'"compose_hash":\s*"([a-f0-9]+)"', decoded)
# compose_hash is there, but it's sha256 of the full app_compose JSON,
# NOT sha256 of your docker-compose.yml file
```

See `starter-kit-app/verify.sh` for a working implementation.

**`phala cvms attestation` only works if you own the app.** Third-party auditors must use the 8090 endpoint.

---

## 9. Reproducible Builds Details

```dockerfile
# Pin base image by digest
FROM node:22-slim@sha256:773413...

# Deterministic timestamps
ARG SOURCE_DATE_EPOCH=0

# Pin system packages (if any)
RUN echo 'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20250101T000000Z bookworm main' \
  > /etc/apt/sources.list

# Normalize timestamps at end
RUN find /app -exec touch -d "@${SOURCE_DATE_EPOCH}" {} + 2>/dev/null || true
```

**Build with:**
```bash
docker buildx build \
  --build-arg SOURCE_DATE_EPOCH=0 \
  --output type=oci,dest=./image.tar,rewrite-timestamp=true \
  .
```

**Known problematic packages:**
| Package | Issue | Fix |
|---------|-------|-----|
| Node.js 22+ | Compile cache in `/tmp/node-compile-cache` | `rm -rf /tmp/node-compile-cache` |
| Python pip | Timestamps in `.pyc` | `PYTHONDONTWRITEBYTECODE=1` |
| Go | Embeds build paths | `-trimpath` flag |

---

## 10. Vercel Frontend Notes

If using Vercel for a dashboard/frontend that calls the TEE backend:

- **Env vars are scoped**: `preview` ≠ `production`. Set both explicitly.
- **No SQLite on Vercel**: If your code falls back to SQLite when `DATABASE_URL` is unset, you'll get `FUNCTION_INVOCATION_FAILED`. Always check the fallback path.
- **Preview deploys require Vercel SSO auth.** Use `--prod` for public access.
- **Git email must match Vercel team.** If deploy fails on auth, check `git config user.email`.

---

## 11. Deployment Checklist

```
Pre-deploy:
[ ] Base image pinned by digest in Dockerfile
[ ] Deploy compose uses image digest (not tag)
[ ] No user-data URLs in allowed_envs
[ ] KMS set to Base (not Pha default)
[ ] GATEWAY_DOMAIN matches actual cluster
[ ] Staging: --dev-os + --ssh-pubkey at creation time
[ ] SOURCE_DATE_EPOCH=0 in Dockerfile

Deploy:
[ ] docker build + push + get digest
[ ] Update digest in docker-compose.deploy.yml
[ ] phala deploy --cvm-id <ID> -c docker-compose.deploy.yml -e .env
[ ] Verify app responds: curl https://<app-id>-<port>.<gateway>/health
[ ] Verify attestation: curl https://<app-id>-8090.<gateway>/

Post-deploy:
[ ] SSH in and check logs: docker logs <container>
[ ] Verify compose hash matches expected
[ ] If custom domain: check both CNAME and TXT records
[ ] Test from client/frontend
```

---

## 12. Debugging Cheat Sheet

| Symptom | Likely Cause |
|---------|-------------|
| App starts but `getKey()` hangs | Simulator socket version mismatch |
| Gateway returns 502/404 | Wrong cluster in URL, or app not listening on expected port |
| dstack-ingress exit code 7 | nginx fails after cert renewal; check logs |
| Custom domain doesn't resolve | Missing TXT `_dstack-app-address` record |
| `phala ssh` permission denied | Key not set at creation time; must delete + recreate CVM |
| `phala ssh` doesn't work | Not on dev image; redeploy with `--dev-os` |
| Image deploy doesn't update | Using tag instead of digest |
| Auditor can't verify | Using Pha KMS (no public log); switch to Base |
| Vercel returns FUNCTION_INVOCATION_FAILED | Missing DATABASE_URL; SQLite not available |
| Compose hash doesn't match | Hash includes full app-compose JSON, not just docker-compose.yml |
| Build not reproducible | Unpinned base image, missing SOURCE_DATE_EPOCH, or node compile cache |
| CVM starts but image pull fails silently | GHCR package is private; make public via web UI |
| `GetKey` returns error about "invalid type: integer" | `purpose` must be a string, not int |
| `GetQuote` returns "Invalid character" error | `report_data` must be hex-encoded, not base64 |
