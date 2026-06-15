import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

interface AuthPageProps {
  mode: "login" | "register"
  onSubmit: (email: string, password: string) => Promise<void>
  onGuestEnter: () => Promise<void>
  onToggleMode: () => void
  error: string | null
}

export function AuthPage({
  mode,
  onSubmit,
  onGuestEnter,
  onToggleMode,
  error,
}: AuthPageProps) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [guestLoading, setGuestLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await onSubmit(email, password)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm space-y-6 rounded-xl border bg-card p-8 shadow-sm">
        <div className="space-y-1 text-center">
          <h1 className="text-xl font-semibold">古典诗词鉴赏助手</h1>
          <p className="text-sm text-muted-foreground">
            {mode === "login" ? "登录您的账户" : "创建新账户"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="email" className="text-sm font-medium">
              邮箱
            </label>
            <Input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="password" className="text-sm font-medium">
              密码
            </label>
            <Input
              id="password"
              type="password"
              required
              minLength={8}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="至少 8 位"
            />
          </div>

          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" className="w-full" disabled={submitting || guestLoading}>
            {submitting ? "请稍候…" : mode === "login" ? "登录" : "注册"}
          </Button>
        </form>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-card px-2 text-muted-foreground">或</span>
          </div>
        </div>

        <Button
          type="button"
          variant="outline"
          className="w-full"
          disabled={submitting || guestLoading}
          onClick={async () => {
            setGuestLoading(true)
            try {
              await onGuestEnter()
            } finally {
              setGuestLoading(false)
            }
          }}
        >
          {guestLoading ? "请稍候…" : "以游客身份继续"}
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          游客模式可体验对话，每日次数有限，对话记录仅保存在当前浏览器会话
        </p>

        <p className="text-center text-sm text-muted-foreground">
          {mode === "login" ? "还没有账户？" : "已有账户？"}
          <button
            type="button"
            className="ml-1 text-primary underline-offset-4 hover:underline"
            onClick={onToggleMode}
          >
            {mode === "login" ? "立即注册" : "去登录"}
          </button>
        </p>
      </div>
    </div>
  )
}
