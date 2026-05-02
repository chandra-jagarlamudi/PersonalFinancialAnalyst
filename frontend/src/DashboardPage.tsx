import { useEffect, useState } from 'react'

import { listCashflow, listCategorySpend, type DashboardCashflowPoint, type DashboardCategorySpendPoint } from './api'

type DashboardPageProps = {
  onError: (message: string | null) => void
}

export function DashboardPage({ onError }: DashboardPageProps) {
  const [cashflow, setCashflow] = useState<DashboardCashflowPoint[]>([])
  const [categorySpend, setCategorySpend] = useState<DashboardCategorySpendPoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const [nextCashflow, nextCategorySpend] = await Promise.all([
          listCashflow(12),
          listCategorySpend(12),
        ])
        if (cancelled) {
          return
        }
        setCashflow(nextCashflow)
        setCategorySpend(nextCategorySpend)
        onError(null)
      } catch (error) {
        if (!cancelled) {
          onError(error instanceof Error ? error.message : 'Unable to load dashboard data')
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
  }, [onError])

  if (loading) {
    return <section className="panel"><p>Loading dashboard…</p></section>
  }

  return (
    <section className="panel">
      <h2>Dashboard</h2>
      <p>Cashflow and category spend light up as soon as you create or import transactions.</p>

      <div className="status-grid">
        <article>
          <span className="metric-label">Cashflow months</span>
          <strong>{cashflow.length}</strong>
        </article>
        <article>
          <span className="metric-label">Category spend rows</span>
          <strong>{categorySpend.length}</strong>
        </article>
      </div>

      <div className="setup-grid">
        <section className="setup-section">
          <h3>Cashflow over time</h3>
          {cashflow.length === 0 ? (
            <p>Add manual transactions from the explorer to populate this view.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Month</th>
                  <th>Income</th>
                  <th>Expenses</th>
                  <th>Net</th>
                </tr>
              </thead>
              <tbody>
                {cashflow.map((row) => (
                  <tr key={row.month}>
                    <td>{row.month}</td>
                    <td>{row.income_total}</td>
                    <td>{row.expense_total_abs}</td>
                    <td>{row.net_total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="setup-section">
          <h3>Category spending over time</h3>
          {categorySpend.length === 0 ? (
            <p>Create categorized manual transactions to populate this view.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Month</th>
                  <th>Category</th>
                  <th>Spend</th>
                </tr>
              </thead>
              <tbody>
                {categorySpend.map((row) => (
                  <tr key={`${row.month}-${row.category_name}`}>
                    <td>{row.month}</td>
                    <td>{row.category_name}</td>
                    <td>{row.spend_total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </section>
  )
}
