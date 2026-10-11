"use client"

import * as React from "react"
import { useSearchParams } from "next/navigation"
import {
  FolderOpen,
  Plus,
  FileText,
  Trash2,
  Eye,
  Play,
  Database,
  GitGraph,
  ChevronRight,
} from "lucide-react"
import { useI18n } from "@/core/i18n/i18n-provider"
import { useFiles, FilesProvider } from "@/core/files-store"
import type { FileItem, PreviewData, UploadConfig } from "@/core/types"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Empty, EmptyDescription, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { cn, formatSize, formatDate } from "@/core/utils"
import { FileUploadDialog } from "./file-upload-dialog"
import { FilePreviewDialog } from "./file-preview-dialog"
import { GraphCanvas } from "./graph-canvas"

export function FilesManager() {
  return (
    <FilesProvider>
      <React.Suspense fallback={null}>
        <FilesManagerInner />
      </React.Suspense>
    </FilesProvider>
  )
}

function FilesManagerInner() {
  const { t } = useI18n()
  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-md bg-primary/10 text-primary">
            <FolderOpen className="size-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold leading-tight">{t("files.title", "文件管理")}</h1>
            <p className="text-xs text-muted-foreground">
              {t("files.subtitle", "上传、解析、预览文件，查看知识图谱")}
            </p>
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <DatasetSidebar />
        <FileMain />
      </div>
    </div>
  )
}

function DatasetSidebar() {
  const { t } = useI18n()
  const {
    datasetList,
    activeDatasetId,
    activeDataset,
    selectDataset,
  } = useFiles()

  return (
    <aside className="flex h-full min-h-0 w-72 shrink-0 flex-col border-r border-border bg-card/40">
      <div className="shrink-0 border-b border-border px-4 py-3">
        <span className="text-xs font-medium text-muted-foreground">{t("files.datasets", "数据集")}</span>
      </div>
      <ScrollArea className="flex-1 min-h-0">
        <div className="flex flex-col gap-0.5 p-2">
          {datasetList.map((ds) => (
            <button
              key={ds.id}
              onClick={() => selectDataset(ds.id)}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-left transition-colors",
                activeDatasetId === ds.id
                  ? "border-primary/30 bg-primary/5"
                  : "hover:bg-muted",
              )}
            >
              {ds.fileType === "graph-data" ? (
                <GitGraph className="size-4 shrink-0 text-muted-foreground" />
              ) : (
                <Database className="size-4 shrink-0 text-muted-foreground" />
              )}
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{ds.name}</div>
                <div className="text-xs text-muted-foreground">
                  {t("files.filesCount", "{count} 个文件").replace("{count}", String(ds.fileCount))}
                </div>
              </div>
              {activeDatasetId === ds.id && (
                <ChevronRight className="size-4 shrink-0 text-primary" />
              )}
            </button>
          ))}
        </div>
      </ScrollArea>
    </aside>
  )
}

