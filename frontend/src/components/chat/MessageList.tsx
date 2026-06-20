import { useEffect, useMemo, useRef } from "react"
import { MessageBubble } from "./MessageBubble"
import { EmptyState } from "./EmptyState"
import type { PromptExample } from "@/lib/promptExamples"
import type { HitlInterrupt, Message, StreamPhase } from "@/types"
import { PHASE_LABELS } from "@/types"
import { Button } from "@/components/ui/button"
import { formatUserDisplay } from "@/lib/formatUserMessage"
import { HitlApprovalCard } from "@/components/chat/HitlApprovalCard"

interface MessageListProps {
  messages: Message[]
  streaming: boolean
  phase: StreamPhase
  error: string | null
  hitlPending?: HitlInterrupt | null
  hitlLoading?: boolean
  onHitlApprove?: () => void
  onHitlReject?: () => void
  onRetry: () => void
  onExampleClick: (example: PromptExample) => void
}

export function MessageList({
  messages,
  streaming,
  phase,
  error,
  hitlPending,
  hitlLoading,
  onHitlApprove,
  onHitlReject,
  onRetry,
  onExampleClick,
}: MessageListProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)

  const lastUserMessage = useMemo(
    () => [...messages].reverse().find((m) => m.role === "user"),
    [messages],
  )

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const onScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = el
      stickRef.current = scrollHeight - scrollTop - clientHeight < 120
    }
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => el.removeEventListener("scroll", onScroll)
  }, [])

  useEffect(() => {
    if (stickRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: streaming ? "auto" : "smooth" })
    }
  }, [messages, streaming, phase])

  const statusLabel = streaming && phase !== "idle" ? PHASE_LABELS[phase] : ""

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
      {lastUserMessage && (
        <div className="shrink-0 border-b bg-muted/40 px-3 py-2 sm:px-4">
          <p className="text-[10px] font-medium text-muted-foreground sm:text-xs">
            你的提问
          </p>
          <p className="line-clamp-3 text-sm leading-snug [overflow-wrap:anywhere]">
            {formatUserDisplay(lastUserMessage.content)}
          </p>
        </div>
      )}

      <div
        ref={containerRef}
        className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-y-contain [-webkit-overflow-scrolling:touch]"
      >
        <div className="mx-auto w-full max-w-3xl space-y-3 p-3 pb-6 sm:space-y-4 sm:p-4 sm:pb-8">
          {messages.length === 0 ? (
            <EmptyState onExampleClick={onExampleClick} />
          ) : (
            messages.map((msg, i) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                streaming={
                  streaming &&
                  msg.role === "assistant" &&
                  i === messages.length - 1
                }
              />
            ))
          )}
          {hitlPending && onHitlApprove && onHitlReject && (
            <HitlApprovalCard
              interrupt={hitlPending}
              loading={hitlLoading}
              onApprove={onHitlApprove}
              onReject={onHitlReject}
            />
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {statusLabel && (
        <div className="pointer-events-none absolute bottom-2 left-1/2 max-w-[calc(100%-1rem)] -translate-x-1/2 truncate rounded-full border bg-background/95 px-3 py-1 text-[11px] text-muted-foreground shadow-sm backdrop-blur sm:px-4 sm:py-1.5 sm:text-xs">
          {statusLabel}
        </div>
      )}

      {error && (
        <div className="absolute bottom-2 left-1/2 flex max-w-[calc(100%-1rem)] -translate-x-1/2 flex-wrap items-center justify-center gap-2 rounded-lg border border-destructive/50 bg-background px-3 py-2 text-xs shadow-sm sm:max-w-md sm:text-sm">
          <span className="text-destructive">{error}</span>
          <Button size="sm" variant="outline" onClick={onRetry}>
            重试
          </Button>
        </div>
      )}
    </div>
  )
}
