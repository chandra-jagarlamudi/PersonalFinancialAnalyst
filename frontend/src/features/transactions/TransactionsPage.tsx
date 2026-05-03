import { useEffect, useState } from 'react'
import {
  createRule,
  listCategories,
  listTransactions,
  proposeRule,
  suggestTransactionCategory,
  updateTransactionCategory,
  type Category,
  type RuleProposal,
  type Transaction,
  type TransactionSort,
} from '@/api'

function formatAmount(amount: string): string {
  const n = parseFloat(amount)
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)
}

const PAGE_SIZE_OPTIONS = [25, 50, 75, 100] as const

type SortColumn = 'date' | 'amount' | 'description' | 'category'

const SORT_PAIR: Record<SortColumn, [TransactionSort, TransactionSort]> = {
  date: ['date_desc', 'date_asc'],
  amount: ['amount_desc', 'amount_asc'],
  description: ['description_desc', 'description_asc'],
  category: ['category_desc', 'category_asc'],
}

function cycleSort(column: SortColumn, current: TransactionSort): TransactionSort {
  const [a, b] = SORT_PAIR[column]
  return current === a ? b : a
}

function sortActiveColumn(sort: TransactionSort): SortColumn | null {
  const entry = (Object.entries(SORT_PAIR) as [SortColumn, [TransactionSort, TransactionSort]][]).find(
    ([, pair]) => pair.includes(sort),
  )
  return entry ? entry[0] : null
}

