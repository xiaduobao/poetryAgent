import { Check, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import type { HitlInterrupt } from "@/types"
import { INTENT_LABELS } from "@/types"

interface HitlApprovalCardProps {
  interrupt: HitlInterrupt
  loading?: boolean
  onApprove: () => void
  onReject: () => void
}

export function HitlApprovalCard({
  interrupt,
  loading,
  onApprove,
  onReject,
}: HitlApprovalCardProps) {
  const intentLabel = INTENT_LABELS[interrupt.intent] || interrupt.intent

  return (
    <div className="mx-auto w-full max-w-3xl px-3 sm:px-4">
      <div className="rounded-2xl border border-amber-500/40 bg-amber-50/80 p-4 dark:bg-amber-950/20">
        <p className="text-sm font-medium text-foreground">{interrupt.message}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="text-xs">
            {intentLabel}
          </Badge>
        </div>
        <ul className="mt-3 space-y-2">
          {interrupt.tool_calls.map((tc) => (
            <li
              key={tc.id || tc.name}
              className="rounded-lg border bg-background/80 px-3 py-2 text-sm"
            >
              <span className="font-medium">{tc.label}</span>
              <span className="mt-0.5 block text-muted-foreground">{tc.summary}</span>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" onClick={onApprove} disabled={loading}>
            <Check className="mr-1.5 h-4 w-4" />
            允许执行
          </Button>
          <Button size="sm" variant="outline" onClick={onReject} disabled={loading}>
            <X className="mr-1.5 h-4 w-4" />
            拒绝
          </Button>
        </div>
      </div>
    </div>
  )
}
