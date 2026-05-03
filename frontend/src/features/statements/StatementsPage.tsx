import { Fragment, useEffect, useState, type FormEvent } from 'react'
import {
  createAccount,
  createInstitution,
  enqueueCsvImport,
  enqueuePdfImport,
  listAccountTypes,
  listAccounts,
  listInstitutions,
  listStatements,
  pollIngestJob,
  purgeStatement,
  type Account,
  type Institution,
  type Statement,
} from '@/api'

type Banner = { type: 'success' | 'error'; message: string }
type ImportKind = 'csv' | 'pdf'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

function accountDisplayName(
  a: Account,
  institutions: Map<string, Institution>,
): string {
  const inst = institutions.get(a.institution_id)
  const base = inst ? `${inst.name} — ${a.name}` : a.name
  return `${base} (${a.account_type_label})`
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
  const [importKind, setImportKind] = useState<ImportKind>('pdf')
  const [expandedStatementId, setExpandedStatementId] = useState<string | null>(null)
  const [setupInstitutionName, setSetupInstitutionName] = useState('')
  const [setupAccountName, setSetupAccountName] = useState('')
  const [setupBusy, setSetupBusy] = useState(false)
  const [accountTypes, setAccountTypes] = useState<
    Awaited<ReturnType<typeof listAccountTypes>>
  >([])
  const [setupAccountTypeId, setSetupAccountTypeId] = useState('')

  async function load() {
    setLoading(true)
    try {
      const data = await listStatements()
      setStatements(data)

      try {
        const [acctList, instList, typesList] = await Promise.all([
          listAccounts(),
          listInstitutions(),
          listAccountTypes(),
        ])
        setAccounts(new Map(acctList.map(a => [a.id, a])))
        setInstitutions(new Map(instList.map(i => [i.id, i])))
        setAccountTypes(typesList)
        if (typesList.length > 0) {
          setSetupAccountTypeId(prev => prev || typesList[0].id)
        }
        if (acctList.length > 0) {
          setImportAccountId(prev => prev || acctList[0].id)
        }
      } catch (err) {
        setAccounts(new Map())
        setInstitutions(new Map())
        setAccountTypes([])
        setBanner({
          type: 'error',
          message:
            err instanceof Error ? err.message : 'Failed to load accounts or institutions',
        })
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
    setImportHint('Uploading…')
    try {
      const pending = await enqueueCsvImport(importAccountId, file)
      setImportHint('Processing…')
      const job = await pollIngestJob(pending.id)
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

  async function handleCreateAccount(event: FormEvent) {
    event.preventDefault()
    const instName = setupInstitutionName.trim()
    const acctName = setupAccountName.trim()
    if (!instName || !acctName || !setupAccountTypeId) return
    setSetupBusy(true)
    setBanner(null)
    try {
      const inst = await createInstitution(instName)
      const acct = await createAccount({
        institution_id: inst.id,
        account_type_id: setupAccountTypeId,
        name: acctName,
        currency: 'USD',
      })
      setImportAccountId(acct.id)
      setSetupInstitutionName('')
      setSetupAccountName('')
      await load()
    } catch (err) {
      setBanner({
        type: 'error',
        message: err instanceof Error ? err.message : 'Could not create institution or account',
      })
    } finally {
      setSetupBusy(false)
    }
  }

  async function handleQueuedPdf(file: File | undefined) {
    if (!file || !importAccountId) return
    setImportBusy(true)
    setImportHint('Uploading…')
    try {
      const pending = await enqueuePdfImport(importAccountId, file)
      setImportHint('Processing…')
      const job = await pollIngestJob(pending.id)
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
      <p className="statements-page-lede">
        Queue statement files to an account, then review uploaded history in the table below.
      </p>

      <details className="account-setup-details" defaultOpen={accountOptions.length === 0}>
        <summary className="account-setup-summary">
          {accountOptions.length === 0 ? 'Set up your first account' : 'Add account'}
        </summary>
        <form className="account-setup-card" onSubmit={event => void handleCreateAccount(event)}>
        <p className="account-setup-lede">
          {accountOptions.length === 0
            ? 'Imports are tied to an account. Create an institution and account here, then you can queue CSV or PDF files below.'
            : 'Create additional accounts under a new or existing institution. Each account uses a type from the catalog (Checking, Savings, …).'}
        </p>
        <div className="account-setup-fields">
          <label>
            Account type
            <select
              value={setupAccountTypeId}
              onChange={event => setSetupAccountTypeId(event.target.value)}
              disabled={setupBusy || accountTypes.length === 0}
              aria-label="Account type"
              required
            >
              {accountTypes.length === 0 ? (
                <option value="">Loading types…</option>
              ) : (
                accountTypes.map(t => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))
              )}
            </select>
          </label>
          <label>
            Institution name
            <input
              type="text"
              value={setupInstitutionName}
              onChange={event => setSetupInstitutionName(event.target.value)}
              placeholder="e.g. First Bank"
              autoComplete="organization"
              disabled={setupBusy}
              required
            />
          </label>
          <label>
            Account name
            <input
              type="text"
              value={setupAccountName}
              onChange={event => setSetupAccountName(event.target.value)}
              placeholder="e.g. Primary checking"
              autoComplete="off"
              disabled={setupBusy}
              required
            />
          </label>
        </div>
        <button type="submit" className="account-setup-submit" disabled={setupBusy}>
          {setupBusy ? 'Creating…' : 'Create and continue'}
        </button>
      </form>
      </details>

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
                accountOptions.map(a => (
                  <option key={a.id} value={a.id}>
                    {accountDisplayName(a, institutions)}
                  </option>
                ))
              )}
            </select>
          </label>
          <div
            className="import-format-group"
            role="group"
            aria-labelledby="import-format-heading"
          >
            <div id="import-format-heading" className="import-format-heading">
              File type
            </div>
            <div className="import-format-radios">
              <label className="import-radio-label">
                <input
                  type="radio"
                  name="import-kind"
                  value="csv"
                  checked={importKind === 'csv'}
                  disabled={importBusy || !importAccountId}
                  onChange={() => setImportKind('csv')}
                />
                CSV
              </label>
              <label className="import-radio-label">
                <input
                  type="radio"
                  name="import-kind"
                  value="pdf"
                  checked={importKind === 'pdf'}
                  disabled={importBusy || !importAccountId}
                  onChange={() => setImportKind('pdf')}
                />
                PDF
              </label>
            </div>
          </div>
          <label>
            Statement file
            <input
              key={importKind}
              type="file"
              accept={importKind === 'csv' ? '.csv,text/csv' : '.pdf,application/pdf'}
              disabled={importBusy || !importAccountId}
              aria-label="Statement file for queued import"
              onChange={event => {
                const file = event.target.files?.[0]
                event.target.value = ''
                void (importKind === 'csv' ? handleQueuedCsv(file) : handleQueuedPdf(file))
              }}
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
              <Fragment key={s.id}>
                <tr
                  tabIndex={0}
                  aria-expanded={expandedStatementId === s.id}
                  className="statement-row"
                  onClick={() =>
                    setExpandedStatementId(prev => (prev === s.id ? null : s.id))
                  }
                  onKeyDown={event => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      setExpandedStatementId(prev => (prev === s.id ? null : s.id))
                    }
                  }}
                >
                  <td>
                    {(() => {
                      const acct = accounts.get(s.account_id)
                      if (!acct) return s.account_id
                      return accountDisplayName(acct, institutions)
                    })()}
                  </td>
                  <td>{s.filename}</td>
                  <td>{formatDate(s.created_at)}</td>
                  <td>{formatBytes(s.byte_size)}</td>
                  <td>{s.inserted}</td>
                  <td>{s.skipped_duplicates}</td>
                  <td onClick={event => event.stopPropagation()}>
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
                {expandedStatementId === s.id ? (
                  <tr className="statement-detail-row" aria-label="Statement details">
                    <td colSpan={7} className="statement-detail-cell">
                      <dl className="statement-detail-dl">
                        <div>
                          <dt>Statement ID</dt>
                          <dd>{s.id}</dd>
                        </div>
                        <div>
                          <dt>SHA-256</dt>
                          <dd>{s.sha256}</dd>
                        </div>
                        <div>
                          <dt>Account ID</dt>
                          <dd>{s.account_id}</dd>
                        </div>
                      </dl>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
