export type SessionState = {
  authenticated: boolean
  username: string | null
}

export type Category = {
  id: string
  slug: string
  name: string
}

export type Institution = {
  id: string
  name: string
}

export type Account = {
  id: string
  institution_id: string
  institution_name: string
  name: string
  currency: string
}

export type AccountAlias = {
  id: string
  account_id: string
  account_name: string
  alias: string
}

export type DashboardCashflowPoint = {
  month: string
  income_total: string
  expense_total_abs: string
  net_total: string
}

export type DashboardCategorySpendPoint = {
  month: string
  category_id: string | null
  category_name: string
  spend_total: string
}

export type Transaction = {
  id: string
  account_id: string
  account_name: string
  institution_name: string
  transaction_date: string
  posted_date: string | null
  amount: string
  currency: string
  description_raw: string
  category_id: string | null
  category_name: string | null
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

export function createCategory(slug: string, name: string): Promise<Category> {
  return request<Category>('/categories', {
    method: 'POST',
    bodyJson: { slug, name },
  })
}

export function updateCategory(id: string, slug: string, name: string): Promise<void> {
  return request<void>(`/categories/${id}`, {
    method: 'PUT',
    bodyJson: { slug, name },
  })
}

export function bootstrapDefaultCategories(): Promise<Category[]> {
  return request<Category[]>('/categories/bootstrap-defaults', {
    method: 'POST',
  })
}

export function listInstitutions(): Promise<Institution[]> {
  return request<Institution[]>('/institutions')
}

export function createInstitution(name: string): Promise<Institution> {
  return request<Institution>('/institutions', {
    method: 'POST',
    bodyJson: { name },
  })
}

export function updateInstitution(id: string, name: string): Promise<void> {
  return request<void>(`/institutions/${id}`, {
    method: 'PUT',
    bodyJson: { name },
  })
}

export function listAccounts(): Promise<Account[]> {
  return request<Account[]>('/accounts')
}

export function createAccount(
  institutionId: string,
  name: string,
  currency: string,
): Promise<Account> {
  return request<Account>('/accounts', {
    method: 'POST',
    bodyJson: { institution_id: institutionId, name, currency },
  })
}

export function updateAccount(
  id: string,
  institutionId: string,
  name: string,
  currency: string,
): Promise<void> {
  return request<void>(`/accounts/${id}`, {
    method: 'PUT',
    bodyJson: { institution_id: institutionId, name, currency },
  })
}

export function listAccountAliases(): Promise<AccountAlias[]> {
  return request<AccountAlias[]>('/account-aliases')
}

export function createAccountAlias(accountId: string, alias: string): Promise<AccountAlias> {
  return request<AccountAlias>('/account-aliases', {
    method: 'POST',
    bodyJson: { account_id: accountId, alias },
  })
}

export function listCashflow(months = 6): Promise<DashboardCashflowPoint[]> {
  return request<DashboardCashflowPoint[]>(`/dashboard/cashflow?months=${months}`)
}

export function listCategorySpend(months = 6): Promise<DashboardCategorySpendPoint[]> {
  return request<DashboardCategorySpendPoint[]>(
    `/dashboard/category-spend?months=${months}`,
  )
}

export function listTransactions(params?: {
  accountId?: string
  categoryId?: string
  q?: string
  startDate?: string
  endDate?: string
  limit?: number
}): Promise<Transaction[]> {
  const search = new URLSearchParams()
  if (params?.accountId) {
    search.set('account_id', params.accountId)
  }
  if (params?.categoryId) {
    search.set('category_id', params.categoryId)
  }
  if (params?.q) {
    search.set('q', params.q)
  }
  if (params?.startDate) {
    search.set('start_date', params.startDate)
  }
  if (params?.endDate) {
    search.set('end_date', params.endDate)
  }
  if (params?.limit) {
    search.set('limit', String(params.limit))
  }
  const suffix = search.toString()
  return request<Transaction[]>(`/transactions${suffix ? `?${suffix}` : ''}`)
}

export function createTransaction(body: {
  accountId: string
  transactionDate: string
  postedDate?: string
  amount: string
  currency: string
  description: string
  categoryId?: string
}): Promise<Transaction> {
  return request<Transaction>('/transactions', {
    method: 'POST',
    bodyJson: {
      account_id: body.accountId,
      transaction_date: body.transactionDate,
      posted_date: body.postedDate || null,
      amount: body.amount,
      currency: body.currency,
      description: body.description,
      category_id: body.categoryId || null,
    },
  })
}
