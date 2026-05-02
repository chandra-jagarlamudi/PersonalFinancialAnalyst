import { useEffect, useState } from 'react'
import {
  createRule,
  listCategories,
  listTransactions,
  proposeRule,
  updateTransactionCategory,
  type Category,
  type RuleProposal,
  type Transaction,
} from './api'

function formatAmount(amount: string): string {
  const n = parseFloat(amount)
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)
}

type EditorState =
  | { phase: 'category' }
  | { phase: 'propose'; pattern: string; retroactive: boolean; preview: RuleProposal | null }
  | { phase: 'done' }

function TransactionRow({
  tx,
  categories,
  categoryError,
  onRetryCategories,
  onUpdated,
  onRuleCreated,
}: {
  tx: Transaction
  categories: Category[]
  categoryError: string | null
  onRetryCategories: () => void
  onUpdated: (updated: Transaction) => void
  onRuleCreated: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [editor, setEditor] = useState<EditorState>({ phase: 'category' })
  const [selectedCategory, setSelectedCategory] = useState(tx.category_id ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Propose-rule sub-state
  const [pattern, setPattern] = useState(tx.description_normalized)
  const [retroactive, setRetroactive] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [preview, setPreview] = useState<RuleProposal | null>(null)
  const [rulePriority, setRulePriority] = useState(100)
  const [creatingRule, setCreatingRule] = useState(false)

  function handleRowClick() {
    setExpanded((e) => !e)
    setError(null)
    setSuccess(null)
    setEditor({ phase: 'category' })
    setSelectedCategory(tx.category_id ?? '')
  }

  async function handleSaveCategory() {
    if (!selectedCategory) return
    setSaving(true)
    setError(null)
    try {
      await updateTransactionCategory(tx.id, selectedCategory)
      const cat = categories.find((c) => c.id === selectedCategory)
      const updated: Transaction = {
        ...tx,
        category_id: selectedCategory,
        category_name: cat?.name ?? null,
      }
      onUpdated(updated)
      setSuccess('Category saved.')
      setPattern(tx.description_normalized)
      setEditor({ phase: 'propose', pattern: tx.description_normalized, retroactive: false, preview: null })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function handlePreviewRule() {
    setPreviewing(true)
    setError(null)
    try {
      const result = await proposeRule(tx.id, { pattern, apply_retroactively: retroactive })
      setPreview(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Preview failed')
    } finally {
      setPreviewing(false)
    }
  }

  async function handleCreateRule() {
    if (!selectedCategory) return
    setCreatingRule(true)
    setError(null)
    try {
      await createRule({
        category_id: selectedCategory,
        pattern,
        priority: rulePriority,
        apply_retroactively: retroactive,
      })
      setSuccess('Rule created successfully.')
      setEditor({ phase: 'done' })
      setExpanded(false)
      if (retroactive) {
        onRuleCreated()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Create rule failed')
    } finally {
      setCreatingRule(false)
    }
  }

  return (
    <>
      <tr
        onClick={handleRowClick}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            handleRowClick()
          }
        }}
        tabIndex={0}
        style={{ cursor: 'pointer' }}
        aria-expanded={expanded}
      >
        <td>{tx.transaction_date}</td>
        <td style={{ textAlign: 'right' }}>{formatAmount(tx.amount)}</td>
        <td>{tx.description_normalized}</td>
        <td>{tx.category_name ?? <em style={{ color: '#888' }}>Uncategorized</em>}</td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={4} style={{ background: '#f9f9f9', padding: '1rem' }}>
            {error && <p className="error-banner">{error}</p>}
            {success && <p className="success-banner">{success}</p>}

            {editor.phase === 'category' && (
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                {categoryError && categories.length === 0 ? (
                  <>
                    <span className="error-banner" style={{ margin: 0 }}>
                      Could not load categories: {categoryError}
                    </span>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); onRetryCategories() }}
                    >
                      Retry
                    </button>
                  </>
                ) : (
                  <>
                    <label htmlFor={`cat-select-${tx.id}`} style={{ fontWeight: 600 }}>Category:</label>
                    <select
                      id={`cat-select-${tx.id}`}
                      value={selectedCategory}
                      onChange={(e) => setSelectedCategory(e.target.value)}
                    >
                      <option value="">— select —</option>
                      {categories.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); void handleSaveCategory() }}
                      disabled={!selectedCategory || saving}
                    >
                      {saving ? 'Saving…' : 'Save correction'}
                    </button>
                  </>
                )}
              </div>
            )}

            {editor.phase === 'propose' && (
              <div>
                <p style={{ marginBottom: '0.75rem', fontWeight: 600 }}>Propose a rule?</p>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                  <label htmlFor={`pattern-${tx.id}`}>Pattern:</label>
                  <input
                    id={`pattern-${tx.id}`}
                    value={pattern}
                    onChange={(e) => { setPattern(e.target.value); setPreview(null) }}
                    style={{ flex: '1', minWidth: '200px' }}
                  />
                  <label>
                    <input
                      type="checkbox"
                      checked={retroactive}
                      onChange={(e) => { setRetroactive(e.target.checked); setPreview(null) }}
                    />{' '}
                    Apply retroactively
                  </label>
                  <label>
                    Priority:
                    <input
                      type="number"
                      value={rulePriority}
                      onChange={(e) => setRulePriority(Number(e.target.value))}
                      style={{ width: '70px', marginLeft: '0.25rem' }}
                    />
                  </label>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); void handlePreviewRule() }}
                    disabled={!pattern || previewing}
                  >
                    {previewing ? 'Previewing…' : 'Preview rule'}
                  </button>
                  {preview && (
                    <span style={{ alignSelf: 'center', color: '#555' }}>
                      Would affect {preview.would_affect_count} transaction(s)
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      if (retroactive) {
                        if (!preview) return
                        const confirmed = window.confirm(
                          `Apply this rule retroactively to ${preview.would_affect_count} transaction(s)? This will update existing transactions.`
                        )
                        if (!confirmed) return
                      }
                      void handleCreateRule()
                    }}
                    disabled={!pattern || creatingRule || (retroactive && !preview)}
                  >
                    {creatingRule ? 'Creating…' : 'Create rule'}
                  </button>
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [categoryError, setCategoryError] = useState<string | null>(null)
  const [uncategorizedOnly, setUncategorizedOnly] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const TRANSACTIONS_PAGE_SIZE = 100

  async function fetchTransactions(uncategorized: boolean) {
    setLoading(true)
    setError(null)
    try {
      const allTransactions: Transaction[] = []
      let offset = 0

      while (true) {
        const page = await listTransactions({
          uncategorized: uncategorized || undefined,
          limit: TRANSACTIONS_PAGE_SIZE,
          offset,
        })

        allTransactions.push(...page)

        if (page.length < TRANSACTIONS_PAGE_SIZE) {
          break
        }

        offset += page.length
      }

      setTransactions(allTransactions)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load transactions')
    } finally {
      setLoading(false)
    }
  }

  async function loadCategories() {
    setCategoryError(null)
    try {
      const cats = await listCategories()
      setCategories(cats)
    } catch (err) {
      setCategoryError(err instanceof Error ? err.message : 'Failed to load categories')
    }
  }

  useEffect(() => {
    void fetchTransactions(uncategorizedOnly)
    void loadCategories()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleToggle() {
    const next = !uncategorizedOnly
    setUncategorizedOnly(next)
    void fetchTransactions(next)
  }

  function isUncategorizedTransaction(tx: Transaction): boolean {
    const candidate = tx as Transaction & {
      category?: Category | null
      categoryId?: string | null
    }

    return candidate.category == null && candidate.categoryId == null
  }

  function handleUpdated(updated: Transaction) {
    setTransactions((prev) => {
      if (!uncategorizedOnly) {
        return prev.map((t) => (t.id === updated.id ? updated : t))
      }

      return prev.flatMap((t) => {
        if (t.id !== updated.id) {
          return [t]
        }

        return isUncategorizedTransaction(updated) ? [updated] : []
      })
    })
  }

  return (
    <section className="panel">
      <h2>Transactions</h2>
      <div style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={uncategorizedOnly}
            onChange={handleToggle}
          />
          Show only uncategorized
        </label>
        <button
          type="button"
          className="secondary-button"
          onClick={() => void fetchTransactions(uncategorizedOnly)}
          disabled={loading}
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {error && <p className="error-banner">{error}</p>}

      {!loading && transactions.length === 0 ? (
        <p>No transactions found.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', paddingBottom: '0.5rem' }}>Date</th>
              <th style={{ textAlign: 'right', paddingBottom: '0.5rem' }}>Amount</th>
              <th style={{ textAlign: 'left', paddingBottom: '0.5rem' }}>Description</th>
              <th style={{ textAlign: 'left', paddingBottom: '0.5rem' }}>Category</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx) => (
              <TransactionRow
                key={tx.id}
                tx={tx}
                categories={categories}
                categoryError={categoryError}
                onRetryCategories={loadCategories}
                onUpdated={handleUpdated}
                onRuleCreated={() => void fetchTransactions(uncategorizedOnly)}
              />
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
