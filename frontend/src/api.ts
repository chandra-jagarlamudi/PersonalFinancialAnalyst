export type SessionState = {
  authenticated: boolean
  username: string | null
}

export type Category = {
  id: string
  slug: string
  name: string
}

export type Statement = {
  id: string
  account_id: string
  filename: string
  sha256: string
  byte_size: number
  inserted: number
  skipped_duplicates: number
  created_at: string
}

export type Institution = {
  id: string
  name: string
}

export type Account = {
  id: string
  institution_id: string
  name: string
  currency: string
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

export function listStatements(accountId?: string): Promise<Statement[]> {
  const qs = accountId ? `?account_id=${accountId}` : ''
  return request<Statement[]>(`/statements${qs}`)
}

export function getStatement(id: string): Promise<Statement> {
  return request<Statement>(`/statements/${id}`)
}

export function purgeStatement(id: string): Promise<void> {
  return request<void>(`/statements/${id}`, { method: 'DELETE' })
}

export function listAccounts(): Promise<Account[]> {
  return request<Account[]>('/accounts')
}

export function listInstitutions(): Promise<Institution[]> {
  return request<Institution[]>('/institutions')
}
