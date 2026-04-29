import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import { streamChat, ChatMessage } from '../api'

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText])

  useEffect(() => {
    return () => { abortRef.current?.abort() }
  }, [])

  const send = useCallback(() => {
    const q = input.trim()
    if (!q || streaming) return
    setInput('')

    const userMsg: ChatMessage = { role: 'user', content: q }
    const updatedHistory = [...messages, userMsg]
    setMessages(updatedHistory)
    setStreaming(true)
    setStreamingText('')

    // last 6 turns sent as history (excluding the current user message)
    const history = messages.slice(-6)

    let accumulated = ''
    abortRef.current = streamChat(
      q,
      history,
      3,
      (token) => {
        accumulated += token
        setStreamingText(accumulated)
      },
      () => {
        setMessages((prev) => [...prev, { role: 'assistant', content: accumulated }])
        setStreamingText('')
        setStreaming(false)
        abortRef.current = null
      },
      (err) => {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `Error: ${err.message}` },
        ])
        setStreamingText('')
        setStreaming(false)
        abortRef.current = null
      },
    )
  }, [input, messages, streaming])

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  function clearHistory() {
    abortRef.current?.abort()
    setMessages([])
    setStreamingText('')
    setStreaming(false)
    abortRef.current = null
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 160px)', maxWidth: 720 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Chat</h1>
        <button
          onClick={clearHistory}
          style={{
            background: 'none',
            border: '1px solid #d1d5db',
            borderRadius: 6,
            padding: '4px 12px',
            cursor: 'pointer',
            fontSize: 13,
            color: '#6b7280',
          }}
        >
          Clear history
        </button>
      </div>

      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '8px 0',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}>
        {messages.length === 0 && !streaming && (
          <div style={{ color: '#9ca3af', fontSize: 14, textAlign: 'center', marginTop: 40 }}>
            Ask anything about your finances
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{
              maxWidth: '80%',
              padding: '10px 14px',
              borderRadius: 10,
              fontSize: 14,
              background: msg.role === 'user' ? '#2563eb' : '#fff',
              color: msg.role === 'user' ? '#fff' : '#111827',
              border: msg.role === 'assistant' ? '1px solid #e5e7eb' : 'none',
              lineHeight: 1.6,
            }}>
              {msg.role === 'assistant'
                ? <ReactMarkdown>{msg.content}</ReactMarkdown>
                : msg.content}
            </div>
          </div>
        ))}
        {streaming && (
          <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
            <div style={{
              maxWidth: '80%',
              padding: '10px 14px',
              borderRadius: 10,
              fontSize: 14,
              background: '#fff',
              border: '1px solid #e5e7eb',
              color: '#111827',
              lineHeight: 1.6,
            }}>
              {streamingText
                ? <ReactMarkdown>{streamingText}</ReactMarkdown>
                : <span style={{ color: '#9ca3af', letterSpacing: 2 }}>●●●</span>}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div style={{
        display: 'flex',
        gap: 8,
        paddingTop: 12,
        borderTop: '1px solid #e5e7eb',
        marginTop: 8,
      }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your spending… (Enter to send, Shift+Enter for newline)"
          disabled={streaming}
          rows={2}
          style={{
            flex: 1,
            resize: 'none',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: 8,
            fontSize: 14,
            fontFamily: 'inherit',
            outline: 'none',
          }}
        />
        <button
          onClick={send}
          disabled={!input.trim() || streaming}
          style={{
            background: '#2563eb',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            padding: '0 18px',
            cursor: !input.trim() || streaming ? 'not-allowed' : 'pointer',
            opacity: !input.trim() || streaming ? 0.6 : 1,
            fontSize: 14,
            fontWeight: 600,
            minWidth: 64,
          }}
        >
          {streaming ? '…' : 'Send'}
        </button>
      </div>
    </div>
  )
}
