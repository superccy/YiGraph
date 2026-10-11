"use client"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { useI18n } from "@/core/i18n/i18n-provider"
import { useAlgorithms } from "@/core/algorithms-store"
import { getCategoryLabel } from "@/core/algorithms-data"
import { Clock, Tag, ArrowDown, ArrowUp, Lightbulb } from "lucide-react"

export function AlgorithmInfoModal({
  algorithmId,
  onClose,
}: {
  algorithmId: string | null
  onClose: () => void
}) {
  const { t, lang } = useI18n()
  const { getById, categories } = useAlgorithms()
  const algo = algorithmId ? getById(algorithmId) : null

  return (
    <Dialog open={!!algo} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="!max-w-3xl max-h-[85vh] overflow-auto">
        {algo && (
          <>
            <DialogHeader>
              <div className="flex items-start gap-3">
                <div className="flex size-11 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground font-mono text-xs font-bold">
                  {algo.name.slice(0, 3).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <DialogTitle className="text-lg">{algo.displayName}</DialogTitle>
                  <DialogDescription className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-mono text-foreground/70 break-all">
                      {algo.name}
                    </span>
                    <span>·</span>
                    <span>{getCategoryLabel(categories, algo.category)}</span>
                    <span>·</span>
                    <span className="flex items-center gap-1">
                      <Clock className="size-3" />
                      {algo.complexity}
                    </span>
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>

            <div className="flex flex-col gap-4 text-sm">
              <p className="leading-relaxed text-foreground/90 break-words">{algo.summary}</p>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-md border border-border bg-muted/30 p-3">
                  <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <ArrowDown className="size-3.5 text-primary" />
                    {t("algorithms.inputs", "输入")}
                  </div>
                  <ul className="flex flex-col gap-1 text-xs text-foreground/80">
                    {algo.inputs.map((x, i) => (
                      <li key={`in-${i}-${x}`} className="break-words">• {x}</li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-md border border-border bg-muted/30 p-3">
                  <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <ArrowUp className="size-3.5 text-accent" />
                    {t("algorithms.outputs", "输出")}
                  </div>
                  <ul className="flex flex-col gap-1 text-xs text-foreground/80">
                    {algo.outputs.map((x, i) => (
                      <li key={`out-${i}-${x}`} className="break-words">• {x}</li>
                    ))}
                  </ul>
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
                  <Lightbulb className="size-3.5 text-primary" />
                  {t("algorithms.typicalScenarios", "典型场景")}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {algo.useCases.map((u, i) => (
                    <Badge key={`${i}-${u}`} variant="secondary" className="font-normal">
                      {u}
                    </Badge>
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
                  <Tag className="size-3.5" />
                  {t("algorithms.tags", "标签")}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {algo.tags.map((t, i) => (
                    <span
                      key={`tag-${i}-${t}`}
                      className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
