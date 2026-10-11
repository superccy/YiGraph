import type { Metadata } from "next"
import "./globals.css"
import { AppShell } from "@/components/app-shell"
import { Toaster } from "@/components/ui/toaster"

export const metadata: Metadata = {
  title: "易图 — 图数据智能分析平台",
  description:
    "用自然语言提问，自动规划图算法工作流 DAG，执行并生成可视化分析报告。",
  icons: {
    icon: "/icon.svg",
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="zh-CN" className="bg-background">
      <body
        className="font-sans antialiased"
      >
        <AppShell>{children}</AppShell>
        <Toaster />
      </body>
    </html>
  )
}
