import { useCallback, useEffect, useRef, useState } from "react"
import { api } from "@/api/client"
import type { Session } from "@/types"

export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState("")
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const refresh = useCallback(async (search?: string) => {
    setLoading(true)
    try {
      const data = await api.listSessions(search)
      setSessions(data)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => refresh(query || undefined), 300)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query, refresh])

  const createSession = useCallback(async () => {
    const session = await api.createSession()
    setSessions((prev) => [session, ...prev])
    return session
  }, [])

  const renameSession = useCallback(async (id: string, title: string) => {
    const updated = await api.renameSession(id, title)
    setSessions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, title: updated.title } : s)),
    )
  }, [])

  const deleteSession = useCallback(async (id: string) => {
    await api.deleteSession(id)
    setSessions((prev) => prev.filter((s) => s.id !== id))
  }, [])

  return {
    sessions,
    loading,
    query,
    setQuery,
    refresh,
    createSession,
    renameSession,
    deleteSession,
  }
}
