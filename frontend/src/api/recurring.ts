import { request } from './http'

export type SupportingTransaction = {
  id: string
  transaction_date: string
  amount: string
  description: string
}

export type RecurringCharge = {
  merchant: string
  typical_amount: string
  occurrences: number
  first_seen: string
  last_seen: string
  monthly_dates: string[]
  category_id: string | null
  cadence: string
  supporting_transactions: SupportingTransaction[]
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
