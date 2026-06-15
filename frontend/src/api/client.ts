const API_BASE = "/api/v1"

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
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
