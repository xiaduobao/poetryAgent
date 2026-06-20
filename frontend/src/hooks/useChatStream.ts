import { useCallback, useRef, useState } from "react"
import { resumeChatStream, streamChat, type StreamCallbacks } from "@/api/chat"
import { api } from "@/api/client"
import type { HitlInterrupt, Message, StreamPhase } from "@/types"

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
  const [hitlPending, setHitlPending] = useState<HitlInterrupt | null>(null)
  const [hitlLoading, setHitlLoading] = useState(false)
  const abortRef = useRef<(() => void) | null>(null)
  const pendingRetryRef = useRef<PendingRetry | null>(null)
  const activeSessionRef = useRef<string | null>(null)
  const pendingAssistantIdRef = useRef<string | null>(null)

  const loadSession = useCallback(async (sessionId: string) => {
    const detail = await api.getSession(sessionId)
    setMessages(detail.messages)
    setError(null)
    setPhase("idle")
    setHitlPending(null)
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    setError(null)
    setPhase("idle")
    setHitlPending(null)
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
      setHitlPending(null)
      setPhase(hasImage ? "describing" : "classifying")

      activeSessionRef.current = sessionId

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
      pendingAssistantIdRef.current = assistantId
      pendingRetryRef.current = null

      const streamCallbacks: StreamCallbacks = {
          onStatus: (p) => setPhase(p),
          onSources: (sources) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, sources } : m,
              ),
            )
          },
          onSubtasks: ({ sub_intents, is_compound }) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      sub_intents,
                      is_compound: is_compound ?? sub_intents.length > 1,
                    }
                  : m,
              ),
            )
          },
          onInterrupt: (data: HitlInterrupt) => {
            setHitlPending(data)
            setPhase("awaiting_approval")
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
            if (data.awaiting_approval) {
              setStreaming(false)
              setPhase("awaiting_approval")
              return
            }
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id === assistantId) {
                  return {
                    ...m,
                    id: data.message_id || m.id,
                    intent: data.intent,
                    sub_intents: data.sub_intents,
                    is_compound: data.is_compound,
                    sources: data.sources ?? m.sources,
                  }
                }
                return m
              }),
            )
            setStreaming(false)
            setPhase("idle")
            setHitlPending(null)
          },
          onError: (detail) => {
            setError(detail)
            setStreaming(false)
            setPhase("error")
            setHitlPending(null)
            pendingRetryRef.current = { text: trimmed, imageBase64 }
          },
        }

      const handle = streamChat(
        sessionId,
        trimmed,
        streamCallbacks,
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

  const resumeHitl = useCallback(
    async (sessionId: string | null, action: "approve" | "reject") => {
      if (!sessionId || !hitlPending) return

      const assistantId = pendingAssistantIdRef.current
      if (!assistantId) return

      setError(null)
      setHitlLoading(true)
      setStreaming(true)
      setPhase(action === "approve" ? "tooling" : "generating")

      const resumeCallbacks: StreamCallbacks = {
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
                  sub_intents: data.sub_intents,
                  is_compound: data.is_compound,
                  sources: data.sources ?? m.sources,
                }
              }
              return m
            }),
          )
          setStreaming(false)
          setHitlLoading(false)
          setHitlPending(null)
          setPhase("idle")
        },
        onError: (detail) => {
          setError(detail)
          setStreaming(false)
          setHitlLoading(false)
          setPhase("error")
        },
      }

      const handle = resumeChatStream(sessionId, action, resumeCallbacks)

      abortRef.current = handle.abort
      await handle.promise
      abortRef.current = null
    },
    [hitlPending],
  )

  return {
    messages,
    streaming,
    phase,
    error,
    hitlPending,
    hitlLoading,
    loadSession,
    clearMessages,
    sendMessage,
    resumeHitl,
    stop,
    retry,
    maxLength: MAX_LENGTH,
  }
}
