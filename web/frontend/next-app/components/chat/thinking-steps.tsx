"use client"

import * as React from "react"
import {
  Brain,
  Split,
  Cpu,
  CheckCircle2,
  Loader2,
  ChevronDown,
} from "lucide-react"
import { useI18n } from "@/core/i18n/i18n-provider"
import type { WorkflowPlan } from "@/core/types"
import { useAlgorithms } from "@/core/algorithms-store"
import { Card } from "@/components/ui/card"
import { cn } from "@/core/utils"
import { Progress } from "@/components/ui/progress"

export function ThinkingSteps({ plan }: { plan: WorkflowPlan }) {
  const { t } = useI18n()
  const { getById } = useAlgorithms()
  const { phase, progress } = plan

  const isUnderstandingActive = phase === "understanding"
  const isDecomposingActive = phase === "decomposing"
  const isSelectingActive = phase === "selecting"

  const isUnderstandingDone = progress.understanding >= 1
  const isDecomposingDone = progress.decomposing >= 1
  const isSelectingDone = progress.selecting >= 1

  const [collapsed, setCollapsed] = React.useState(false)
  const allDone = phase === "executed" || (progress.understanding >= 1 && progress.decomposing >= 1 && progress.selecting >= 1)

  return (
    <Card className="overflow-hidden border-border p-0">
      <button
        onClick={() => setCollapsed((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left transition-colors hover:bg-muted/40"
      >
        <div className="flex items-center gap-2">
          <Brain className="size-4 text-primary" />
          <span className="text-sm font-medium">{t("dag.reasoning", "构造 DAG 的推理过程")}</span>
          {allDone && (
            <span className="ml-2 rounded-full bg-accent/20 px-2 py-0.5 text-[10px] font-medium text-accent-foreground">
              {t("dag.completed", "已完成")}
            </span>
          )}
        </div>
        <ChevronDown
          className={cn(
            "size-4 text-muted-foreground transition-transform",
            collapsed ? "" : "rotate-180",
          )}
        />
      </button>

      {!collapsed && (
        <div className="border-t border-border px-5 py-5">
          <div className="flex flex-col gap-5">
            {/* Step 1: Understanding */}
            <StepRow
              index={1}
              icon={Brain}
              title={t("dag.understanding", "理解用户问题")}
              status={
                isUnderstandingActive
                  ? "active"
                  : isUnderstandingDone
                    ? "done"
                    : "todo"
              }
              progress={progress.understanding}
            >
              <p className="text-sm leading-relaxed text-foreground/90">
                {plan.understanding || t("dag.parsingIntent", "正在解析意图…")}
              </p>
            </StepRow>

            {/* Step 2: Sub-problems */}
            {(phase !== "executed" || plan.subProblems.length > 0) && <>
            <StepRow
              index={2}
              icon={Split}
              title={t("dag.decomposing", "拆解为子问题")}
              status={
                isDecomposingActive
                  ? "active"
                  : isDecomposingDone
                    ? "done"
                    : isUnderstandingDone
                      ? "todo"
                      : "todo"
              }
              progress={progress.decomposing}
            >
              {progress.decomposing > 0 ? (
                <ul className="flex flex-col gap-2">
                  {plan.subProblems
                    .slice(0, Math.ceil(plan.subProblems.length * progress.decomposing))
                    .map((sp, i) => (
                      <li
                        key={sp.id}
                        className="flex items-start gap-3 rounded-md border border-border bg-muted/30 p-3"
                      >
                        <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-semibold text-primary">
                          {i + 1}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-foreground">
                            {sp.title}
                          </div>

                        </div>
                      </li>
                    ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">
                  {t("dag.waitingDecompose", "等待理解完成后开始拆解…")}
                </p>
              )}
            </StepRow>

            {/* Step 3: Algorithm selection */}
            <StepRow
              index={3}
              icon={Cpu}
              title={t("dag.selecting", "为每个子问题选择图算法")}
              status={
                isSelectingActive
                  ? "active"
                  : isSelectingDone
                    ? "done"
                    : "todo"
              }
              progress={progress.selecting}
            >
              {progress.selecting > 0 ? (
                <div className="grid gap-2 md:grid-cols-2">
                  {plan.subProblems
                    .slice(0, Math.ceil(plan.subProblems.length * progress.selecting))
                    .map((sp) => {
                      const a = sp.algorithmId ? getById(sp.algorithmId) : undefined
                      const noAlgo = !sp.algorithmId
                      const label = noAlgo
                        ? sp.rationale
                        : a?.displayName ?? sp.algorithmId
                      return (
                        <div
                          key={sp.id}
                          className="flex items-start gap-3 rounded-md border border-border bg-card px-3 py-2"
                        >
                          <div className={noAlgo
                            ? "flex size-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground font-mono text-[10px] font-semibold"
                            : "flex size-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground font-mono text-[10px] font-semibold"
                          }>
                            {noAlgo ? "···" : (a?.name ?? "ALG").slice(0, 3).toUpperCase()}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="break-words text-xs font-medium leading-snug text-foreground">
                              {label}
                            </div>
                            <div className="break-words text-[11px] leading-snug text-muted-foreground">
                              → {sp.title}
                            </div>
                          </div>
                        </div>
                      )
                    })}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  {t("dag.waitingSelect", "等待子问题拆解完成后开始选择算法…")}
                </p>
              )}
            </StepRow>
            </>}
          </div>
        </div>
      )}
    </Card>
  )
}

function StepRow({
  index,
  icon: Icon,
  title,
  status,
  progress,
  children,
}: {
  index: number
  icon: React.ElementType
  title: string
  status: "todo" | "active" | "done"
  progress: number
  children: React.ReactNode
}) {
  const { t } = useI18n()
  return (
    <div className="flex gap-4">
      <div className="relative flex flex-col items-center">
        <div
          className={cn(
            "flex size-8 items-center justify-center rounded-full border-2",
            status === "done"
              ? "border-accent bg-accent/15 text-accent-foreground"
              : status === "active"
                ? "border-primary bg-primary/10 text-primary pulse-ring"
                : "border-border bg-muted text-muted-foreground",
          )}
        >
          {status === "done" ? (
            <CheckCircle2 className="size-4" />
          ) : status === "active" ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Icon className="size-4" />
          )}
        </div>
        <div className="mt-1 flex-1 w-px bg-border" />
      </div>
      <div className="flex-1 pb-2">
        <div className="mb-2 flex items-center gap-2">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t("dag.step", "步骤 {n}").replace("{n}", String(index))}
          </span>
          <span className="text-sm font-semibold text-foreground">{title}</span>
          {status === "active" && (
            <span className="ml-2 text-[10px] uppercase tracking-wide text-primary">
              {t("dag.inProgress", "进行中")}
            </span>
          )}
        </div>
        {status === "active" && (
          <Progress value={Math.round(progress * 100)} className="mb-3 h-1" />
        )}
        <div>{children}</div>
      </div>
    </div>
  )
}
