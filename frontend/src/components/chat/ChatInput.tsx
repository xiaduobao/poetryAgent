import { useEffect, useRef, useState, type ChangeEvent, type DragEvent, type KeyboardEvent } from "react"
import { ImagePlus, Loader2, Send, Square, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { GithubRepoLink } from "@/components/GithubRepoLink"
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
  const dragCounterRef = useRef(0)
  const [focused, setFocused] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
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

  const processImageFile = async (file: File) => {
    if (streaming) return

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

  const handleImageSelect = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    await processImageFile(file)
  }

  const hasImageFiles = (e: DragEvent) =>
    Array.from(e.dataTransfer?.types ?? []).includes("Files")

  const handleDragEnter = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    if (streaming || !hasImageFiles(e)) return
    dragCounterRef.current += 1
    setIsDragging(true)
  }

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    if (!hasImageFiles(e)) return
    dragCounterRef.current -= 1
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0
      setIsDragging(false)
    }
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const handleDrop = async (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current = 0
    setIsDragging(false)
    if (streaming) return

    const file = Array.from(e.dataTransfer.files).find((f) =>
      ACCEPTED_IMAGE_TYPES.includes(f.type),
    )
    if (!file) {
      setImageError("仅支持 JPEG、PNG、WebP 格式")
      return
    }
    await processImageFile(file)
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
    const trimmed = text.trim()
    if (streaming || !trimmed || trimmed.length > maxLength) return
    onSend(trimmed)
    onDraftChange("")
    clearImage()
  }

  const showSuggestions =
    suggestions.length > 0 && !draft.trim() && !imageBase64 && !streaming

  return (
    <div className="safe-area-bottom border-t bg-background p-2 sm:p-4">
      {showSuggestions && (
        <PromptChips
          suggestions={suggestions}
          onSelect={handleSuggestionSelect}
          className="mx-auto mb-2 max-w-3xl sm:mb-3"
        />
      )}
      <div
        className={cn(
          "relative mx-auto max-w-3xl rounded-2xl border bg-card p-2 shadow-sm transition-shadow sm:p-3",
          focused && "ring-2 ring-ring/20",
          isDragging && "border-primary ring-2 ring-primary/30",
        )}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        {isDragging && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-primary/5">
            <p className="flex items-center gap-2 text-sm font-medium text-primary">
              <ImagePlus className="h-4 w-4" />
              松开以添加图片
            </p>
          </div>
        )}
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
          placeholder="输入问题，或拖拽/上传图片…"
          rows={1}
          className="min-h-[40px] resize-none border-0 bg-transparent text-base shadow-none focus-visible:ring-0 sm:min-h-[44px] sm:text-sm"
          disabled={streaming}
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-y-2">
          <div className="flex min-w-0 flex-1 items-center gap-1 sm:gap-2">
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
              className="h-9 px-2 sm:px-3"
              disabled={streaming}
              onClick={() => fileInputRef.current?.click()}
              title="上传图片作诗"
            >
              <ImagePlus className="h-4 w-4 sm:mr-1" />
              <span className="hidden sm:inline">图片</span>
            </Button>
            {(draft || imageBase64) && !streaming && (
              <Button
                variant="ghost"
                size="sm"
                className="h-9 px-2 sm:px-3"
                onClick={() => {
                  onDraftChange("")
                  clearImage()
                }}
              >
                <X className="h-3 w-3 sm:mr-1" />
                <span className="hidden sm:inline">清空</span>
              </Button>
            )}
            <span
              className={cn(
                "ml-auto text-[11px] sm:ml-0 sm:text-xs",
                overLimit ? "text-destructive" : "text-muted-foreground",
              )}
            >
              {draft.length}/{maxLength}
            </span>
          </div>
          <div className="flex shrink-0 gap-1 sm:gap-2">
            {streaming ? (
              <Button variant="outline" size="sm" className="h-9" onClick={onStop}>
                <Square className="h-3 w-3 fill-current sm:mr-1" />
                <span className="hidden sm:inline">停止</span>
              </Button>
            ) : (
              <Button size="sm" className="h-9" disabled={!canSend} onClick={submit}>
                {streaming ? (
                  <Loader2 className="h-4 w-4 animate-spin sm:mr-1" />
                ) : (
                  <Send className="h-4 w-4 sm:mr-1" />
                )}
                <span className="hidden sm:inline">发送</span>
              </Button>
            )}
          </div>
        </div>
      </div>
      <div className="mx-auto mt-2 flex max-w-3xl justify-center">
        <GithubRepoLink className="text-[11px] sm:text-xs" />
      </div>
    </div>
  )
}
