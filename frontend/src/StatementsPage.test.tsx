import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import StatementsPage from './StatementsPage'

// Fetch mock order: GET /api/statements, GET /api/accounts, GET /api/institutions
const INSTITUTION = { id: 'inst-1', name: 'First Bank' }
const ACCOUNT = { id: 'acct-1', institution_id: 'inst-1', name: 'Checking', currency: 'USD' }
const STATEMENT = {
  id: 'stmt-1',
  account_id: 'acct-1',
  filename: 'jan.csv',
  sha256: 'abc123',
  byte_size: 2048,
  inserted: 3,
  skipped_duplicates: 1,
  created_at: '2025-01-15T10:00:00',
}

function mockFetch(responses: Array<{ ok?: boolean; status?: number; body?: unknown }>) {
  const mock = vi.fn()
  for (const r of responses) {
    mock.mockResolvedValueOnce({
      ok: r.ok ?? true,
      status: r.status ?? 200,
      json: async () => r.body,
    })
  }
  vi.stubGlobal('fetch', mock)
  return mock
}

describe('StatementsPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    cleanup()
  })

  it('shows loading state while fetching', async () => {
    // Never resolves so the loading indicator stays visible.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    render(<StatementsPage />)
    expect(screen.getByText(/loading statements/i)).toBeInTheDocument()
  })

  it('shows empty state when there are no statements', async () => {
    mockFetch([
      { body: [] }, // listStatements
      { body: [] }, // listAccounts
      { body: [] }, // listInstitutions
    ])
    render(<StatementsPage />)
    expect(await screen.findByText(/no statements recorded yet/i)).toBeInTheDocument()
  })

  it('renders the statement list with institution and account name', async () => {
    mockFetch([
      { body: [STATEMENT] },    // listStatements
      { body: [ACCOUNT] },      // listAccounts
      { body: [INSTITUTION] },  // listInstitutions
    ])
    render(<StatementsPage />)

    const table = await screen.findByRole('table')
    expect(within(table).getByText('First Bank — Checking')).toBeInTheDocument()
    // Filename appears.
    expect(screen.getByText('jan.csv')).toBeInTheDocument()
    // Inserted / skipped counts.
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    // Purge button is visible.
    expect(screen.getByRole('button', { name: /purge/i })).toBeInTheDocument()
  })

  it('shows only account name when institution is not found', async () => {
    mockFetch([
      { body: [STATEMENT] },
      { body: [ACCOUNT] },
      { body: [] }, // no institutions
    ])
    render(<StatementsPage />)
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Checking')).toBeInTheDocument()
  })

  it('falls back to account_id when account is not in the accounts list', async () => {
    mockFetch([
      { body: [STATEMENT] },
      { body: [] }, // listAccounts — empty
      { body: [] }, // listInstitutions
    ])
    render(<StatementsPage />)
    expect(await screen.findByText('acct-1')).toBeInTheDocument()
  })

  it('shows inline confirmation when Purge is clicked', async () => {
    mockFetch([
      { body: [STATEMENT] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
    ])
    render(<StatementsPage />)

    fireEvent.click(await screen.findByRole('button', { name: /purge/i }))

    expect(screen.getByText(/are you sure/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /yes, delete/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })

  it('cancel dismisses the confirmation without deleting', async () => {
    mockFetch([
      { body: [STATEMENT] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
    ])
    render(<StatementsPage />)

    fireEvent.click(await screen.findByRole('button', { name: /purge/i }))
    expect(screen.getByRole('button', { name: /yes, delete/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() => {
      expect(screen.queryByText(/are you sure/i)).not.toBeInTheDocument()
    })
    // Row should still be present.
    expect(screen.getByText('jan.csv')).toBeInTheDocument()
  })

  it('shows success banner and removes row after successful purge', async () => {
    mockFetch([
      { body: [STATEMENT] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
      { status: 204, body: undefined }, // DELETE
    ])
    render(<StatementsPage />)

    fireEvent.click(await screen.findByRole('button', { name: /purge/i }))
    fireEvent.click(screen.getByRole('button', { name: /yes, delete/i }))

    expect(await screen.findByText(/statement removed from the app/i)).toBeInTheDocument()
    expect(screen.queryByText('jan.csv')).not.toBeInTheDocument()
  })

  it('shows error banner when purge fails', async () => {
    mockFetch([
      { body: [STATEMENT] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
      { ok: false, status: 500, body: { detail: 'internal server error' } }, // DELETE
    ])
    render(<StatementsPage />)

    fireEvent.click(await screen.findByRole('button', { name: /purge/i }))
    fireEvent.click(screen.getByRole('button', { name: /yes, delete/i }))

    expect(await screen.findByText(/internal server error/i)).toBeInTheDocument()
    // Row should still be present.
    expect(screen.getByText('jan.csv')).toBeInTheDocument()
  })

  it('shows error banner when loading statements fails', async () => {
    const mock = vi.fn().mockRejectedValue(new Error('network failure'))
    vi.stubGlobal('fetch', mock)
    render(<StatementsPage />)
    // The banner renders the Error's message directly; the 'Failed to load statements'
    // fallback only fires for non-Error throws.
    expect(await screen.findByText(/network failure/i)).toBeInTheDocument()
    expect(screen.getByText(/network failure/i).closest('p')).toHaveClass('error-banner')
  })
})

