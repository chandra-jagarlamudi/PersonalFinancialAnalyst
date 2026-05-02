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

export type Transaction = {
  id: string
  account_id: string
  transaction_date: string
  amount: string
  description_raw: string
  description_normalized: string
  category_id: string | null
  category_name: string | null
  created_at: string
}

export type Rule = {
  id: string
  category_id: string
  category_name: string
  pattern: string
  priority: number
}

export type RuleProposal = {
  proposed_rule: { pattern: string; apply_retroactively: boolean }
  would_affect_count: number
}

export function listTransactions(params?: {
  account_id?: string
  uncategorized?: boolean
  limit?: number
  offset?: number
}): Promise<Transaction[]> {
  const search = new URLSearchParams()
  if (params?.account_id) search.set('account_id', params.account_id)
  if (params?.uncategorized) search.set('uncategorized', 'true')
  if (params?.limit != null) search.set('limit', String(params.limit))
  if (params?.offset != null) search.set('offset', String(params.offset))
  const qs = search.toString()
  return request<Transaction[]>(`/transactions${qs ? `?${qs}` : ''}`)
}

export function updateTransactionCategory(txId: string, categoryId: string): Promise<void> {
  return request<void>(`/transactions/${txId}/category`, {
    method: 'PUT',
    bodyJson: { category_id: categoryId },
  })
}

export function proposeRule(
  txId: string,
  body: { pattern: string; apply_retroactively: boolean },
): Promise<RuleProposal> {
  return request<RuleProposal>(`/transactions/${txId}/rule-proposal`, {
    method: 'POST',
    bodyJson: body,
  })
}

export function createRule(body: {
  category_id: string
  pattern: string
  priority: number
  apply_retroactively: boolean
}): Promise<Rule> {
  return request<Rule>('/categorization/rules', { method: 'POST', bodyJson: body })
}

export function listRules(): Promise<Rule[]> {
  return request<Rule[]>('/categorization/rules')
}
