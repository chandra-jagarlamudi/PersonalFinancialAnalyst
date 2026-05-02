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

export type BudgetRow = {
  category_id: string
  slug: string
  name: string
  amount: string
  currency: string
}

export type BudgetStatus = {
  category_id: string
  slug: string
  name: string
  budget_amount: string
  spent_mtd: string
  projected_spend: string
  remaining_mtd: string
  remaining_projected: string
  days_elapsed: number
  days_in_month: number
}

export type BudgetSuggestion = {
  category_id: string
  slug: string
  name: string
  suggested_amount: string
  history_total_spend: string
  lookback_months: number
}

export type CategoryCreate = { slug: string; name: string }

export function listCategories(): Promise<Category[]> {
  return request<Category[]>('/categories')
}

export function createCategory(body: CategoryCreate): Promise<Category> {
  return request<Category>('/categories', { method: 'POST', bodyJson: body })
}

export function listBudgets(yearMonth: string): Promise<BudgetRow[]> {
  return request<BudgetRow[]>(`/budgets/${yearMonth}`)
}

export function putBudgets(
  yearMonth: string,
  items: Array<{ category_id: string; amount: string }>,
): Promise<void> {
  return request<void>(`/budgets/${yearMonth}`, { method: 'PUT', bodyJson: { items } })
}

export function getBudgetStatus(yearMonth: string): Promise<BudgetStatus[]> {
  return request<BudgetStatus[]>(`/budgets/${yearMonth}/status`)
}

export function suggestBudgets(yearMonth: string, lookbackMonths?: number): Promise<BudgetSuggestion[]> {
  return request<BudgetSuggestion[]>(`/budgets/${yearMonth}/suggest`, {
    method: 'POST',
    bodyJson: lookbackMonths !== undefined ? { lookback_months: lookbackMonths } : {},
  })
}
