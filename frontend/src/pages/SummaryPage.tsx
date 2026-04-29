import { useState, useEffect, ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  PieChart, Pie, Cell, Tooltip,
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer,
} from 'recharts'
import {
  summarizeMonth,
  findUnusualSpend,
  listRecurringSubscriptions,
  getTransactions,
  Transaction,
} from '../api'

const COLORS = ['#2563eb', '#7c3aed', '#db2777', '#dc2626', '#ea580c', '#ca8a04', '#16a34a', '#0891b2', '#6366f1', '#ec4899']

function currentMonth() {
  return new Date().toISOString().slice(0, 7)
}

function monthStart(m: string) {
  return `${m}-01`
}

function monthEnd(m: string) {
  const d = new Date(`${m}-01`)
  d.setMonth(d.getMonth() + 1)
  d.setDate(0)
  return d.toISOString().slice(0, 10)
}

function monthLabel(m: string) {
  const [y, mo] = m.split('-')
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${months[parseInt(mo) - 1]} ${y}`
}

async function fetchMonthTransactions(month: string): Promise<Transaction[]> {
  const all: Transaction[] = []
  let p = 1
  for (let attempt = 0; attempt < 20; attempt++) {
    const res = await getTransactions({ start_date: monthStart(month), end_date: monthEnd(month), page: p })
    all.push(...res.transactions)
    if (p >= res.pages) break
    p++
  }
  return all
}

function buildCategoryData(txns: Transaction[]) {
  const map: Record<string, number> = {}
  for (const t of txns) {
    if (t.transaction_type !== 'debit') continue
    const key = t.category ?? 'Uncategorized'
    map[key] = (map[key] ?? 0) + parseFloat(t.amount)
  }
  return Object.entries(map)
    .map(([name, value]) => ({ name, value: Math.round(value * 100) / 100 }))
    .sort((a, b) => b.value - a.value)
}

function buildMerchantData(txns: Transaction[]) {
  const map: Record<string, number> = {}
  for (const t of txns) {
    if (t.transaction_type !== 'debit') continue
    const key = t.merchant || t.description.slice(0, 32)
    map[key] = (map[key] ?? 0) + parseFloat(t.amount)
  }
  return Object.entries(map)
    .map(([name, value]) => ({ name, value: Math.round(value * 100) / 100 }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)
}

async function buildTrendData(baseMonth: string) {
  const months = Array.from({ length: 6 }, (_, i) => {
    const d = new Date(`${baseMonth}-01`)
    d.setMonth(d.getMonth() - (5 - i))
    return d.toISOString().slice(0, 7)
  })
  return Promise.all(
    months.map(async (m) => {
      const txns = await fetchMonthTransactions(m)
      const total = txns
        .filter((t) => t.transaction_type === 'debit')
        .reduce((s, t) => s + parseFloat(t.amount), 0)
      return { month: m.slice(5), label: monthLabel(m), value: Math.round(total * 100) / 100 }
    }),
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ToolPanel({ loading, error, result }: { loading: boolean; error: string | null; result: string | null }) {
  if (loading) return <div style={{ color: '#9ca3af', fontSize: 14, padding: '12px 0' }}>Loading…</div>
  if (error) return <div style={{ color: '#dc2626', fontSize: 14 }}>Error: {error}</div>
  if (!result) return null
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '16px 20px', fontSize: 14, lineHeight: 1.7 }}>
      <ReactMarkdown>{result}</ReactMarkdown>
    </div>
  )
}

function LookbackSelector({ value, options, onChange }: { value: number; options: number[]; onChange: (n: number) => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
      <span style={{ fontSize: 13, color: '#374151', fontWeight: 500 }}>Lookback:</span>
      {options.map((n) => (
        <button
          key={n}
          onClick={() => onChange(n)}
          style={{
            padding: '3px 10px',
            border: `1px solid ${value === n ? '#2563eb' : '#d1d5db'}`,
            borderRadius: 4,
            background: value === n ? '#eff6ff' : '#fff',
            color: value === n ? '#2563eb' : '#374151',
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          {n}mo
        </button>
      ))}
    </div>
  )
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16 }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: '#374151' }}>{title}</div>
      {children}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

type Tab = 'summary' | 'unusual' | 'subscriptions'

export function SummaryPage() {
  const [month, setMonth] = useState(currentMonth())
  const [activeTab, setActiveTab] = useState<Tab>('summary')
  const [unusualLookback, setUnusualLookback] = useState(3)
  const [subLookback, setSubLookback] = useState(6)

  const [summaryResult, setSummaryResult] = useState<string | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  const [unusualResult, setUnusualResult] = useState<string | null>(null)
  const [unusualLoading, setUnusualLoading] = useState(false)
  const [unusualError, setUnusualError] = useState<string | null>(null)

  const [subResult, setSubResult] = useState<string | null>(null)
  const [subLoading, setSubLoading] = useState(false)
  const [subError, setSubError] = useState<string | null>(null)

  const [chartTxns, setChartTxns] = useState<Transaction[]>([])
  const [trendData, setTrendData] = useState<{ month: string; label: string; value: number }[]>([])
  const [chartLoading, setChartLoading] = useState(false)

  useEffect(() => {
    setSummaryResult(null); setSummaryError(null); setSummaryLoading(true)
    summarizeMonth(month, true)
      .then((r) => setSummaryResult(r.result))
      .catch((e: Error) => setSummaryError(e.message))
      .finally(() => setSummaryLoading(false))
  }, [month])

  useEffect(() => {
    setUnusualResult(null); setUnusualError(null); setUnusualLoading(true)
    findUnusualSpend(month, unusualLookback)
      .then((r) => setUnusualResult(r.result))
      .catch((e: Error) => setUnusualError(e.message))
      .finally(() => setUnusualLoading(false))
  }, [month, unusualLookback])

  useEffect(() => {
    setSubResult(null); setSubError(null); setSubLoading(true)
    listRecurringSubscriptions(subLookback)
      .then((r) => setSubResult(r.result))
      .catch((e: Error) => setSubError(e.message))
      .finally(() => setSubLoading(false))
  }, [subLookback])

  useEffect(() => {
    let cancelled = false
    setChartLoading(true)
    Promise.all([fetchMonthTransactions(month), buildTrendData(month)])
      .then(([txns, trend]) => {
        if (!cancelled) { setChartTxns(txns); setTrendData(trend) }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setChartLoading(false) })
    return () => { cancelled = true }
  }, [month])

  const categoryData = buildCategoryData(chartTxns)
  const merchantData = buildMerchantData(chartTxns)

  const tabs: { id: Tab; label: string }[] = [
    { id: 'summary', label: 'Month Summary' },
    { id: 'unusual', label: 'Unusual Spend' },
    { id: 'subscriptions', label: 'Subscriptions' },
  ]

  return (
    <div style={{ maxWidth: 900 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Summary</h1>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
          <span style={{ color: '#374151', fontWeight: 500 }}>Month</span>
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            style={{ padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14 }}
          />
        </label>
      </div>

      {/* Tabs */}
      <div style={{ borderBottom: '1px solid #e5e7eb', marginBottom: 20 }}>
        <div style={{ display: 'flex' }}>
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              style={{
                padding: '10px 20px',
                border: 'none',
                background: 'none',
                cursor: 'pointer',
                fontSize: 14,
                fontWeight: activeTab === t.id ? 600 : 400,
                color: activeTab === t.id ? '#2563eb' : '#6b7280',
                borderBottom: activeTab === t.id ? '2px solid #2563eb' : '2px solid transparent',
                marginBottom: -1,
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ marginBottom: 32 }}>
        {activeTab === 'summary' && (
          <ToolPanel loading={summaryLoading} error={summaryError} result={summaryResult} />
        )}
        {activeTab === 'unusual' && (
          <>
            <LookbackSelector value={unusualLookback} options={[1, 3, 6]} onChange={setUnusualLookback} />
            <ToolPanel loading={unusualLoading} error={unusualError} result={unusualResult} />
          </>
        )}
        {activeTab === 'subscriptions' && (
          <>
            <LookbackSelector value={subLookback} options={[3, 6, 12]} onChange={setSubLookback} />
            <ToolPanel loading={subLoading} error={subError} result={subResult} />
          </>
        )}
      </div>

      {/* Charts */}
      <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 24 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 20 }}>Spend Breakdown</h2>
        {chartLoading ? (
          <div style={{ color: '#9ca3af', fontSize: 14 }}>Loading charts…</div>
        ) : chartTxns.length === 0 ? (
          <div style={{ color: '#9ca3af', fontSize: 14 }}>No transaction data for {monthLabel(month)}</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

            <ChartCard title="Spending by Category">
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={categoryData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={({ name, percent }: { name: string; percent: number }) =>
                      `${name} ${(percent * 100).toFixed(0)}%`
                    }
                  >
                    {categoryData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => [`$${v.toFixed(2)}`, 'Amount']} />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Monthly Spending Trend (last 6 months)">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={trendData} margin={{ top: 5, right: 20, bottom: 5, left: 20 }}>
                  <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} tickFormatter={(v: number) => `$${v}`} />
                  <Tooltip
                    labelFormatter={(label: string) => {
                      const entry = trendData.find((d) => d.month === label)
                      return entry?.label ?? label
                    }}
                    formatter={(v: number) => [`$${v.toFixed(2)}`, 'Spending']}
                  />
                  <Bar dataKey="value" fill="#2563eb" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Top 10 Merchants">
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={merchantData} layout="vertical" margin={{ top: 5, right: 30, bottom: 5, left: 110 }}>
                  <XAxis type="number" tick={{ fontSize: 12 }} tickFormatter={(v: number) => `$${v}`} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={110} />
                  <Tooltip formatter={(v: number) => [`$${v.toFixed(2)}`, 'Amount']} />
                  <Bar dataKey="value" fill="#7c3aed" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

          </div>
        )}
      </div>
    </div>
  )
}
