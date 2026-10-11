"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  MessageSquareText,
  Library,
  Github,
  Sun,
  Moon,
  Database,
  FolderOpen,
} from "lucide-react"
import { cn } from "@/core/utils"
import { Button } from "@/components/ui/button"
import { AlgorithmsProvider } from "@/core/algorithms-store"
import { ChatSessionsProvider } from "@/core/chat-store"
import { DatasetsProvider } from "@/core/datasets-store"
import { ModelsProvider } from "@/core/models-store"
import { I18nProvider, useI18n } from "@/core/i18n/i18n-provider"
import { BackendOverlay } from "@/components/backend-overlay"

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <I18nProvider>
      <AlgorithmsProvider>
        <ModelsProvider>
          <DatasetsProvider>
            <ChatSessionsProvider>
              <AppShellInner>{children}</AppShellInner>
            </ChatSessionsProvider>
          </DatasetsProvider>
        </ModelsProvider>
      </AlgorithmsProvider>
    </I18nProvider>
  )
}

function AppShellInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { t, lang, mounted, ready, toggle } = useI18n()
  const [dark, setDark] = React.useState(false)

  React.useEffect(() => {
    const root = document.documentElement
    if (dark) root.classList.add("dark")
    else root.classList.remove("dark")
  }, [dark])

  // 动态设置浏览器标签标题 & html lang
  React.useEffect(() => {
    const appTitle = t("app.title")
    const appSubtitle = t("app.subtitle")
    const sectionKey =
      pathname === "/" ? null
      : pathname?.startsWith("/algorithms") ? "nav.algorithms"
      : pathname?.startsWith("/datasets") ? "nav.datasets"
      : pathname?.startsWith("/files") ? "nav.files"
      : null
    if (sectionKey) {
      document.title = `${t(sectionKey)} · ${appTitle}`
    } else {
      document.title = `${appTitle} — ${appSubtitle}`
    }
    document.documentElement.lang = lang
  }, [lang, ready, pathname, t])

  const NAV = [
    { href: "/", label: t("nav.analysis", "智能分析"), icon: MessageSquareText },
    { href: "/algorithms", label: t("nav.algorithms", "算法库"), icon: Library },
    { href: "/datasets", label: t("nav.datasets", "数据集管理"), icon: Database },
    { href: "/files", label: t("nav.files", "文件管理"), icon: FolderOpen },
  ]

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      {/* Top navigation bar */}
      <header className="flex h-14 shrink-0 items-center gap-6 border-b border-border bg-card px-6">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2">
          <img src="/logo.png" alt="Logo" className="size-8 rounded-md" />
          <div className="leading-tight">
            <div className="text-sm font-semibold">{t("app.title", "易图")}</div>
            <div className="text-[11px] text-muted-foreground">
              {t("app.subtitle", "图数据智能分析平台")}
            </div>
          </div>
        </Link>

        <div className="w-16 md:w-24"></div>

        {/* Nav */}
        <nav className="flex items-center gap-1">
          {NAV.map((item) => {
            const active =
              pathname === item.href ||
              (item.href !== "/" && pathname?.startsWith(item.href))
            const Icon = item.icon
            const baseCls = cn(
              "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              active
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )
            return (
              <Link key={item.href} href={item.href} className={baseCls}>
                <Icon className="size-4 shrink-0" />
                <span>{item.label}</span>
              </Link>
            )
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          {/* Language toggle */}
          <Button
            size="icon"
            variant="ghost"
            className="size-8 text-xs font-bold"
            onClick={toggle}
            aria-label="切换语言"
          >
            <span className="text-[10px] font-bold" suppressHydrationWarning>
              {mounted ? (lang === "zh-CN" ? "EN" : "中") : "EN"}
            </span>
          </Button>

          {/* Theme toggle */}
          <Button
            size="icon"
            variant="ghost"
            className="size-8"
            onClick={() => setDark((v) => !v)}
            aria-label="切换主题"
          >
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>

          <a
            href="https://github.com/iDC-NEU/YiGraph"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Github className="size-3.5" />
            <span className="hidden sm:inline">{t("app.openSource", "开源 · 欢迎贡献")}</span>
          </a>
        </div>
      </header>

      {/* Main content */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</div>

      {/* Backend not-ready overlay */}
      <BackendOverlay />
    </div>
  )
}
