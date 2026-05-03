import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listAccounts, listAnomalies, type Account, type AnomalySignal } from '@/api'

function formatMoney(amount: string | null): string {
  if (amount === null || amount === '') {
    return '—'
  }
  return amount
}

export default function AnomaliesPage() {
  const [signals, setSignals] = useState<AnomalySignal[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [accountId, setAccountId] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function load(selected?: string) {
    setLoading(true)
    setError(null)
    try {
      const [acctList, anomalyData] = await Promise.all([
        listAccounts(),
        listAnomalies(selected || undefined),
      ])
      setAccounts(acctList)
      setSignals(anomalyData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load anomalies')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load(accountId || undefined)
  }, [accountId])

  return (
    <section className="panel">
      <h2>Anomalies</h2>
      <p className="intro">
        Deterministic signals from your ledger: unusually large charges vs a merchant&apos;s usual pattern,
        month-over-month spikes, and merchants you had not spent with before within the detection window.
      </p>

      <label className="filter-field">
        <span>Account scope</span>
        <select
          value={accountId}
          onChange={event => setAccountId(event.target.value)}
          aria-label="Filter anomalies by account"
        >
          <option value="">All accounts</option>
          {accounts.map(a => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </label>

      {error ? <p className="error-banner">{error}</p> : null}

      {loading ? (
        <p>Loading anomalies…</p>
      ) : signals.length === 0 ? (
        <p className="empty-state">No anomaly signals for this scope.</p>
      ) : (
        <table className="statements-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Merchant</th>
              <th>Why it flagged</th>
              <th>Reference date</th>
              <th>Amount</th>
              <th scope="col">Ledger link</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((s, idx) => (
              <tr key={`${s.kind}-${s.merchant}-${s.transaction_date}-${idx}`}>
                <td>
                  <span className="pill">{s.kind}</span>
                </td>
                <td>{s.merchant}</td>
                <td className="detail-cell">{s.detail}</td>
                <td>{s.transaction_date}</td>
                <td>{formatMoney(s.amount)}</td>
                <td>
                  {s.transaction_id ? (
                    <Link className="shell-nav-inline" to={`/transactions/${s.transaction_id}`}>
                      View transaction
                    </Link>
                  ) : (
                    <span className="muted">Monthly aggregate signal</span>
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
