import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BudgetPage from './BudgetPage'

// Compute the expected year-months the same way the component does so the tests
// stay correct regardless of when they run.
function yearMonthOf(now: Date): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}
function shiftYearMonth(ym: string, delta: number): string {
  const [y, m] = ym.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
const CURRENT_YM = yearMonthOf(new Date())
const PREV_YM = shiftYearMonth(CURRENT_YM, -1)
const NEXT_YM = shiftYearMonth(CURRENT_YM, 1)

const CAT = { id: 'cat-1', slug: 'groceries', name: 'Groceries' }
const BUDGET_ROW = { category_id: 'cat-1', slug: 'groceries', name: 'Groceries', amount: '300', currency: 'USD' }
const STATUS_ROW = {
  category_id: 'cat-1',
  slug: 'groceries',
  name: 'Groceries',
  budget_amount: '300',
  spent_mtd: '150',
  projected_spend: '270',
  remaining_mtd: '150',
  remaining_projected: '30',
  days_elapsed: 15,
  days_in_month: 30,
}

function mockFetch(responses: Array<{ ok?: boolean; status?: number; body?: unknown }>) {
  const fn = vi.fn()
  for (const r of responses) {
    fn.mockResolvedValueOnce({
      ok: r.ok ?? true,
      status: r.status ?? 200,
      json: async () => r.body,
    })
  }
  vi.stubGlobal('fetch', fn)
  return fn
}

/** Three fetches needed on every loadData call: listCategories, listBudgets, getBudgetStatus */
function loadResponses(
  cats: unknown[] = [],
  budgets: unknown[] = [],
  status: unknown[] = [],
) {
  return [{ body: cats }, { body: budgets }, { body: status }] as const
}

describe('BudgetPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    cleanup()
  })

  it('displays the current year-month on load', async () => {
    mockFetch([...loadResponses()])
    render(<BudgetPage />)
    expect(await screen.findByText(CURRENT_YM)).toBeInTheDocument()
  })

  it('shows empty-state form when no categories exist', async () => {
    mockFetch([...loadResponses([], [], [])])
    render(<BudgetPage />)
    expect(await screen.findByText(/no categories yet/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^slug$/i)).toBeInTheDocument()
  })

  it('renders the budget table with existing categories', async () => {
    mockFetch([...loadResponses([CAT], [BUDGET_ROW], [])])
    render(<BudgetPage />)
    expect(await screen.findByText('Groceries')).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /budgeted amount for groceries/i })).toHaveValue(300)
  })

  it('navigates to the previous month', async () => {
    mockFetch([...loadResponses(), ...loadResponses()])
    render(<BudgetPage />)
    await screen.findByText(CURRENT_YM)
    fireEvent.click(screen.getByRole('button', { name: /prev/i }))
    expect(await screen.findByText(PREV_YM)).toBeInTheDocument()
  })

  it('navigates to the next month', async () => {
    mockFetch([...loadResponses(), ...loadResponses()])
    render(<BudgetPage />)
    await screen.findByText(CURRENT_YM)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(await screen.findByText(NEXT_YM)).toBeInTheDocument()
  })

  it('populates amounts from suggest-from-history', async () => {
    mockFetch([
      ...loadResponses([CAT], [], []),
      {
        body: [
          {
            category_id: 'cat-1',
            slug: 'groceries',
            name: 'Groceries',
            suggested_amount: '450',
            history_total_spend: '1350',
            lookback_months: 3,
          },
        ],
      },
    ])
    render(<BudgetPage />)
    await screen.findByText('Groceries')
    fireEvent.click(screen.getByRole('button', { name: /suggest from history/i }))
    await waitFor(() => {
      expect(screen.getByRole('spinbutton', { name: /budgeted amount for groceries/i })).toHaveValue(450)
    })
  })

  it('shows a success message after saving budgets', async () => {
    mockFetch([
      ...loadResponses([CAT], [], []),
      { status: 204 }, // putBudgets (204 No Content)
      { body: [] },    // getBudgetStatus refresh
    ])
    render(<BudgetPage />)
    await screen.findByText('Groceries')
    fireEvent.click(screen.getByRole('button', { name: /save budgets/i }))
    expect(await screen.findByText(/budgets saved/i)).toBeInTheDocument()
  })

  it('shows the status table when status rows exist', async () => {
    mockFetch([...loadResponses([CAT], [], [STATUS_ROW])])
    render(<BudgetPage />)
    expect(await screen.findByRole('heading', { name: /budget vs actual/i })).toBeInTheDocument()
    const cells = await screen.findAllByText('150')
    expect(cells.length).toBeGreaterThan(0)
  })

  it('shows an empty-state message in the status section when no rows', async () => {
    mockFetch([...loadResponses([CAT], [], [])])
    render(<BudgetPage />)
    await screen.findByText('Groceries')
    expect(await screen.findByText(/no budget data yet for this month/i)).toBeInTheDocument()
  })

  it('creates a category without discarding existing budget edits', async () => {
    mockFetch([
      ...loadResponses([CAT], [BUDGET_ROW], []),
      // createCategory response
      { body: { id: 'cat-2', slug: 'rent', name: 'Rent' } },
      // listCategories refresh after creation
      { body: [CAT, { id: 'cat-2', slug: 'rent', name: 'Rent' }] },
    ])
    render(<BudgetPage />)
    await screen.findByText('Groceries')

    // Edit the Groceries amount
    const groceriesInput = screen.getByRole('spinbutton', { name: /budgeted amount for groceries/i })
    fireEvent.change(groceriesInput, { target: { value: '500' } })
    expect(groceriesInput).toHaveValue(500)

    // Open the "Add new category" details panel and fill the form
    fireEvent.click(screen.getByText(/add new category/i))
    const slugInput = screen.getByLabelText(/^slug$/i)
    const nameInput = screen.getByLabelText(/^name$/i)
    fireEvent.change(slugInput, { target: { value: 'rent' } })
    fireEvent.change(nameInput, { target: { value: 'Rent' } })
    fireEvent.click(screen.getByRole('button', { name: /create category/i }))

    // After creation, the Rent category appears and the Groceries edit is preserved
    expect(await screen.findByText('Rent')).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /budgeted amount for groceries/i })).toHaveValue(500)
  })
})
