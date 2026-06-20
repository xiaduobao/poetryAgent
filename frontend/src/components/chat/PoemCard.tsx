import { ChevronDown, ChevronUp } from "lucide-react"
import { useId, useState } from "react"
import {
  formatMetaValue,
  type PoemStructuredData,
} from "@/lib/parseStructuredOutput"

interface PoemCardProps {
  data: PoemStructuredData
}

function MetaChip({ label }: { label: string }) {
  return (
    <span className="text-[11px] text-muted-foreground sm:text-xs">
      {label}
    </span>
  )
}

function MetaDivider() {
  return <span className="text-muted-foreground/40" aria-hidden>·</span>
}

export function PoemCard({ data }: PoemCardProps) {
  const [open, setOpen] = useState(false)
  const contentId = useId()

  const author = formatMetaValue(data.author)
  const genre = formatMetaValue(data.genre)
  const metaParts = [author, data.dynasty, genre, data.theme].filter(
    (v): v is string => Boolean(v),
  )

  const appreciation = data.appreciation
    ?.split("\n")
    .map((p) => p.trim())
    .filter(Boolean)

  const hasBody = Boolean(data.lines?.length)
  const hasFamousLines = Boolean(data.famous_lines?.length)
  const hasAppreciation = Boolean(appreciation?.length)
  const hasFooter = hasFamousLines || hasAppreciation
  const hasExpandableContent = hasBody || hasFooter

  return (
    <section className="poem-card not-prose" aria-label="诗作卡片">
      <button
        type="button"
        className="poem-card-toggle"
        aria-expanded={open}
        aria-controls={hasExpandableContent ? contentId : undefined}
        onClick={() => hasExpandableContent && setOpen((v) => !v)}
        disabled={!hasExpandableContent}
      >
        <span className="poem-card-toggle-main min-w-0">
          {data.title && (
            <span className="poem-card-title [overflow-wrap:anywhere]">
              {data.title}
            </span>
          )}
          {metaParts.length > 0 && (
            <span className="poem-card-meta">
              {metaParts.map((part, i) => (
                <span key={part} className="inline-flex items-center gap-1.5">
                  {i > 0 && <MetaDivider />}
                  <MetaChip label={part} />
                </span>
              ))}
            </span>
          )}
          {!data.title && metaParts.length === 0 && (
            <span className="text-xs text-muted-foreground">鉴赏卡片</span>
          )}
        </span>
        {hasExpandableContent && (
          <span className="poem-card-toggle-icon shrink-0 text-muted-foreground">
            {open ? (
              <ChevronUp className="h-4 w-4" aria-hidden />
            ) : (
              <ChevronDown className="h-4 w-4" aria-hidden />
            )}
          </span>
        )}
      </button>

      {open && hasExpandableContent && (
        <div id={contentId} className="poem-card-content">
          {hasBody && (
            <div className="poem-card-body">
              {data.lines!.map((line, i) => (
                <p key={`line-${i}`} className="[overflow-wrap:anywhere]">
                  {line}
                </p>
              ))}
            </div>
          )}

          {hasFooter && (
            <footer className="poem-card-footer space-y-2.5">
              {hasFamousLines && (
                <div className="space-y-1.5">
                  <p className="poem-card-famous-label">
                    代表名句（节选，非全文）
                  </p>
                  <div className="space-y-1">
                    {data.famous_lines!.map((line, i) => (
                      <p
                        key={`famous-${i}`}
                        className="poem-card-quote [overflow-wrap:anywhere]"
                      >
                        {line}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {hasAppreciation && (
                <div className="space-y-1.5">
                  {appreciation!.map((para, i) => (
                    <p
                      key={`app-${i}`}
                      className="poem-card-note [overflow-wrap:anywhere]"
                    >
                      {para}
                    </p>
                  ))}
                </div>
              )}
            </footer>
          )}
        </div>
      )}
    </section>
  )
}
