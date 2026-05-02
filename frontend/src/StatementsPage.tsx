import { useEffect, useState } from 'react'
import {
  enqueueCsvImport,
  enqueuePdfImport,
  listAccounts,
  listInstitutions,
  listStatements,
  purgeStatement,
  type Account,
  type Institution,
  type Statement,
} from './api'

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
  const [institutions, setInstitutions] = useState<Map<string, Institution>>(new Map())
  const [loading, setLoading] = useState(true)
  const [banner, setBanner] = useState<Banner | null>(null)
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [purging, setPurging] = useState(false)
  const [importAccountId, setImportAccountId] = useState('')
  const [importBusy, setImportBusy] = useState(false)
  const [importHint, setImportHint] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    try {
      const data = await listStatements()
      setStatements(data)

      try {
        const [acctList, instList] = await Promise.all([listAccounts(), listInstitutions()])
        setAccounts(new Map(acctList.map(a => [a.id, a])))
        setInstitutions(new Map(instList.map(i => [i.id, i])))
        if (acctList.length > 0) {
          setImportAccountId(prev => prev || acctList[0].id)
        }
      } catch {
        setAccounts(new Map())
        setInstitutions(new Map())
      }
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
      setBanner({ type: 'success', message: 'Statement removed from the app. This operation does not confirm that any underlying uploaded file bytes were deleted.' })
    } catch (err) {
      setBanner({ type: 'error', message: err instanceof Error ? err.message : 'Purge failed' })
    } finally {
      setPurging(false)
      setConfirmId(null)
    }
  }

  async function handleQueuedCsv(file: File | undefined) {
    if (!file || !importAccountId) return
    setImportBusy(true)
    setImportHint(null)
    try {
      const job = await enqueueCsvImport(importAccountId, file)
      setImportHint(
        `CSV job ${job.status}: ${job.filename} (${job.job_type}). Parsed rows ${job.parsed_rows ?? '—'}, inserted ${job.inserted_rows ?? '—'}.`,
      )
      await load()
    } catch (err) {
      setBanner({
        type: 'error',
        message: err instanceof Error ? err.message : 'CSV queue import failed',
      })
    } finally {
      setImportBusy(false)
    }
  }

  async function handleQueuedPdf(file: File | undefined) {
    if (!file || !importAccountId) return
    setImportBusy(true)
    setImportHint(null)
    try {
      const job = await enqueuePdfImport(importAccountId, file)
      const tail =
        job.status === 'needs_review'
          ? ' Parser flagged low confidence — review required before trusting extracted rows.'
          : ''
      setImportHint(
        `PDF job ${job.status}: ${job.filename}.${tail}${job.error_detail ? ` (${job.error_detail})` : ''}`,
      )
      await load()
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'PDF queue import failed'
      setBanner({
        type: 'error',
        message:
          msg.includes('%PDF') || msg.includes('PDF')
            ? `${msg} Unsupported files fail fast; parser-backed PDFs may stop in review when confidence is low.`
            : msg,
      })
    } finally {
      setImportBusy(false)
    }
  }

  const accountOptions = [...accounts.values()]

  return (
    <section className="panel">
      <h2>Statements</h2>

      <div className="import-actions">
        <h3>Queue imports</h3>
        <p className="intro">
          Upload through the durable ingest job pipeline (same persistence path as CSV jobs). PDF uses the targeted
          parser with a human-review gate when confidence is low.
        </p>
        <div className="import-row">
          <label>
            Target account
            <select
              className="import-account-select"
              value={importAccountId}
              disabled={accountOptions.length === 0 || importBusy}
              onChange={event => setImportAccountId(event.target.value)}
              aria-label="Account for queued import"
            >
              {accountOptions.length === 0 ? (
                <option value="">No accounts yet</option>
              ) : (
                accountOptions.map(a => {
                  const inst = institutions.get(a.institution_id)
                  const label = inst ? `${inst.name} — ${a.name}` : a.name
                  return (
                    <option key={a.id} value={a.id}>
                      {label}
                    </option>
                  )
                })
              )}
            </select>
          </label>
          <label>
            CSV job
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={importBusy || !importAccountId}
              onChange={event => void handleQueuedCsv(event.target.files?.[0])}
            />
          </label>
          <label>
            PDF job
            <input
              type="file"
              accept=".pdf,application/pdf"
              disabled={importBusy || !importAccountId}
              onChange={event => void handleQueuedPdf(event.target.files?.[0])}
            />
          </label>
        </div>
        {importHint ? <p className="import-status">{importHint}</p> : null}
      </div>

      {banner ? (
        <p className={banner.type === 'success' ? 'success-banner' : 'error-banner'}>
          {banner.message}
        </p>
      ) : null}

      {loading ? (
        <p>Loading statements…</p>
      ) : statements.length === 0 ? (
        <p className="empty-state">No statements recorded yet — queue a CSV or PDF import above.</p>
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
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {statements.map(s => (
              <tr key={s.id}>
                <td>
                  {(() => {
                    const acct = accounts.get(s.account_id)
                    if (!acct) return s.account_id
                    const inst = institutions.get(acct.institution_id)
                    return inst ? `${inst.name} — ${acct.name}` : acct.name
                  })()}
                </td>
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
