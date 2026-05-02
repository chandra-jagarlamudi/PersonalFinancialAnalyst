import { useEffect, useState } from 'react'
import { listRecurring, type RecurringCharge } from './api'

type State =
  | { status: 'loading' }
  | { status: 'ready'; charges: RecurringCharge[] }
  | { status: 'error'; message: string }

function formatAmount(amount: string): string {
  return `$${parseFloat(amount).toFixed(2)}/mo`
}

function formatDateRange(first: string, last: string): string {
  return `${first} → ${last}`
}

function ChargeRow({ charge }: { charge: RecurringCharge }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <article className="panel recurring-row">
      <div className="recurring-main">
        <div className="recurring-merchant">
          <strong>{charge.merchant}</strong>
        </div>
        <div className="recurring-amount">{formatAmount(charge.typical_amount)}</div>
        <div className="recurring-occurrences">
          <span className="metric-label">Occurrences</span>
          {charge.occurrences} months
        </div>
        <div className="recurring-range">
          <span className="metric-label">Date range</span>
          {formatDateRange(charge.first_seen, charge.last_seen)}
        </div>
        <button
          type="button"
          className="secondary-button recurring-toggle"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
        >
          {expanded ? 'Hide dates' : 'Show dates'}
        </button>
      </div>
      {expanded && (
        <ul className="recurring-dates">
          {charge.monthly_dates.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      )}
    </article>
  )
}

export function RecurringPage() {
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    listRecurring()
      .then((charges) => {
        if (!cancelled) setState({ status: 'ready', charges })
      })
      .catch((err) => {
        if (!cancelled)
          setState({
            status: 'error',
            message: err instanceof Error ? err.message : 'Failed to load recurring charges',
          })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="panel">
      <h2>Recurring Charges</h2>
      <p className="recurring-note">
        Charges are flagged as recurring when the same merchant appears in 3 or more different
        months with a similar amount.
      </p>

      {state.status === 'loading' && <p>Loading recurring charges…</p>}

      {state.status === 'error' && (
        <p className="error-banner">{state.message}</p>
      )}

      {state.status === 'ready' && state.charges.length === 0 && (
        <p className="recurring-empty">
          No recurring charges detected. Import at least 3 months of transactions to start
          detecting recurring patterns.
        </p>
      )}

      {state.status === 'ready' && state.charges.length > 0 && (
        <div className="recurring-list">
          {state.charges.map((charge) => (
            <ChargeRow key={charge.merchant} charge={charge} />
          ))}
        </div>
      )}
    </section>
  )
}
