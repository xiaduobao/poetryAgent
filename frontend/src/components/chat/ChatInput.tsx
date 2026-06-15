import { useEffect, useRef, useState, type KeyboardEvent } from "react"
import { Loader2, Send, Square, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

interface ChatInputProps {
  onSend: (text: string) => void
  onStop: () => void
  streaming: boolean
  maxLength: number
  draft: string
  onDraftChange: (text: string) => void
}

export function ChatInput({
  onSend,
  onStop,
  streaming,
  maxLength,
  draft,
  onDraftChange,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [focused, setFocused] = useState(false)

  const overLimit = draft.length > maxLength
  const canSend = draft.trim().length > 0 && !overLimit && !streaming

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    const lineHeight = 24
    const maxHeight = lineHeight * 6
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`
  }, [draft])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (canSend) {
        onSend(draft)
        onDraftChange("")
      }
    }
  }

  const handleSend = () => {
    if (!canSend) return
    onSend(draft)
    onDraftChange("")
  }

  return (
    <div className="border-t bg-background p-4">
      <div
        className={cn(
          "mx-auto max-w-3xl rounded-2xl border bg-card p-3 shadow-sm transition-shadow",
          focused && "ring-2 ring-ring/20",
        )}
      >
        <Textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="输入问题… Shift+Enter 换行，Enter 发送"
          rows={1}
          className="min-h-[44px] resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
          disabled={streaming}
        />
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {draft && !streaming && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onDraftChange("")}
              >
                <X className="mr-1 h-3 w-3" />
                清空
              </Button>
            )}
            <span
              className={cn(
                "text-xs",
                overLimit ? "text-destructive" : "text-muted-foreground",
              )}
            >
              {draft.length} / {maxLength}
            </span>
          </div>
          <div className="flex gap-2">
            {streaming ? (
              <Button variant="outline" size="sm" onClick={onStop}>
                <Square className="mr-1 h-3 w-3 fill-current" />
                停止
              </Button>
            ) : (
              <Button size="sm" disabled={!canSend} onClick={handleSend}>
                {streaming ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <Send className="mr-1 h-4 w-4" />
                )}
                发送
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
