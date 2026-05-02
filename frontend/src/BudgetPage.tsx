import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createCategory,
  getBudgetStatus,
  listBudgets,
  listCategories,
  putBudgets,
  suggestBudgets,
  type BudgetStatus,
  type Category,
} from './api'

function currentYearMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function shiftMonth(ym: string, delta: number): string {
  const [y, m] = ym.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export default function BudgetPage() {
  const [yearMonth, setYearMonth] = useState(currentYearMonth)
  const [categories, setCategories] = useState<Category[]>([])
  const [amountMap, setAmountMap] = useState<Record<string, string>>({})
  const [statusRows, setStatusRows] = useState<BudgetStatus[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [suggesting, setSuggesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  const [newSlug, setNewSlug] = useState('')
  const [newName, setNewName] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const loadData = useCallback(async (ym: string) => {
    setLoading(true)
    setError(null)
    setSaveMsg(null)
    try {
      const [cats, budgets, status] = await Promise.all([
        listCategories(),
        listBudgets(ym),
        getBudgetStatus(ym),
      ])
      setCategories(cats)
      const map: Record<string, string> = {}
      for (const cat of cats) {
        map[cat.id] = '0'
      }
      for (const b of budgets) {
        map[b.category_id] = b.amount
      }
      setAmountMap(map)
      setStatusRows(status)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load budget data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData(yearMonth)
  }, [yearMonth, loadData])

  async function handleSave() {
    setSaving(true)
    setSaveMsg(null)
    setError(null)
    try {
      const items = Object.entries(amountMap)
        .filter(([, v]) => v !== '' && parseFloat(v) > 0)
        .map(([category_id, amount]) => ({ category_id, amount }))
      await putBudgets(yearMonth, items)
      setSaveMsg('Budgets saved.')
      const status = await getBudgetStatus(yearMonth)
      setStatusRows(status)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save budgets')
    } finally {
      setSaving(false)
    }
  }

  async function handleSuggest() {
    setSuggesting(true)
    setError(null)
    try {
      const suggestions = await suggestBudgets(yearMonth)
      setAmountMap((prev) => {
        const next = { ...prev }
        for (const s of suggestions) {
          next[s.category_id] = s.suggested_amount
        }
        return next
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch suggestions')
    } finally {
      setSuggesting(false)
    }
  }

  async function handleCreateCategory(e: FormEvent) {
    e.preventDefault()
    setCreating(true)
    setCreateError(null)
    try {
      await createCategory({ slug: newSlug.trim(), name: newName.trim() })
      setNewSlug('')
      setNewName('')
      await loadData(yearMonth)
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create category')
    } finally {
      setCreating(false)
    }
  }

  return (
    <section className="panel">
      <div className="budget-month-nav">
        <button
          type="button"
          className="secondary-button"
          onClick={() => setYearMonth(shiftMonth(yearMonth, -1))}
        >
          ‹ Prev
        </button>
        <h2 className="budget-month-label">{yearMonth}</h2>
        <button
          type="button"
          className="secondary-button"
          onClick={() => setYearMonth(shiftMonth(yearMonth, 1))}
        >
          Next ›
        </button>
      </div>

      {error ? <p className="error-banner">{error}</p> : null}
      {saveMsg ? <p className="success-banner">{saveMsg}</p> : null}

      {loading ? (
        <p className="budget-loading">Loading…</p>
      ) : categories.length === 0 ? (
        <div>
          <p className="budget-empty-msg">No categories yet. Create one below.</p>
          <form className="budget-create-form" onSubmit={(e) => void handleCreateCategory(e)}>
            <input
              placeholder="slug (e.g. groceries)"
              value={newSlug}
              onChange={(e) => setNewSlug(e.target.value)}
              required
            />
            <input
              placeholder="Name (e.g. Groceries)"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              required
            />
            <button type="submit" disabled={creating || !newSlug || !newName}>
              {creating ? 'Creating…' : 'Create category'}
            </button>
            {createError ? <p className="error-banner">{createError}</p> : null}
          </form>
        </div>
      ) : (
        <>
          <div className="budget-toolbar">
            <button
              type="button"
              className="secondary-button"
              onClick={() => void handleSuggest()}
              disabled={suggesting}
            >
              {suggesting ? 'Fetching…' : 'Suggest from history'}
            </button>
            <button type="button" onClick={() => void handleSave()} disabled={saving}>
              {saving ? 'Saving…' : 'Save budgets'}
            </button>
          </div>

          <table className="budget-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Budgeted Amount</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((cat) => (
                <tr key={cat.id}>
                  <td>{cat.name}</td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={amountMap[cat.id] ?? '0'}
                      onChange={(e) =>
                        setAmountMap((prev) => ({ ...prev, [cat.id]: e.target.value }))
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <details className="budget-add-category">
            <summary>Add new category</summary>
            <form className="budget-create-form" onSubmit={(e) => void handleCreateCategory(e)}>
              <input
                placeholder="slug (e.g. rent)"
                value={newSlug}
                onChange={(e) => setNewSlug(e.target.value)}
                required
              />
              <input
                placeholder="Name (e.g. Rent)"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                required
              />
              <button type="submit" disabled={creating || !newSlug || !newName}>
                {creating ? 'Creating…' : 'Create category'}
              </button>
              {createError ? <p className="error-banner">{createError}</p> : null}
            </form>
          </details>

          {statusRows.length > 0 && (
            <div className="budget-status-section">
              <h3>Budget vs Actual</h3>
              <table className="budget-table">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Budget</th>
                    <th>Spent MTD</th>
                    <th>Projected</th>
                    <th>Remaining</th>
                  </tr>
                </thead>
                <tbody>
                  {statusRows.map((row) => {
                    const isOver = parseFloat(row.remaining_mtd) < 0
                    return (
                      <tr key={row.category_id}>
                        <td>{row.name}</td>
                        <td>{row.budget_amount}</td>
                        <td>{row.spent_mtd}</td>
                        <td>{row.projected_spend}</td>
                        <td className={isOver ? 'budget-remaining-over' : 'budget-remaining-ok'}>
                          {row.remaining_mtd}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}
