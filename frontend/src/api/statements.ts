import { request } from './http'

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

export type AccountType = {
  id: string
  code: string
  label: string
  sort_order: number
}

export type Account = {
  id: string
  institution_id: string
  account_type_id: string
  account_type_label: string
  name: string
  currency: string
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

export function listAccountTypes(): Promise<AccountType[]> {
  return request<AccountType[]>('/account-types')
}

export function createInstitution(name: string): Promise<Institution> {
  return request<Institution>('/institutions', { method: 'POST', bodyJson: { name } })
}

export function createAccount(body: {
  institution_id: string
  account_type_id: string
  name: string
  currency?: string
}): Promise<Account> {
  return request<Account>('/accounts', { method: 'POST', bodyJson: body })
}
