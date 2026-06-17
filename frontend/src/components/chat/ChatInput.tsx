import { useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react"
import { ImagePlus, Loader2, Send, Square, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { PromptChips } from "./PromptChips"

const MAX_IMAGE_BYTES = 4 * 1024 * 1024
const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]

interface ChatInputProps {
  onSend: (text: string, imageBase64?: string) => void
  onStop: () => void
  streaming: boolean
  maxLength: number
  draft: string
  onDraftChange: (text: string) => void
  suggestions?: string[]
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      if (typeof result !== "string") {
        reject(new Error("无法读取图片"))
        return
      }
      const base64 = result.includes(",") ? result.split(",")[1] : result
      resolve(base64)
    }
    reader.onerror = () => reject(new Error("无法读取图片"))
    reader.readAsDataURL(file)
  })
}

export function ChatInput({
  onSend,
  onStop,
  streaming,
  maxLength,
  draft,
  onDraftChange,
  suggestions = [],
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [focused, setFocused] = useState(false)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [imageBase64, setImageBase64] = useState<string | null>(null)
  const [imageError, setImageError] = useState<string | null>(null)

  const overLimit = draft.length > maxLength
  const canSend =
    (draft.trim().length > 0 || Boolean(imageBase64)) &&
    !overLimit &&
    !streaming &&
    !imageError

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    const lineHeight = 24
    const maxHeight = lineHeight * 6
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`
  }, [draft])

  const clearImage = () => {
    if (imagePreview) {
      URL.revokeObjectURL(imagePreview)
    }
    setImagePreview(null)
    setImageBase64(null)
    setImageError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const handleImageSelect = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setImageError(null)

    if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
      setImageError("仅支持 JPEG、PNG、WebP 格式")
      if (fileInputRef.current) fileInputRef.current.value = ""
      return
    }

    if (file.size > MAX_IMAGE_BYTES) {
      setImageError("图片大小不能超过 4MB")
      if (fileInputRef.current) fileInputRef.current.value = ""
      return
    }

    try {
      if (imagePreview) {
        URL.revokeObjectURL(imagePreview)
      }
      const base64 = await readFileAsBase64(file)
      setImageBase64(base64)
      setImagePreview(URL.createObjectURL(file))
    } catch {
      setImageError("图片读取失败，请重试")
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  const submit = () => {
    if (!canSend) return
    onSend(draft, imageBase64 || undefined)
    onDraftChange("")
    clearImage()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const handleSuggestionSelect = (text: string) => {
    onDraftChange(text)
    textareaRef.current?.focus()
  }

  const showSuggestions =
    suggestions.length > 0 && !draft.trim() && !imageBase64 && !streaming

  return (
    <div className="border-t bg-background p-4">
      {showSuggestions && (
        <PromptChips
          suggestions={suggestions}
          onSelect={handleSuggestionSelect}
          className="mx-auto mb-3 max-w-3xl"
        />
      )}
      <div
        className={cn(
          "mx-auto max-w-3xl rounded-2xl border bg-card p-3 shadow-sm transition-shadow",
          focused && "ring-2 ring-ring/20",
        )}
      >
        {imagePreview && (
          <div className="relative mb-3 inline-block">
            <img
              src={imagePreview}
              alt="待发送图片预览"
              className="h-20 w-20 rounded-lg border object-cover"
            />
            {!streaming && (
              <Button
                type="button"
                variant="secondary"
                size="icon"
                className="absolute -right-2 -top-2 h-6 w-6 rounded-full"
                onClick={clearImage}
                aria-label="移除图片"
              >
                <X className="h-3 w-3" />
              </Button>
            )}
          </div>
        )}
        {imageError && (
          <p className="mb-2 text-xs text-destructive">{imageError}</p>
        )}
        <Textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="输入问题，或上传图片作诗… Shift+Enter 换行，Enter 发送"
          rows={1}
          className="min-h-[44px] resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
          disabled={streaming}
        />
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_IMAGE_TYPES.join(",")}
              className="hidden"
              onChange={handleImageSelect}
              disabled={streaming}
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={streaming}
              onClick={() => fileInputRef.current?.click()}
              title="上传图片作诗"
            >
              <ImagePlus className="mr-1 h-4 w-4" />
              图片
            </Button>
            {(draft || imageBase64) && !streaming && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  onDraftChange("")
                  clearImage()
                }}
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
              <Button size="sm" disabled={!canSend} onClick={submit}>
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
