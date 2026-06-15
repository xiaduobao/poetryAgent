import { useState } from "react"
import { AppLayout } from "@/components/layout/AppLayout"
import { AuthPage } from "@/components/auth/AuthPage"
import { useAuth } from "@/hooks/useAuth"

function App() {
  const { user, loading, login, register } = useAuth()
  const [mode, setMode] = useState<"login" | "register">("login")
  const [error, setError] = useState<string | null>(null)

  if (loading) {
    return (
      <div className="flex min-h-svh items-center justify-center text-muted-foreground">
        加载中…
      </div>
    )
  }

  if (!user) {
    return (
      <AuthPage
        mode={mode}
        error={error}
        onToggleMode={() => {
          setMode(mode === "login" ? "register" : "login")
          setError(null)
        }}
        onSubmit={async (email, password) => {
          setError(null)
          try {
            if (mode === "login") {
              await login(email, password)
            } else {
              await register(email, password)
            }
          } catch (e) {
            setError(e instanceof Error ? e.message : "操作失败")
          }
        }}
      />
    )
  }

  return <AppLayout />
}

export default App
