import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import {
  createTransaction,
  listAccounts,
  listCategories,
  listTransactions,
  type Account,
  type Category,
  type Transaction,
} from './api'

type TransactionsPageProps = {
  onError: (message: string | null) => void
}

export function TransactionsPage({ onError }: TransactionsPageProps) {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)

  const [accountId, setAccountId] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const [transactionDate, setTransactionDate] = useState('')
  const [searchText, setSearchText] = useState('')

  async function refreshExplorer() {
    const [nextAccounts, nextCategories, nextTransactions] = await Promise.all([
      listAccounts(),
      listCategories(),
      listTransactions({ q: searchText || undefined, limit: 50 }),
    ])
    setAccounts(nextAccounts)
    setCategories(nextCategories)
    setTransactions(nextTransactions)
    if (!accountId && nextAccounts[0]) {
      setAccountId(nextAccounts[0].id)
    }
    if (!categoryId && nextCategories[0]) {
      setCategoryId(nextCategories[0].id)
    }
  }

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        await refreshExplorer()
        if (!cancelled) {
          onError(null)
        }
      } catch (error) {
        if (!cancelled) {
          onError(error instanceof Error ? error.message : 'Unable to load transactions')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
    // searchText is user-triggered through the filter form.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      await createTransaction({
        accountId,
        transactionDate,
        amount,
        currency: 'USD',
        description,
        categoryId: categoryId || undefined,
      })
      setDescription('')
      setAmount('')
      setTransactionDate('')
      await refreshExplorer()
      onError(null)
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to create transaction')
    }
  }

  async function handleFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setTransactions(await listTransactions({ q: searchText || undefined, limit: 50 }))
      onError(null)
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to filter transactions')
    }
  }

  return (
    <section className="panel">
      <h2>Transaction explorer</h2>
      <p>
        Enter sample transactions manually before async ingestion is ready, then
        filter and inspect them here.
      </p>

      <div className="setup-grid">
        <section className="setup-section">
          <h3>Add manual transaction</h3>
          {accounts.length === 0 ? (
            <p>Create an institution and account in Setup before adding transactions.</p>
          ) : (
            <form className="stacked-form" onSubmit={handleCreate}>
              <label>
                Account
                <select value={accountId} onChange={(event) => setAccountId(event.target.value)}>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Category
                <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
                  <option value="">Uncategorized</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Description
                <input
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </label>
              <label>
                Amount
                <input value={amount} onChange={(event) => setAmount(event.target.value)} />
              </label>
              <label>
                Transaction date
                <input
                  type="date"
                  value={transactionDate}
                  onChange={(event) => setTransactionDate(event.target.value)}
                />
              </label>
              <button type="submit" disabled={!accountId || !description || !amount || !transactionDate}>
                Save transaction
              </button>
            </form>
          )}
        </section>

        <section className="setup-section">
          <h3>Filter transactions</h3>
          <form className="stacked-form" onSubmit={handleFilter}>
            <label>
              Search description
              <input value={searchText} onChange={(event) => setSearchText(event.target.value)} />
            </label>
            <button type="submit">Apply filter</button>
          </form>
        </section>
      </div>

      {loading ? (
        <p>Loading transactions…</p>
      ) : transactions.length === 0 ? (
        <p>No transactions yet. Add one manually to seed the dashboard.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th>Account</th>
              <th>Category</th>
              <th>Amount</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((transaction) => (
              <tr key={transaction.id}>
                <td>{transaction.transaction_date}</td>
                <td>{transaction.description_raw}</td>
                <td>
                  {transaction.account_name}
                  <div className="muted-inline">{transaction.institution_name}</div>
                </td>
                <td>{transaction.category_name ?? 'Uncategorized'}</td>
                <td>{transaction.amount}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
