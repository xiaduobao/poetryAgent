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
    <div className={cn("flex flex-wrap justify-center gap-2", className)}>
      {suggestions.map((text) => (
        <button
          key={text}
          type="button"
          className="rounded-full border bg-card px-4 py-2 text-sm transition-colors hover:bg-accent"
          onClick={() => onSelect(text)}
        >
          {text}
        </button>
      ))}
    </div>
  )
}
