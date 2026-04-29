/**
 * T-072: Typed API client — all server calls go through this module.
 *
 * - credentials: 'include' on every request (session cookie sent automatically)
 * - X-CSRF-Token header attached from non-HttpOnly CSRF cookie on every POST
 * - 401 → redirect to /login
 * - Network error → toast notification
 */

const BASE = '/api'

// ── CSRF ─────────────────────────────────────────────────────────────────────

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : ''
}

// ── Toast (simple DOM-level notification) ────────────────────────────────────

function showNetworkErrorToast(message: string) {
  const el = document.createElement('div')
  el.textContent = message
  el.style.cssText =
    'position:fixed;bottom:16px;right:16px;background:#dc2626;color:#fff;padding:12px 16px;' +
    'border-radius:6px;z-index:9999;font-size:14px;max-width:300px;'
  document.body.appendChild(el)
  setTimeout(() => el.remove(), 5000)
}

// ── Core fetch wrapper ────────────────────────────────────────────────────────

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')

  if (init.method && init.method.toUpperCase() !== 'GET') {
    const token = getCsrfToken()
    if (token) headers.set('X-CSRF-Token', token)
  }

  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers,
      credentials: 'include',
    })
  } catch (err) {
    showNetworkErrorToast('Network error — check your connection.')
    throw err
  }

  if (response.status === 401) {
    window.location.href = '/login'
    throw new Error('Unauthenticated')
  }

  return response
}

async function apiFetchMultipart(path: string, body: FormData): Promise<Response> {
  // No Content-Type header — let browser set multipart boundary
  const headers: Record<string, string> = {}
  const token = getCsrfToken()
  if (token) headers['X-CSRF-Token'] = token

  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers,
      credentials: 'include',
      body,
    })
  } catch (err) {
    showNetworkErrorToast('Network error — check your connection.')
    throw err
  }

  if (response.status === 401) {
    window.location.href = '/login'
    throw new Error('Unauthenticated')
  }

  return response
}

// ── Auth endpoints ────────────────────────────────────────────────────────────

export async function getAuthStatus(): Promise<{ auth_enabled: boolean }> {
  const res = await apiFetch('/auth/status')
  return res.json()
}

export async function getAuthMe(): Promise<{ email: string }> {
  const res = await apiFetch('/auth/me')
  return res.json()
}

export async function postLogout(): Promise<void> {
  await apiFetch('/auth/logout', { method: 'POST' })
}

// ── Upload ────────────────────────────────────────────────────────────────────

export interface UploadResult {
  statement_id: string
  bank_detected: string
  transaction_count: number
  duplicates_skipped: number
  period_start: string | null
  period_end: string | null
}

export async function uploadStatement(file: File, bank?: string): Promise<Response> {
  const fd = new FormData()
  fd.append('file', file)
  if (bank) fd.append('bank', bank)
  return apiFetchMultipart('/upload', fd)
}

// ── Analytics tools ───────────────────────────────────────────────────────────

export async function summarizeMonth(
  month: string,
  includeCategories = true,
): Promise<{ result: string }> {
  const res = await apiFetch('/tools/summarize_month', {
    method: 'POST',
    body: JSON.stringify({ month, include_categories: includeCategories }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function findUnusualSpend(
  month: string,
  lookbackMonths = 3,
): Promise<{ result: string }> {
  const res = await apiFetch('/tools/find_unusual_spend', {
    method: 'POST',
    body: JSON.stringify({ month, lookback_months: lookbackMonths }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function listRecurringSubscriptions(
  lookbackMonths = 6,
): Promise<{ result: string }> {
  const res = await apiFetch('/tools/list_recurring_subscriptions', {
    method: 'POST',
    body: JSON.stringify({ lookback_months: lookbackMonths }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ── Transactions ──────────────────────────────────────────────────────────────

export interface Transaction {
  id: string
  date: string
  description: string
  merchant: string
  amount: string
  transaction_type: 'debit' | 'credit'
  category: string | null
  source_bank: string
}

export interface TransactionsPage {
  transactions: Transaction[]
  total: number
  page: number
  page_size: number
  pages: number
}

export async function getTransactions(params: {
  start_date: string
  end_date: string
  bank?: string[]
  category?: string[]
  transaction_type?: string
  page?: number
}): Promise<TransactionsPage> {
  const q = new URLSearchParams()
  q.set('start_date', params.start_date)
  q.set('end_date', params.end_date)
  if (params.bank) params.bank.forEach((b) => q.append('bank', b))
  if (params.category) params.category.forEach((c) => q.append('category', c))
  if (params.transaction_type) q.set('transaction_type', params.transaction_type)
  if (params.page) q.set('page', String(params.page))
  const res = await apiFetch(`/transactions?${q}`)
  return res.json()
}

// ── Chat streaming ────────────────────────────────────────────────────────────

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export function streamChat(
  question: string,
  history: ChatMessage[],
  contextMonths = 3,
  onToken: (text: string) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController()

  const token = getCsrfToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['X-CSRF-Token'] = token

  fetch(`${BASE}/chat`, {
    method: 'POST',
    headers,
    credentials: 'include',
    signal: controller.signal,
    body: JSON.stringify({ question, history, context_months: contextMonths }),
  })
    .then(async (res) => {
      if (!res.ok || !res.body) {
        onError(new Error(`Chat error: ${res.status}`))
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6)
          if (payload === '[DONE]') { onDone(); return }
          try {
            const parsed = JSON.parse(payload)
            if (parsed.text) onToken(parsed.text)
          } catch {}
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError(err)
    })

  return controller
}
