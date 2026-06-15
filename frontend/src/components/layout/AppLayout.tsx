import { useState } from "react"
import { Menu, Moon, Sun } from "lucide-react"
import { SessionSidebar } from "@/components/sidebar/SessionSidebar"
import { MessageList } from "@/components/chat/MessageList"
import { ChatInput } from "@/components/chat/ChatInput"
import { Button } from "@/components/ui/button"
import { useSessions } from "@/hooks/useSessions"
import { useChatStream } from "@/hooks/useChatStream"

export function AppLayout() {
  const {
    sessions,
    loading,
    query,
    setQuery,
    createSession,
    renameSession,
    deleteSession,
    refresh,
  } = useSessions()

  const {
    messages,
    streaming,
    phase,
    error,
    loadSession,
    clearMessages,
    sendMessage,
    stop,
    retry,
    maxLength,
  } = useChatStream()

  const [activeId, setActiveId] = useState<string | null>(null)
  const [draft, setDraft] = useState("")
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
  )

  const toggleTheme = () => {
    document.documentElement.classList.toggle("dark")
    setDark((d) => !d)
  }

  const handleCreate = async () => {
    const session = await createSession()
    setActiveId(session.id)
    clearMessages()
    setSidebarOpen(false)
  }

  const handleSelect = async (id: string) => {
    setActiveId(id)
    await loadSession(id)
    setSidebarOpen(false)
  }

  const handleDelete = async (id: string) => {
    await deleteSession(id)
    if (activeId === id) {
      setActiveId(null)
      clearMessages()
    }
  }

  const handleSend = async (text: string) => {
    let sessionId = activeId
    if (!sessionId) {
      const session = await createSession()
      sessionId = session.id
      setActiveId(sessionId)
    }
    await sendMessage(sessionId, text)
    refresh(query || undefined)
  }

  return (
    <div className="flex h-svh w-full overflow-hidden bg-background text-foreground">
      {/* Desktop sidebar */}
      <SessionSidebar
        className="hidden md:flex"
        sessions={sessions}
        loading={loading}
        query={query}
        onQueryChange={setQuery}
        activeId={activeId}
        onSelect={handleSelect}
        onCreate={handleCreate}
        onRename={renameSession}
        onDelete={handleDelete}
      />

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/50"
            onClick={() => setSidebarOpen(false)}
            aria-label="关闭侧边栏"
          />
          <SessionSidebar
            className="relative z-50 h-full shadow-xl"
            sessions={sessions}
            loading={loading}
            query={query}
            onQueryChange={setQuery}
            activeId={activeId}
            onSelect={handleSelect}
            onCreate={handleCreate}
            onRename={renameSession}
            onDelete={handleDelete}
          />
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </Button>
          <h1 className="truncate text-sm font-semibold">
            {sessions.find((s) => s.id === activeId)?.title || "古典诗词鉴赏助手"}
          </h1>
          <div className="ml-auto">
            <Button variant="ghost" size="icon" onClick={toggleTheme}>
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
          </div>
        </header>

        <MessageList
          messages={messages}
          streaming={streaming}
          phase={phase}
          error={error}
          onRetry={() => retry(activeId)}
          onExampleClick={setDraft}
        />

        <ChatInput
          draft={draft}
          onDraftChange={setDraft}
          onSend={handleSend}
          onStop={stop}
          streaming={streaming}
          maxLength={maxLength}
        />
      </main>
    </div>
  )
}
