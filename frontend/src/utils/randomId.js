// crypto.randomUUID is only available in a secure context (HTTPS or localhost).
// The public site is also opened over plain HTTP, where that call throws and
// leaves dialog buttons with no visible result.

function bytesToUuid(bytes) {
  const value = Uint8Array.from(bytes)
  value[6] = (value[6] & 0x0f) | 0x40
  value[8] = (value[8] & 0x3f) | 0x80
  const hex = Array.from(value, (byte) => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

export function randomId() {
  const cryptoObj = globalThis.crypto
  try {
    if (typeof cryptoObj?.randomUUID === 'function') return cryptoObj.randomUUID()
  } catch {
    // Insecure HTTP: the method may exist but refuse to run.
  }
  const bytes = new Uint8Array(16)
  if (typeof cryptoObj?.getRandomValues === 'function') cryptoObj.getRandomValues(bytes)
  else {
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256)
  }
  return bytesToUuid(bytes)
}
