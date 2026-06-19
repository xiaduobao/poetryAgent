import { useState } from "react"
import {
  MessageSquarePlus,
  MoreHorizontal,
  Pencil,
  Search,
  Trash2,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn, formatRelativeTime, groupSessionsByDate } from "@/lib/utils"
import { GithubRepoLink } from "@/components/GithubRepoLink"
import type { Session } from "@/types"

interface SessionSidebarProps {
  sessions: Session[]
  loading: boolean
  query: string
  onQueryChange: (q: string) => void
  activeId: string | null
  onSelect: (id: string) => void
  onCreate: () => void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void
  className?: string
  onClose?: () => void
}

export function SessionSidebar({
  sessions,
  loading,
  query,
  onQueryChange,
  activeId,
  onSelect,
  onCreate,
  onRename,
  onDelete,
  className,
  onClose,
}: SessionSidebarProps) {
  const [renameTarget, setRenameTarget] = useState<Session | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [deleteTarget, setDeleteTarget] = useState<Session | null>(null)

  const groups = groupSessionsByDate(sessions)

  const openRename = (session: Session) => {
    setRenameTarget(session)
    setRenameValue(session.title)
  }

  const confirmRename = async () => {
    if (!renameTarget || !renameValue.trim()) return
    await onRename(renameTarget.id, renameValue.trim())
    setRenameTarget(null)
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    await onDelete(deleteTarget.id)
    setDeleteTarget(null)
  }

  return (
    <aside
      className={cn(
        "flex h-full w-72 max-w-[min(18rem,85vw)] shrink-0 flex-col border-r",
        onClose ? "bg-background" : "bg-muted/30",
        className,
      )}
    >
      <div className="safe-area-top flex items-center gap-2 border-b p-3">
        <Button className="flex-1" onClick={onCreate}>
          <MessageSquarePlus className="h-4 w-4" />
          新建对话
        </Button>
        {onClose && (
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0 md:hidden"
            onClick={onClose}
            aria-label="关闭侧边栏"
          >
            <X className="h-5 w-5" />
          </Button>
        )}
      </div>

      <div className="relative px-3 py-2">
        <Search className="absolute left-5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-8"
          placeholder="搜索历史会话…"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
        />
      </div>

      <ScrollArea className="flex-1 px-2">
        {loading && sessions.length === 0 && (
          <p className="px-2 py-4 text-center text-sm text-muted-foreground">
            加载中…
          </p>
        )}
        {!loading && sessions.length === 0 && (
          <p className="px-2 py-4 text-center text-sm text-muted-foreground">
            {query ? "无匹配会话" : "暂无会话，点击上方新建"}
          </p>
        )}

        {groups.map((group) => (
          <div key={group.label} className="mb-3">
            <p className="px-2 py-1 text-xs font-medium text-muted-foreground">
              {group.label}
            </p>
            {group.items.map((session) => (
              <div
                key={session.id}
                className={cn(
                  "group mb-0.5 flex items-center rounded-md",
                  activeId === session.id && "bg-accent",
                )}
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 px-2 py-2 text-left"
                  onClick={() => onSelect(session.id)}
                >
                  <p className="truncate text-sm font-medium">{session.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatRelativeTime(session.updated_at)}
                  </p>
                </button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="mr-1 h-8 w-8 shrink-0 opacity-100 md:opacity-0 md:group-hover:opacity-100"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => openRename(session)}>
                      <Pencil className="mr-2 h-4 w-4" />
                      重命名
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="text-destructive focus:text-destructive"
                      onClick={() => setDeleteTarget(session)}
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      删除
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            ))}
          </div>
        ))}
      </ScrollArea>

      <div className="safe-area-bottom shrink-0 border-t px-3 py-2.5">
        <GithubRepoLink
          className="w-full justify-center text-xs"
          label="GitHub 项目 README"
        />
      </div>

      <Dialog open={!!renameTarget} onOpenChange={() => setRenameTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重命名会话</DialogTitle>
          </DialogHeader>
          <Input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && confirmRename()}
            autoFocus
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameTarget(null)}>
              取消
            </Button>
            <Button onClick={confirmRename}>保存</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除会话</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            确定删除「{deleteTarget?.title}」？此操作不可恢复。
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button variant="destructive" onClick={confirmDelete}>
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </aside>
  )
}
