import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom'
import { getSession, listCategories, login, logout, type SessionState } from './api'
import { DashboardPage } from './DashboardPage'
import { SetupPage } from './SetupPage'
import { TransactionsPage } from './TransactionsPage'
import './App.css'

type ProtectedState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; categoryCount: number }
  | { status: 'error'; message: string }

function LoginForm({
  onLogin,
  loading,
}: {
  onLogin: (username: string, password: string) => Promise<void>
  loading: boolean
}) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    try {
      await onLogin(username, password)
      setPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in')
    }
  }

  return (
    <section className="auth-card">
      <div className="eyebrow">Slice 1 MVP shell</div>
      <h1>Sign in to Personal Financial Analyst</h1>
      <p className="intro">
        Start the backend on <code>127.0.0.1:8000</code>, then sign in with the
        single-user credentials from <code>.env</code>.
      </p>
      <form className="login-form" onSubmit={handleSubmit}>
        <label>
          Username
          <input
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </label>
        <label>
          Password
          <input
            autoComplete="current-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <p className="error-banner">{error}</p> : null}
        <button type="submit" disabled={loading || !username || !password}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </section>
  )
}

function Overview({ username }: { username: string }) {
  return (
    <section className="panel">
      <h2>Welcome back, {username}</h2>
      <p>The dashboard and transaction explorer are now available in the app shell.</p>
    </section>
  )
}

function SmokePage({ protectedState }: { protectedState: ProtectedState }) {
  return (
    <section className="panel">
      <h2>Protected API smoke check</h2>
      <p>
        The shell calls <code>GET /categories</code> through the session cookie to
        confirm protected API access from the browser.
      </p>
      {protectedState.status === 'ready' ? (
        <p className="success-banner">
          Protected API is reachable. Category count: {protectedState.categoryCount}
        </p>
      ) : protectedState.status === 'loading' ? (
        <p>Loading protected API data…</p>
      ) : protectedState.status === 'error' ? (
        <p className="error-banner">{protectedState.message}</p>
      ) : (
        <p>Waiting for authentication.</p>
      )}
    </section>
  )
}

function Shell({
  session,
  protectedState,
  onLogout,
  onCategoryCountChange,
}: {
  session: SessionState
  protectedState: ProtectedState
  onLogout: () => Promise<void>
  onCategoryCountChange: (count: number) => void
}) {
  const username = session.username ?? 'admin'

  return (
    <div className="app-shell">
      <header className="shell-header">
        <div>
          <div className="eyebrow">Personal Financial Analyst</div>
          <h1>Authenticated app shell</h1>
        </div>
        <button type="button" className="secondary-button" onClick={() => void onLogout()}>
          Sign out
        </button>
      </header>
      <div className="shell-body">
        <nav className="shell-nav">
          <Link to="/">Dashboard</Link>
          <Link to="/setup">Setup</Link>
          <Link to="/transactions">Transactions</Link>
          <Link to="/smoke">API smoke</Link>
        </nav>
        <Routes>
          <Route path="/" element={<DashboardPage onError={(message) => {
            if (message) {
              onCategoryCountChange(0)
            }
          }} />} />
          <Route path="/overview" element={<Overview username={username} />} />
          <Route
            path="/setup"
            element={<SetupPage onCategoryCountChange={onCategoryCountChange} />}
          />
          <Route path="/transactions" element={<TransactionsPage onError={() => undefined} />} />
          <Route path="/smoke" element={<SmokePage protectedState={protectedState} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </div>
  )
}

function App() {
  const [session, setSession] = useState<SessionState | null>(null)
  const [checkingSession, setCheckingSession] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [protectedState, setProtectedState] = useState<ProtectedState>({ status: 'idle' })

  async function refreshProtectedState(nextSession: SessionState) {
    if (!nextSession.authenticated) {
      setProtectedState({ status: 'idle' })
      return
    }
    setProtectedState({ status: 'loading' })
    try {
      const categories = await listCategories()
      setProtectedState({ status: 'ready', categoryCount: categories.length })
    } catch (error) {
      setProtectedState({
        status: 'error',
        message: error instanceof Error ? error.message : 'Unable to reach protected API',
      })
    }
  }

  useEffect(() => {
    let cancelled = false

    async function bootstrapSession() {
      try {
        const nextSession = await getSession()
        if (cancelled) {
          return
        }
        setSession(nextSession)
        await refreshProtectedState(nextSession)
      } finally {
        if (!cancelled) {
          setCheckingSession(false)
        }
      }
    }

    void bootstrapSession()

    return () => {
      cancelled = true
    }
  }, [])

  const isAuthenticated = useMemo(() => session?.authenticated === true, [session])

  async function handleLogin(username: string, password: string) {
    setSubmitting(true)
    try {
      const nextSession = await login(username, password)
      setSession(nextSession)
      await refreshProtectedState(nextSession)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleLogout() {
    await logout()
    const nextSession = { authenticated: false, username: null }
    setSession(nextSession)
    setProtectedState({ status: 'idle' })
  }

  if (checkingSession) {
    return <main className="loading-state">Checking session…</main>
  }

  return (
    <BrowserRouter>
      <main className="app-root">
        {isAuthenticated && session ? (
          <Shell
            session={session}
            protectedState={protectedState}
            onLogout={handleLogout}
            onCategoryCountChange={(count) =>
              setProtectedState({ status: 'ready', categoryCount: count })
            }
          />
        ) : (
          <LoginForm onLogin={handleLogin} loading={submitting} />
        )}
      </main>
    </BrowserRouter>
  )
}

export default App
