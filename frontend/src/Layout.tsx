/**
 * T-080: App shell — sidebar nav + header with user email.
 * T-074: DevBanner always at top when auth disabled.
 */

import { NavLink, Outlet } from 'react-router-dom'
import { DevBanner } from './DevBanner'
import { useAuth } from './AuthContext'
import { postLogout } from './api'

const NAV_ITEMS = [
  { to: '/upload', label: 'Upload' },
  { to: '/summary', label: 'Summary' },
  { to: '/transactions', label: 'Transactions' },
  { to: '/chat', label: 'Chat' },
]

export function Layout() {
  const { email } = useAuth()

  async function handleLogout() {
    await postLogout()
    window.location.href = '/login'
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <DevBanner />
      <div style={{ display: 'flex', flex: 1 }}>
        {/* Sidebar */}
        <nav style={{
          width: 220,
          background: '#1e293b',
          color: '#cbd5e1',
          display: 'flex',
          flexDirection: 'column',
          padding: '24px 0',
          minHeight: '100vh',
        }}>
          <div style={{ padding: '0 20px 24px', fontWeight: 700, fontSize: 16, color: '#fff' }}>
            💰 Finance Assistant
          </div>
          {NAV_ITEMS.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              style={({ isActive }) => ({
                display: 'block',
                padding: '10px 20px',
                color: isActive ? '#fff' : '#94a3b8',
                background: isActive ? '#334155' : 'transparent',
                textDecoration: 'none',
                fontSize: 14,
                fontWeight: isActive ? 600 : 400,
              })}
            >
              {label}
            </NavLink>
          ))}
          <div style={{ flex: 1 }} />
          {email && (
            <div style={{ padding: '16px 20px', fontSize: 12, color: '#64748b' }}>
              <div style={{ marginBottom: 8, wordBreak: 'break-all' }}>{email}</div>
              <button
                onClick={handleLogout}
                style={{
                  background: 'transparent',
                  color: '#94a3b8',
                  border: '1px solid #334155',
                  borderRadius: 4,
                  padding: '4px 10px',
                  cursor: 'pointer',
                  fontSize: 12,
                }}
              >
                Sign out
              </button>
            </div>
          )}
        </nav>

        {/* Main content */}
        <main style={{ flex: 1, padding: 32, background: '#f8fafc', overflowY: 'auto' }}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
