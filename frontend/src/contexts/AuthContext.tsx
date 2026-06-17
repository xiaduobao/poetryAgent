import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import {
  authApi,
  clearTokens,
  getAccessToken,
  setGuestToken,
  setTokens,
} from "@/api/client"
import type { AuthUser } from "@/api/auth-storage"

interface AuthContextValue {
  user: AuthUser | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  enterAsGuest: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  const loadUser = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      const me = await authApi.me()
      setUser(me)
    } catch {
      clearTokens()
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadUser()
  }, [loadUser])

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await authApi.login(email, password)
      setTokens(tokens.access_token, tokens.refresh_token)
      await loadUser()
    },
    [loadUser],
  )

  const register = useCallback(
    async (email: string, password: string) => {
      const tokens = await authApi.register(email, password)
      setTokens(tokens.access_token, tokens.refresh_token)
      await loadUser()
    },
    [loadUser],
  )

  const enterAsGuest = useCallback(async () => {
    const token = await authApi.guest()
    setGuestToken(token.access_token)
    await loadUser()
  }, [loadUser])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      clearTokens()
      setUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, enterAsGuest, logout }),
    [user, loading, login, register, enterAsGuest, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider")
  }
  return ctx
}
