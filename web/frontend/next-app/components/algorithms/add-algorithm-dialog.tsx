"use client"

import * as React from "react"
import {
  Sparkles,
  Search,
  Loader2,
  AlertCircle,
  CheckCircle2,
} from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useI18n } from "@/core/i18n/i18n-provider"
import { useAlgorithms } from "@/core/algorithms-store"
import type { Algorithm } from "@/core/types"
import { useToast } from "@/hooks/use-toast"
import { createAlgorithm } from "@/core/api/algorithms"

type Stage = "idle" | "loading" | "done" | "error"

export function AddAlgorithmDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const { t, lang } = useI18n()
  const { algorithms, addAlgorithm } = useAlgorithms()
  const { toast } = useToast()
  const [name, setName] = React.useState("")
  const [stage, setStage] = React.useState<Stage>("idle")
  const [draft, setDraft] = React.useState<Algorithm | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  function reset() {
    setName("")
    setStage("idle")
    setDraft(null)
    setError(null)
  }

  async function handleSearch() {
    const trimmed = name.trim()
    if (!trimmed) return
    if (
      algorithms.some(
        (a) =>
          a.name.toLowerCase() === trimmed.toLowerCase() ||
          a.displayName === trimmed,
      )
    ) {
      setError(t("algorithms.duplicateError", "该算法已存在于知识库中。"))
      setStage("error")
      return
    }
    setError(null)
    setStage("loading")

    try {
      const result = await createAlgorithm({ name: trimmed, lang })
      setDraft(result)
      setStage("done")
    } catch (err) {
      setError(
        err instanceof Error ? err.message : String(err),
      )
      setStage("error")
    }
  }

  function handleConfirm() {
    if (!draft) return
    addAlgorithm(draft)
    toast({
      title: t("algorithms.addedTitle", "已添加到知识库"),
      description: t("algorithms.addedDesc", "{name} 现在可用于工作流规划。").replace(
        "{name}",
        `${draft.displayName} (${draft.name})`,
      ),
    })
    onOpenChange(false)
    setTimeout(reset, 200)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v)
        if (!v) setTimeout(reset, 200)
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" />
            {t("algorithms.addDialogTitle", "智能扩充算法知识")}
          </DialogTitle>
          <DialogDescription>
            {t("algorithms.addDialogDesc", "输入算法名称，系统将自动检索相关资料并扩充到知识库。")}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="algo-name">{t("algorithms.nameLabel", "算法名称")}</Label>
            <Input
              id="algo-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("algorithms.namePlaceholder", "例如：Katz Centrality / HITS / GCN")}
              disabled={stage === "loading"}
            />
          </div>

          {/* Progress area */}
          <div className="rounded-lg border border-border bg-muted/30 p-4">
            {stage === "idle" && (
              <p className="text-xs text-muted-foreground">
                {t("algorithms.idleHint", "输入算法名称后点击「检索并生成」，系统将自动联网检索资料并调用 LLM 生成结构化条目。")}
              </p>
            )}
            {stage === "loading" && (
              <div className="flex items-center gap-3">
                <Loader2 className="size-5 animate-spin text-primary" />
                <div>
                  <p className="text-sm font-medium">
                    {t("algorithms.generating", "正在检索资料并生成算法条目…")}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t("algorithms.generatingHint", "此过程需要联网检索学术资料、解析文档并调用 LLM，可能需要 1-3 分钟。")}
                  </p>
                </div>
              </div>
            )}
            {stage === "error" && error && (
              <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
                <AlertCircle className="size-3.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}
            {stage === "done" && draft && (
              <div className="flex items-center gap-2 text-sm text-accent">
                <CheckCircle2 className="size-4 shrink-0" />
                {t("algorithms.generationDone", "算法条目生成完成！请确认后加入知识库。")}
              </div>
            )}
          </div>

          {/* Draft preview */}
          {stage === "done" && draft && (
            <div className="rounded-lg border border-border bg-card p-4">
              <div className="flex items-start gap-3">
                <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground font-mono text-xs font-semibold">
                  {draft.name.slice(0, 3).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold">
                    {draft.displayName}{" "}
                    <span className="font-mono text-xs text-muted-foreground">
                      ({draft.name})
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {draft.summary}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {draft.tags.map((tg) => (
                      <span
                        key={tg}
                        className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground"
                      >
                        {tg}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="mt-3 border-t border-border pt-3">
                <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-muted-foreground">
                  <span>
                    {t("algorithms.category", "分类")}: {draft.category}
                  </span>
                  <span>
                    {t("algorithms.complexity", "复杂度")}: {draft.complexity}
                  </span>
                  <span>
                    {t("algorithms.inputsCount", "输入参数")}: {draft.inputs.length}
                  </span>
                  <span>
                    {t("algorithms.outputsCount", "输出参数")}: {draft.outputs.length}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          {stage === "done" ? (
            <>
              <Button variant="outline" onClick={reset}>
                {t("algorithms.regenerate", "重新生成")}
              </Button>
              <Button onClick={handleConfirm} className="gap-2">
                <CheckCircle2 className="size-4" />
                {t("algorithms.confirmAdd", "确认加入知识库")}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {t("common.cancel", "取消")}
              </Button>
              <Button
                onClick={handleSearch}
                disabled={!name.trim() || stage === "loading"}
                className="gap-2"
              >
                {stage === "loading" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Search className="size-4" />
                )}
                {t("algorithms.searchGenerate", "检索并生成")}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
