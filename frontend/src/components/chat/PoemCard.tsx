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
  const author = formatMetaValue(data.author)
  const genre = formatMetaValue(data.genre)
  const metaParts = [author, data.dynasty, genre, data.theme].filter(
    (v): v is string => Boolean(v),
  )

  const appreciation = data.appreciation
    ?.split("\n")
    .map((p) => p.trim())
    .filter(Boolean)

  const hasFooter =
    (data.famous_lines && data.famous_lines.length > 0) ||
    (appreciation && appreciation.length > 0)

  return (
    <section className="poem-card not-prose" aria-label="诗作">
      {(data.title || metaParts.length > 0) && (
        <header className="poem-card-header">
          {data.title && (
            <h3 className="poem-card-title [overflow-wrap:anywhere]">
              {data.title}
            </h3>
          )}
          {metaParts.length > 0 && (
            <div className="poem-card-meta">
              {metaParts.map((part, i) => (
                <span key={part} className="inline-flex items-center gap-1.5">
                  {i > 0 && <MetaDivider />}
                  <MetaChip label={part} />
                </span>
              ))}
            </div>
          )}
        </header>
      )}

      {data.lines && data.lines.length > 0 && (
        <div className="poem-card-body">
          {data.lines.map((line, i) => (
            <p key={`line-${i}`} className="[overflow-wrap:anywhere]">
              {line}
            </p>
          ))}
        </div>
      )}

      {hasFooter && (
        <footer className="poem-card-footer space-y-2.5">
          {data.famous_lines && data.famous_lines.length > 0 && (
            <div className="space-y-1">
              {data.famous_lines.map((line, i) => (
                <p
                  key={`famous-${i}`}
                  className="poem-card-quote [overflow-wrap:anywhere]"
                >
                  {line}
                </p>
              ))}
            </div>
          )}

          {appreciation && appreciation.length > 0 && (
            <div className="space-y-1.5">
              {appreciation.map((para, i) => (
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
    </section>
  )
}
