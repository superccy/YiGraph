
"use client"

import { Clock, ArrowDown, ArrowUp, Tag, Lightbulb, LineChart, CheckCircle2 } from "lucide-react"
import type { Algorithm } from "@/core/types"
import { useI18n } from "@/core/i18n/i18n-provider"
import { getCategoryLabel } from "@/core/algorithms-data"
import { useAlgorithms } from "@/core/algorithms-store"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Card, CardContent } from "@/components/ui/card"

export function AlgorithmDetail({ algorithm }: { algorithm: Algorithm }) {
  const { t, lang } = useI18n()
  const { categories } = useAlgorithms()
  return (
    <ScrollArea className="h-full">
      <div className="mx-auto max-w-4xl px-8 py-10">
        <div className="flex items-start gap-5">
          <div className="flex size-14 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground font-mono text-sm font-bold">
            {algorithm.name.slice(0, 3).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold leading-tight text-foreground">{algorithm.displayName}</h1>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span className="font-mono text-foreground/80">{algorithm.name}</span>
              <span>·</span>
              <span>{getCategoryLabel(categories, algorithm.category)}</span>
              <span>·</span>
              <span className="flex items-center gap-1"><Clock className="size-3.5" />{algorithm.complexity}</span>
            </div>
            <p className="mt-3 text-pretty text-[15px] leading-relaxed text-foreground/90">{algorithm.summary}</p>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {algorithm.tags.map((tg) => (
                <Badge key={tg} variant="secondary" className="gap-1 font-normal">
                  <Tag className="size-3" />{tg}
                </Badge>
              ))}
            </div>
          </div>
        </div>

        <Separator className="my-8" />

        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            {t("algorithms.description", "算法描述")}
          </h2>
          <p className="mt-3 text-pretty leading-relaxed text-foreground/90">{algorithm.description}</p>
        </section>

        <section className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2">
          <Card className="bg-muted/30">
            <CardContent className="p-5">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <ArrowDown className="size-4 text-primary" />
                {t("algorithms.inputs", "输入")}
              </div>
              <ul className="flex flex-col gap-2">
                {algorithm.inputs.map((x) => (
                  <li key={x} className="flex items-center gap-2 text-sm text-foreground/90">
                    <span className="size-1.5 rounded-full bg-primary" />{x}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card className="bg-muted/30">
            <CardContent className="p-5">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <ArrowUp className="size-4 text-accent" />
                {t("algorithms.outputs", "输出")}
              </div>
              <ul className="flex flex-col gap-2">
                {algorithm.outputs.map((x) => (
                  <li key={x} className="flex items-center gap-2 text-sm text-foreground/90">
                    <span className="size-1.5 rounded-full bg-accent" />{x}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </section>

        <section className="mt-8">
          <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            <Lightbulb className="size-4" />
            {t("algorithms.useCases", "典型应用场景")}
          </h2>
          <ul className="mt-4 grid gap-3 md:grid-cols-2">
            {algorithm.useCases.map((u, i) => (
              <li key={i} className="flex items-start gap-3 rounded-md border border-border bg-card p-4 text-sm">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" />
                <span className="text-foreground/90">{u}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-8 rounded-lg border border-border bg-card p-5">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <LineChart className="size-4 text-primary" />
            {t("algorithms.chartPref", "推荐可视化")}
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {t("algorithms.chartPrefDesc", "该算法的输出在工作流中默认使用图表进行展示，可在后处理代码中自定义。")}
          </p>
        </section>
      </div>
    </ScrollArea>
  )
}