function SortHeader({
  label,
  column,
  sort,
  onSort,
}: {
  label: string
  column: SortColumn
  sort: TransactionSort
  onSort: (col: SortColumn) => void
}) {
  const activeCol = sortActiveColumn(sort)
  const isActive = activeCol === column
  const arrow =
    !isActive ? '↕' : sort.endsWith('_asc') ? '↑' : '↓'
  return (
    <th scope="col" className="txn-th">
      <button
        type="button"
        className={'txn-sort-btn' + (isActive ? ' txn-sort-btn-active' : '')}
        onClick={() => onSort(column)}
      >
        <span>{label}</span>
        <span className="txn-sort-indicator" aria-hidden>
          {arrow}
        </span>
      </button>
    </th>
  )
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

  const [pattern, setPattern] = useState(tx.description_normalized)
  const [retroactive, setRetroactive] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [preview, setPreview] = useState<RuleProposal | null>(null)
  const [rulePriority, setRulePriority] = useState(100)
  const [creatingRule, setCreatingRule] = useState(false)
  const [suggesting, setSuggesting] = useState(false)

  function handleRowClick() {
    setExpanded((e) => !e)
    setError(null)
    setSuccess(null)
    setEditor({ phase: 'category' })
    setSelectedCategory(tx.category_id ?? '')
  }

  async function handleSuggestCategory() {
    setSuggesting(true)
    setError(null)
    try {
      const result = await suggestTransactionCategory(tx.id)
      if (result.error || !result.category_id) {
        setError(result.error ?? 'No suggestion available')
        return
      }
      setSelectedCategory(result.category_id)
      setSuccess(
        result.slug ? `Suggested: ${result.slug.replace(/-/g, ' ')} — pick Save correction to apply.` : 'Suggestion ready.',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Suggestion failed')
    } finally {
      setSuggesting(false)
    }
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
        className="txn-row"
        onClick={handleRowClick}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            handleRowClick()
          }
        }}
        tabIndex={0}
        aria-expanded={expanded}
      >
        <td>{tx.transaction_date}</td>
        <td className="txn-num">{formatAmount(tx.amount)}</td>
        <td className="txn-desc">{tx.description_normalized}</td>
        <td className="txn-cat">{tx.category_name ?? <em className="txn-uncat">Uncategorized</em>}</td>
        <td className="txn-source" title={tx.source_statement_filename ?? undefined}>
          {tx.source_statement_filename ?? '—'}
        </td>
      </tr>
      {expanded && (
        <tr className="txn-expand-row">
          <td colSpan={5} className="txn-row-detail">
            {error && <p className="error-banner">{error}</p>}
            {success && <p className="success-banner">{success}</p>}

            {editor.phase === 'category' && (
              <div className="txn-editor-row">
                {categoryError && categories.length === 0 ? (
                  <>
                    <span className="error-banner" style={{ margin: 0 }}>
                      Could not load categories: {categoryError}
                    </span>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={(e) => {
                        e.stopPropagation()
                        onRetryCategories()
                      }}
                    >
                      Retry
                    </button>
                  </>
                ) : (
                  <>
                    <label htmlFor={`cat-select-${tx.id}`} className="txn-editor-label">
                      Category:
                    </label>
                    <select
                      id={`cat-select-${tx.id}`}
                      value={selectedCategory}
                      onChange={(e) => setSelectedCategory(e.target.value)}
                      className="txn-editor-select"
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
                      className="secondary-button"
                      onClick={(e) => {
                        e.stopPropagation()
                        void handleSuggestCategory()
                      }}
                      disabled={suggesting || categories.length === 0}
                    >
                      {suggesting ? 'Suggesting…' : 'Suggest with AI'}
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        void handleSaveCategory()
                      }}
                      disabled={!selectedCategory || saving}
                    >
                      {saving ? 'Saving…' : 'Save correction'}
                    </button>
                  </>
                )}
              </div>
            )}

            {editor.phase === 'propose' && (
              <div className="txn-rule-block">
                <p className="txn-rule-title">Propose a rule?</p>
                <div className="txn-editor-row txn-editor-row-wrap">
                  <label htmlFor={`pattern-${tx.id}`}>Pattern:</label>
                  <input
                    id={`pattern-${tx.id}`}
                    value={pattern}
                    onChange={(e) => {
                      setPattern(e.target.value)
                      setPreview(null)
                    }}
                    className="txn-pattern-input"
                  />
                  <label className="txn-inline-check">
                    <input
                      type="checkbox"
                      checked={retroactive}
                      onChange={(e) => {
                        setRetroactive(e.target.checked)
                        setPreview(null)
                      }}
                    />{' '}
                    Apply retroactively
                  </label>
                  <label>
                    Priority:
                    <input
                      type="number"
                      value={rulePriority}
                      onChange={(e) => setRulePriority(Number(e.target.value))}
                      className="txn-priority-input"
                    />
                  </label>
                </div>
                <div className="txn-editor-row txn-editor-row-wrap">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={(e) => {
                      e.stopPropagation()
                      void handlePreviewRule()
                    }}
                    disabled={!pattern || previewing}
                  >
                    {previewing ? 'Previewing…' : 'Preview rule'}
                  </button>
                  {preview && (
                    <span className="txn-preview-hint">
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
                          `Apply this rule retroactively to ${preview.would_affect_count} transaction(s)? This will update existing transactions.`,
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
  const [total, setTotal] = useState(0)
  const [categories, setCategories] = useState<Category[]>([])
  const [categoryError, setCategoryError] = useState<string | null>(null)
  const [uncategorizedOnly, setUncategorizedOnly] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState<number>(25)
  const [sort, setSort] = useState<TransactionSort>('date_desc')
  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(searchInput.trim()), 350)
    return () => window.clearTimeout(t)
  }, [searchInput])

  useEffect(() => {
    setPage(0)
  }, [debouncedSearch])

  async function fetchTransactions() {
    setLoading(true)
    setError(null)
    try {
      const { items, total: n } = await listTransactions({
        uncategorized: uncategorizedOnly || undefined,
        limit: pageSize,
        offset: page * pageSize,
        sort,
        q: debouncedSearch || undefined,
      })
      setTransactions(items)
      setTotal(n)
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
    void fetchTransactions()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, sort, debouncedSearch, uncategorizedOnly])

  useEffect(() => {
    void loadCategories()
  }, [])

  function handleToggleUncategorized() {
    const next = !uncategorizedOnly
    setUncategorizedOnly(next)
    setPage(0)
  }

  function handleSortColumn(column: SortColumn) {
    setSort((prev) => cycleSort(column, prev))
    setPage(0)
  }

  function handlePageSizeChange(nextSize: number) {
    setPageSize(nextSize)
    setPage(0)
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

  const startIdx = total === 0 ? 0 : page * pageSize + 1
  const endIdx = Math.min((page + 1) * pageSize, total)
  const lastPage = Math.max(0, Math.ceil(total / pageSize) - 1)

  return (
    <section className="panel transactions-panel">
      <h2>Transactions</h2>

      <div className="txn-toolbar">
        <label className="txn-filter-check">
          <input type="checkbox" checked={uncategorizedOnly} onChange={handleToggleUncategorized} />
          Show only uncategorized
        </label>

        <label className="txn-search-label">
          <span className="txn-search-span">Search description</span>
          <input
            type="search"
            className="txn-search-input"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Filter by text…"
            aria-label="Filter transactions by description"
          />
        </label>

        <button
          type="button"
          className="secondary-button"
          onClick={() => void fetchTransactions()}
          disabled={loading}
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {error && <p className="error-banner">{error}</p>}

      {loading && transactions.length === 0 ? (
        <p className="txn-loading-muted">Loading transactions…</p>
      ) : !loading && transactions.length === 0 ? (
        <p className="txn-empty">No transactions found.</p>
      ) : (
        <>
          <div className="txn-table-wrap">
            <table className="txn-table">
              <thead>
                <tr>
                  <SortHeader label="Date" column="date" sort={sort} onSort={handleSortColumn} />
                  <SortHeader label="Amount" column="amount" sort={sort} onSort={handleSortColumn} />
                  <SortHeader label="Description" column="description" sort={sort} onSort={handleSortColumn} />
                  <SortHeader label="Category" column="category" sort={sort} onSort={handleSortColumn} />
                  <th scope="col" className="txn-th txn-th-source">
                    Source
                  </th>
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
                    onRuleCreated={() => void fetchTransactions()}
                  />
                ))}
              </tbody>
            </table>
          </div>

          <div className="txn-pagination" aria-label="Pagination">
            <span className="txn-page-info">
              Showing <strong>{startIdx}</strong>–<strong>{endIdx}</strong> of <strong>{total}</strong>
            </span>
            <label className="txn-page-size">
              Rows per page
              <select
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                aria-label="Rows per page"
              >
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <div className="txn-page-nav">
              <button
                type="button"
                className="secondary-button"
                disabled={page <= 0 || loading}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                Previous
              </button>
              <span className="txn-page-num">
                Page {total === 0 ? 0 : page + 1} of {total === 0 ? 0 : lastPage + 1}
              </span>
              <button
                type="button"
                className="secondary-button"
                disabled={loading || page >= lastPage || total === 0}
                onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  )
}
