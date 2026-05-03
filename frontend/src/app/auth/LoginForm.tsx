import type { FormEvent } from 'react'
import { useState } from 'react'

export function LoginForm({
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
      <h1>Sign in to Personal Financial Analyst</h1>
      <form className="login-form" onSubmit={handleSubmit}>
        <label>
          Username
          <input
            autoComplete="username"
            value={username}
            onChange={event => setUsername(event.target.value)}
          />
        </label>
        <label>
          Password
          <input
            autoComplete="current-password"
            type="password"
            value={password}
            onChange={event => setPassword(event.target.value)}
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
