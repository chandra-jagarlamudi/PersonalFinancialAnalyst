import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './AuthContext'
import { Layout } from './Layout'
import { LoginPage } from './pages/LoginPage'
import { ReactNode } from 'react'

// Placeholder pages — replaced in Tier 11
function PlaceholderPage({ title }: { title: string }) {
  return <div style={{ color: '#64748b', fontSize: 14 }}>{title} — coming soon</div>
}

function AuthGuard({ children }: { children: ReactNode }) {
  const { authEnabled, email } = useAuth()
  if (authEnabled === null) return null  // loading
  if (authEnabled && !email) return <Navigate to="/login" replace />
  return <>{children}</>
}

const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: (
      <AuthGuard>
        <Layout />
      </AuthGuard>
    ),
    children: [
      { index: true, element: <Navigate to="/upload" replace /> },
      { path: 'upload', element: <PlaceholderPage title="Upload" /> },
      { path: 'summary', element: <PlaceholderPage title="Summary" /> },
      { path: 'transactions', element: <PlaceholderPage title="Transactions" /> },
      { path: 'chat', element: <PlaceholderPage title="Chat" /> },
    ],
  },
])

export default function App() {
  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  )
}
