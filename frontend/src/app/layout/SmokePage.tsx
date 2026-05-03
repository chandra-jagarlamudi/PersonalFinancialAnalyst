import type { ProtectedState } from './types'

export function SmokePage({ protectedState }: { protectedState: ProtectedState }) {
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
