# Starter Kit: Minimal (TEE Microservice)

Minimal TEE app template for dstack/Phala Cloud (~85 lines). KMS key derivation, attestation, signed reports.

**Full guide:** [../README.md](../README.md)

## Endpoints

| Endpoint | What it does |
|----------|-------------|
| `GET /health` | Health check |
| `GET /key` | KMS-derived signing key + address |
| `GET /attestation` | TDX attestation quote |
| `GET /secret` | Injected secret (env var) |
| `GET /report` | Signed report (requires `HOST_KEY` bearer token) |

## Files

| File | Purpose |
|------|---------|
| `app.js` | App server (~85 lines). Add your endpoints here. |
| `Dockerfile` | Reproducible build (pinned base image, `SOURCE_DATE_EPOCH=0`) |
| `docker-compose.yaml` | Local dev with simulator |
| `docker-compose.staging.yaml` | Staging deploy (dev base image, SSH works) |
| `docker-compose.prod.yaml` | Production deploy (prod base image, Base KMS) |
| `build-reproducible.sh` | Double-build + hash comparison for reproducibility |
| `verify.sh` | Fetch attestation from 8090 endpoint and verify compose hash |
