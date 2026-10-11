"use client"

import { ServerCrash, LoaderCircle } from "lucide-react"
import { useI18n } from "@/core/i18n/i18n-provider"
import { useBackendStatus } from "@/hooks/use-backend-status"

/** 后端首次上线前的全屏遮罩；上线后即使掉线也不遮挡，交由 socket 静默重连。 */
export function BackendOverlay() {
  const { status, failures, everOnline } = useBackendStatus()
  const { t } = useI18n()

  // 从未连上时才显示遮罩（含首次探测中），第一帧就出现；
  // 曾经连上过则不再遮挡，断线由 socket 自动重连处理
  if (status === "online" || everOnline) return null

  // 视为后端启动中；启动一段时间后仍失败则提示检查后端
  const starting = failures <= 2
  const title = starting
    ? t("backend.startingTitle", "后端服务启动中")
    : t("backend.unreachableTitle", "无法连接后端服务")
  const desc = starting
    ? t("backend.startingDesc", "正在等待后端服务就绪，请稍候…")
    : t("backend.unreachableDesc", "请确认后端服务已启动，前端将自动重试连接。")

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-background/80 backdrop-blur-sm animate-in fade-in duration-300"
      role="alert"
      aria-live="assertive"
    >
      <div className="flex flex-col items-center gap-4 rounded-xl border border-border bg-card px-10 py-8 shadow-lg">
        <div className="relative">
          <div className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <LoaderCircle className="size-6 animate-spin" />
          </div>
          {!starting && (
            <ServerCrash className="absolute -bottom-1 -right-1 size-5 rounded-full bg-card p-0.5 text-destructive" />
          )}
        </div>
        <div className="flex flex-col items-center gap-1 text-center">
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="max-w-xs text-sm text-muted-foreground">{desc}</p>
        </div>
      </div>
    </div>
  )
}
