import { clearTokens, getValidToken, refreshAccessToken } from "./client"
import { isGuestSession } from "./auth-storage"
import type { SourceRef, StreamPhase } from "../types"

export interface StreamCallbacks {
  onStatus?: (phase: StreamPhase) => void
  onToken?: (content: string) => void
  onSources?: (sources: SourceRef[]) => void
  onDone?: (data: {
    session_id: string
    intent: string
    message_id: string
    sources?: SourceRef[]
  }) => void
  onError?: (detail: string) => void
}

export interface StreamHandle {
  abort: () => void
  promise: Promise<void>
}

async function fetchStream(
  sessionId: string | null,
  message: string,
  callbacks: StreamCallbacks,
  signal: AbortSignal,
  retry = true,
): Promise<Response | null> {
  const token = await getValidToken()
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers,
    body: JSON.stringify({
      message,
      session_id: sessionId,
      thread_id: sessionId || "default",
    }),
    signal,
  })

  if (res.status === 401 && retry) {
    if (isGuestSession()) {
      clearTokens()
      callbacks.onError?.("游客会话已过期，请重新进入或注册登录")
      return null
    }
    const newToken = await refreshAccessToken()
    if (newToken) {
      return fetchStream(sessionId, message, callbacks, signal, false)
    }
    clearTokens()
    callbacks.onError?.("登录已过期，请重新登录")
    return null
  }

  return res
}

export function streamChat(
  sessionId: string | null,
  message: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): StreamHandle {
  const controller = new AbortController()
  const combinedSignal = signal
    ? AbortSignal.any([signal, controller.signal])
    : controller.signal

  const promise = (async () => {
    const res = await fetchStream(sessionId, message, callbacks, combinedSignal)
    if (!res) return

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      const message =
        err.detail ||
        err.error ||
        (res.status === 429 ? "请求过于频繁，请稍后再试" : `HTTP ${res.status}`)
      callbacks.onError?.(message)
      return
    }

    const reader = res.body?.getReader()
    if (!reader) {
      callbacks.onError?.("无法读取响应流")
      return
    }

    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split("\n\n")
      buffer = parts.pop() || ""

      for (const part of parts) {
        if (!part.trim()) continue
        parseSSE(part, callbacks)
      }
    }

    if (buffer.trim()) {
      parseSSE(buffer, callbacks)
    }
  })().catch((err) => {
    if (err.name === "AbortError") return
    callbacks.onError?.(err.message || "网络错误")
  })

  return {
    abort: () => controller.abort(),
    promise,
  }
}

function parseSSE(raw: string, callbacks: StreamCallbacks) {
  let event = "message"
  let data = ""

  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim()
    else if (line.startsWith("data:")) data = line.slice(5).trim()
  }

  if (!data) return

  try {
    const parsed = JSON.parse(data)
    switch (event) {
      case "status":
        callbacks.onStatus?.(parsed.phase)
        break
      case "sources":
        callbacks.onSources?.(parsed.sources || [])
        break
      case "token":
        callbacks.onToken?.(parsed.content)
        break
      case "done":
        callbacks.onDone?.(parsed)
        break
      case "error":
        callbacks.onError?.(parsed.detail)
        break
    }
  } catch {
    /* ignore malformed SSE */
  }
}
