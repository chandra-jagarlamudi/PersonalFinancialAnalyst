import { useCallback, useRef, useState, type FormEvent } from 'react'
import { streamChat } from './api'

type ChatMsg = { role: 'user' | 'assistant'; text: string }

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  async function handleSend(event: FormEvent) {
    event.preventDefault()
    const trimmed = input.trim()
    if (!trimmed || busy) {
      return
    }
    setInput('')
    setBusy(true)
    setError(null)
    setMessages(prev => [...prev, { role: 'user', text: trimmed }, { role: 'assistant', text: '' }])

    let assistantText = ''

    try {
      await streamChat(trimmed, ev => {
        if (ev.type === 'delta' && typeof ev.text === 'string') {
          assistantText += ev.text
          setMessages(prev => {
            const next = [...prev]
            const last = next[next.length - 1]
            if (last?.role === 'assistant') {
              next[next.length - 1] = { role: 'assistant', text: assistantText }
            }
            return next
          })
          scrollToBottom()
        }
      })
      scrollToBottom()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Chat failed')
      setMessages(prev => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last?.role === 'assistant' && last.text === '') {
          next.pop()
        }
        return next
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel chat-panel">
      <h2>Chat</h2>
      <p className="intro">
        Streaming assistant wired to read-only ledger tools (aggregates first). Try prompts such as{' '}
        <strong>ledger summary</strong>, <strong>budget status</strong>, <strong>cashflow</strong>,{' '}
        <strong>recurring charges</strong>, <strong>anomalies</strong>, or{' '}
        <strong>category breakdown</strong>. For advanced queries, paste a Markdown fenced block whose
        opening fence is tagged <code>sql</code>, containing a single <code>SELECT</code> (or{' '}
        <code>WITH</code>) ending in <code>LIMIT n</code> where <code>n ≤ 500</code>.
      </p>

      {error ? <p className="error-banner">{error}</p> : null}

      <div className="chat-thread" aria-live="polite">
        {messages.length === 0 ? (
          <p className="empty-state muted">No messages yet.</p>
        ) : (
          messages.map((m, i) => (
            <article key={`${i}-${m.role}`} className={`chat-bubble chat-${m.role}`}>
              <header>{m.role === 'user' ? 'You' : 'Assistant'}</header>
              <pre className="chat-body">{m.text || (busy && m.role === 'assistant' ? '…' : '')}</pre>
            </article>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      <form className="chat-compose" onSubmit={e => void handleSend(e)}>
        <label className="chat-label">
          Message
          <textarea
            rows={3}
            value={input}
            disabled={busy}
            placeholder="Ask about budgets, cashflow, anomalies…"
            onChange={event => setInput(event.target.value)}
          />
        </label>
        <button type="submit" disabled={busy || !input.trim()}>
          {busy ? 'Sending…' : 'Send'}
        </button>
      </form>
    </section>
  )
}
