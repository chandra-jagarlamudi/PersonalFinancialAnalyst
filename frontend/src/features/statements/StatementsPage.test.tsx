import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import StatementsPage from './StatementsPage'

// Fetch mock order: GET /api/statements, then parallel GET /api/accounts, /api/institutions, /api/account-types
const ACCOUNT_TYPES = [
  { id: 'type-checking', code: 'checking', label: 'Checking', sort_order: 10 },
  { id: 'type-savings', code: 'savings', label: 'Savings', sort_order: 20 },
]
const INSTITUTION = { id: 'inst-1', name: 'First Bank' }
const ACCOUNT = {
  id: 'acct-1',
  institution_id: 'inst-1',
  account_type_id: 'type-checking',
  account_type_label: 'Checking',
  name: 'Checking',
  currency: 'USD',
}
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

const INGEST_JOB_CSV = {
  id: 'job-csv-1',
  job_type: 'csv-import',
  status: 'succeeded',
  account_id: 'acct-1',
  statement_id: 'stmt-new',
  filename: 'data.csv',
  byte_size: 48,
  parsed_rows: 1,
  inserted_rows: 1,
  skipped_duplicates: 0,
  error_detail: null,
  retry_count: 0,
  steps: [],
}

const INGEST_JOB_PDF = {
  id: 'job-pdf-1',
  job_type: 'pdf-import',
  status: 'needs_review',
  account_id: 'acct-1',
  statement_id: 'stmt-pdf-1',
  filename: 'stmt.pdf',
  byte_size: 64,
  parsed_rows: 0,
  inserted_rows: null,
  skipped_duplicates: null,
  error_detail: 'PDF_REVIEW_REQUIRED confidence=0.35 rows=0 notes=stub_parser_v0:no_rows',
  retry_count: 0,
  steps: [],
}

const STATEMENT_AFTER_CSV = {
  id: 'stmt-new',
  account_id: 'acct-1',
  filename: 'data.csv',
  sha256: 'aa11',
  byte_size: 48,
  inserted: 1,
  skipped_duplicates: 0,
  created_at: '2025-02-01T10:00:00',
}

const STATEMENT_AFTER_PDF = {
  id: 'stmt-pdf-1',
  account_id: 'acct-1',
  filename: 'stmt.pdf',
  sha256: 'bb22',
  byte_size: 64,
  inserted: 0,
  skipped_duplicates: 0,
  created_at: '2025-02-01T11:00:00',
}

