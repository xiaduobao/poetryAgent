import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  isGuestSession,
  setGuestToken,
  setTokens,
  type AuthUser,
  type GuestToken,
  type TokenPair,
} from "./auth-storage"

const API_BASE = "/api/v1"

let refreshPromise: Promise<string | null> | null = null

export async function refreshAccessToken(): Promise<string | null> {
  if (isGuestSession()) return null
  const refresh = getRefreshToken()
  if (!refresh) return null
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  })
  if (!res.ok) {
    clearTokens()
    return null
  }
  const data: TokenPair = await res.json()
  setTokens(data.access_token, data.refresh_token)
  return data.access_token
}

async function getValidToken(): Promise<string | null> {
  const token = getAccessToken()
  if (token) return token
  if (isGuestSession()) return null
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

export async function request<T>(
  path: string,
  options?: RequestInit,
  retry = true,
): Promise<T> {
  const token = await getValidToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (res.status === 401 && retry) {
    if (isGuestSession()) {
      clearTokens()
      window.location.reload()
      throw new Error("游客会话已过期，请重新进入或注册登录")
    }
    const newToken = await refreshAccessToken()
    if (newToken) {
      return request<T>(path, options, false)
    }
    clearTokens()
    window.location.reload()
    throw new Error("登录已过期，请重新登录")
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail) || `HTTP ${res.status}`,
    )
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const authApi = {
  register: async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(typeof err.detail === "string" ? err.detail : "注册失败")
    }
    return res.json() as Promise<TokenPair>
  },

  login: async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(typeof err.detail === "string" ? err.detail : "登录失败")
    }
    return res.json() as Promise<TokenPair>
  },

  logout: () => {
    const refresh = getRefreshToken()
    if (refresh) {
      return request<void>("/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refresh }),
      })
    }
    return Promise.resolve()
  },

  me: () => request<AuthUser>("/auth/me"),

  guest: async () => {
    const res = await fetch(`${API_BASE}/auth/guest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(typeof err.detail === "string" ? err.detail : "游客访问失败")
    }
    return res.json() as Promise<GuestToken>
  },
}

export const api = {
  listSessions: (q?: string) =>
    request<import("../types").Session[]>(
      `/sessions${q ? `?q=${encodeURIComponent(q)}` : ""}`,
    ),

  createSession: (title = "新对话") =>
    request<import("../types").Session>("/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),

  getSession: (id: string) =>
    request<import("../types").SessionDetail>(`/sessions/${id}`),

  renameSession: (id: string, title: string) =>
    request<import("../types").Session>(`/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),

  deleteSession: (id: string) =>
    request<void>(`/sessions/${id}`, { method: "DELETE" }),
}

export type { AuthUser, GuestToken, TokenPair } from "./auth-storage"
export {
  getAccessToken,
  getValidToken,
  clearTokens,
  setTokens,
  setGuestToken,
  isGuestSession,
}
