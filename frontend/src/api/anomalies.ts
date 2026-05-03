import { request } from './http'

export type AnomalySignal = {
  kind: string
  merchant: string
  detail: string
  transaction_id: string | null
  transaction_date: string
  amount: string | null
}

export function listAnomalies(accountId?: string): Promise<AnomalySignal[]> {
  const qs = accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''
  return request<AnomalySignal[]>(`/anomalies${qs}`)
}
