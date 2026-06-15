import { ChevronDown, ChevronUp, BookOpen } from "lucide-react"
import { useState } from "react"
import type { SourceRef } from "@/types"

interface SourcePanelProps {
  sources: SourceRef[]
}

export function SourcePanel({ sources }: SourcePanelProps) {
  const [open, setOpen] = useState(false)

  if (!sources.length) return null

  return (
    <div className="mt-2 rounded-lg border bg-muted/40 text-xs">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left text-muted-foreground hover:text-foreground"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="flex items-center gap-1.5">
          <BookOpen className="h-3.5 w-3.5" />
          引用来源 ({sources.length})
        </span>
        {open ? (
          <ChevronUp className="h-3.5 w-3.5" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" />
        )}
      </button>
      {open && (
        <ul className="space-y-2 border-t px-3 py-2">
          {sources.map((src, i) => (
            <li key={`${src.source_file || src.title}-${i}`} className="space-y-0.5">
              <p className="font-medium text-foreground">
                {src.title ? `《${src.title}》` : "参考资料"}
                {src.author ? ` · ${src.author}` : ""}
              </p>
              {src.snippet && (
                <p className="text-muted-foreground line-clamp-2">{src.snippet}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
