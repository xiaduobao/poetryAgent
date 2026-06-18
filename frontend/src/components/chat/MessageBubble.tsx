import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Copy, Check } from "lucide-react"
import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { formatUserDisplay } from "@/lib/formatUserMessage"
import { INTENT_LABELS } from "@/types"
import type { Message } from "@/types"
import { SourcePanel } from "@/components/chat/SourcePanel"

interface MessageBubbleProps {
  message: Message
  streaming?: boolean
}

export function MessageBubble({ message, streaming }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false)
  const isUser = message.role === "user"

  const copy = async () => {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="flex w-full min-w-0">
      <div
        className={cn(
          "min-w-0 w-full",
          isUser ? "flex justify-end" : "",
        )}
      >
        <div
          className={cn(
            "min-w-0 rounded-2xl px-3 py-2.5 text-sm sm:px-4 sm:py-3",
            isUser
              ? "w-fit max-w-full bg-primary text-primary-foreground"
              : "w-full border bg-card text-card-foreground",
          )}
        >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
            {formatUserDisplay(message.content)}
          </p>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none min-w-0 break-words [overflow-wrap:anywhere]">
            {message.content ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            ) : streaming ? (
              <span className="inline-block h-4 w-1.5 animate-pulse bg-muted-foreground" />
            ) : null}
          </div>
        )}

        {!isUser && message.content && !streaming && (
          <div className="mt-2 flex flex-col gap-2">
            <div className="flex items-center gap-2">
              {message.intent && (
                <Badge variant="secondary" className="text-xs">
                  {INTENT_LABELS[message.intent] || message.intent}
                </Badge>
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={copy}
                title="复制"
              >
                {copied ? (
                  <Check className="h-3 w-3" />
                ) : (
                  <Copy className="h-3 w-3" />
                )}
              </Button>
            </div>
            {message.sources && message.sources.length > 0 && (
              <SourcePanel sources={message.sources} />
            )}
          </div>
        )}
        </div>
      </div>
    </div>
  )
}
