import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

function mockFetchSequence(
  responses: Array<{ ok?: boolean; status?: number; body?: unknown }>,
) {
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

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    cleanup()
  })

  it('shows the login form when no active session exists', async () => {
    mockFetchSequence([{ body: { authenticated: false, username: null } }])

    render(<App />)

    expect(
      await screen.findByRole('heading', {
        name: /sign in to personal financial analyst/i,
      }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
  })

  it('signs in and renders the authenticated shell', async () => {
    const fetchMock = mockFetchSequence([
      { body: { authenticated: false, username: null } },
      { body: { authenticated: true, username: 'admin' } },
      { body: [] },
      { body: [] },
      { body: [] },
    ])

    render(<App />)

    fireEvent.change(await screen.findByLabelText(/username/i), {
      target: { value: 'admin' },
    })
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'test-password' },
    })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(
      await screen.findByRole('heading', { name: /dashboard/i }),
    ).toBeInTheDocument()
    expect(await screen.findByText(/cashflow over time/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/auth/login',
        expect.objectContaining({
          credentials: 'include',
          method: 'POST',
        }),
      )
    })
  })

  it('loads the setup workflow for an authenticated session', async () => {
    mockFetchSequence([
      { body: { authenticated: true, username: 'admin' } },
      { body: [] },
      { body: [] },
      { body: [] },
      { body: [] },
      { body: [] },
      { body: [] },
      { body: [] },
      { body: [] },
    ])

    render(<App />)

    expect(
      await screen.findByRole('heading', { name: /dashboard/i }),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: /setup/i }))

    expect(
      await screen.findByRole('heading', { name: /ledger bootstrap workflows/i }),
    ).toBeInTheDocument()
  })
})
