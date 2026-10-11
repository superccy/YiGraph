"use client"

import * as React from "react"
import {
  FileText,
  TrendingUp,
  TrendingDown,
  Minus,
  CheckCircle2,
  Sparkles,
  ArrowRight,
  Download,
  ThumbsUp,
  ThumbsDown,
} from "lucide-react"
import { marked } from "marked"
import { useI18n } from "@/core/i18n/i18n-provider"
import type { AnalysisReport as Report } from "@/core/types"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { cn } from "@/core/utils"
import { submitFeedback } from "@/core/api/feedback"

export function AnalysisReport({
  report,
  markdown,
  userQuestion,
  streaming = false,
}: {
  report?: Report | null
  markdown?: string | null
  userQuestion: string
  streaming?: boolean
}) {
  const { t } = useI18n()
  const [feedback, setFeedback] = React.useState<"like" | "dislike" | null>(null)

  const disclaimer = t(
    "dag.disclaimer",
    "本报告由 YiGraph 智能分析系统自动生成，仅供初步核查参考，不构成最终结论。",
  )

  const html = React.useMemo(() => {
    if (!markdown) return ""
    return marked.parse(appendDisclaimer(markdown, disclaimer)) as string
    // disclaimer 的取值跟随当前界面语言；语言切换后此处随依赖变化重新解析
  }, [markdown, disclaimer])

  const handleFeedback = (type: "like" | "dislike") => {
    if (feedback) return
    setFeedback(type)
    const output = report
      ? JSON.stringify(report)
      : markdown ?? ""
    submitFeedback({
      userQuestion,
      analysisOutput: output,
      type: "report",
      feedback: type,
    }).catch(() => {
      setFeedback(null)
    })
  }

  return (
    <Card className="overflow-hidden border-primary/30 p-0">
      <div className="flex items-center justify-between border-b border-border bg-primary/5 px-5 py-3">
        <div className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <FileText className="size-3.5" />
          </div>
          <div>
            <div className="text-sm font-semibold">
              {report?.title ?? t("dag.reportTitle", "分析报告")}
            </div>
            <div className="text-[11px] text-muted-foreground">
              {streaming ? t("dag.receivingResult", "正在接收分析结果…") : t("dag.executedDesc", "工作流执行完成 · 自动生成")}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => {
            const blob = new Blob([markdown ?? JSON.stringify(report, null, 2)], { type: "text/markdown;charset=utf-8" })
            const url = URL.createObjectURL(blob)
            const link = document.createElement("a")
            link.href = url
            link.download = "yigraph-analysis.md"
            link.click()
            setTimeout(() => URL.revokeObjectURL(url), 1000)
          }}>
            <Download className="size-3.5" />
            {t("dag.exportReport", "导出报告")}
          </Button>
          <button
            onClick={() => handleFeedback("like")}
            disabled={feedback !== null}
            className={cn(
              "rounded p-1.5 transition-colors",
              feedback === "like"
                ? "text-primary"
                : "text-muted-foreground hover:text-primary",
              feedback !== null && feedback !== "like" && "opacity-40",
            )}
          >
            <ThumbsUp className={cn("size-3.5", feedback === "like" && "fill-primary")} />
          </button>
          <button
            onClick={() => handleFeedback("dislike")}
            disabled={feedback !== null}
            className={cn(
              "rounded p-1.5 transition-colors",
              feedback === "dislike"
                ? "text-destructive"
                : "text-muted-foreground hover:text-destructive",
              feedback !== null && feedback !== "dislike" && "opacity-40",
            )}
          >
            <ThumbsDown className={cn("size-3.5", feedback === "dislike" && "fill-destructive")} />
          </button>
        </div>
      </div>

      {markdown ? (
        <div className="px-5 py-5">
          <div
            className="prose prose-sm max-w-none dark:prose-invert"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        </div>
      ) : report ? (
        <div className="flex flex-col gap-6 px-5 py-5">
          {/* Executive summary */}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t("dag.summary", "结论概要")}
            </h3>
            <p className="text-pretty text-[15px] leading-relaxed text-foreground/90">
              {report.executiveSummary}
            </p>
          </section>

          {/* Metrics */}
          <section>
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t("dag.metrics", "关键指标")}
            </h3>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {report.metrics.map((m) => (
                <div
                  key={m.label}
                  className="rounded-lg border border-border bg-muted/30 p-4"
                >
                  <div className="text-xs text-muted-foreground">{m.label}</div>
                  <div className="mt-1 flex items-baseline gap-2">
                    <span className="text-2xl font-semibold tabular-nums text-foreground">
                      {m.value}
                    </span>
                    <TrendIcon trend={m.trend} />
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Findings */}
          <section>
            <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <Sparkles className="size-3.5 text-primary" />
              {t("dag.findings", "主要发现")}
            </h3>
            <ul className="flex flex-col gap-2">
              {report.keyFindings.map((f, i) => (
                <li
                  key={i}
                  className="flex items-start gap-3 rounded-md border border-border bg-card p-3 text-sm leading-relaxed"
                >
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" />
                  <span className="text-foreground/90">{f}</span>
                </li>
              ))}
            </ul>
          </section>

          {/* Recommendations */}
          <section>
            <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <ArrowRight className="size-3.5 text-primary" />
              {t("dag.recommendations", "后续建议")}
            </h3>
            <ol className="flex flex-col gap-2">
              {report.recommendations.map((r, i) => (
                <li
                  key={i}
                  className="flex items-start gap-3 rounded-md bg-muted/30 p-3 text-sm leading-relaxed"
                >
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
                    {i + 1}
                  </span>
                  <span className="text-foreground/90">{r}</span>
                </li>
              ))}
            </ol>
          </section>

          {/* 免责声明（结构化报告分支） */}
          <div className="border-t border-border pt-4">
            <p className="text-xs italic leading-relaxed text-muted-foreground">
              {disclaimer}
            </p>
          </div>
        </div>
      ) : null}
    </Card>
  )
}

function TrendIcon({ trend }: { trend?: "up" | "down" | "flat" }) {
  if (!trend) return null
  const Icon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus
  const color =
    trend === "up"
      ? "text-accent"
      : trend === "down"
        ? "text-destructive"
        : "text-muted-foreground"
  return <Icon className={cn("size-4", color)} />
}

/**
 * 报告末尾追加免责声明（渲染时跟随当前界面语言）。
 * 若报告结尾已包含类似声明（如后端自行生成），则不重复追加。
 */
function appendDisclaimer(markdown: string, disclaimer: string): string {
  const body = markdown.trimEnd()
  const tail = body.slice(-400)
  if (/仅供.{0,12}参考|does not constitute|preliminary review reference/i.test(tail)) {
    return markdown
  }
  return `${body}\n\n---\n\n*${disclaimer}*\n`
}
