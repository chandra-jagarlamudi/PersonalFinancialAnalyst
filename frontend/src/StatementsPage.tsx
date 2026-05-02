import { useEffect, useState } from 'react'
import { listAccounts, listStatements, purgeStatement, type Account, type Statement } from './api'

type Banner = { type: 'success' | 'error'; message: string }

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

export default function StatementsPage() {
  const [statements, setStatements] = useState<Statement[]>([])
  const [accounts, setAccounts] = useState<Map<string, Account>>(new Map())
  const [loading, setLoading] = useState(true)
  const [banner, setBanner] = useState<Banner | null>(null)
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [purging, setPurging] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const [data, acctList] = await Promise.all([listStatements(), listAccounts()])
      setStatements(data)
      setAccounts(new Map(acctList.map(a => [a.id, a])))
    } catch (err) {
      setBanner({ type: 'error', message: err instanceof Error ? err.message : 'Failed to load statements' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function handlePurge(id: string) {
    setPurging(true)
    setBanner(null)
    try {
      await purgeStatement(id)
      setStatements(prev => prev.filter(s => s.id !== id))
      setBanner({ type: 'success', message: 'Statement removed from the app. Associated file cleanup may complete separately.' })
    } catch (err) {
      setBanner({ type: 'error', message: err instanceof Error ? err.message : 'Purge failed' })
    } finally {
      setPurging(false)
      setConfirmId(null)
    }
  }

  return (
    <section className="panel">
      <h2>Statements</h2>

      {banner ? (
        <p className={banner.type === 'success' ? 'success-banner' : 'error-banner'}>
          {banner.message}
        </p>
      ) : null}

      {loading ? (
        <p>Loading statements…</p>
      ) : statements.length === 0 ? (
        <p className="empty-state">No statements uploaded yet.</p>
      ) : (
        <table className="statements-table">
          <thead>
            <tr>
              <th>Account</th>
              <th>Filename</th>
              <th>Uploaded</th>
              <th>Size</th>
              <th>Inserted</th>
              <th>Skipped</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {statements.map(s => (
              <tr key={s.id}>
                <td>{accounts.get(s.account_id)?.name ?? s.account_id}</td>
                <td>{s.filename}</td>
                <td>{formatDate(s.created_at)}</td>
                <td>{formatBytes(s.byte_size)}</td>
                <td>{s.inserted}</td>
                <td>{s.skipped_duplicates}</td>
                <td>
                  {confirmId === s.id ? (
                    <span className="confirm-inline">
                      <span className="confirm-text">
                        Are you sure? This permanently deletes the file and all transactions from this statement.
                      </span>
                      <button
                        type="button"
                        className="danger-button"
                        disabled={purging}
                        onClick={() => void handlePurge(s.id)}
                      >
                        {purging ? 'Deleting…' : 'Yes, delete'}
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={purging}
                        onClick={() => setConfirmId(null)}
                      >
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="danger-button"
                      onClick={() => setConfirmId(s.id)}
                    >
                      Purge
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
