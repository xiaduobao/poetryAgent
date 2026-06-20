export interface SourceRef {
  title?: string
  author?: string
  snippet?: string
  source_file?: string
}

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface SubIntent {
  text: string
  intent: string
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  intent?: string | null
  sub_intents?: SubIntent[] | null
  is_compound?: boolean
  sources?: SourceRef[]
  created_at: string
}

export interface SessionDetail extends Session {
  messages: Message[]
}

export type StreamPhase =
  | "classifying"
  | "decomposing"
  | "executing"
  | "describing"
  | "retrieving"
  | "tooling"
  | "generating"
  | "awaiting_approval"
  | "idle"
  | "error"

export interface HitlToolCall {
  id?: string
  name: string
  args: Record<string, unknown>
  label: string
  summary: string
}

export interface HitlInterrupt {
  type: "tool_approval"
  thread_id: string
  session_id: string
  intent: string
  tool_calls: HitlToolCall[]
  message: string
}

export const PHASE_LABELS: Record<StreamPhase, string> = {
  classifying: "正在理解问题…",
  decomposing: "正在拆解问题…",
  executing: "正在处理多个子任务…",
  describing: "正在理解画面…",
  retrieving: "正在检索知识库…",
  tooling: "正在调用工具…",
  generating: "正在生成回答…",
  awaiting_approval: "等待你的确认…",
  idle: "",
  error: "出错了",
}

export const INTENT_LABELS: Record<string, string> = {
  rag: "诗词鉴赏",
  tool_author: "作者查询",
  tool_meter: "格律分析",
  tool_compare: "风格对比",
  tool_lookup: "诗词检索",
  tool_theme: "主题推荐",
  tool_allusion: "典故释义",
  tool_writing: "创作辅助",
  chat: "闲聊",
}
