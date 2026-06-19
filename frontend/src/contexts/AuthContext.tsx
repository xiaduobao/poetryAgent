import {
  useCallback,
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
import { AuthContext } from "@/contexts/auth-context"

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(() => Boolean(getAccessToken()))

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
    if (!getAccessToken()) return

    let cancelled = false
    authApi
      .me()
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch(() => {
        if (!cancelled) {
          clearTokens()
          setUser(null)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

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
