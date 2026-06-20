import { useMemo, useRef, useState } from "react"
import { getFollowUpSuggestions, type PromptExample } from "@/lib/promptExamples"
import { LogOut, Menu, Moon, Sun } from "lucide-react"
import { SessionSidebar } from "@/components/sidebar/SessionSidebar"
import { MessageList } from "@/components/chat/MessageList"
import { ChatInput, type ChatInputHandle } from "@/components/chat/ChatInput"
import { Button } from "@/components/ui/button"
import { GithubRepoLink } from "@/components/GithubRepoLink"
import { useSessions } from "@/hooks/useSessions"
import { useChatStream } from "@/hooks/useChatStream"
import { useAuth } from "@/hooks/useAuth"

export function AppLayout() {
  const { user, logout } = useAuth()
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
    hitlPending,
    hitlLoading,
    loadSession,
    clearMessages,
    sendMessage,
    resumeHitl,
    stop,
    retry,
    maxLength,
  } = useChatStream()

  const [activeId, setActiveId] = useState<string | null>(null)
  const [draft, setDraft] = useState("")
  const [imagePickHint, setImagePickHint] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const chatInputRef = useRef<ChatInputHandle>(null)
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

  const followUpSuggestions = useMemo(
    () =>
      messages.length > 0 && !streaming
        ? getFollowUpSuggestions(messages)
        : [],
    [messages, streaming],
  )

  const handleSend = async (text: string, imageBase64?: string) => {
    let sessionId = activeId
    if (!sessionId) {
      const session = await createSession()
      sessionId = session.id
      setActiveId(sessionId)
    }
    await sendMessage(sessionId, text, imageBase64)
    refresh(query || undefined)
  }

  const handleDraftChange = (text: string) => {
    setDraft(text)
    if (!text.trim()) {
      setImagePickHint(null)
    }
  }

  const handlePromptSelect = (example: PromptExample) => {
    if (streaming) return

    if (example.type === "image") {
      setDraft(example.text)
      setImagePickHint(
        example.hint ?? "请先选择一张风景照片，再点击发送",
      )
      chatInputRef.current?.openImagePicker()
      return
    }

    setImagePickHint(null)
    void handleSend(example.text)
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
        <div className="fixed inset-0 z-40 flex md:hidden">
          <SessionSidebar
            className="relative z-50 h-full shrink-0 shadow-xl"
            sessions={sessions}
            loading={loading}
            query={query}
            onQueryChange={setQuery}
            activeId={activeId}
            onSelect={handleSelect}
            onCreate={handleCreate}
            onRename={renameSession}
            onDelete={handleDelete}
            onClose={() => setSidebarOpen(false)}
          />
          <button
            type="button"
            className="min-w-0 flex-1 bg-black/50"
            onClick={() => setSidebarOpen(false)}
            aria-label="关闭侧边栏"
          />
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="safe-area-top flex h-12 shrink-0 items-center gap-2 border-b px-3 sm:h-14 sm:gap-3 sm:px-4">
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </Button>
          <h1 className="min-w-0 flex-1 truncate text-sm font-semibold">
            {sessions.find((s) => s.id === activeId)?.title || "古典诗词鉴赏助手"}
          </h1>
          <div className="ml-auto flex shrink-0 items-center gap-1">
            <GithubRepoLink
              label="GitHub"
              className="h-9 shrink-0 rounded-md px-2 text-xs font-medium hover:bg-accent hover:text-accent-foreground"
            />
            {user && (
              <span className="mr-2 hidden text-xs text-muted-foreground sm:inline">
                {user.is_guest ? "游客" : user.email} · {user.plan}
              </span>
            )}
            <Button variant="ghost" size="icon" onClick={() => logout()} title="退出登录">
              <LogOut className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" onClick={toggleTheme}>
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
          </div>
        </header>

        {user?.is_guest && (
          <div className="border-b bg-muted/40 px-3 py-1.5 text-center text-[11px] leading-snug text-muted-foreground sm:px-4 sm:py-2 sm:text-xs">
            游客模式：注册登录可保存更多对话并提升每日额度
          </div>
        )}

        <MessageList
          messages={messages}
          streaming={streaming}
          phase={phase}
          error={error}
          hitlPending={hitlPending}
          hitlLoading={hitlLoading}
          onHitlApprove={() => resumeHitl(activeId, "approve")}
          onHitlReject={() => resumeHitl(activeId, "reject")}
          onRetry={() => retry(activeId)}
          onExampleClick={handlePromptSelect}
        />

        <ChatInput
          ref={chatInputRef}
          draft={draft}
          onDraftChange={handleDraftChange}
          onSend={handleSend}
          onStop={stop}
          streaming={streaming && !hitlPending}
          maxLength={maxLength}
          suggestions={followUpSuggestions}
          imagePickHint={imagePickHint}
          onImageAttached={() => setImagePickHint(null)}
        />
      </main>
    </div>
  )
}
