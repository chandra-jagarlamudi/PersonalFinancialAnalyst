export async function streamChat(
  message: string,
  onEvent: (ev: Record<string, unknown>) => void,
): Promise<void> {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })

  if (!response.ok || !response.body) {
    let detail = `Chat request failed with status ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) {
        detail = payload.detail
      }
    } catch {
      // Ignore non-JSON error payloads.
    }
    throw new Error(detail)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''
    for (const chunk of chunks) {
      const line = chunk.trim()
      if (!line.startsWith('data:')) {
        continue
      }
      const payload = line.slice(line.indexOf('data:') + 5).trim()
      try {
        onEvent(JSON.parse(payload) as Record<string, unknown>)
      } catch {
        // Ignore malformed SSE frames.
      }
    }
  }
}
