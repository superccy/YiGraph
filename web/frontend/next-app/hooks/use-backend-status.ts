"use client"

import * as React from "react"
import { ensureChatConnection } from "@/core/api/chat"
import { probeBackend } from "@/core/api/base"

const OFFLINE_POLL_MS = 2000
const ONLINE_POLL_MS = 10000
/** 在线后连续失败多少次才判定离线，避免网络抖动导致遮罩闪烁 */
const FAILURE_THRESHOLD = 2

export type BackendStatus = "checking" | "online" | "offline"

/**
 * 轮询后端 /api/health，返回后端连接状态。
 * 初始为 checking（遮罩自第一帧起显示），首次探测成功即进入 online（遮罩消失）；
 * 在线后需连续失败 FAILURE_THRESHOLD 次才重新判定为离线，避免抖动闪烁。
 */
export function useBackendStatus() {
  const [status, setStatus] = React.useState<BackendStatus>("checking")
  const [failures, setFailures] = React.useState(0)
  const [everOnline, setEverOnline] = React.useState(false)
  const stateRef = React.useRef({
    status: "checking" as BackendStatus,
    failures: 0,
    everOnline: false,
  })

  React.useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const chat = ensureChatConnection()
    async function poll() {
      const url = await probeBackend()
      if (cancelled) return

      const s = stateRef.current
      // 注意：同源模式下 probeBackend 返回空串（有效 base），必须用 null 判断
      if (url !== null && chat.connected) {
        s.status = "online"
        s.failures = 0
        s.everOnline = true
        setStatus("online")
        setFailures(0)
        setEverOnline(true)
      } else {
        s.failures += 1
        setFailures(s.failures)
        if (s.status === "checking" || s.failures >= FAILURE_THRESHOLD) {
          s.status = "offline"
          setStatus("offline")
          // 后端掉线时 base.ts 内部会重置 pendingPromise，使后续 API 请求重新等待
        }
      }

      timer = setTimeout(
        poll,
        url !== null ? ONLINE_POLL_MS : OFFLINE_POLL_MS,
      )
    }

    poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [])

  return { status, failures, everOnline }
}
