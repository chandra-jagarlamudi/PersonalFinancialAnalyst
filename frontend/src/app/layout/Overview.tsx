import type { ProtectedState } from './types'

export function Overview({
  username,
  protectedState,
}: {
  username: string
  protectedState: ProtectedState
}) {
  return (
    <section className="panel">
      <h2>Welcome back, {username}</h2>
      <p>
        This first shell proves the frontend can authenticate, keep a session,
        and reach protected backend APIs.
      </p>
      <div className="status-grid">
        <article>
          <span className="metric-label">Session</span>
          <strong>Authenticated</strong>
        </article>
        <article>
          <span className="metric-label">Protected API</span>
          <strong>
            {protectedState.status === 'ready'
              ? 'Reachable'
              : protectedState.status === 'error'
                ? 'Failed'
                : protectedState.status === 'loading'
                  ? 'Loading…'
                  : 'Not started'}
          </strong>
        </article>
        <article>
          <span className="metric-label">Categories</span>
          <strong>
            {protectedState.status === 'ready'
              ? protectedState.categoryCount
              : '—'}
          </strong>
        </article>
      </div>
      {protectedState.status === 'error' ? (
        <p className="error-banner">{protectedState.message}</p>
      ) : null}
    </section>
  )
}
