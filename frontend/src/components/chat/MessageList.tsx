import { useEffect, useRef } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { MessageBubble } from "./MessageBubble"
import { EmptyState } from "./EmptyState"
import type { Message, StreamPhase } from "@/types"
import { PHASE_LABELS } from "@/types"
import { Button } from "@/components/ui/button"

interface MessageListProps {
  messages: Message[]
  streaming: boolean
  phase: StreamPhase
  error: string | null
  onRetry: () => void
  onExampleClick: (text: string) => void
}

export function MessageList({
  messages,
  streaming,
  phase,
  error,
  onRetry,
  onExampleClick,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)

  useEffect(() => {
    const el = containerRef.current?.querySelector("[data-radix-scroll-area-viewport]")
    if (!el) return

    const onScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = el
      stickRef.current = scrollHeight - scrollTop - clientHeight < 80
    }
    el.addEventListener("scroll", onScroll)
    return () => el.removeEventListener("scroll", onScroll)
  }, [])

  useEffect(() => {
    if (stickRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }
  }, [messages, streaming, phase])

  const statusLabel = streaming && phase !== "idle" ? PHASE_LABELS[phase] : ""

  return (
    <div ref={containerRef} className="relative flex-1 overflow-hidden">
      <ScrollArea className="h-full">
        <div className="mx-auto max-w-3xl space-y-4 p-4 pb-8">
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
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      {statusLabel && (
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 rounded-full border bg-background/95 px-4 py-1.5 text-xs text-muted-foreground shadow-sm backdrop-blur">
          {statusLabel}
        </div>
      )}

      {error && (
        <div className="absolute bottom-2 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-lg border border-destructive/50 bg-background px-4 py-2 text-sm shadow-sm">
          <span className="text-destructive">{error}</span>
          <Button size="sm" variant="outline" onClick={onRetry}>
            重试
          </Button>
        </div>
      )}
    </div>
  )
}
