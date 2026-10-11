"use client"

import * as React from "react"
import type { ChatMessage, ChatSession, WorkflowPlan } from "./types"

interface ChatCtxValue {
  sessions: ChatSession[]
  activeId: string | null
  activeSession: ChatSession | null
  createSession: (title?: string) => string
  selectSession: (id: string) => void
  deleteSession: (id: string) => void
  renameSession: (id: string, title: string) => void
  appendMessage: (sessionId: string, msg: ChatMessage) => void
  updatePlan: (
    sessionId: string,
    messageId: string,
    updater: (plan: WorkflowPlan) => WorkflowPlan,
  ) => void
}

const ChatCtx = React.createContext<ChatCtxValue | null>(null)

const STORAGE_KEY = "a_chat_sessions_v1"
const ACTIVE_KEY = "a_chat_active_id_v1"

function readSessions(): ChatSession[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw) as ChatSession[]
  } catch {
    return []
  }
}

function readActiveId(): string | null {
  try {
    return sessionStorage.getItem(ACTIVE_KEY)
  } catch {
    return null
  }
}

function saveSessions(sessions: ChatSession[], activeId: string | null) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(sessions))
    if (activeId) {
      sessionStorage.setItem(ACTIVE_KEY, activeId)
    } else {
      sessionStorage.removeItem(ACTIVE_KEY)
    }
  } catch {
    // quota exceeded or private browsing — silently ignore
  }
}

export function ChatSessionsProvider({
  children,
}: {
  children: React.ReactNode
}) {
  // 初始状态始终为空，避免 SSR hydration mismatch
  const [sessions, setSessions] = React.useState<ChatSession[]>([])
  const [activeId, setActiveId] = React.useState<string | null>(null)
  const hydratedRef = React.useRef(false)

  // 挂载后从 sessionStorage 恢复
  React.useEffect(() => {
    const saved = readSessions()
    const savedId = readActiveId()
    if (saved.length > 0) {
      setSessions(saved)
      setActiveId(savedId)
    }
    hydratedRef.current = true
  }, [])

  const createSession = React.useCallback((title = "") => {
    const id = `s-${Date.now()}`
    const session: ChatSession = {
      id,
      title,
      createdAt: new Date().toISOString(),
      messages: [],
    }
    setSessions((prev) => [session, ...prev])
    setActiveId(id)
    return id
  }, [])

  const selectSession = React.useCallback((id: string) => setActiveId(id), [])

  const deleteSession = React.useCallback(
    (id: string) => {
      setSessions((prev) => prev.filter((s) => s.id !== id))
      setActiveId((curr) => (curr === id ? null : curr))
    },
    [],
  )

  const renameSession = React.useCallback((id: string, title: string) => {
    setSessions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, title } : s)),
    )
  }, [])

  const appendMessage = React.useCallback(
    (sessionId: string, msg: ChatMessage) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId ? { ...s, messages: [...s.messages, msg] } : s,
        ),
      )
    },
    [],
  )

  const updatePlan = React.useCallback(
    (
      sessionId: string,
      messageId: string,
      updater: (plan: WorkflowPlan) => WorkflowPlan,
    ) => {
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== sessionId) return s
          return {
            ...s,
            messages: s.messages.map((m) => {
              if (m.id !== messageId || !m.plan) return m
              return { ...m, plan: updater(m.plan) }
            }),
          }
        }),
      )
    },
    [],
  )

  // 只在 hydrate 完成后才持久化，避免空数组覆盖 sessionStorage
  React.useEffect(() => {
    if (hydratedRef.current) {
      saveSessions(sessions, activeId)
    }
  }, [sessions, activeId])

  const activeSession =
    sessions.find((s) => s.id === activeId) ?? null

  const value = React.useMemo<ChatCtxValue>(
    () => ({
      sessions,
      activeId,
      activeSession,
      createSession,
      selectSession,
      deleteSession,
      renameSession,
      appendMessage,
      updatePlan,
    }),
    [
      sessions,
      activeId,
      activeSession,
      createSession,
      selectSession,
      deleteSession,
      renameSession,
      appendMessage,
      updatePlan,
    ],
  )

  return <ChatCtx.Provider value={value}>{children}</ChatCtx.Provider>
}

export function useChat() {
  const ctx = React.useContext(ChatCtx)
  if (!ctx) throw new Error("useChat must be used inside ChatSessionsProvider")
  return ctx
}
