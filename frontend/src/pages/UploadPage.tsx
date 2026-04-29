import { useState, useRef, DragEvent } from 'react'
import { uploadStatement, UploadResult } from '../api'

const BANKS = [
  { value: '', label: 'Auto-detect' },
  { value: 'chase', label: 'Chase' },
  { value: 'amex', label: 'American Express' },
  { value: 'capital_one', label: 'Capital One' },
  { value: 'robinhood', label: 'Robinhood' },
]

type UploadState =
  | { status: 'idle' }
  | { status: 'uploading' }
  | { status: 'success'; result: UploadResult }
  | { status: 'duplicate'; message: string }
  | { status: 'error'; message: string }

export function UploadPage() {
  const [bank, setBank] = useState('')
  const [state, setState] = useState<UploadState>({ status: 'idle' })
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function handleFile(file: File) {
    setState({ status: 'uploading' })
    try {
      const res = await uploadStatement(file, bank || undefined)
      if (res.ok) {
        const result: UploadResult = await res.json()
        setState({ status: 'success', result })
      } else if (res.status === 409) {
        const body = await res.json().catch(() => ({})) as { detail?: string }
        setState({ status: 'duplicate', message: body.detail ?? 'Already ingested' })
      } else if (res.status === 400) {
        const body = await res.json().catch(() => ({})) as { detail?: string }
        setState({ status: 'error', message: body.detail ?? 'Invalid file' })
      } else {
        setState({ status: 'error', message: `Upload failed (${res.status})` })
      }
    } catch {
      setState({ status: 'error', message: 'Network error during upload' })
    }
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  return (
    <div style={{ maxWidth: 540 }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 24 }}>Upload Statement</h1>

      <label style={{ display: 'block', marginBottom: 16 }}>
        <span style={{ fontSize: 13, fontWeight: 500, color: '#374151', display: 'block', marginBottom: 6 }}>
          Bank
        </span>
        <select
          value={bank}
          onChange={(e) => setBank(e.target.value)}
          disabled={state.status === 'uploading'}
          style={{
            width: '100%',
            padding: '8px 10px',
            border: '1px solid #d1d5db',
            borderRadius: 6,
            fontSize: 14,
            background: '#fff',
          }}
        >
          {BANKS.map((b) => (
            <option key={b.value} value={b.value}>{b.label}</option>
          ))}
        </select>
      </label>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        style={{
          border: `2px dashed ${dragging ? '#2563eb' : '#d1d5db'}`,
          borderRadius: 8,
          padding: '40px 24px',
          textAlign: 'center',
          cursor: state.status === 'uploading' ? 'not-allowed' : 'pointer',
          background: dragging ? '#eff6ff' : '#f9fafb',
          marginBottom: 16,
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.pdf"
          style={{ display: 'none' }}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleFile(file)
            e.target.value = ''
          }}
        />
        <div style={{ fontSize: 32, marginBottom: 8 }}>📄</div>
        <div style={{ fontSize: 14, color: '#374151', fontWeight: 500 }}>
          Drag & drop a CSV or PDF
        </div>
        <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>
          or click to browse
        </div>
      </div>

      {state.status === 'uploading' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#2563eb', fontSize: 14, padding: '8px 0' }}>
          <span>⏳</span> Uploading…
        </div>
      )}

      {state.status === 'success' && (
        <div style={{ background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 8, padding: 16 }}>
          <div style={{ fontWeight: 600, color: '#166534', marginBottom: 8 }}>✓ Upload successful</div>
          <table style={{ fontSize: 13, borderCollapse: 'collapse', width: '100%' }}>
            <tbody>
              {([
                ['Bank detected', state.result.bank_detected],
                ['Transactions', String(state.result.transaction_count)],
                ['Duplicates skipped', String(state.result.duplicates_skipped)],
                ['Period start', state.result.period_start ?? '—'],
                ['Period end', state.result.period_end ?? '—'],
              ] as [string, string][]).map(([k, v]) => (
                <tr key={k}>
                  <td style={{ color: '#6b7280', paddingRight: 12, paddingBottom: 4 }}>{k}</td>
                  <td style={{ fontWeight: 500, color: '#111827' }}>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <button
            onClick={() => setState({ status: 'idle' })}
            style={{
              marginTop: 12,
              background: '#2563eb',
              color: '#fff',
              border: 'none',
              borderRadius: 6,
              padding: '6px 14px',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            Upload another
          </button>
        </div>
      )}

      {state.status === 'duplicate' && (
        <div style={{ background: '#fefce8', border: '1px solid #fde047', borderRadius: 8, padding: 16, fontSize: 14, color: '#854d0e' }}>
          ⚠️ Already ingested — {state.message}
          <button
            onClick={() => setState({ status: 'idle' })}
            style={{ display: 'block', marginTop: 8, fontSize: 13, color: '#2563eb', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          >
            Try a different file
          </button>
        </div>
      )}

      {state.status === 'error' && (
        <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, padding: 16, fontSize: 14, color: '#991b1b' }}>
          ✗ {state.message}
          <button
            onClick={() => setState({ status: 'idle' })}
            style={{ display: 'block', marginTop: 8, fontSize: 13, color: '#2563eb', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          >
            Try again
          </button>
        </div>
      )}
    </div>
  )
}
