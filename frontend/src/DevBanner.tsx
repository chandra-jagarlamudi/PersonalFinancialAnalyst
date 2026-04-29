/** T-074: Persistent non-dismissable dev mode banner. */

import { useAuth } from './AuthContext'

export function DevBanner() {
  const { authEnabled } = useAuth()
  if (authEnabled !== false) return null
  return (
    <div style={{
      position: 'sticky',
      top: 0,
      zIndex: 1000,
      background: '#fbbf24',
      color: '#1c1917',
      textAlign: 'center',
      padding: '8px 16px',
      fontWeight: 600,
      fontSize: 14,
    }}>
      Auth disabled — dev mode
    </div>
  )
}
