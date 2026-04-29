import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './AuthContext'
import { Layout } from './Layout'
import { LoginPage } from './pages/LoginPage'
import { UploadPage } from './pages/UploadPage'
import { SummaryPage } from './pages/SummaryPage'
import { TransactionsPage } from './pages/TransactionsPage'
import { ChatPage } from './pages/ChatPage'
import { ReactNode } from 'react'

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
      { path: 'upload', element: <UploadPage /> },
      { path: 'summary', element: <SummaryPage /> },
      { path: 'transactions', element: <TransactionsPage /> },
      { path: 'chat', element: <ChatPage /> },
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
