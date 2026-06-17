import { PROMPT_EXAMPLES } from "@/lib/promptExamples"
import { PromptChips } from "./PromptChips"

interface EmptyStateProps {
  onExampleClick: (text: string) => void
}

export function EmptyState({ onExampleClick }: EmptyStateProps) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center text-center">
      <h2 className="mb-2 text-2xl font-semibold">古典诗词鉴赏智能助手</h2>
      <p className="mb-8 max-w-md text-muted-foreground">
        我可以帮你赏析诗词、查询作者、分析格律、按主题推荐、解释典故，还能辅助创作。试试下面的示例：
      </p>
      <PromptChips
        suggestions={PROMPT_EXAMPLES}
        onSelect={onExampleClick}
        className="gap-3"
      />
    </div>
  )
}
