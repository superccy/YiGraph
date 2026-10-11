"use client"

import * as React from "react"
import { Sparkles } from "lucide-react"
import { useI18n } from "@/core/i18n/i18n-provider"
import type { ChatMessage, WorkflowPlan } from "@/core/types"
import { ThinkingSteps } from "./thinking-steps"
import { DagPanel } from "./dag-panel"
import { ExecutionPanel } from "./execution-panel"
import { AnalysisReport } from "./analysis-report"

export function MessageAssistant({
  message,
  userQuestion,
  onExecute,
  onModify,
  onLayoutChange,
  interactive,
}: {
  message: ChatMessage
  userQuestion: string
  onExecute: () => void
  onModify: (modificationText: string) => void
  onLayoutChange: (layout: Record<string, { x: number; y: number }>) => void
  interactive: boolean
}) {
  const { t } = useI18n()
  const plan = message.plan
  if (!plan) return null

  const phase = plan.phase

  return (
    <div className="flex items-start gap-3">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
        <Sparkles className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <span className="text-foreground">{t("chat.engine", "易图 规划引擎")}</span>
          <span>·</span>
          <span>{phaseLabel(phase, t)}</span>
        </div>

        <div className="flex flex-col gap-4">
          {plan.error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {plan.error}
            </div>
          )}
          {phase === "checking_intent" && <p className="rounded-md border px-4 py-3 text-sm text-muted-foreground">{t("chat.checkingIntent", "正在检查分析对象、目标和判断标准…")}</p>}
          {plan.clarification && <div className="rounded-md border bg-card px-4 py-3 text-sm">
            <p className="whitespace-pre-wrap">{plan.clarification.question}</p>
            <p className="mt-2 text-xs text-muted-foreground">{phase === "waiting_clarification" ? t("chat.replyToClarify", "请在下方回复，补充后再构建工作流。") : t("chat.clarificationAnswered", "已补充说明。")}</p>
          </div>}
          {phase !== "checking_intent" && phase !== "waiting_clarification" && phase !== "clarified" && phase !== "blocked" && <ThinkingSteps plan={plan} />}

          {plan.nodes.length > 0 && (phase === "dag-ready" ||
            phase === "executing" ||
            phase === "executed") && (
            <DagPanel
              plan={plan}
              userQuestion={userQuestion}
              onExecute={onExecute}
              onModify={onModify}
              onLayoutChange={onLayoutChange}
              interactive={interactive}
            />
          )}

          {plan.nodes.length > 0 && (phase === "executing" || phase === "executed") && (
            <ExecutionPanel plan={plan} />
          )}

          {/* Markdown from backend, or structured report from mock */}
          {(plan.markdown || plan.report) && (
            <AnalysisReport report={plan.report} markdown={plan.markdown} userQuestion={userQuestion} streaming={phase !== "executed"} />
          )}
        </div>
      </div>
    </div>
  )
}

function phaseLabel(phase: WorkflowPlan["phase"], t: (k: string, f?: string) => string) {
  switch (phase) {
    case "checking_intent": return t("chat.checkingIntentTitle", "检查分析意图")
    case "waiting_clarification": return t("chat.clarificationTitle", "等待澄清")
    case "clarified": return t("chat.clarificationAnswered", "已补充说明")
    case "blocked": return t("chat.intentBlocked", "尚未开始分析")
    case "understanding": return t("dag.phaseUnderstanding", "正在理解问题")
    case "decomposing":   return t("dag.phaseDecomposing", "正在拆解子问题")
    case "selecting":     return t("dag.phaseSelecting", "正在选择算法")
    case "dag-ready":     return t("dag.phaseReady", "DAG 构建完成")
    case "executing":     return t("dag.phaseExecuting", "工作流执行中")
    case "executed":      return t("dag.phaseExecuted", "分析报告已生成")
    default:              return t("dag.phaseThinking", "思考中")
  }
}
