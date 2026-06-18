import { INTENT_LABELS } from "@/types"
import type { Message, SubIntent } from "@/types"

export interface IntentBadge {
  key: string
  intent: string
  label: string
}

/** 从消息中提取要展示的全部意图标签（多主题时逐个展示，去重保留顺序） */
export function getIntentBadges(message: Message): IntentBadge[] {
  const subs: SubIntent[] = message.sub_intents?.length
    ? message.sub_intents
    : message.intent
      ? [{ text: "", intent: message.intent }]
      : []

  const seen = new Set<string>()
  const badges: IntentBadge[] = []

  for (let i = 0; i < subs.length; i++) {
    const sub = subs[i]
    if (!sub.intent) continue
    if (seen.has(sub.intent)) continue
    seen.add(sub.intent)
    badges.push({
      key: `${sub.intent}-${i}`,
      intent: sub.intent,
      label: INTENT_LABELS[sub.intent] || sub.intent,
    })
  }

  return badges
}
