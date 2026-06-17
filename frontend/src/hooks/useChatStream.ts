import { useCallback, useRef, useState } from "react"
import { streamChat } from "@/api/chat"
import { api } from "@/api/client"
import type { Message, StreamPhase } from "@/types"

const MAX_LENGTH = 2000

interface PendingRetry {
  text: string
  imageBase64?: string
}

function formatUserContent(text: string, hasImage: boolean): string {
  const trimmed = text.trim()
  if (hasImage && trimmed) {
    return `[已上传图片]\n${trimmed}`
  }
  if (hasImage) {
    return "[已上传图片]"
  }
  return trimmed
}

export function useChatStream() {
  const [messages, setMessages] = useState<Message[]>([])
  const [streaming, setStreaming] = useState(false)
  const [phase, setPhase] = useState<StreamPhase>("idle")
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<(() => void) | null>(null)
  const pendingRetryRef = useRef<PendingRetry | null>(null)

  const loadSession = useCallback(async (sessionId: string) => {
    const detail = await api.getSession(sessionId)
    setMessages(detail.messages)
    setError(null)
    setPhase("idle")
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    setError(null)
    setPhase("idle")
  }, [])

  const stop = useCallback(() => {
    abortRef.current?.()
    abortRef.current = null
    setStreaming(false)
    setPhase("idle")
  }, [])

  const sendMessage = useCallback(
    async (sessionId: string | null, text: string, imageBase64?: string) => {
      const trimmed = text.trim()
      const hasImage = Boolean(imageBase64)
      if ((!trimmed && !hasImage) || trimmed.length > MAX_LENGTH) return

      setError(null)
      setStreaming(true)
      setPhase(hasImage ? "describing" : "classifying")

      const userMsg: Message = {
        id: `temp-user-${Date.now()}`,
        role: "user",
        content: formatUserContent(trimmed, hasImage),
        created_at: new Date().toISOString(),
      }
      const assistantId = `temp-assistant-${Date.now()}`
      const assistantMsg: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
      }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      pendingRetryRef.current = null

      const handle = streamChat(
        sessionId,
        trimmed,
        {
          onStatus: (p) => setPhase(p),
          onSources: (sources) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, sources } : m,
              ),
            )
          },
          onToken: (content) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: m.content + content }
                  : m,
              ),
            )
          },
          onDone: (data) => {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id === assistantId) {
                  return {
                    ...m,
                    id: data.message_id || m.id,
                    intent: data.intent,
                    sources: data.sources ?? m.sources,
                  }
                }
                return m
              }),
            )
            setStreaming(false)
            setPhase("idle")
          },
          onError: (detail) => {
            setError(detail)
            setStreaming(false)
            setPhase("error")
            pendingRetryRef.current = { text: trimmed, imageBase64 }
          },
        },
        undefined,
        imageBase64,
      )

      abortRef.current = handle.abort
      await handle.promise
      abortRef.current = null
    },
    [],
  )

  const retry = useCallback(
    (sessionId: string | null) => {
      const pending = pendingRetryRef.current
      if (!pending) return
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last?.role === "assistant" && !last.content) {
          return prev.slice(0, -2)
        }
        return prev.slice(0, -1)
      })
      sendMessage(sessionId, pending.text, pending.imageBase64)
    },
    [sendMessage],
  )

  return {
    messages,
    streaming,
    phase,
    error,
    loadSession,
    clearMessages,
    sendMessage,
    stop,
    retry,
    maxLength: MAX_LENGTH,
  }
}
