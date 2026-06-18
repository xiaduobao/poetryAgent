import { PROMPT_EXAMPLES, type PromptExample } from "@/lib/promptExamples"
import { PromptChips } from "./PromptChips"

interface EmptyStateProps {
  onExampleClick: (example: PromptExample) => void
}

export function EmptyState({ onExampleClick }: EmptyStateProps) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center px-2 text-center sm:min-h-[50vh]">
      <h2 className="mb-2 text-xl font-semibold sm:text-2xl">古典诗词鉴赏智能助手</h2>
      <p className="mb-6 max-w-md text-sm text-muted-foreground sm:mb-8 sm:text-base">
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