describe('StatementsPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    cleanup()
  })

  it('shows loading state while fetching', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    render(<StatementsPage />)
    expect(screen.getByText(/loading statements/i)).toBeInTheDocument()
  })

  it('shows empty state when there are no statements', async () => {
    mockFetch([
      { body: [] },
      { body: [] },
      { body: [] },
      { body: ACCOUNT_TYPES },
    ])
    render(<StatementsPage />)
    expect(await screen.findByText(/add your first account/i)).toBeInTheDocument()
    expect(await screen.findByText(/no statements recorded yet/i)).toBeInTheDocument()
  })

  it('creates institution and account then enables import controls', async () => {
    const NEW_INST = { id: 'inst-new', name: 'My Bank' }
    const NEW_ACCT = {
      id: 'acct-new',
      institution_id: 'inst-new',
      account_type_id: 'type-checking',
      account_type_label: 'Checking',
      name: 'Checking',
      currency: 'USD',
    }
    const mock = mockFetch([
      { body: [] },
      { body: [] },
      { body: [] },
      { body: ACCOUNT_TYPES },
      { body: NEW_INST },
      { body: NEW_ACCT },
      { body: [] },
      { body: [NEW_ACCT] },
      { body: [NEW_INST] },
      { body: ACCOUNT_TYPES },
    ])
    render(<StatementsPage />)
    await screen.findByRole('heading', { name: /add your first account/i })

    fireEvent.change(screen.getByPlaceholderText(/first bank/i), {
      target: { value: 'My Bank' },
    })
    fireEvent.change(screen.getByPlaceholderText(/primary checking/i), {
      target: { value: 'Checking' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create and continue/i }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /add another account/i })).toBeInTheDocument()
    })

    const postUrls = mock.mock.calls.filter(args => args[1]?.method === 'POST').map(c => String(c[0]))
    expect(postUrls.some(u => u.includes('/api/institutions'))).toBe(true)
    expect(postUrls.some(u => u.includes('/api/accounts'))).toBe(true)

    const fileInput = screen.getByLabelText(/statement file for queued import/i)
    expect(fileInput).not.toBeDisabled()
  })

  it('shows add another account heading when accounts already exist', async () => {
    mockFetch([
      { body: [] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
      { body: ACCOUNT_TYPES },
    ])
    render(<StatementsPage />)
    expect(await screen.findByRole('heading', { name: /add another account/i })).toBeInTheDocument()
  })

  it('expands a statement row on click to show identifiers, and collapses on second click', async () => {
    mockFetch([
      { body: [STATEMENT] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
      { body: ACCOUNT_TYPES },
    ])
    render(<StatementsPage />)
    await screen.findByText('jan.csv')
    expect(screen.queryByText(STATEMENT.sha256)).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('jan.csv'))
    expect(screen.getByText(STATEMENT.sha256)).toBeInTheDocument()

    fireEvent.click(screen.getByText('jan.csv'))
    expect(screen.queryByText(STATEMENT.sha256)).not.toBeInTheDocument()
  })

  it('renders the statement list with institution and account name', async () => {
    mockFetch([
      { body: [STATEMENT] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
      { body: ACCOUNT_TYPES },
    ])
    render(<StatementsPage />)

    const table = await screen.findByRole('table')
    expect(within(table).getByText('First Bank — Checking (Checking)')).toBeInTheDocument()
    expect(screen.getByText('jan.csv')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /purge/i })).toBeInTheDocument()
  })

  it('shows only account name when institution is not found', async () => {
    mockFetch([
      { body: [STATEMENT] },
      { body: [ACCOUNT] },
      { body: [] },
      { body: ACCOUNT_TYPES },
    ])
    render(<StatementsPage />)
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Checking (Checking)')).toBeInTheDocument()
  })

  it('falls back to account_id when account is not in the accounts list', async () => {
    mockFetch([
      { body: [STATEMENT] },
      { body: [] },
      { body: [] },
      { body: ACCOUNT_TYPES },
    ])
    render(<StatementsPage />)
    expect(await screen.findByText('acct-1')).toBeInTheDocument()
  })

  it('shows inline confirmation when Purge is clicked', async () => {
    mockFetch([
      { body: [STATEMENT] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
      { body: ACCOUNT_TYPES },
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
      { body: ACCOUNT_TYPES },
    ])
    render(<StatementsPage />)

    fireEvent.click(await screen.findByRole('button', { name: /purge/i }))
    expect(screen.getByRole('button', { name: /yes, delete/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() => {
      expect(screen.queryByText(/are you sure/i)).not.toBeInTheDocument()
    })
    expect(screen.getByText('jan.csv')).toBeInTheDocument()
  })

  it('shows success banner and removes row after successful purge', async () => {
    mockFetch([
      { body: [STATEMENT] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
      { body: ACCOUNT_TYPES },
      { status: 204, body: undefined },
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
      { body: ACCOUNT_TYPES },
      { ok: false, status: 500, body: { detail: 'internal server error' } },
    ])
    render(<StatementsPage />)

    fireEvent.click(await screen.findByRole('button', { name: /purge/i }))
    fireEvent.click(screen.getByRole('button', { name: /yes, delete/i }))

    expect(await screen.findByText(/internal server error/i)).toBeInTheDocument()
    expect(screen.getByText('jan.csv')).toBeInTheDocument()
  })

  it('shows error banner when loading statements fails', async () => {
    const mock = vi.fn().mockRejectedValue(new Error('network failure'))
    vi.stubGlobal('fetch', mock)
    render(<StatementsPage />)
    expect(await screen.findByText(/network failure/i)).toBeInTheDocument()
    expect(screen.getByText(/network failure/i).closest('p')).toHaveClass('error-banner')
  })

  it('posts CSV to ingest job endpoint with FormData then reloads statements', async () => {
    const mock = mockFetch([
      { body: [] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
      { body: ACCOUNT_TYPES },
      { status: 202, body: INGEST_JOB_CSV },
      { body: INGEST_JOB_CSV },
      { body: [STATEMENT_AFTER_CSV] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
      { body: ACCOUNT_TYPES },
    ])
    render(<StatementsPage />)
    await screen.findByText(/queue imports/i)

    fireEvent.click(screen.getByRole('radio', { name: 'CSV' }))
    const fileInput = screen.getByLabelText(/statement file for queued import/i)
    const file = new File(['transaction_date,amount,description\n2025-03-01,-1.00,X\n'], 'data.csv', {
      type: 'text/csv',
    })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('data.csv')).toBeInTheDocument()
    })

    const postCall = mock.mock.calls.find(args => args[1]?.method === 'POST')
    expect(postCall).toBeDefined()
    expect(String(postCall![0])).toContain('/api/ingest/jobs/csv')
    expect(postCall![1]?.body).toBeInstanceOf(FormData)
    const fd = postCall![1]!.body as FormData
    expect(fd.get('account_id')).toBe('acct-1')
    expect(fd.get('file')).toBeInstanceOf(File)
    expect((fd.get('file') as File).name).toBe('data.csv')
  })

  it('posts PDF to ingest job endpoint with FormData then reloads statements', async () => {
    const mock = mockFetch([
      { body: [] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
      { body: ACCOUNT_TYPES },
      { status: 202, body: INGEST_JOB_PDF },
      { body: INGEST_JOB_PDF },
      { body: [STATEMENT_AFTER_PDF] },
      { body: [ACCOUNT] },
      { body: [INSTITUTION] },
      { body: ACCOUNT_TYPES },
    ])
    render(<StatementsPage />)
    await screen.findByText(/queue imports/i)

    const minimalPdf = new Uint8Array([
      0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x34, 0x0a, 0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a,
    ])
    const file = new File([minimalPdf], 'stmt.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByLabelText(/statement file for queued import/i), {
      target: { files: [file] },
    })

    await waitFor(() => {
      expect(screen.getByText('stmt.pdf')).toBeInTheDocument()
    })

    const postCall = mock.mock.calls.find(args => args[1]?.method === 'POST')
    expect(postCall).toBeDefined()
    expect(String(postCall![0])).toContain('/api/ingest/jobs/pdf')
    expect(postCall![1]?.body).toBeInstanceOf(FormData)
    const fd = postCall![1]!.body as FormData
    expect(fd.get('account_id')).toBe('acct-1')
    expect((fd.get('file') as File).name).toBe('stmt.pdf')
  })
})
