#!/usr/bin/env python3
"""
Verify a signed report from the toy-example TEE app, then audit
the on-chain history of the AppAuth contract on Base.

Prerequisites: pip install eth-account eth-keys requests
"""
import sys, json, argparse, requests
from eth_account import Account
from eth_utils import keccak
from eth_keys import keys

KMS_ROOT_ADDRESS = "0x52d3CF51c8A37A2CCfC79bBb98c7810d7Dd4CE51"
DEFAULT_RPC = "https://base-mainnet.public.blastapi.io"

EVENT_TOPICS = {
    "ComposeHashAdded":   "0xfecb34306dd9d8b785b54d65489d06afc8822a0893ddacedff40c50a4942d0af",
    "ComposeHashRemoved": "0x755b79bd4b0eeab344d032284a99003b2ddc018b646752ac72d681593a6e8947",
    "DeviceAdded":        "0x67fc71ab96fe3fa3c6f78e9a00e635d591b7333ce611c0380bc577aac702243b",
    "DeviceRemoved":      "0xe0862975ac517b0478d308012afabc4bc37c23874a18144d7f2dfb852ff95c2c",
    "AllowAnyDeviceSet":  "0xbb2cdb6c7b362202d40373f87bc4788301cca658f91711ac1662e1ad2cba4a20",
}
TOPIC_TO_NAME = {v: k for k, v in EVENT_TOPICS.items()}

def verify_report(data, expected_kms_root):
    chain = data["signatureChain"]
    derived_pubkey = bytes.fromhex(chain["derivedPubkey"].replace("0x", ""))
    app_signature = bytes.fromhex(chain["appSignature"].replace("0x", ""))
    kms_signature = bytes.fromhex(chain["kmsSignature"].replace("0x", ""))
    message_hash = bytes.fromhex(data["messageHash"].replace("0x", ""))
    message_signature = bytes.fromhex(data["signature"].replace("0x", ""))
    app_id_bytes = bytes.fromhex(data["appId"].replace("0x", ""))

    report_json = json.dumps(data["report"], separators=(",", ":"))
    expected_hash = keccak(report_json.encode())
    print(f"Report hash (recomputed): 0x{expected_hash.hex()}")
    print(f"Report hash (claimed):    {data['messageHash']}")
    if expected_hash != message_hash:
        print("FAILED: report hash mismatch — report was tampered")
        return False
    print("OK: report hash matches\n")

    purpose = "ethereum"
    app_message = f"{purpose}:{derived_pubkey.hex()}"
    app_message_hash = keccak(text=app_message)
    app_sig_obj = keys.Signature(app_signature)
    app_pubkey = app_sig_obj.recover_public_key_from_msg_hash(app_message_hash)
    app_pubkey_compressed = app_pubkey.to_compressed_bytes()
    print(f"Step 1: App signature over derived key")
    print(f"  App Address: {app_pubkey.to_checksum_address()}")

    kms_message = b"dstack-kms-issued:" + app_id_bytes + app_pubkey_compressed
    kms_message_hash = keccak(kms_message)
    kms_signer = Account._recover_hash(kms_message_hash, signature=kms_signature)
    print(f"\nStep 2: KMS signature over app key")
    print(f"  Recovered KMS: {kms_signer}")
    print(f"  Expected KMS:  {expected_kms_root}")
    if kms_signer.lower() != expected_kms_root.lower():
        print("  FAILED: KMS signature mismatch")
        return False
    print("  OK: KMS signature verified")

    eth_message = b"\x19Ethereum Signed Message:\n32" + message_hash
    eth_hash = keccak(eth_message)
    message_signer = Account._recover_hash(eth_hash, signature=message_signature)
    expected_signer = keys.PublicKey.from_compressed_bytes(derived_pubkey).to_checksum_address()
    print(f"\nStep 3: Report signature")
    print(f"  Recovered signer: {message_signer}")
    print(f"  Expected signer:  {expected_signer}")
    if message_signer.lower() != expected_signer.lower():
        print("  FAILED: Report signature mismatch")
        return False
    print("  OK: Report signature verified")
    return True

# --- On-chain audit ---

def eth_get_logs(rpc_url, address, topics):
    resp = requests.post(rpc_url, json={
        "jsonrpc": "2.0", "id": 1, "method": "eth_getLogs",
        "params": [{"address": address, "fromBlock": "0x0", "toBlock": "latest", "topics": [topics]}],
    })
    result = resp.json()
    if "error" in result:
        print(f"  RPC error: {result['error']}")
        return []
    return result.get("result", [])

def get_block_timestamp(rpc_url, block_hex):
    resp = requests.post(rpc_url, json={
        "jsonrpc": "2.0", "id": 1, "method": "eth_getBlockByNumber",
        "params": [block_hex, False],
    })
    block = resp.json().get("result")
    if not block:
        return None
    return int(block["timestamp"], 16)

def fmt_block(block_hex, timestamp=None):
    num = int(block_hex, 16)
    if timestamp:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return f"block {num} ({dt})"
    return f"block {num}"

