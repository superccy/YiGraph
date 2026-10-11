"use client"

import * as React from "react"
import { Plus, MessageCircle, Trash2, Clock } from "lucide-react"
import { useI18n } from "@/core/i18n/i18n-provider"
import type { ChatSession } from "@/core/types"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/core/utils"

export function ChatHistory({
  sessions,
  activeId,
  onSelect,
  onCreate,
  onDelete,
}: {
  sessions: ChatSession[]
  activeId: string | null
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
}) {
  const { t, lang } = useI18n()
  const [mounted, setMounted] = React.useState(false)
  React.useEffect(() => setMounted(true), [])
  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-border bg-card/30">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <div className="text-sm font-semibold">{t("chat.history", "会话历史")}</div>
          <div className="text-[11px] text-muted-foreground">
            {t("chat.sessionCount", "{count} 条记录").replace("{count}", String(sessions.length))}
          </div>
        </div>
        <Button size="sm" className="gap-1.5" onClick={onCreate}>
          <Plus className="size-3.5" />
          {t("chat.newChat", "新会话")}
        </Button>
      </div>

      <ScrollArea className="flex-1 min-h-0">
        <ul className="flex flex-col gap-1 p-2">
          {sessions.map((s) => {
            const isActive = s.id === activeId
            const preview =
              s.messages.find((m) => m.role === "user")?.content ??
              t("chat.noMessages", "尚未开始，点击输入你的第一个问题")
            return (
              <li key={s.id}>
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(s.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault()
                      onSelect(s.id)
                    }
                  }}
                  className={cn(
                    "group relative w-full cursor-pointer rounded-md border border-transparent px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    isActive
                      ? "border-primary/30 bg-primary/5"
                      : "hover:bg-muted",
                  )}
                >
                  <div className="flex items-start gap-2.5">
                    <div
                      className={cn(
                        "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md",
                        isActive
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground",
                      )}
                    >
                      <MessageCircle className="size-3.5" />
                    </div>
                    <div className="min-w-0 flex-1 pr-6">
                      <div className="truncate text-sm font-medium text-foreground">
                        {s.title || t("chat.heading")}
                      </div>
                      <div className="truncate text-[11px] text-muted-foreground">
                        {preview}
                      </div>
                      <div className="mt-1 flex items-center gap-1 text-[10px] text-muted-foreground/80">
                        <Clock className="size-3" />
                        <span suppressHydrationWarning>
                          {mounted ? formatTime(s.createdAt, t, lang) : ""}
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        onDelete(s.id)
                      }}
                      className="absolute right-2 top-2 hidden size-6 items-center justify-center rounded text-muted-foreground hover:bg-destructive/10 hover:text-destructive group-hover:flex"
                      aria-label={t("chat.deleteSession", "删除会话")}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
              </li>
            )
          })}

          {sessions.length === 0 && (
            <div className="px-3 py-10 text-center text-xs text-muted-foreground">
              {t("chat.noSessions", "暂无会话，点击右上角新建。")}
            </div>
          )}
        </ul>
      </ScrollArea>
    </aside>
  )
}

function formatTime(iso: string, t: (key: string, fallback?: string) => string, lang: string) {
  let d: Date
  if (iso.startsWith("offset:")) {
    const offset = Number(iso.slice("offset:".length))
    d = new Date(Date.now() + offset)
  } else {
    d = new Date(iso)
  }
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const h = diffMs / 3600_000
  if (h < 1) return t("time.minutesAgo", "{n} 分钟前").replace("{n}", String(Math.max(1, Math.round(diffMs / 60_000))))
  if (h < 24) return t("time.hoursAgo", "{n} 小时前").replace("{n}", String(Math.round(h)))
  const days = Math.round(h / 24)
  if (days < 7) return t("time.daysAgo", "{n} 天前").replace("{n}", String(days))
  return d.toLocaleDateString(lang === "en-US" ? "en-US" : "zh-CN")
}
