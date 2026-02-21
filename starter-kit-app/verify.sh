#!/bin/bash
# Verify attestation + compose hash from a deployed CVM
# Usage: ./verify.sh <app-id> [gateway]
# Example: ./verify.sh abc123def dstack-pha-prod7.phala.network

set -e

APP_ID=${1:?Usage: ./verify.sh <app-id> [gateway]}
GATEWAY=${2:-dstack-pha-prod7.phala.network}
BASE_URL="https://${APP_ID}-8090.${GATEWAY}"

echo "=== Toy Example Attestation Verification ==="
echo "Target: $BASE_URL"
echo ""

# Fetch the 8090 metadata page (HTML with embedded JSON data)
echo "Fetching attestation metadata from 8090..."
RAW=$(curl -sf "$BASE_URL/")

python3 -c "
import sys, json, hashlib, html, re

raw = sys.stdin.read()

# 8090 returns HTML with HTML-entity-encoded JSON. Decode entities first.
decoded = html.unescape(raw)

# Extract compose_hash directly
m = re.search(r'\"compose_hash\":\s*\"([a-f0-9]+)\"', decoded)
if m:
    print(f'compose_hash (from 8090): {m.group(1)}')

# Extract app_compose JSON string
m = re.search(r'\"app_compose\":\s*\"({.*?})\"', decoded)
if m:
    compose_str = m.group(1).replace(r'\"', '\"')
    # The compose_hash should be sha256 of the app_compose JSON string
    h = hashlib.sha256(compose_str.encode()).hexdigest()
    print(f'app_compose sha256:       {h}')
    print(f'app_compose (first 200):  {compose_str[:200]}')
else:
    print('Could not extract app_compose from 8090 HTML')
    # Show what fields are available
    for field in ['compose_hash', 'os_image_hash', 'app_compose']:
        if field in decoded:
            print(f'  found: {field}')
" <<< "$RAW"

# Also hit the app endpoints to verify they're working
echo ""
echo "=== App Health Check ==="
curl -sf "https://${APP_ID}-8080.${GATEWAY}/health" | python3 -m json.tool 2>/dev/null || echo "(health check failed)"

echo ""
echo "=== Derived Key ==="
curl -sf "https://${APP_ID}-8080.${GATEWAY}/key" | python3 -m json.tool 2>/dev/null || echo "(key endpoint failed)"

echo ""
echo "Done. Compare compose_hash with expected value from your deployment."
