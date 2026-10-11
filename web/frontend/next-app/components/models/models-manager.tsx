"use client"

import * as React from "react"
import {
  Cpu,
  Plus,
  Search,
  Trash2,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Globe,
  Key,
} from "lucide-react"
import { useI18n } from "@/core/i18n/i18n-provider"
import { ModelsProvider, useModels } from "@/core/models-store"
import type { Model } from "@/core/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { formatDate } from "@/core/utils"
import { CreateModelDialog } from "./create-model-dialog"

export function ModelsManager() {
  return (
    <ModelsProvider>
      <ModelsManagerInner />
    </ModelsProvider>
  )
}

function ModelsManagerInner() {
  const { t } = useI18n()
  const {
    models,
    total,
    page,
    totalPages,
    loading,
    search,
    setSearch,
    setPage,
    createModel,
    deleteModel,
  } = useModels()

  const [query, setQuery] = React.useState(search)
  const [createOpen, setCreateOpen] = React.useState(false)
  const debounceRef = React.useRef<ReturnType<typeof setTimeout>>(undefined)

  const handleQueryChange = (val: string) => {
    setQuery(val)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setSearch(val)
      setPage(1)
    }, 300)
  }

  React.useEffect(() => {
    return () => clearTimeout(debounceRef.current)
  }, [])

  const handleCreate = async (input: {
    name: string
    baseUrl: string
    apiKey: string
  }) => {
    await createModel(input)
  }

  const handleDelete = async (id: string) => {
    await deleteModel(id)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-16 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Cpu className="size-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold leading-tight">{t("models.title", "模型管理")}</h1>
            <p className="text-xs text-muted-foreground">
              {t("models.subtitle", "配置 AI 模型，管理 API 接入信息")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            {t("models.total", "共 {count} 个模型").replace("{count}", String(total))}
          </span>
          <Button onClick={() => setCreateOpen(true)} className="gap-2">
            <Plus className="size-4" />
            {t("models.addButton", "添加模型")}
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-6">
        <div className="mb-4 shrink-0">
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => handleQueryChange(e.target.value)}
              placeholder={t("models.search", "搜索模型名称")}
              className="h-9 pl-9"
            />
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-auto rounded-xl border bg-card">
          {loading ? (
            <div className="p-0">
              <TableSkeleton />
            </div>
          ) : models.length === 0 ? (
            <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
              {t("models.noData", "暂无模型，点击「添加模型」开始配置。")}
            </div>
          ) : (
            <div className="pb-2">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground">
                      {t("models.name", "模型名称")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground">
                      {t("models.baseUrl", "API Base URL")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground">
                      {t("models.createdAt", "创建时间")}
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground">
                      {t("models.actions", "操作")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {models.map((m) => (
                    <tr
                      key={m.id}
                      className="transition-colors hover:bg-muted/50"
                    >
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex size-8 items-center justify-center rounded-full bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-400">
                            <Cpu className="size-3.5" />
                          </div>
                          <span className="text-sm font-medium">{m.name}</span>
                        </div>
                      </td>
                      <td className="px-6 py-3">
                        <Badge
                          variant="secondary"
                          className="gap-1 font-mono text-xs"
                        >
                          <Globe className="size-3" />
                          {m.baseUrl}
                        </Badge>
                      </td>
                      <td className="px-6 py-3">
                        <span className="text-sm text-muted-foreground">
                          {formatDate(m.createdAt)}
                        </span>
                      </td>
                      <td className="px-6 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 text-muted-foreground hover:text-destructive"
                            onClick={() => handleDelete(m.id)}
                            title={t("models.delete", "删除模型")}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {totalPages > 1 && (
          <div className="shrink-0">
            <Pagination
              page={page}
              totalPages={totalPages}
              onPageChange={setPage}
            />
          </div>
        )}
      </div>

      <CreateModelDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreate={handleCreate}
      />
    </div>
  )
}

function Pagination({
  page,
  totalPages,
  onPageChange,
}: {
  page: number
  totalPages: number
  onPageChange: (p: number) => void
}) {
  const pages: (number | "...")[] = []
  const maxVisible = 7

  if (totalPages <= maxVisible) {
    for (let i = 1; i <= totalPages; i++) pages.push(i)
  } else {
    pages.push(1)
    if (page > 3) pages.push("...")

    const start = Math.max(2, page - 1)
    const end = Math.min(totalPages - 1, page + 1)

    for (let i = start; i <= end; i++) pages.push(i)

    if (page < totalPages - 2) pages.push("...")
    pages.push(totalPages)
  }

  return (
    <div className="flex items-center justify-center gap-1 pt-4">
      <Button
        variant="outline"
        size="icon"
        className="size-8"
        disabled={page === 1}
        onClick={() => onPageChange(1)}
      >
        <ChevronsLeft className="size-3.5" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        className="size-8"
        disabled={page === 1}
        onClick={() => onPageChange(page - 1)}
      >
        <ChevronLeft className="size-3.5" />
      </Button>
      {pages.map((p, i) =>
        p === "..." ? (
          <span
            key={`ellipsis-${i}`}
            className="flex size-8 items-center justify-center text-xs text-muted-foreground"
          >
            ...
          </span>
        ) : (
          <Button
            key={p}
            variant={p === page ? "default" : "outline"}
            size="icon"
            className="size-8 text-xs"
            onClick={() => onPageChange(p as number)}
          >
            {p}
          </Button>
        ),
      )}
      <Button
        variant="outline"
        size="icon"
        className="size-8"
        disabled={page === totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        <ChevronRight className="size-3.5" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        className="size-8"
        disabled={page === totalPages}
        onClick={() => onPageChange(totalPages)}
      >
        <ChevronsRight className="size-3.5" />
      </Button>
    </div>
  )
}

function TableSkeleton() {
  return (
    <div className="divide-y divide-border">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-6 py-3">
          <div className="h-4 w-40 animate-pulse rounded bg-muted" />
          <div className="h-5 w-48 animate-pulse rounded bg-muted" />
          <div className="h-4 w-32 animate-pulse rounded bg-muted" />
          <div className="ml-auto h-8 w-8 animate-pulse rounded bg-muted" />
        </div>
      ))}
    </div>
  )
}
