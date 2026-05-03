import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import TransactionsPage from './TransactionsPage'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TX_1 = {
  id: 'tx-1',
  account_id: 'acc-1',
  transaction_date: '2024-01-15',
  amount: '-42.50',
  description_raw: 'STARBUCKS #1234',
  description_normalized: 'starbucks',
  category_id: null as string | null,
  category_name: null as string | null,
  account_name: 'Checking' as string | null,
  created_at: '2024-01-15T10:00:00Z',
}

const CAT_1 = { id: 'cat-1', slug: 'food', name: 'Food & Drink' }

const TX_EMPTY_PAGE = { items: [] as typeof TX_1[], total: 0 }
const TX_ONE_PAGE = { items: [TX_1], total: 1 }

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type MockResponse = { ok?: boolean; status?: number; body?: unknown }

function mockFetchSequence(responses: MockResponse[]) {
  const fetchMock = vi.fn()
  for (const item of responses) {
    fetchMock.mockResolvedValueOnce({
      ok: item.ok ?? true,
      status: item.status ?? 200,
      json: async () => item.body,
    })
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TransactionsPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    cleanup()
  })

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it('shows a loading indicator while transactions are being fetched', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn()
        .mockReturnValueOnce(new Promise(() => { /* never resolves */ }))
        .mockResolvedValueOnce({ ok: true, status: 200, json: async () => [] }),
    )

    render(<TransactionsPage />)

    expect(await screen.findByText(/loading transactions/i)).toBeInTheDocument()
  })

  // -------------------------------------------------------------------------
  // Renders data
  // -------------------------------------------------------------------------

  it('renders a row for each transaction', async () => {
    mockFetchSequence([{ body: TX_ONE_PAGE }, { body: [CAT_1] }])

    render(<TransactionsPage />)

    expect(await screen.findByText(TX_1.description_normalized)).toBeInTheDocument()
    expect(screen.getByText(TX_1.transaction_date)).toBeInTheDocument()
  })

  it('shows "No transactions found." when the list is empty', async () => {
    mockFetchSequence([{ body: TX_EMPTY_PAGE }, { body: [] }])

    render(<TransactionsPage />)

    expect(await screen.findByText('No transactions found.')).toBeInTheDocument()
  })

  // -------------------------------------------------------------------------
  // Filter toggle
  // -------------------------------------------------------------------------

  it('re-fetches with uncategorized=true when the filter is toggled', async () => {
    const fetchMock = mockFetchSequence([
      { body: TX_ONE_PAGE },
      { body: [CAT_1] },
      { body: TX_EMPTY_PAGE },
    ])

    render(<TransactionsPage />)
    await screen.findByText(TX_1.description_normalized)

    fireEvent.click(screen.getByRole('checkbox', { name: /show only uncategorized/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(3)
    })
    const thirdUrl = fetchMock.mock.calls[2][0] as string
    expect(thirdUrl).toContain('uncategorized=true')
  })

  // -------------------------------------------------------------------------
  // Category error + retry
  // -------------------------------------------------------------------------

  it('shows a category-load error and a Retry button when /categories fails', async () => {
    mockFetchSequence([
      { body: TX_ONE_PAGE },
      { ok: false, status: 500, body: { detail: 'db error' } },
    ])

    render(<TransactionsPage />)

    // Expand the row to see the correction UI
    fireEvent.click(await screen.findByText(TX_1.description_normalized))

    expect(await screen.findByText(/Could not load categories/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('clicking Retry re-fetches categories and shows the dropdown', async () => {
    mockFetchSequence([
      { body: TX_ONE_PAGE },
      { ok: false, status: 500, body: { detail: 'db error' } },
      { body: [CAT_1] },
    ])

    render(<TransactionsPage />)
    fireEvent.click(await screen.findByText(TX_1.description_normalized))

    const retryBtn = await screen.findByRole('button', { name: 'Retry' })
    fireEvent.click(retryBtn)

    expect(await screen.findByLabelText('Category:')).toBeInTheDocument()
  })

  // -------------------------------------------------------------------------
  // Row expansion – click and keyboard
  // -------------------------------------------------------------------------

  it('expands the correction UI when a row is clicked', async () => {
    mockFetchSequence([{ body: TX_ONE_PAGE }, { body: [CAT_1] }])

    render(<TransactionsPage />)
    fireEvent.click(await screen.findByText(TX_1.description_normalized))

    expect(await screen.findByLabelText('Category:')).toBeInTheDocument()
  })

  it('expands the correction UI when Enter is pressed on a row', async () => {
    mockFetchSequence([{ body: TX_ONE_PAGE }, { body: [CAT_1] }])

    render(<TransactionsPage />)
    await screen.findByText(TX_1.description_normalized)

    // rows[0] = header, rows[1] = first data row
    const rows = screen.getAllByRole('row')
    fireEvent.keyDown(rows[1], { key: 'Enter' })

    expect(await screen.findByLabelText('Category:')).toBeInTheDocument()
  })

  it('expands the correction UI when Space is pressed on a row', async () => {
    mockFetchSequence([{ body: TX_ONE_PAGE }, { body: [CAT_1] }])

    render(<TransactionsPage />)
    await screen.findByText(TX_1.description_normalized)

    const rows = screen.getAllByRole('row')
    fireEvent.keyDown(rows[1], { key: ' ' })

    expect(await screen.findByLabelText('Category:')).toBeInTheDocument()
  })

  // -------------------------------------------------------------------------
  // Category correction
  // -------------------------------------------------------------------------

  it('saves a category correction and transitions to the rule-proposal phase', async () => {
    mockFetchSequence([
      { body: TX_ONE_PAGE },
      { body: [CAT_1] },
      { body: { id: TX_1.id, category_id: CAT_1.id } }, // PUT /category
    ])

    render(<TransactionsPage />)
    fireEvent.click(await screen.findByText(TX_1.description_normalized))

    const select = await screen.findByLabelText('Category:')
    fireEvent.change(select, { target: { value: CAT_1.id } })
    fireEvent.click(screen.getByRole('button', { name: 'Save correction' }))

    expect(await screen.findByText('Category saved.')).toBeInTheDocument()
    expect(await screen.findByText('Propose a rule?')).toBeInTheDocument()
    expect(screen.getByLabelText('Pattern:')).toBeInTheDocument()
  })

  // -------------------------------------------------------------------------
  // Rule preview
  // -------------------------------------------------------------------------

  it('previews a rule and shows the affected-transaction count', async () => {
    const PROPOSAL = {
      proposed_rule: { pattern: TX_1.description_normalized, apply_retroactively: false },
      would_affect_count: 5,
    }

    mockFetchSequence([
      { body: TX_ONE_PAGE },
      { body: [CAT_1] },
      { body: { id: TX_1.id, category_id: CAT_1.id } },
      { body: PROPOSAL },
    ])

    render(<TransactionsPage />)
    fireEvent.click(await screen.findByText(TX_1.description_normalized))
    fireEvent.change(await screen.findByLabelText('Category:'), { target: { value: CAT_1.id } })
    fireEvent.click(screen.getByRole('button', { name: 'Save correction' }))
    await screen.findByText('Propose a rule?')

    fireEvent.click(screen.getByRole('button', { name: 'Preview rule' }))

    expect(await screen.findByText(/Would affect 5 transaction/)).toBeInTheDocument()
  })

  // -------------------------------------------------------------------------
  // Create rule (non-retroactive)
  // -------------------------------------------------------------------------

  it('creates a non-retroactive rule without requiring a preview', async () => {
    const RULE = {
      id: 'rule-1',
      category_id: CAT_1.id,
      category_name: CAT_1.name,
      pattern: TX_1.description_normalized,
      priority: 100,
    }

    const fetchMock = mockFetchSequence([
      { body: TX_ONE_PAGE },
      { body: [CAT_1] },
      { body: { id: TX_1.id, category_id: CAT_1.id } },
      { body: RULE },
    ])

    render(<TransactionsPage />)
    fireEvent.click(await screen.findByText(TX_1.description_normalized))
    fireEvent.change(await screen.findByLabelText('Category:'), { target: { value: CAT_1.id } })
    fireEvent.click(screen.getByRole('button', { name: 'Save correction' }))
    await screen.findByText('Propose a rule?')

    // Create rule without preview (no retroactive checked)
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }))

    // Row collapses on success
    await waitFor(() => {
      expect(screen.queryByText('Propose a rule?')).not.toBeInTheDocument()
    })

    // POST to /categorization/rules was made
    const urls = fetchMock.mock.calls.map(([url]) => url as string)
    expect(urls.some((u) => u.includes('/categorization/rules'))).toBe(true)
  })

  // -------------------------------------------------------------------------
  // Retroactive rule creation triggers table refresh
  // -------------------------------------------------------------------------

  it('re-fetches all transactions after a retroactive rule is created', async () => {
    const PROPOSAL = {
      proposed_rule: { pattern: TX_1.description_normalized, apply_retroactively: true },
      would_affect_count: 2,
    }
    const RULE = {
      id: 'rule-1',
      category_id: CAT_1.id,
      category_name: CAT_1.name,
      pattern: TX_1.description_normalized,
      priority: 100,
    }

    const fetchMock = mockFetchSequence([
      { body: TX_ONE_PAGE },                                        // initial tx fetch
      { body: [CAT_1] },                                       // categories
      { body: { id: TX_1.id, category_id: CAT_1.id } },       // PUT category
      { body: PROPOSAL },                                      // POST rule-proposal
      { body: RULE },                                          // POST create rule
      { body: TX_EMPTY_PAGE },
    ])

    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)

    render(<TransactionsPage />)

    // Save correction
    fireEvent.click(await screen.findByText(TX_1.description_normalized))
    fireEvent.change(await screen.findByLabelText('Category:'), { target: { value: CAT_1.id } })
    fireEvent.click(screen.getByRole('button', { name: 'Save correction' }))
    await screen.findByText('Propose a rule?')

    // Enable retroactive
    fireEvent.click(screen.getByRole('checkbox', { name: /apply retroactively/i }))

    // Preview
    fireEvent.click(screen.getByRole('button', { name: 'Preview rule' }))
    await screen.findByText(/Would affect 2 transaction/)

    // Create rule (confirm dialog auto-accepts via spy)
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }))

    // A 6th fetch must occur (the table re-fetch)
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(6)
    })

    const urls = fetchMock.mock.calls.map(([url]) => url as string)
    expect(urls[5]).toContain('/api/transactions')
  })
})
