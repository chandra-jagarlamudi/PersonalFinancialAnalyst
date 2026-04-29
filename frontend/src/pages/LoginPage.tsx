/** T-073: Login page with Google sign-in button. */

export function LoginPage() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      background: '#f9fafb',
    }}>
      <div style={{
        background: '#fff',
        border: '1px solid #e5e7eb',
        borderRadius: 12,
        padding: '48px 40px',
        textAlign: 'center',
        maxWidth: 380,
        width: '100%',
      }}>
        <h1 style={{ marginBottom: 8, fontSize: 24, fontWeight: 700 }}>
          Financial Hygiene Assistant
        </h1>
        <p style={{ color: '#6b7280', marginBottom: 32 }}>
          Sign in to access your financial data
        </p>
        <a
          href="/api/auth/login"
          style={{
            display: 'inline-block',
            background: '#2563eb',
            color: '#fff',
            padding: '12px 24px',
            borderRadius: 8,
            textDecoration: 'none',
            fontWeight: 600,
            fontSize: 15,
          }}
        >
          Sign in with Google
        </a>
      </div>
    </div>
  )
}
