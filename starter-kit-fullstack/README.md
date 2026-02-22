# Starter Kit: Fullstack (Vercel + TEE + Neon)

Encrypted key-value store running in a TEE. Values are AES-256-GCM encrypted inside the enclave and stored as ciphertext in Postgres. The encryption key never leaves the TEE.

**Full guide:** [../README.md](../README.md) · **[Verification guide](VERIFY.md)**

## Architecture

```
Browser → Vercel (cookie sessions) → TEE (encrypt/decrypt) → Neon Postgres (ciphertext only)
```

| Layer | Sees |
|-------|------|
| Browser | keys, plaintext values |
| Vercel | keys, ciphertext, session cookies |
| TEE | keys, plaintext values, encryption key |
| Neon DB | keys, ciphertext |

## Endpoints (TEE — `enclave/app.js`)

| Endpoint | What it does |
|----------|-------------|
| `GET /health` | Health check |
| `GET /key` | KMS-derived key |
| `GET /stats` | Uptime, request counts, DB totals |
| `POST /fetch` | TLS oracle — fetch HTTPS URL through the TEE with TDX-attested hash |
| `GET /report` | Stats + TDX attestation quote |
| `POST /records` | Write encrypted KV record to Neon |
| `GET /records` | Read/list encrypted records |
| `POST /store` | Write to local encrypted file store |
| `GET /store` | Read from local encrypted file store |

## Files

```
enclave/
  app.js                       # TEE server (~250 lines)
  Dockerfile                   # Reproducible build (pinned base, SOURCE_DATE_EPOCH=0)
  docker-compose.yaml          # Local dev (simulator)
  docker-compose.staging.yaml  # Staging (dev base image, SSH)
  docker-compose.prod.yaml     # Production (Base KMS)
  build-reproducible.sh        # Double-build + hash comparison
  package.json
api/
  session.js                   # Cookie sessions (anonymous, auto-created)
  records.js                   # KV store proxy (Vercel → TEE)
  token.js                     # JWT for TEE gateway auth
  verify.js                    # TEE health + attestation check
  _db.js                       # Neon client
frontend/
  index.html                   # Main app (vanilla JS, no build step)
  docs/index.html              # API reference
scripts/
  verify.sh                    # CLI attestation verification
vercel.json                    # Vercel routing
package.json                   # Root workspace
VERIFY.md                      # Audit guide for third parties
```

## Local Development

```bash
phala simulator start
cd enclave && docker compose up --build
curl localhost:8080/health
```

## Deploy

See the [quickstart in the main guide](../README.md#quickstart) for full instructions. The short version:

1. Create a Neon database, get `DATABASE_URL`
2. Build + push enclave image to GHCR (make package public)
3. Pin the digest in `docker-compose.prod.yaml`
4. `phala deploy -c enclave/docker-compose.prod.yaml --kms base --private-key "$PRIVATE_KEY"`
5. Link Vercel, set env vars (`DATABASE_URL`, `JWT_SECRET`, `CVM_URL`), deploy