def audit_onchain(app_id, rpc_url, basescan_key=None):
    address = app_id if app_id.startswith("0x") else "0x" + app_id
    print(f"\nOn-Chain Audit Trail (Base)")
    print("=" * 50)
    print(f"AppAuth contract: {address}")
    if basescan_key:
        print(f"  https://basescan.org/address/{address}")

    all_topics = list(EVENT_TOPICS.values())
    logs = eth_get_logs(rpc_url, address, all_topics)

    if not logs:
        print("\n  No on-chain events found for this appId.")
        print("  (Expected if using a simulator or if appId is not deployed on Base)")
        return

    logs.sort(key=lambda l: int(l["blockNumber"], 16))

    # Optionally resolve timestamps
    block_timestamps = {}
    if basescan_key:
        unique_blocks = {l["blockNumber"] for l in logs}
        for bh in unique_blocks:
            block_timestamps[bh] = get_block_timestamp(rpc_url, bh)

    # Categorize
    compose_added, compose_removed = set(), set()
    device_added, device_removed = set(), set()
    allow_any_device = None

    print(f"\nEvent History ({len(logs)} events):")
    for i, log in enumerate(logs, 1):
        topic0 = log["topics"][0]
        name = TOPIC_TO_NAME.get(topic0, topic0[:18] + "...")
        block_hex = log["blockNumber"]
        ts = block_timestamps.get(block_hex)
        data_val = log["data"] if log["data"] != "0x" else (log["topics"][1] if len(log["topics"]) > 1 else "0x")

        print(f"  {i}. [{fmt_block(block_hex, ts)}] {name}: {data_val}")

        if name == "ComposeHashAdded":
            compose_added.add(data_val)
        elif name == "ComposeHashRemoved":
            compose_removed.add(data_val)
        elif name == "DeviceAdded":
            device_added.add(data_val)
        elif name == "DeviceRemoved":
            device_removed.add(data_val)
        elif name == "AllowAnyDeviceSet":
            val = int(data_val, 16) if data_val != "0x" else 0
            allow_any_device = bool(val)

    active_compose = compose_added - compose_removed
    active_devices = device_added - device_removed

    print(f"\nCompose Hashes:")
    print(f"  Active: {len(active_compose)}")
    for h in sorted(active_compose):
        print(f"    {h}")
    if len(active_compose) > 1:
        print(f"  \u26a0\ufe0f  Multiple active compose hashes \u2014 downgrade possible")

    print(f"\nDevices:")
    print(f"  Active: {len(active_devices)}")
    for d in sorted(active_devices):
        print(f"    {d}")
    if allow_any_device is not None:
        print(f"  allowAnyDevice: {allow_any_device}")
        if allow_any_device:
            print(f"  \u26a0\ufe0f  Any TEE machine can run this app (no datacenter restriction)")

    print(f"\nAuditor Notes:")
    print(f"  - Verify active compose hash matches source code in repository")
    print(f"  - Verify device IDs belong to trusted datacenters (not adversarial labs)")
    print(f"  - Check KMS root address against known Base KMS contract")

    return active_compose

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify TEE report and audit on-chain history")
    parser.add_argument("report", help="Path to report JSON file")
    parser.add_argument("--kms-root", default=KMS_ROOT_ADDRESS, help="Expected KMS root address")
    parser.add_argument("--app-id", help="Override appId (hex address on Base)")
    parser.add_argument("--rpc-url", default=DEFAULT_RPC, help="Base JSON-RPC URL")
    parser.add_argument("--basescan-key", help="Basescan API key for timestamps")
    parser.add_argument("--skip-onchain", action="store_true", help="Skip on-chain audit")
    parser.add_argument("--manifest", help="Path to build-manifest.json for full source→chain verification")
    args = parser.parse_args()

    with open(args.report) as f:
        data = json.load(f)

    app_id = args.app_id or data["appId"]

    print("TEE Report Verification")
    print("=" * 50)
    print(f"Report period: {data['report']['started']} \u2192 {data['report']['now']}")
    print(f"Total requests: {sum(data['report']['requests'].values())}")
    print(f"Signer: {data['signerAddress']}")
    print(f"App ID: {app_id}")
    print()

    if not verify_report(data, args.kms_root):
        print("\nVerification FAILED")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("All signature verifications passed:")
    print("  - Report hash matches content (not tampered)")
    print("  - KMS signed the app key")
    print("  - App key signed the derived key")
    print("  - Derived key signed this report")

    active_compose = None
    if not args.skip_onchain:
        active_compose = audit_onchain(app_id, args.rpc_url, args.basescan_key)

    if args.manifest:
        print("\n" + "=" * 50)
        print("Build Manifest Verification")
        print("=" * 50)
        with open(args.manifest) as f:
            manifest = json.load(f)
        print(f"  Manifest image digest: {manifest['image_digest']}")
        print(f"  Manifest image hash:   {manifest['image_hash']}")
        print(f"  Source date epoch:      {manifest.get('source_date_epoch', 'N/A')}")
        print(f"  Build date:             {manifest.get('build_date', 'N/A')}")
        if active_compose:
            print(f"\n  Active on-chain compose hashes: {len(active_compose)}")
            for h in sorted(active_compose):
                print(f"    {h}")
            print(f"\n  To complete the audit loop:")
            print(f"    1. Rebuild from source: ./build-reproducible.sh")
            print(f"    2. Verify build-manifest.json image_digest matches")
            print(f"    3. Verify the compose file references this digest")
            print(f"    4. Verify compose hash of that file matches on-chain hash")
        else:
            print(f"\n  (Skipped on-chain cross-reference — use without --skip-onchain)")
