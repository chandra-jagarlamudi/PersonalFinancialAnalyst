import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RecurringPage } from './RecurringPage'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const CHARGE = {
  merchant: 'netflix',
  typical_amount: '-9.9900',
  occurrences: 3,
  first_seen: '2025-01-01',
  last_seen: '2025-03-01',
  monthly_dates: ['2025-01-01', '2025-02-01', '2025-03-01'],
  category_id: null,
  cadence: 'monthly',
  supporting_transactions: [
    { id: 'tx-1', transaction_date: '2025-01-01', amount: '-9.9900', description: 'NETFLIX' },
    { id: 'tx-2', transaction_date: '2025-02-01', amount: '-9.9900', description: 'NETFLIX' },
    { id: 'tx-3', transaction_date: '2025-03-01', amount: '-9.9900', description: 'NETFLIX' },
  ],
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type MockResponse = { ok?: boolean; status?: number; body?: unknown }

function mockFetch(responses: MockResponse[]) {
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RecurringPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    cleanup()
  })

  it('shows a loading indicator while charges are being fetched', () => {
    vi.stubGlobal('fetch', () => new Promise(() => {}))
    render(<RecurringPage />)
    expect(screen.getByText(/loading recurring charges/i)).toBeInTheDocument()
  })

  it('renders a recurring charge row with merchant, amount, and cadence', async () => {
    mockFetch([{ body: [CHARGE] }])
    render(<RecurringPage />)
    expect(await screen.findByText('netflix')).toBeInTheDocument()
    expect(screen.getByText('$9.99')).toBeInTheDocument()
    expect(screen.getByText('monthly')).toBeInTheDocument()
    expect(screen.getByText('3 months')).toBeInTheDocument()
  })

  it('shows empty state when no charges are returned', async () => {
    mockFetch([{ body: [] }])
    render(<RecurringPage />)
    expect(
      await screen.findByText(/no recurring charges detected/i),
    ).toBeInTheDocument()
  })

  it('shows error banner on fetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
    render(<RecurringPage />)
    expect(await screen.findByText(/network error/i)).toBeInTheDocument()
  })

  it('expands supporting transactions on button click', async () => {
    mockFetch([{ body: [CHARGE] }])
    render(<RecurringPage />)
    const toggle = await screen.findByRole('button', { name: /show transactions/i })
    fireEvent.click(toggle)
    expect(screen.getAllByText('NETFLIX')).toHaveLength(3)
    expect(
      screen.getByRole('button', { name: /hide transactions/i }),
    ).toBeInTheDocument()
  })
})
