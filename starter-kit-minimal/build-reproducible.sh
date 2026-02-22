#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

for cmd in docker skopeo jq; do
    command -v "$cmd" >/dev/null || { echo "Required: $cmd"; exit 1; }
done

echo "=== Building devproof-toy (reproducible) ==="

if ! docker buildx inspect repro-builder &>/dev/null; then
    docker buildx create --name repro-builder --driver docker-container
fi

build_image() {
    docker buildx build \
        --builder repro-builder \
        --build-arg SOURCE_DATE_EPOCH=0 \
        --no-cache \
        --output type=oci,dest="$1",rewrite-timestamp=true \
        .
}

echo -e "\nBuild 1..."
build_image build1.tar
HASH1=$(sha256sum build1.tar | awk '{print $1}')
echo "  Hash: ${HASH1:0:16}..."

echo -e "\nBuild 2..."
build_image build2.tar
HASH2=$(sha256sum build2.tar | awk '{print $1}')
echo "  Hash: ${HASH2:0:16}..."

echo -e "\n=== Results ==="
if [[ "$HASH1" == "$HASH2" ]]; then
    echo "REPRODUCIBLE - both builds identical"
    DIGEST=$(skopeo inspect oci-archive:build1.tar | jq -r .Digest)
    echo "Image digest: $DIGEST"

    cat > build-manifest.json << EOF
{
  "image_hash": "$HASH1",
  "image_digest": "$DIGEST",
  "build_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source_date_epoch": 0
}
EOF
    echo "Saved: build-manifest.json"

    docker load < build1.tar 2>/dev/null || true
    rm -f build1.tar build2.tar
    exit 0
else
    echo "NOT REPRODUCIBLE - builds differ"
    echo "Build 1: $HASH1"
    echo "Build 2: $HASH2"
    echo "Debug: keeping build1.tar and build2.tar"
    exit 1
fi
