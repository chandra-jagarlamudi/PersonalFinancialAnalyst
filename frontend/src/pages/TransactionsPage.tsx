import { useState, useEffect, useMemo } from 'react'
import { getTransactions, Transaction, TransactionsPage as TxPage } from '../api'

const KNOWN_BANKS = ['chase', 'amex', 'capital_one', 'robinhood']

function isoDate(d: Date) {
  return d.toISOString().split('T')[0]
}

function daysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return isoDate(d)
}

export function TransactionsPage() {
  const [startDate, setStartDate] = useState(daysAgo(30))
  const [endDate, setEndDate] = useState(isoDate(new Date()))
  const [selectedBanks, setSelectedBanks] = useState<string[]>([])
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const [txType, setTxType] = useState<'' | 'debit' | 'credit'>('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<TxPage | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [knownCategories, setKnownCategories] = useState<string[]>([])

  useEffect(() => {
    setPage(1)
  }, [startDate, endDate, selectedBanks, selectedCategories, txType])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getTransactions({
      start_date: startDate,
      end_date: endDate,
      bank: selectedBanks.length ? selectedBanks : undefined,
      category: selectedCategories.length ? selectedCategories : undefined,
      transaction_type: txType || undefined,
      page,
    })
      .then((result) => {
        if (cancelled) return
        setData(result)
        const cats = result.transactions
          .map((t) => t.category)
          .filter((c): c is string => c !== null)
        setKnownCategories((prev) => Array.from(new Set([...prev, ...cats])).sort())
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [startDate, endDate, selectedBanks, selectedCategories, txType, page])

  const displayed = useMemo(() => {
    if (!data) return []
    const q = search.toLowerCase()
    if (!q) return data.transactions
    return data.transactions.filter(
      (t) =>
        t.description.toLowerCase().includes(q) ||
        t.merchant.toLowerCase().includes(q),
    )
  }, [data, search])

  function exportCSV() {
    const header = ['Date', 'Description', 'Merchant', 'Amount', 'Type', 'Category', 'Bank']
    const rows = displayed.map((t) => [
      t.date,
      t.description,
      t.merchant,
      t.amount,
      t.transaction_type,
      t.category ?? '',
      t.source_bank,
    ])
    const csv = [header, ...rows]
      .map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `transactions-${startDate}-${endDate}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  function toggleBank(b: string) {
    setSelectedBanks((prev) => (prev.includes(b) ? prev.filter((x) => x !== b) : [...prev, b]))
  }

  function toggleCategory(c: string) {
    setSelectedCategories((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Transactions</h1>
        <button
          onClick={exportCSV}
          disabled={displayed.length === 0}
          style={{
            background: '#2563eb',
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            padding: '6px 14px',
            cursor: displayed.length === 0 ? 'not-allowed' : 'pointer',
            fontSize: 13,
            opacity: displayed.length === 0 ? 0.5 : 1,
          }}
        >
          Export CSV
        </button>
      </div>

      {/* Filters */}
      <div style={{
        background: '#fff',
        border: '1px solid #e5e7eb',
        borderRadius: 8,
        padding: 16,
        marginBottom: 12,
        display: 'flex',
        flexWrap: 'wrap',
        gap: 20,
        alignItems: 'flex-start',
      }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#374151', marginBottom: 4 }}>Date range</div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
              style={{ padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }} />
            <span style={{ color: '#9ca3af', fontSize: 13 }}>–</span>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
              style={{ padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }} />
          </div>
        </div>

        <div>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#374151', marginBottom: 4 }}>Bank</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {KNOWN_BANKS.map((b) => (
              <label key={b} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, cursor: 'pointer' }}>
                <input type="checkbox" checked={selectedBanks.includes(b)} onChange={() => toggleBank(b)} />
                {b.replace(/_/g, ' ')}
              </label>
            ))}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#374151', marginBottom: 4 }}>Type</div>
          <div style={{ display: 'flex', gap: 8 }}>
            {([['', 'All'], ['debit', 'Debit'], ['credit', 'Credit']] as [typeof txType, string][]).map(([v, label]) => (
              <label key={v} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, cursor: 'pointer' }}>
                <input type="radio" name="txtype" checked={txType === v} onChange={() => setTxType(v)} />
                {label}
              </label>
            ))}
          </div>
        </div>

        {knownCategories.length > 0 && (
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: '#374151', marginBottom: 4 }}>Category</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', maxWidth: 360 }}>
              {knownCategories.map((c) => (
                <label key={c} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, cursor: 'pointer' }}>
                  <input type="checkbox" checked={selectedCategories.includes(c)} onChange={() => toggleCategory(c)} />
                  {c}
                </label>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Search */}
      <input
        type="text"
        placeholder="Search description or merchant…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{
          width: '100%',
          padding: '8px 12px',
          border: '1px solid #d1d5db',
          borderRadius: 6,
          fontSize: 14,
          marginBottom: 12,
          boxSizing: 'border-box',
        }}
      />

      {loading ? (
        <div style={{ color: '#6b7280', fontSize: 14, padding: '24px 0', textAlign: 'center' }}>
          Loading transactions…
        </div>
      ) : error ? (
        <div style={{ color: '#dc2626', fontSize: 14, padding: '16px 0' }}>{error}</div>
      ) : (
        <>
          <div style={{ overflowX: 'auto', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                  {['Date', 'Description', 'Merchant', 'Amount', 'Type', 'Category', 'Bank'].map((h) => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, color: '#374151', whiteSpace: 'nowrap' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {displayed.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ padding: 24, textAlign: 'center', color: '#9ca3af' }}>
                      No transactions found
                    </td>
                  </tr>
                ) : (
                  displayed.map((t: Transaction) => (
                    <tr key={t.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '8px 12px', whiteSpace: 'nowrap', color: '#374151' }}>{t.date}</td>
                      <td style={{ padding: '8px 12px', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={t.description}>{t.description}</td>
                      <td style={{ padding: '8px 12px', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={t.merchant}>{t.merchant}</td>
                      <td style={{
                        padding: '8px 12px',
                        whiteSpace: 'nowrap',
                        fontWeight: 500,
                        color: t.transaction_type === 'debit' ? '#c0392b' : '#27ae60',
                      }}>
                        {t.transaction_type === 'debit' ? '−' : '+'}${t.amount}
                      </td>
                      <td style={{ padding: '8px 12px', color: '#6b7280' }}>{t.transaction_type}</td>
                      <td style={{ padding: '8px 12px', color: '#6b7280' }}>{t.category ?? '—'}</td>
                      <td style={{ padding: '8px 12px', color: '#6b7280' }}>{t.source_bank}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {data && data.pages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, fontSize: 13, color: '#6b7280' }}>
              <span>Page {data.page} of {data.pages} ({data.total} total)</span>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  style={{ padding: '4px 10px', border: '1px solid #d1d5db', borderRadius: 4, cursor: page <= 1 ? 'not-allowed' : 'pointer', opacity: page <= 1 ? 0.5 : 1, background: '#fff' }}
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                  disabled={page >= data.pages}
                  style={{ padding: '4px 10px', border: '1px solid #d1d5db', borderRadius: 4, cursor: page >= data.pages ? 'not-allowed' : 'pointer', opacity: page >= data.pages ? 0.5 : 1, background: '#fff' }}
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
