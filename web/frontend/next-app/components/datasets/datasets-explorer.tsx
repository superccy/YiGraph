"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import {
  Database,
  Plus,
  Search,
  Trash2,
  GitGraph,
  FileText,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ExternalLink,
} from "lucide-react"
import { useI18n } from "@/core/i18n/i18n-provider"
import { useDatasets, DatasetsProvider } from "@/core/datasets-store"
import type { Dataset } from "@/core/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { cn, formatDate } from "@/core/utils"
import { CreateDatasetDialog } from "./create-dataset-dialog"

export function DatasetsExplorer() {
  return (
    <DatasetsProvider>
      <DatasetsExplorerInner />
    </DatasetsProvider>
  )
}

function DatasetsExplorerInner() {
  const { t } = useI18n()
  const {
    datasets,
    total,
    page,
    totalPages,
    loading,
    search,
    setSearch,
    setPage,
    createDataset,
    deleteDataset,
  } = useDatasets()

  const router = useRouter()
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

  const handleCreate = async (input: { name: string; fileType: Dataset["fileType"] }) => {
    await createDataset(input)
  }

  const handleDelete = async (id: string) => {
    await deleteDataset(id)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-16 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Database className="size-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold leading-tight">{t("datasets.title", "数据集管理")}</h1>
            <p className="text-xs text-muted-foreground">
              {t("datasets.subtitle", "创建和管理图数据集、原始数据集，组织分析所需的数据文件")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            {t("datasets.total", "共 {count} 个数据集").replace("{count}", String(total))}
          </span>
          <Button onClick={() => setCreateOpen(true)} className="gap-2">
            <Plus className="size-4" />
            {t("datasets.createButton", "创建数据集")}
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
              placeholder={t("datasets.search", "搜索数据集名称")}
              className="h-9 pl-9"
            />
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-auto rounded-xl border bg-card">
          {loading ? (
            <div className="p-0">
              <TableSkeleton />
            </div>
          ) : datasets.length === 0 ? (
            <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
              {t("datasets.noMatch", "未找到匹配的数据集。")}
            </div>
          ) : (
            <div className="pb-2">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground">
                      {t("datasets.name", "名称")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground">
                      {t("datasets.fileType", "文件类型")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground">
                      {t("datasets.fileCount", "文件数量")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground">
                      {t("datasets.createdAt", "创建时间")}
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground">
                      {t("datasets.actions", "操作")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {datasets.map((ds) => (
                    <tr
                      key={ds.id}
                      className="transition-colors hover:bg-muted/50"
                    >
                      <td className="px-6 py-3">
                        <button
                          onClick={() => router.push(`/files?datasetId=${ds.id}`)}
                          className="flex items-center gap-2 text-left hover:underline"
                        >
                          <FileText className="size-4 shrink-0 text-muted-foreground" />
                          <span className="truncate text-sm font-medium text-primary">
                            {ds.name}
                          </span>
                        </button>
                      </td>
                      <td className="px-6 py-3">
                        <Badge
                          variant="secondary"
                          className="gap-1"
                        >
                          {ds.fileType === "graph-data" ? (
                            <GitGraph className="size-3" />
                          ) : (
                            <Database className="size-3" />
                          )}
                          {ds.fileType === "graph-data" ? t("datasets.graphData") : t("datasets.rawData")}
                        </Badge>
                      </td>
                      <td className="px-6 py-3">
                        <span className="text-sm text-muted-foreground">
                          {ds.fileCount} 个文件
                        </span>
                      </td>
                      <td className="px-6 py-3">
                        <span className="text-sm text-muted-foreground">
                          {formatDate(ds.createdAt)}
                        </span>
                      </td>
                      <td className="px-6 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 text-muted-foreground hover:text-primary"
                            onClick={() => router.push(`/files?datasetId=${ds.id}`)}
                            title="查看文件"
                          >
                            <ExternalLink className="size-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 text-muted-foreground hover:text-destructive"
                            onClick={() => handleDelete(ds.id)}
                            title="删除数据集"
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

      <CreateDatasetDialog
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
          <div className="h-4 w-48 animate-pulse rounded bg-muted" />
          <div className="h-5 w-20 animate-pulse rounded bg-muted" />
          <div className="h-4 w-16 animate-pulse rounded bg-muted" />
          <div className="h-4 w-32 animate-pulse rounded bg-muted" />
          <div className="ml-auto h-8 w-8 animate-pulse rounded bg-muted" />
        </div>
      ))}
    </div>
  )
}
