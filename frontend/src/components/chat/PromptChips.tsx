import { ImagePlus } from "lucide-react"
import type { PromptExample } from "@/lib/promptExamples"
import { promptExampleKey } from "@/lib/promptExamples"
import { cn } from "@/lib/utils"

interface PromptChipsProps {
  suggestions: PromptExample[]
  onSelect: (example: PromptExample) => void
  className?: string
}

export function PromptChips({
  suggestions,
  onSelect,
  className,
}: PromptChipsProps) {
  if (suggestions.length === 0) return null

  return (
    <div className={cn("flex flex-wrap justify-center gap-1.5 sm:gap-2", className)}>
      {suggestions.map((example) => (
        <button
          key={promptExampleKey(example)}
          type="button"
          className="inline-flex max-w-full items-center gap-1.5 rounded-full border bg-card px-3 py-1.5 text-left text-xs transition-colors hover:bg-accent sm:px-4 sm:py-2 sm:text-center sm:text-sm"
          onClick={() => onSelect(example)}
        >
          {example.type === "image" && (
            <ImagePlus className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )}
          {example.text}
        </button>
      ))}
    </div>
  )
}
