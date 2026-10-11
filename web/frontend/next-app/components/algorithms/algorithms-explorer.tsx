"use client"

import * as React from "react"
import { Plus, Search, Tag, Gauge, BookOpen, ListTree, ArrowRight } from "lucide-react"
import { useI18n } from "@/core/i18n/i18n-provider"
import { useAlgorithms } from "@/core/algorithms-store"
import { getCategoryLabel } from "@/core/algorithms-data"
import type { Algorithm, AlgorithmCategory } from "@/core/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/core/utils"
import { AddAlgorithmDialog } from "./add-algorithm-dialog"
import { AlgorithmDetail } from "./algorithm-detail"

export function AlgorithmsExplorer() {
  const { t, lang } = useI18n()
  const { algorithms, categories } = useAlgorithms()
  const [query, setQuery] = React.useState("")
  const [activeId, setActiveId] = React.useState<string>(algorithms[0]?.id ?? "")
  const [addOpen, setAddOpen] = React.useState(false)

  React.useEffect(() => {
    if (!algorithms.find((a) => a.id === activeId) && algorithms[0]) {
      setActiveId(algorithms[0].id)
    }
  }, [algorithms, activeId])

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return algorithms
    return algorithms.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.displayName.includes(query) ||
        a.tags.some((tg) => tg.toLowerCase().includes(q)),
    )
  }, [algorithms, query])

  const grouped = React.useMemo(() => {
    const map = new Map<AlgorithmCategory, Algorithm[]>()
    for (const a of filtered) {
      const arr = map.get(a.category) ?? []
      arr.push(a)
      map.set(a.category, arr)
    }
    return map
  }, [filtered])

  const active = algorithms.find((a) => a.id === activeId)

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader onAdd={() => setAddOpen(true)} total={algorithms.length} />

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside className="flex h-full min-h-0 w-80 shrink-0 flex-col border-r border-border bg-card/40">
          <div className="border-b border-border p-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t("algorithms.search", "搜索算法名称或标签")}
                className="h-9 pl-9"
              />
            </div>
          </div>

          <ScrollArea className="flex-1 min-h-0">
            <div className="flex flex-col gap-5 p-3">
              {Array.from(grouped.entries()).map(([cat, list]) => (
                <div key={cat}>
                  <div className="mb-2 flex items-center justify-between px-1">
                    <div className="flex items-center gap-2">
                      <span className="size-1.5 rounded-full bg-primary" />
                      <span className="text-xs font-medium text-foreground">
                        {getCategoryLabel(categories, cat)}
                      </span>
                    </div>
                    <span className="text-[11px] text-muted-foreground">{list.length}</span>
                  </div>
                  <ul className="flex flex-col gap-1">
                    {list.map((a) => (
                      <li key={a.id} style={{ contentVisibility: "auto", containIntrinsicSize: "auto 56px" }}>
                        <button
                          onClick={() => setActiveId(a.id)}
                          className={cn(
                            "group flex w-full items-start gap-3 rounded-md border border-transparent px-3 py-2 text-left transition-colors",
                            activeId === a.id ? "border-primary/30 bg-primary/5" : "hover:bg-muted",
                          )}
                        >
                          <div
                            className={cn(
                              "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md font-mono text-[11px] font-semibold",
                              activeId === a.id ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
                            )}
                          >
                            {a.name.slice(0, 2).toUpperCase()}
                          </div>
                          <div className="min-w-0 flex-1">
                            <span className="truncate text-sm font-medium text-foreground">{a.displayName}</span>
                            <div className="truncate text-[11px] text-muted-foreground">
                              {a.name} · {a.complexity}
                            </div>
                          </div>
                          <ArrowRight
                            className={cn(
                              "size-3.5 shrink-0 self-center text-muted-foreground transition-opacity",
                              activeId === a.id ? "opacity-100" : "opacity-0 group-hover:opacity-60",
                            )}
                          />
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              {filtered.length === 0 && (
                <div className="px-3 py-10 text-center text-sm text-muted-foreground">
                  {t("algorithms.noMatch", "未找到匹配的算法。")}
                </div>
              )}
            </div>
          </ScrollArea>
        </aside>

        <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
          {active ? (
            <AlgorithmDetail algorithm={active} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              {t("algorithms.selectHint", "请选择左侧算法查看详情")}
            </div>
          )}
        </main>
      </div>

      <AddAlgorithmDialog open={addOpen} onOpenChange={setAddOpen} />
    </div>
  )
}

function PageHeader({ onAdd, total }: { onAdd: () => void; total: number }) {
  const { t } = useI18n()
  const { categories } = useAlgorithms()
  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="flex size-9 items-center justify-center rounded-md bg-primary/10 text-primary">
          <BookOpen className="size-4" />
        </div>
        <div>
          <h1 className="text-base font-semibold leading-tight">{t("algorithms.title", "算法知识库")}</h1>
          <p className="text-xs text-muted-foreground">{t("algorithms.subtitle", "浏览图算法、查看详细信息、一键扩充新算法")}</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <div className="hidden items-center gap-4 text-xs text-muted-foreground md:flex">
          <span className="flex items-center gap-1.5"><ListTree className="size-3.5" />{t("algorithms.algosCount", "{count} 个算法").replace("{count}", String(total))}</span>
          <span className="flex items-center gap-1.5"><Tag className="size-3.5" />{t("algorithms.catsCount", "{count} 个分类").replace("{count}", String(categories.length))}</span>
          <span className="flex items-center gap-1.5"><Gauge className="size-3.5" />{t("algorithms.liveAvailable", "实时可用")}</span>
        </div>
        <Button disabled title={t("algorithms.readOnly", "现有算法只读浏览")} className="gap-2">
          <Plus className="size-4" />
          {t("algorithms.addButton", "新增算法")}
        </Button>
      </div>
    </header>
  )
}
