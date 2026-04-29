/**
 * T-073/T-074: Auth context — tracks auth_enabled flag and user email.
 * Consumed by all pages to drive login redirect and dev banner.
 */

import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { getAuthStatus, getAuthMe } from './api'

interface AuthState {
  authEnabled: boolean | null  // null = loading
  email: string | null
}

const AuthContext = createContext<AuthState>({ authEnabled: null, email: null })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ authEnabled: null, email: null })

  useEffect(() => {
    async function load() {
      try {
        const { auth_enabled } = await getAuthStatus()
        let email: string | null = null
        if (auth_enabled) {
          try {
            const me = await getAuthMe()
            email = me.email
          } catch {
            // 401 means not logged in — AuthGuard handles redirect
          }
        }
        setState({ authEnabled: auth_enabled, email })
      } catch {
        setState({ authEnabled: true, email: null })
      }
    }
    load()
  }, [])

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
