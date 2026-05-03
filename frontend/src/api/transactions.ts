import { request } from './http'

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

export type TransactionSort =
  | 'date_desc'
  | 'date_asc'
  | 'amount_desc'
  | 'amount_asc'
  | 'description_asc'
  | 'description_desc'
  | 'category_asc'
  | 'category_desc'

export type TransactionListResponse = {
  items: Transaction[]
  total: number
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

export type TransactionDetail = {
  id: string
  account_id: string
  transaction_date: string
  posted_date: string | null
  amount: string
  currency: string
  description_raw: string
  description_normalized: string
  category_id: string | null
  category_slug: string | null
  category_name: string | null
}

export function listTransactions(params?: {
  account_id?: string
  uncategorized?: boolean
  limit?: number
  offset?: number
  q?: string
  sort?: TransactionSort
}): Promise<TransactionListResponse> {
  const search = new URLSearchParams()
  if (params?.account_id) search.set('account_id', params.account_id)
  if (params?.uncategorized) search.set('uncategorized', 'true')
  if (params?.limit != null) search.set('limit', String(params.limit))
  if (params?.offset != null) search.set('offset', String(params.offset))
  if (params?.q != null && params.q.trim() !== '') search.set('q', params.q.trim())
  if (params?.sort) search.set('sort', params.sort)
  const qs = search.toString()
  return request<TransactionListResponse>(`/transactions${qs ? `?${qs}` : ''}`)
}

export type CategorySuggestion = {
  category_id: string | null
  slug: string | null
  error: string | null
}

export function suggestTransactionCategory(txId: string): Promise<CategorySuggestion> {
  return request<CategorySuggestion>(`/transactions/${txId}/suggest-category`, {
    method: 'POST',
  })
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

export function getTransaction(id: string): Promise<TransactionDetail> {
  return request<TransactionDetail>(`/transactions/${id}`)
}
