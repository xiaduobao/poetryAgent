import { cn } from "@/lib/utils"

interface PromptChipsProps {
  suggestions: string[]
  onSelect: (text: string) => void
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
      {suggestions.map((text) => (
        <button
          key={text}
          type="button"
          className="max-w-full rounded-full border bg-card px-3 py-1.5 text-left text-xs transition-colors hover:bg-accent sm:px-4 sm:py-2 sm:text-center sm:text-sm"
          onClick={() => onSelect(text)}
        >
          {text}
        </button>
      ))}
    </div>
  )
}
