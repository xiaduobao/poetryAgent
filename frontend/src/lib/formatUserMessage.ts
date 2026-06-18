/** 将用户消息内容格式化为适合 UI 展示的文本。 */
export function formatUserDisplay(content: string): string {
  const text = content.trim()
  if (!text) return text

  if (text.startsWith("【看图创作】")) {
    const requestMatch = text.match(/用户要求：(.+)/s)
    if (requestMatch?.[1]?.trim()) {
      return requestMatch[1].trim()
    }
    const descMatch = text.match(/画面描述：(.+)/s)
    if (descMatch?.[1]?.trim()) {
      return `[看图] ${descMatch[1].trim().slice(0, 80)}…`
    }
  }

  return text.replace(/^\[已上传图片\]\n?/, "").trim() || text
}
