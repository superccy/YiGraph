"use client"

import * as React from "react"
import type { Lang } from "@/core/types"

function getSavedLang(): Lang {
  if (typeof window === "undefined") return "zh-CN"
  try {
    const saved = localStorage.getItem("app_lang")
    if (saved === "en-US") return "en-US"
  } catch { /* localStorage 不可用时忽略 */ }
  return "zh-CN"
}

interface I18nValue {
  lang: Lang
  mounted: boolean
  ready: boolean
  t: (key: string, fallback?: string) => string
  toggle: () => void
}

const I18nContext = React.createContext<I18nValue | null>(null)

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLang] = React.useState<Lang>(getSavedLang)
  const [mounted, setMounted] = React.useState(false)
  const [ready, setReady] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
    const saved = localStorage.getItem("app_lang") as Lang | null
    if (saved === "en-US" || saved === "zh-CN") {
      if (saved !== lang) setLang(saved)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const dataRef = React.useRef<Record<string, string>>({})

  React.useEffect(() => {
    let cancelled = false
    setReady(false)
    import(`./${lang}.json`).then((mod) => {
      if (cancelled) return
      const flat: Record<string, string> = {}
      function walk(obj: unknown, prefix = "") {
        if (typeof obj === "string") flat[prefix] = obj
        else if (Array.isArray(obj)) obj.forEach((item, i) => walk(item, `${prefix}.${i}`))
        else if (obj && typeof obj === "object") for (const [k, v] of Object.entries(obj)) walk(v, prefix ? `${prefix}.${k}` : k)
      }
      walk(mod)
      dataRef.current = flat
      setReady(true)
    }).catch(() => { setReady(true) })
    return () => { cancelled = true }
  }, [lang])

  const toggle = React.useCallback(() => {
    setLang((prev) => {
      const next = prev === "zh-CN" ? "en-US" : "zh-CN"
      localStorage.setItem("app_lang", next)
      return next
    })
  }, [])

  const t = React.useCallback(
    (key: string, fallback = "") => dataRef.current[key] || fallback || key,
    [],
  )

  const value = React.useMemo(() => ({ lang, mounted, ready, t, toggle }), [lang, mounted, ready, t, toggle])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const ctx = React.useContext(I18nContext)
  if (!ctx) throw new Error("useI18n must be used within I18nProvider")
  return ctx
}
