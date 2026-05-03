import { Link, Navigate, Route, Routes } from 'react-router-dom'
import type { SessionState } from '@/api'
import AnomaliesPage from '@/features/anomalies/AnomaliesPage'
import BudgetPage from '@/features/budget/BudgetPage'
import ChatPage from '@/features/chat/ChatPage'
import { RecurringPage } from '@/features/recurring/RecurringPage'
import StatementsPage from '@/features/statements/StatementsPage'
import TransactionDetailPage from '@/features/transactions/TransactionDetailPage'
import TransactionsPage from '@/features/transactions/TransactionsPage'
import { Overview } from './Overview'
import { SmokePage } from './SmokePage'
import type { ProtectedState } from './types'

export function AppShell({
  session,
  protectedState,
  onLogout,
}: {
  session: SessionState
  protectedState: ProtectedState
  onLogout: () => Promise<void>
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
          <Link to="/">Overview</Link>
          <Link to="/smoke">API smoke</Link>
          <Link to="/statements">Statements</Link>
          <Link to="/transactions">Transactions</Link>
          <Link to="/budgets">Budgets</Link>
          <Link to="/recurring">Recurring</Link>
          <Link to="/anomalies">Anomalies</Link>
          <Link to="/chat">Chat</Link>
        </nav>
        <div className="shell-content">
          <Routes>
            <Route path="/" element={<Overview username={username} protectedState={protectedState} />} />
            <Route path="/smoke" element={<SmokePage protectedState={protectedState} />} />
            <Route path="/statements" element={<StatementsPage />} />
            <Route path="/statements/:id" element={<Navigate to="/statements" replace />} />
            <Route path="/transactions/:id" element={<TransactionDetailPage />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/budgets" element={<BudgetPage />} />
            <Route path="/recurring" element={<RecurringPage />} />
            <Route path="/anomalies" element={<AnomaliesPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </div>
    </div>
  )
}
