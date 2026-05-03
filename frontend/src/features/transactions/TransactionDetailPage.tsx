import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getTransaction, listAccounts, listInstitutions, type Account, type Institution, type TransactionDetail } from '@/api'

export default function TransactionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [detail, setDetail] = useState<TransactionDetail | null>(null)
  const [accounts, setAccounts] = useState<Map<string, Account>>(new Map())
  const [institutions, setInstitutions] = useState<Map<string, Institution>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) {
      setError('Missing transaction id')
      setLoading(false)
      return
    }
    const transactionId: string = id

    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [tx, acctList, instList] = await Promise.all([
          getTransaction(transactionId),
          listAccounts(),
          listInstitutions(),
        ])
        if (cancelled) {
          return
        }
        setDetail(tx)
        setAccounts(new Map(acctList.map(a => [a.id, a])))
        setInstitutions(new Map(instList.map(i => [i.id, i])))
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unable to load transaction')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [id])

  return (
    <section className="panel">
      <p className="breadcrumb">
        <Link to="/anomalies">← Back to anomalies</Link>
      </p>
      <h2>Transaction</h2>

      {loading ? (
        <p>Loading…</p>
      ) : error ? (
        <p className="error-banner">{error}</p>
      ) : detail ? (
        <dl className="txn-detail">
          <div>
            <dt>Account</dt>
            <dd>
              {(() => {
                const acct = accounts.get(detail.account_id)
                if (!acct) return detail.account_id
                const inst = institutions.get(acct.institution_id)
                return inst ? `${inst.name} — ${acct.name}` : acct.name
              })()}
            </dd>
          </div>
          <div>
            <dt>Date</dt>
            <dd>{detail.transaction_date}</dd>
          </div>
          {detail.posted_date ? (
            <div>
              <dt>Posted</dt>
              <dd>{detail.posted_date}</dd>
            </div>
          ) : null}
          <div>
            <dt>Amount</dt>
            <dd>
              {detail.amount} {detail.currency}
            </dd>
          </div>
          <div>
            <dt>Description</dt>
            <dd>{detail.description_raw}</dd>
          </div>
          <div>
            <dt>Normalized merchant key</dt>
            <dd>{detail.description_normalized}</dd>
          </div>
          <div>
            <dt>Category</dt>
            <dd>{detail.category_name ?? detail.category_slug ?? '—'}</dd>
          </div>
        </dl>
      ) : null}
    </section>
  )
}
