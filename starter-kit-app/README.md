# dstack Toy Example

Minimal "hello world" for dstack TEE deployment. Tests KMS, attestation, secret injection, and gateway routing in ~50 lines of code.

**Companion to:** [dstack DevProof Microservice Guide](../dstack-devproof-microservice-guide.md)

## Endpoints

| Endpoint | What it proves |
|----------|---------------|
| `GET /health` | App is running |
| `GET /key` | KMS connectivity — returns derived public key |
| `GET /attestation` | TEE works — returns TDX quote (or simulated) |
| `GET /secret` | Secret injection — returns env var value |

## Workflow: Local → Staging → Production

### 1. Local Dev (simulator)

```bash
# Start the dstack simulator (guide §6)
phala simulator start

# Check your phala version matches the socket path in docker-compose.yaml
phala --version  # should be 0.5.3

docker compose up --build
```

Test it:
```bash
curl localhost:8080/health       # { "ok": true }
curl localhost:8080/key          # derived public key (proves simulator KMS)
curl localhost:8080/attestation  # simulated quote
curl localhost:8080/secret       # "local-dev-secret"
```

### 2. Deploy to Staging (dev image, SSH works)

Use the dev base image (`dstack-dev-0.5.x`) so `phala ssh` works. See guide §4.

```bash
# Build and push your image, get the digest (guide §2)
docker build -t ghcr.io/you/toy-example:staging .
docker push ghcr.io/you/toy-example:staging
docker inspect ghcr.io/you/toy-example:staging --format '{{index .RepoDigests 0}}'
# Update the digest in docker-compose.staging.yaml

phala deploy -c docker-compose.staging.yaml -e SECRET_VALUE=staging-secret
```

Verify:
```bash
curl https://<app-id>-8080.<gateway>/health
phala ssh my-app                  # interactive shell
phala ssh my-app -- cat /proc/1/cmdline  # check what's running
```

### 3. Verify Attestation

```bash
./verify.sh <app-id> dstack-pha-prod7.phala.network
```

This fetches the compose hash from port 8090 and compares it to your local file. See guide §8 for why `compose_hash ≠ sha256(docker-compose.yml)`.

### 4. Deploy to Production (prod image, Base KMS)

Use the prod base image (`dstack-0.5.x`) — no SSH by design. Use Base KMS for on-chain transparency. See guide §1.

```bash
phala deploy -c docker-compose.prod.yaml \
  --kms-id kms-base-prod5 \
  --private-key "$PRIVATE_KEY"
```

Verify:
```bash
curl https://<app-id>-8080.<gateway>/health
./verify.sh <app-id> <gateway>
# Confirm: phala ssh should NOT work (prod image has no SSH)
```

## Three Compose Files

| File | Base Image | SSH | KMS | Secrets |
|------|-----------|-----|-----|---------|
| `docker-compose.yaml` | Local build | N/A | Simulator | Inline env |
| `docker-compose.staging.yaml` | `dstack-dev-0.5.x` | `phala ssh` works | Pha (fine for staging) | `allowed_envs` |
| `docker-compose.prod.yaml` | `dstack-0.5.x` | None (by design) | Base (on-chain) | Hardcoded in compose |

## Guide Cross-References

| Step | Guide Section |
|------|--------------|
| KMS selection | §1 — You're Probably on the Wrong One |
| Image digests | §2 — Image Tags Don't Do What You Think |
| Gateway URLs | §3 — The Three Patterns |
| SSH access | §4 — Dev Image for Staging |
| Simulator socket | §6 — Socket Version Mismatch |
| Secret injection | §7 — allowed_envs: The #1 Vulnerability |
| Compose hash | §8 — Compose Hash ≠ docker-compose.yml Hash |
