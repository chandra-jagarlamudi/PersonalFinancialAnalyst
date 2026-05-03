import { useEffect, useMemo, useState } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { getSession, listCategories, login, logout, type SessionState } from '@/api'
import { LoginForm } from '@/app/auth/LoginForm'
import { AppShell } from '@/app/layout/AppShell'
import type { ProtectedState } from '@/app/layout/types'
import '@/styles/index.css'

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
          <AppShell session={session} protectedState={protectedState} onLogout={handleLogout} />
        ) : (
          <LoginForm onLogin={handleLogin} loading={submitting} />
        )}
      </main>
    </BrowserRouter>
  )
}

export default App
