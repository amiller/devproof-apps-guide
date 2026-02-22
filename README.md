# Build a TEE App with dstack

A guide and two starter kits for building verifiable apps on dstack/Phala Cloud. Pick a starter kit, customize it, deploy to a TEE with attestation and on-chain transparency.

## Starter Kits

### [starter-kit-minimal/](./starter-kit-minimal/) — TEE Microservice

Pure TEE backend (~85 lines). KMS key derivation, attestation quotes, signed Ethereum-compatible reports, secret injection. Uses `@phala/dstack-sdk`.

**Good for:** microservices, oracles, signers, attestation endpoints, anything that doesn't need a frontend or database.

### [starter-kit-fullstack/](./starter-kit-fullstack/) — Vercel + TEE + Neon

Full-stack encrypted KV store. AES-256-GCM encryption inside the TEE, ciphertext in Neon Postgres, Vercel frontend with session auth, TLS oracle. Talks to dstack via raw socket.

**Good for:** user-facing apps, encrypted storage, TLS oracles, anything needing a frontend + database + TEE backend.

**References:** [Phala Cloud docs](https://docs.phala.com) · [dstack SDK](https://github.com/aspect-build/dstack) · [dstack-tutorial](https://github.com/aspect-build/dstack-tutorial) · [devproof-audits-guide](https://github.com/aspect-build/devproof-audits-guide)

---

## Quickstart

### 1. Run locally with the simulator

```bash
npm i -g @aspect-build/phala
phala simulator start

# Minimal kit
cd starter-kit-minimal
docker compose up --build
curl localhost:8080/health        # {"ok":true}
curl localhost:8080/key           # KMS-derived public key
curl localhost:8080/attestation   # simulated TDX quote

# Fullstack kit
cd starter-kit-fullstack/enclave
docker compose up --build
curl localhost:8080/health
curl localhost:8080/key
```

### 2. Build and push your image

```bash
docker build -t ghcr.io/YOU/my-app:v1 .
docker push ghcr.io/YOU/my-app:v1

# Get the pinned digest (tags are mutable, digests are not)
docker inspect ghcr.io/YOU/my-app:v1 --format '{{index .RepoDigests 0}}'
# → ghcr.io/YOU/my-app@sha256:abc123...
```

Update `docker-compose.prod.yaml` with the digest:
```yaml
image: ghcr.io/YOU/my-app@sha256:abc123...
```

> GHCR packages default to private. Make yours public at `https://github.com/users/YOU/packages/container/my-app/settings` — the CVM will silently fail to pull private images.

### 3. Deploy to Phala Cloud

```bash
phala deploy -c docker-compose.prod.yaml \
  --kms base \
  --private-key "$PRIVATE_KEY"
```

### 4. Verify it works

```bash
curl https://<app-id>-8080.<gateway>/health
curl https://<app-id>-8090.<gateway>/        # attestation metadata
./verify.sh <app-id> <gateway>
```

Gateway URL format: `<app-id>-<port>.dstack-base-prodN.phala.network` (Base KMS) or `<app-id>-<port>.dstack-pha-prodN.phala.network` (Pha KMS).

---

## Three Compose Files

Both kits follow the same three-compose-file pattern:

| File | Base Image | SSH | KMS | Use Case |
|------|-----------|-----|-----|----------|
| `docker-compose.yaml` | Local build | N/A | Simulator | Development |
| `docker-compose.staging.yaml` | `dstack-dev-0.5.x` | `phala ssh` works | Pha (fine for staging) | Testing on real CVM |
| `docker-compose.prod.yaml` | `dstack-0.5.x` | None (by design) | Base (on-chain log) | Production |

---

## Reproducible Builds

Both Dockerfiles are set up for reproducible builds:
- Base image pinned by digest (not tag)
- `SOURCE_DATE_EPOCH=0` normalizes all timestamps
- Node compile cache cleaned
- All file timestamps normalized

```bash
./build-reproducible.sh
# Builds twice, compares hashes — should say "REPRODUCIBLE"

# Push a reproducible image
skopeo copy oci-archive:build.tar docker://ghcr.io/YOU/my-app:v1
```

---

## Verification & Attestation

Every CVM exposes port 8090 with metadata including:
- **`compose_hash`** — SHA-256 of the full app-compose JSON (your docker-compose + allowed_envs + features + KMS config). This is NOT `sha256(docker-compose.yml)`.
- **`os_image_hash`** — The base VM image hash.
- **TDX quote** — Hardware attestation from Intel TDX proving the code runs in a real enclave.

### How a Third Party Verifies

1. Fetch metadata: `curl https://<app-id>-8090.<gateway>/`
2. Compare `compose_hash` against expected (from your repo + deploy config)
3. Verify the TDX quote chain (Intel root of trust)
4. If using Base KMS: query on-chain upgrade logs to confirm the compose hash has been stable

The `verify.sh` script in each kit does steps 1-2. The fullstack kit also includes [VERIFY.md](./starter-kit-fullstack/VERIFY.md) — a narrative audit guide for third parties.

### Base KMS vs Pha KMS

| | Base KMS | Pha KMS (default) |
|---|---|---|
| On-chain upgrade log | Yes | No |
| Auditable history | Yes | No |
| Deploy flag | `--kms base` | (default, no flag needed) |

**Always use Base KMS for production.** Pha KMS has no public log — an operator could deploy malicious code, exfiltrate data, and redeploy clean with no evidence.

---

## Customizing

### Adding Endpoints

Minimal kit — edit `app.js`, add to the `routes` object. Fullstack kit — edit `enclave/app.js` for TEE logic, add `api/*.js` for Vercel proxy endpoints.

### Adding a Database

For local dev, use in-memory or SQLite. For production, use a managed database (Neon Postgres, Firestore, etc.) and hardcode the URL in your compose file:

```yaml
# docker-compose.prod.yaml
environment:
  - DATABASE_URL=postgres://user:pass@host/db   # hardcoded, not in allowed_envs
```

**Never put database URLs in `allowed_envs`** — the operator could redirect them. See [Pitfalls §7](./PITFALLS.md#7-allowed_envs-the-1-vulnerability).

### Custom Domains

Add a `dstack-ingress` sidecar to your compose file. See [Pitfalls §5](./PITFALLS.md#5-dstack-ingress-custom-domains-and-tls) for details.

---

## Staging Workflow

```bash
ssh-keygen -t ed25519 -f deploy_key -N "" -C "staging"

phala deploy -n my-app-staging \
  -c docker-compose.staging.yaml \
  --dev-os \
  --ssh-pubkey deploy_key.pub

phala ssh my-app-staging -- -i deploy_key
phala ssh my-app-staging -- -i deploy_key -L 8080:localhost:8080
```

Note: `--ssh-pubkey` only works on initial CVM creation. To change keys, delete and recreate the CVM.

---

## Pitfalls & Debugging

See **[PITFALLS.md](./PITFALLS.md)** for the full reference.

| Symptom | Likely Cause |
|---------|-------------|
| `getKey()` hangs | Simulator socket version mismatch ([§6](./PITFALLS.md#6-simulator-socket-version-mismatch)) |
| Gateway 502/404 | Wrong cluster in URL ([§3](./PITFALLS.md#3-gateway-urls-the-three-patterns)) |
| Image deploy doesn't update | Using tag instead of digest ([§2](./PITFALLS.md#2-image-tags-dont-do-what-you-think)) |
| CVM fails to pull image | GHCR package is private ([§2](./PITFALLS.md#2-image-tags-dont-do-what-you-think)) |
| Compose hash mismatch | Hash includes full app-compose, not just YAML ([§8](./PITFALLS.md#8-compose-hash--docker-composeyml-hash)) |
