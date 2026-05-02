import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import {
  bootstrapDefaultCategories,
  createAccount,
  createAccountAlias,
  createCategory,
  createInstitution,
  listAccountAliases,
  listAccounts,
  listCategories,
  listInstitutions,
  updateAccount,
  updateCategory,
  updateInstitution,
  type Account,
  type AccountAlias,
  type Category,
  type Institution,
} from './api'

type SetupPageProps = {
  onCategoryCountChange: (count: number) => void
}

export function SetupPage({ onCategoryCountChange }: SetupPageProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [institutions, setInstitutions] = useState<Institution[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [aliases, setAliases] = useState<AccountAlias[]>([])
  const [categories, setCategories] = useState<Category[]>([])

  const [institutionName, setInstitutionName] = useState('')
  const [institutionEditId, setInstitutionEditId] = useState('')
  const [institutionEditName, setInstitutionEditName] = useState('')

  const [accountInstitutionId, setAccountInstitutionId] = useState('')
  const [accountName, setAccountName] = useState('')
  const [accountCurrency, setAccountCurrency] = useState('USD')
  const [accountEditId, setAccountEditId] = useState('')
  const [accountEditInstitutionId, setAccountEditInstitutionId] = useState('')
  const [accountEditName, setAccountEditName] = useState('')
  const [accountEditCurrency, setAccountEditCurrency] = useState('USD')

  const [aliasAccountId, setAliasAccountId] = useState('')
  const [aliasValue, setAliasValue] = useState('')

  const [categorySlug, setCategorySlug] = useState('')
  const [categoryName, setCategoryName] = useState('')
  const [categoryEditId, setCategoryEditId] = useState('')
  const [categoryEditSlug, setCategoryEditSlug] = useState('')
  const [categoryEditName, setCategoryEditName] = useState('')

  async function loadSnapshot() {
    const [nextInstitutions, nextAccounts, nextAliases, nextCategories] =
      await Promise.all([
        listInstitutions(),
        listAccounts(),
        listAccountAliases(),
        listCategories(),
      ])

    setInstitutions(nextInstitutions)
    setAccounts(nextAccounts)
    setAliases(nextAliases)
    setCategories(nextCategories)
    onCategoryCountChange(nextCategories.length)

    if ((!accountInstitutionId || !nextInstitutions.some((item) => item.id === accountInstitutionId)) && nextInstitutions[0]) {
      setAccountInstitutionId(nextInstitutions[0].id)
    }
    if ((!accountEditInstitutionId || !nextInstitutions.some((item) => item.id === accountEditInstitutionId)) && nextInstitutions[0]) {
      setAccountEditInstitutionId(nextInstitutions[0].id)
    }
    if ((!aliasAccountId || !nextAccounts.some((item) => item.id === aliasAccountId)) && nextAccounts[0]) {
      setAliasAccountId(nextAccounts[0].id)
    }
    if ((!institutionEditId || !nextInstitutions.some((item) => item.id === institutionEditId)) && nextInstitutions[0]) {
      setInstitutionEditId(nextInstitutions[0].id)
      setInstitutionEditName(nextInstitutions[0].name)
    }
    if ((!accountEditId || !nextAccounts.some((item) => item.id === accountEditId)) && nextAccounts[0]) {
      setAccountEditId(nextAccounts[0].id)
      setAccountEditInstitutionId(nextAccounts[0].institution_id)
      setAccountEditName(nextAccounts[0].name)
      setAccountEditCurrency(nextAccounts[0].currency)
    }
    if ((!categoryEditId || !nextCategories.some((item) => item.id === categoryEditId)) && nextCategories[0]) {
      setCategoryEditId(nextCategories[0].id)
      setCategoryEditSlug(nextCategories[0].slug)
      setCategoryEditName(nextCategories[0].name)
    }
  }

  async function refreshAll() {
    setLoading(true)
    setError(null)
    try {
      await loadSnapshot()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load setup data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        await loadSnapshot()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unable to load setup data')
      } finally {
        setLoading(false)
      }
    }

    void bootstrap()
    // Initial bootstrap only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function submitAndRefresh(action: () => Promise<unknown>, reset: () => void) {
    setError(null)
    try {
      await action()
      reset()
      await refreshAll()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    }
  }

  return (
    <section className="panel">
      <div className="setup-header">
        <div>
          <h2>Ledger bootstrap workflows</h2>
          <p>
            Set up institutions, accounts, aliases, and starter categories before
            ingestion and dashboards build on top of them.
          </p>
        </div>
        <button type="button" className="secondary-button" onClick={() => void refreshAll()}>
          Refresh
        </button>
      </div>

      {error ? <p className="error-banner">{error}</p> : null}
      {loading ? <p>Loading setup data…</p> : null}

      <div className="setup-grid">
        <section className="setup-section">
          <h3>Institutions</h3>
          <ul className="simple-list">
            {institutions.map((institution) => (
              <li key={institution.id}>{institution.name}</li>
            ))}
          </ul>
          <form
            className="stacked-form"
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault()
              void submitAndRefresh(
                () => createInstitution(institutionName),
                () => setInstitutionName(''),
              )
            }}
          >
            <label>
              New institution
              <input
                value={institutionName}
                onChange={(event) => setInstitutionName(event.target.value)}
              />
            </label>
            <button type="submit" disabled={!institutionName}>
              Add institution
            </button>
          </form>
          {institutions.length > 0 ? (
            <form
              className="stacked-form"
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault()
                void submitAndRefresh(
                  () => updateInstitution(institutionEditId, institutionEditName),
                  () => undefined,
                )
              }}
            >
              <label>
                Edit institution
                <select
                  value={institutionEditId}
                  onChange={(event) => {
                    const nextId = event.target.value
                    setInstitutionEditId(nextId)
                    const match = institutions.find((item) => item.id === nextId)
                    setInstitutionEditName(match?.name ?? '')
                  }}
                >
                  {institutions.map((institution) => (
                    <option key={institution.id} value={institution.id}>
                      {institution.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Updated name
                <input
                  value={institutionEditName}
                  onChange={(event) => setInstitutionEditName(event.target.value)}
                />
              </label>
              <button type="submit" disabled={!institutionEditName}>
                Save institution
              </button>
            </form>
          ) : null}
        </section>

        <section className="setup-section">
          <h3>Accounts</h3>
          <ul className="simple-list">
            {accounts.map((account) => (
              <li key={account.id}>
                {account.name} — {account.institution_name} ({account.currency})
              </li>
            ))}
          </ul>
          <form
            className="stacked-form"
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault()
              void submitAndRefresh(
                () => createAccount(accountInstitutionId, accountName, accountCurrency),
                () => {
                  setAccountName('')
                  setAccountCurrency('USD')
                },
              )
            }}
          >
            <label>
              Institution
              <select
                value={accountInstitutionId}
                onChange={(event) => setAccountInstitutionId(event.target.value)}
                disabled={institutions.length === 0}
              >
                {institutions.map((institution) => (
                  <option key={institution.id} value={institution.id}>
                    {institution.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Account name
              <input value={accountName} onChange={(event) => setAccountName(event.target.value)} />
            </label>
            <label>
              Currency
              <input
                value={accountCurrency}
                onChange={(event) => setAccountCurrency(event.target.value.toUpperCase())}
              />
            </label>
            <button type="submit" disabled={!accountInstitutionId || !accountName}>
              Add account
            </button>
          </form>
          {accounts.length > 0 ? (
            <form
              className="stacked-form"
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault()
                void submitAndRefresh(
                  () =>
                    updateAccount(
                      accountEditId,
                      accountEditInstitutionId,
                      accountEditName,
                      accountEditCurrency,
                    ),
                  () => undefined,
                )
              }}
            >
              <label>
                Edit account
                <select
                  value={accountEditId}
                  onChange={(event) => {
                    const nextId = event.target.value
                    setAccountEditId(nextId)
                    const match = accounts.find((item) => item.id === nextId)
                    setAccountEditInstitutionId(match?.institution_id ?? '')
                    setAccountEditName(match?.name ?? '')
                    setAccountEditCurrency(match?.currency ?? 'USD')
                  }}
                >
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Institution
                <select
                  value={accountEditInstitutionId}
                  onChange={(event) => setAccountEditInstitutionId(event.target.value)}
                >
                  {institutions.map((institution) => (
                    <option key={institution.id} value={institution.id}>
                      {institution.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Updated account name
                <input
                  value={accountEditName}
                  onChange={(event) => setAccountEditName(event.target.value)}
                />
              </label>
              <label>
                Currency
                <input
                  value={accountEditCurrency}
                  onChange={(event) => setAccountEditCurrency(event.target.value.toUpperCase())}
                />
              </label>
              <button type="submit" disabled={!accountEditName || !accountEditInstitutionId}>
                Save account
              </button>
            </form>
          ) : null}
        </section>

        <section className="setup-section">
          <h3>Account aliases</h3>
          <ul className="simple-list">
            {aliases.map((alias) => (
              <li key={alias.id}>
                {alias.alias} → {alias.account_name}
              </li>
            ))}
          </ul>
          <form
            className="stacked-form"
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault()
              void submitAndRefresh(
                () => createAccountAlias(aliasAccountId, aliasValue),
                () => setAliasValue(''),
              )
            }}
          >
            <label>
              Account
              <select
                value={aliasAccountId}
                onChange={(event) => setAliasAccountId(event.target.value)}
                disabled={accounts.length === 0}
              >
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Alias
              <input value={aliasValue} onChange={(event) => setAliasValue(event.target.value)} />
            </label>
            <button type="submit" disabled={!aliasAccountId || !aliasValue}>
              Add alias
            </button>
          </form>
        </section>

        <section className="setup-section">
          <h3>Categories</h3>
          <ul className="simple-list">
            {categories.map((category) => (
              <li key={category.id}>
                {category.name} <span className="muted-inline">({category.slug})</span>
              </li>
            ))}
          </ul>
          <form
            className="stacked-form"
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault()
              void submitAndRefresh(
                () => createCategory(categorySlug, categoryName),
                () => {
                  setCategorySlug('')
                  setCategoryName('')
                },
              )
            }}
          >
            <label>
              Category slug
              <input
                value={categorySlug}
                onChange={(event) => setCategorySlug(event.target.value)}
              />
            </label>
            <label>
              Category name
              <input
                value={categoryName}
                onChange={(event) => setCategoryName(event.target.value)}
              />
            </label>
            <button type="submit" disabled={!categorySlug || !categoryName}>
              Add category
            </button>
          </form>
          {categories.length > 0 ? (
            <form
              className="stacked-form"
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault()
                void submitAndRefresh(
                  () => updateCategory(categoryEditId, categoryEditSlug, categoryEditName),
                  () => undefined,
                )
              }}
            >
              <label>
                Edit category
                <select
                  value={categoryEditId}
                  onChange={(event) => {
                    const nextId = event.target.value
                    setCategoryEditId(nextId)
                    const match = categories.find((item) => item.id === nextId)
                    setCategoryEditSlug(match?.slug ?? '')
                    setCategoryEditName(match?.name ?? '')
                  }}
                >
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Updated slug
                <input
                  value={categoryEditSlug}
                  onChange={(event) => setCategoryEditSlug(event.target.value)}
                />
              </label>
              <label>
                Updated name
                <input
                  value={categoryEditName}
                  onChange={(event) => setCategoryEditName(event.target.value)}
                />
              </label>
              <button type="submit" disabled={!categoryEditSlug || !categoryEditName}>
                Save category
              </button>
            </form>
          ) : null}
          <button
            type="button"
            className="secondary-button"
            onClick={() => void submitAndRefresh(() => bootstrapDefaultCategories(), () => undefined)}
          >
            Load starter categories
          </button>
        </section>
      </div>
    </section>
  )
}
