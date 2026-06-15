const TOKEN_KEY = "poetry_agent_access_token"
const REFRESH_KEY = "poetry_agent_refresh_token"
const GUEST_KEY = "poetry_agent_is_guest"

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function isGuestSession(): boolean {
  return localStorage.getItem(GUEST_KEY) === "1"
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(TOKEN_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
  localStorage.removeItem(GUEST_KEY)
}

export function setGuestToken(access: string): void {
  localStorage.setItem(TOKEN_KEY, access)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.setItem(GUEST_KEY, "1")
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(GUEST_KEY)
}

export interface AuthUser {
  id: string
  email: string
  role: string
  tenant_id: string
  plan: string
  is_guest: boolean
  created_at: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface GuestToken {
  access_token: string
  token_type: string
}
