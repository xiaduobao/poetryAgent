export type PromptExample =
  | { type: "text"; text: string }
  | { type: "image"; text: string; hint?: string }

export const PROMPT_EXAMPLES: PromptExample[] = [
  { type: "text", text: "请赏析《登高》" },
  { type: "text", text: "介绍杜甫" },
  { type: "text", text: "李白和杜甫的诗歌风格有什么区别？" },
  { type: "text", text: "查找《枫桥夜泊》的原文和注释" },
  { type: "text", text: "推荐几首关于思乡的诗" },
  { type: "text", text: "「渚清沙白」中的「渚」是什么意思？" },
  { type: "text", text: "帮我写一首关于春天的五言绝句" },
  {
    type: "image",
    text: "上传风景照，写一首五言绝句",
    hint: "请先选择一张风景照片，再点击发送",
  },
]

export function promptExampleKey(example: PromptExample): string {
  return example.text
}

export function asTextPrompt(text: string): PromptExample {
  return { type: "text", text }
}

export function resolvePromptExample(text: string): PromptExample {
  return PROMPT_EXAMPLES.find((item) => item.text === text) ?? asTextPrompt(text)
}

const INTENT_FOLLOW_UPS: Record<string, string[]> = {
  tool_writing: [
    "帮我改成七言绝句",
    "解释一下其中用到的典故",
    "推荐几首类似主题的古诗",
  ],
  rag: [
    "分析一下这首诗的格律",
    "作者还有哪些代表作？",
    "诗中有什么典故？",
  ],
  tool_author: [
    "推荐几首这位诗人的代表作",
    "和李白比，风格有什么不同？",
  ],
  tool_theme: [
    "再推荐几首其他的",
    "帮我赏析其中一首",
  ],
  tool_lookup: [
    "请赏析这首诗",
    "分析这首诗的格律",
    "解释诗中的典故",
  ],
  tool_meter: [
    "这首诗表达了什么情感？",
    "作者创作背景是什么？",
  ],
  tool_compare: [
    "再推荐几首相关主题的诗",
    "帮我写一首类似风格的诗",
  ],
  tool_allusion: [
    "还有哪些诗用到这个典故？",
    "推荐几首相关主题的诗",
  ],
  chat: [
    "推荐几首关于思乡的诗",
    "请赏析《登高》",
  ],
}

const THEME_PAIRS: [RegExp, string][] = [
  [/春|春天|春日/, "推荐几首关于秋天的诗"],
  [/秋|秋天|秋日/, "推荐几首关于春天的诗"],
  [/思乡|故乡|归家/, "推荐几首关于离别的诗"],
  [/离别|送别|别离/, "推荐几首关于思乡的诗"],
  [/爱情|相思|闺怨/, "推荐几首关于友情的诗"],
  [/友情|知己|赠别/, "推荐几首关于思乡的诗"],
]

function extractPoemTitle(text: string): string | null {
  const match = text.match(/《([^》]+)》/)
  return match?.[1] ?? null
}

function wasAsked(text: string, recentUserTexts: string[]): boolean {
  const normalized = text.trim()
  return recentUserTexts.some(
    (u) => u.includes(normalized) || normalized.includes(u.trim()),
  )
}

function contextFollowUps(userText: string, assistantText: string): string[] {
  const suggestions: string[] = []
  const combined = `${userText} ${assistantText}`

  const poem = extractPoemTitle(combined)
  if (poem) {
    suggestions.push(`请赏析《${poem}》`)
    suggestions.push(`《${poem}》的作者是谁？`)
  }

  for (const [pattern, followUp] of THEME_PAIRS) {
    if (pattern.test(combined)) {
      suggestions.push(followUp)
    }
  }

  return suggestions
}

export function getFollowUpSuggestions(
  messages: { role: string; content: string; intent?: string | null }[],
  max = 3,
): PromptExample[] {
  if (messages.length === 0) return []

  const recentUserTexts = messages
    .filter((m) => m.role === "user")
    .slice(-5)
    .map((m) => m.content)

  const lastAssistant = [...messages]
    .reverse()
    .find((m) => m.role === "assistant" && m.content.trim())

  const lastUser = [...messages]
    .reverse()
    .find((m) => m.role === "user")

  const candidates: PromptExample[] = []

  if (lastAssistant?.intent && INTENT_FOLLOW_UPS[lastAssistant.intent]) {
    candidates.push(
      ...INTENT_FOLLOW_UPS[lastAssistant.intent].map(asTextPrompt),
    )
  }

  if (lastUser && lastAssistant) {
    candidates.push(
      ...contextFollowUps(lastUser.content, lastAssistant.content).map(
        asTextPrompt,
      ),
    )
  }

  candidates.push(...PROMPT_EXAMPLES)

  const seen = new Set<string>()
  const result: PromptExample[] = []

  for (const example of candidates) {
    const trimmed = example.text.trim()
    if (!trimmed || seen.has(trimmed)) continue
    if (wasAsked(trimmed, recentUserTexts)) continue
    seen.add(trimmed)
    result.push(example)
    if (result.length >= max) break
  }

  return result
}
