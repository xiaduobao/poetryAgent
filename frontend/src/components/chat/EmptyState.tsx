const EXAMPLES = [
  "请赏析《登高》",
  "介绍杜甫",
  "李白和杜甫的诗歌风格有什么区别？",
  "查找《枫桥夜泊》的原文和注释",
  "推荐几首关于思乡的诗",
  "「渚清沙白」中的「渚」是什么意思？",
  "帮我写一首关于春天的五言绝句",
]

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
      <div className="flex flex-wrap justify-center gap-3">
        {EXAMPLES.map((text) => (
          <button
            key={text}
            type="button"
            className="rounded-full border bg-card px-4 py-2 text-sm transition-colors hover:bg-accent"
            onClick={() => onExampleClick(text)}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  )
}
