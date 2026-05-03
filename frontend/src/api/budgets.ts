import { request } from './http'

export type Category = {
  id: string
  slug: string
  name: string
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
