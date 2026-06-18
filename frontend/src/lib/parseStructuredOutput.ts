export interface PoemStructuredData {
  title?: string
  author?: string | string[]
  dynasty?: string
  genre?: string | string[]
  theme?: string
  famous_lines?: string[]
  lines?: string[]
  appreciation?: string
}

function isPoemStructuredData(value: unknown): value is PoemStructuredData {
  if (!value || typeof value !== "object") return false
  const obj = value as Record<string, unknown>
  return Boolean(
    obj.title ||
      obj.lines ||
      obj.famous_lines ||
      obj.appreciation ||
      obj.author ||
      obj.theme,
  )
}

export function parseStructuredOutput(content: string): {
  markdown: string
  structured: PoemStructuredData | null
} {
  const jsonBlockRegex = /```(?:json)?\s*\n([\s\S]*?)\n```\s*$/
  const match = content.match(jsonBlockRegex)
  if (!match || match.index === undefined) {
    return { markdown: content, structured: null }
  }

  try {
    const parsed: unknown = JSON.parse(match[1].trim())
    if (isPoemStructuredData(parsed)) {
      const markdown = content.slice(0, match.index).trimEnd()
      return {
        markdown: stripDuplicatedPoemFromMarkdown(markdown, parsed),
        structured: parsed,
      }
    }
  } catch {
    /* keep raw content */
  }

  return { markdown: content, structured: null }
}

export function formatMetaValue(value: string | string[] | undefined): string {
  if (!value) return ""
  return Array.isArray(value) ? value.join("、") : value
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

/** Remove poem lines already shown in the structured card from markdown body. */
export function stripDuplicatedPoemFromMarkdown(
  markdown: string,
  structured: PoemStructuredData,
): string {
  if (!structured.lines?.length) return markdown

  let result = markdown
  const linesToStrip = [
    ...structured.lines,
    ...(structured.famous_lines ?? []),
  ]

  for (const line of linesToStrip) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const core = escapeRegExp(trimmed)
    result = result.replace(
      new RegExp(`^\\s*(?:>\\s*)?${core}[，。、；：！？,.;:!?]?\\s*$`, "gm"),
      "",
    )
  }

  if (structured.title?.trim()) {
    const title = escapeRegExp(structured.title.trim())
    result = result.replace(new RegExp(`^#{1,4}\\s*${title}\\s*$`, "gm"), "")
    result = result.replace(new RegExp(`^\\*\\*${title}\\*\\*\\s*$`, "gm"), "")
    result = result.replace(new RegExp(`^${title}\\s*$`, "gm"), "")
  }

  result = result.replace(/^#{1,4}\s*(诗作|全文|成诗|创作结果|作品)\s*$/gm, "")
  result = result.replace(/^>\s*$/gm, "")
  result = result.replace(/\n{3,}/g, "\n\n").trim()

  return result
}

/** Hide trailing JSON block while content is still streaming. */
export function stripStreamingJsonBlock(content: string): string {
  const fenceStart = content.search(/```(?:json)?\s*\n/)
  if (fenceStart === -1) return content
  return content.slice(0, fenceStart).trimEnd()
}
