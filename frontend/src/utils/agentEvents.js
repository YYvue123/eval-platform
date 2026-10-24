import { buildApiUrl } from './request'

// Fetch-based SSE keeps Authorization out of URLs and supports resume by sequence.
export async function subscribeAgentEvents({ runId, afterSeq, token, signal, onEvent, onConnected }) {
  const response = await fetch(buildApiUrl(`/agents/runs/${runId}/events/stream`, { after_seq: afterSeq }), {
    headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' }, signal,
  })
  if (!response.ok || !response.body) throw new Error(`实时动态连接失败（${response.status}）`)
  onConnected?.()
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n')
      let end
      while ((end = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, end)
        buffer = buffer.slice(end + 2)
        const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
        if (data) onEvent(JSON.parse(data))
      }
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
