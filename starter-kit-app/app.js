import { createServer } from 'http'
import { createHash } from 'crypto'
import { DstackClient } from '@phala/dstack-sdk'
import { privateKeyToAccount } from 'viem/accounts'
import { keccak256, encodePacked, toHex, hexToBytes } from 'viem'
import { secp256k1 } from '@noble/curves/secp256k1'

const PORT = process.env.PORT || 8080
const HOST_KEY = process.env.HOST_KEY
const client = new DstackClient()

let stats = { started: new Date().toISOString(), requests: {} }

// Derive signing key + signature chain from KMS
async function getSigningKey() {
  const result = await client.getKey('/toy-example', 'ethereum')
  const privateKey = '0x' + Buffer.from(result.key).toString('hex').slice(0, 64)
  const account = privateKeyToAccount(privateKey)
  const derivedPubkey = secp256k1.getPublicKey(hexToBytes(privateKey).slice(0, 32), true)
  const toHexStr = (x) => typeof x === 'string' ? x : '0x' + Buffer.from(x).toString('hex')
  return {
    account,
    derivedPubkey: toHex(derivedPubkey),
    appSignature: toHexStr(result.signature_chain[0]),
    kmsSignature: toHexStr(result.signature_chain[1]),
  }
}

async function getQuote() {
  const report = createHash('sha256').update('toy-example').digest('hex')
  const res = await client.getQuote(report)
  return res.quote
}

// Init signing key at startup
const signer = await getSigningKey()
const appInfo = await client.info()
console.log('Signer:', signer.account.address, 'App ID:', appInfo.app_id)

const routes = {
  '/health': async () => ({ ok: true }),
  '/key': async () => ({ publicKey: signer.derivedPubkey, address: signer.account.address }),
  '/attestation': async () => ({ quote: await getQuote() }),
  '/secret': async () => ({ secret: process.env.SECRET_VALUE || '(not set)' }),
  '/report': async (req) => {
    if (!HOST_KEY || req.headers.authorization !== `Bearer ${HOST_KEY}`)
      return { _status: 401, error: 'unauthorized' }

    const report = { ...stats, now: new Date().toISOString() }
    const messageHash = keccak256(encodePacked(['string'], [JSON.stringify(report)]))
    const signature = await signer.account.signMessage({ message: { raw: messageHash } })

    return {
      report,
      messageHash,
      signature,
      signatureChain: {
        derivedPubkey: signer.derivedPubkey,
        appSignature: signer.appSignature,
        kmsSignature: signer.kmsSignature,
      },
      signerAddress: signer.account.address,
      appId: appInfo.app_id,
    }
  },
}

const server = createServer(async (req, res) => {
  stats.requests[req.url] = (stats.requests[req.url] || 0) + 1
  const handler = routes[req.url]
  if (!handler) {
    res.writeHead(404)
    return res.end(JSON.stringify({ error: 'not found', endpoints: Object.keys(routes) }))
  }
  try {
    const body = await handler(req)
    const status = body._status || 200
    delete body._status
    res.writeHead(status, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify(body, null, 2))
  } catch (e) {
    res.writeHead(500)
    res.end(JSON.stringify({ error: e.message }))
  }
})

server.listen(PORT, () => console.log(`toy-example listening on :${PORT}`))
