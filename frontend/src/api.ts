export type SessionState = {
  authenticated: boolean
  username: string | null
}

export type Category = {
  id: string
  slug: string
  name: string
}

type RequestOptions = Omit<RequestInit, 'credentials'> & {
  bodyJson?: unknown
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.bodyJson !== undefined) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    credentials: 'include',
    body: options.bodyJson === undefined ? options.body : JSON.stringify(options.bodyJson),
  })

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) {
        detail = payload.detail
      }
    } catch {
      // Ignore non-JSON error payloads.
    }
    throw new Error(detail)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export function getSession(): Promise<SessionState> {
  return request<SessionState>('/auth/session')
}

export function login(username: string, password: string): Promise<SessionState> {
  return request<SessionState>('/auth/login', {
    method: 'POST',
    bodyJson: { username, password },
  })
}

export function logout(): Promise<void> {
  return request<void>('/auth/logout', { method: 'POST' })
}

export function listCategories(): Promise<Category[]> {
  return request<Category[]>('/categories')
}

export type RecurringCharge = {
  merchant: string
  typical_amount: string
  occurrences: number
  first_seen: string
  last_seen: string
  monthly_dates: string[]
  category_id: string | null
}

export function listRecurring(params?: {
  account_id?: string
  min_occurrences?: number
}): Promise<RecurringCharge[]> {
  const query = new URLSearchParams()
  if (params?.account_id) query.set('account_id', params.account_id)
  if (params?.min_occurrences !== undefined)
    query.set('min_occurrences', String(params.min_occurrences))
  const qs = query.toString()
  return request<RecurringCharge[]>(`/recurring${qs ? `?${qs}` : ''}`)
}