function FileMain() {
  const { t } = useI18n()
  const {
    activeDataset,
    activeDatasetId,
    files,
    graphData,
    triplets,
    graphLoading,
    loading,
    uploadFiles,
    deleteFile,
    parseFile,
    previewFile,
    refreshFiles,
    selectDataset,
    generateGraph,
  } = useFiles()

  const searchParams = useSearchParams()

  React.useEffect(() => {
    const datasetId = searchParams.get("datasetId") ?? searchParams.get("dataset") ?? searchParams.get("kb_id")
    if (datasetId) selectDataset(datasetId)
  }, [searchParams, selectDataset])

  const [uploadOpen, setUploadOpen] = React.useState(false)
  const [previewOpen, setPreviewOpen] = React.useState(false)
  const [previewFileName, setPreviewFileName] = React.useState("")
  const [previewData, setPreviewData] = React.useState<PreviewData | null>(null)
  const [previewLoading, setPreviewLoading] = React.useState(false)
  const [error, setError] = React.useState("")
  const runAction = async (action: () => Promise<void>) => {
    setError("")
    try { await action() } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
  }

  const handleUpload = async (
    fileList: File[],
    config: UploadConfig,
  ) => {
    if (!activeDatasetId || !activeDataset) return
    const fileType = activeDataset.fileType === "graph-data" ? "graph" : "text"
    await uploadFiles(activeDatasetId, fileList, fileType, config)
  }

  const handlePreview = async (file: FileItem) => {
    setPreviewFileName(file.name)
    setPreviewOpen(true)
    setPreviewLoading(true)
    setPreviewData(null)
    try {
      const data = await previewFile(file.name)
      setPreviewData(data)
    } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
    finally { setPreviewLoading(false) }
  }

  if (!activeDatasetId) {
    return (
      <main className="flex min-h-0 min-w-0 flex-1 items-center justify-center">
        <Empty>
          <EmptyMedia>
            <Database className="size-12 text-muted-foreground/40" />
          </EmptyMedia>
          <EmptyTitle>{t("files.noDataset", "未选择数据集")}</EmptyTitle>
          <EmptyDescription>
            {t("files.noDatasetDesc", "请在左侧选择一个数据集以查看其文件。")}
          </EmptyDescription>
        </Empty>
      </main>
    )
  }

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-3">
        <div>
          <span className="text-sm font-medium">
            {t("files.ofDataset", "{name} 的文件").replace("{name}", activeDataset?.name ?? "")}
          </span>
          <span className="ml-2 text-xs text-muted-foreground">
            {t("files.filesCount", "{count} 个文件").replace("{count}", String(files.length))}
          </span>
        </div>
        <Button
          size="sm"
          className="gap-1.5"
          onClick={() => setUploadOpen(true)}
        >
          <Plus className="size-3.5" />
          {t("files.uploadButton", "上传文件")}
        </Button>
      </div>

      {error && <p role="alert" className="px-6 py-2 text-sm text-destructive">{error}</p>}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-auto">
          {loading ? (
            <div className="divide-y divide-border">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="flex items-center gap-4 px-6 py-3"
                >
                  <div className="h-4 w-48 animate-pulse rounded bg-muted" />
                  <div className="h-4 w-20 animate-pulse rounded bg-muted" />
                  <div className="h-4 w-32 animate-pulse rounded bg-muted" />
                  <div className="h-4 w-16 animate-pulse rounded bg-muted" />
                </div>
              ))}
            </div>
          ) : files.length === 0 ? (
            <div className="flex h-48 items-center justify-center">
              <Empty>
                <EmptyTitle>{t("files.noFiles", "暂无文件")}</EmptyTitle>
                <EmptyDescription>
                  {t("files.noFilesDesc", "此数据集尚未上传任何文件，点击\"上传文件\"开始。")}
                </EmptyDescription>
              </Empty>
            </div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-6 py-2.5 text-left text-xs font-medium text-muted-foreground">
                    {t("files.name", "文件名")}
                  </th>
                  <th className="px-6 py-2.5 text-left text-xs font-medium text-muted-foreground">
                    {t("files.size", "大小")}
                  </th>
                  <th className="px-6 py-2.5 text-left text-xs font-medium text-muted-foreground">
                    {t("files.uploadTime", "上传时间")}
                  </th>
                  <th className="px-6 py-2.5 text-left text-xs font-medium text-muted-foreground">
                    {t("files.status", "解析状态")}
                  </th>
                  <th className="px-6 py-2.5 text-right text-xs font-medium text-muted-foreground">
                    {t("files.actions", "操作")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {files.map((f) => (
                  <tr
                    key={f.id}
                    className="transition-colors hover:bg-muted/50"
                  >
                    <td className="px-6 py-2.5">
                      <div className="flex items-center gap-2">
                        <FileText className="size-4 shrink-0 text-muted-foreground" />
                        <span className="truncate text-sm">{f.name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-2.5">
                      <span className="text-sm text-muted-foreground">
                        {formatSize(f.size)}
                      </span>
                    </td>
                    <td className="px-6 py-2.5">
                      <span className="text-sm text-muted-foreground">
                        {formatDate(f.uploadTime)}
                      </span>
                    </td>
                    <td className="px-6 py-2.5">
                      <ParseStatusBadge status={f.parseStatus} progress={f.progress} />
                    </td>
                    <td className="px-6 py-2.5">
                      <div className="flex items-center justify-end gap-1">
                        {f.parseStatus === "pending" && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 text-muted-foreground hover:text-primary"
                            onClick={() => runAction(() => parseFile(f.name))}
                            title={t("files.parse", "开始解析")}
                          >
                            <Play className="size-3.5" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-8 text-muted-foreground hover:text-foreground"
                          onClick={() => handlePreview(f)}
                          title={t("files.preview", "预览")}
                        >
                          <Eye className="size-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-8 text-muted-foreground hover:text-destructive"
                          onClick={() => runAction(() => deleteFile(f.name))}
                          title={t("files.delete", "删除")}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="shrink-0" style={{ height: "60%" }}>
          <div className="h-full px-6 pb-4">
            <GraphCanvas
              graphData={graphData}
              triplets={triplets}
              graphLoading={graphLoading}
              onGenerate={() => runAction(generateGraph)}
            />
          </div>
        </div>
      </div>

      <FileUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUpload={handleUpload}
        isGraphDataset={activeDataset?.fileType === "graph-data"}
      />

      <FilePreviewDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        fileName={previewFileName}
        preview={previewData}
        loading={previewLoading}
      />
    </main>
  )
}

function ParseStatusBadge({
  status,
  progress,
}: {
  status: FileItem["parseStatus"]
  progress: number
}) {
  const { t } = useI18n()
  if (status === "completed") {
    return (
      <Badge variant="default" className="gap-1 bg-emerald-500/15 text-emerald-500 hover:bg-emerald-500/15">
        <span className="size-1 rounded-full bg-emerald-500" />
        {t("files.completed", "已完成")}
      </Badge>
    )
  }
  if (status === "parsing") {
    return (
      <div className="flex w-32 items-center gap-2">
        <Progress value={progress} className="h-1.5 flex-1" />
        <span className="shrink-0 text-[11px] text-muted-foreground">
          {Math.round(progress)}%
        </span>
      </div>
    )
  }
  if (status === "error") {
    return (
      <Badge variant="destructive" className="gap-1">
        <span className="size-1 rounded-full bg-destructive-foreground" />
        {t("files.error", "失败")}
      </Badge>
    )
  }
  return (
    <Badge variant="secondary" className="gap-1">
      <span className="size-1 rounded-full bg-muted-foreground" />
      {t("files.pending", "待解析")}
    </Badge>
  )
}
