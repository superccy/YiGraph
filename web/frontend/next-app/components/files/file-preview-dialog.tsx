"use client"

import * as React from "react"
import { FileText, Table } from "lucide-react"
import { marked } from "marked"
import { useI18n } from "@/core/i18n/i18n-provider"
import type { PreviewData } from "@/core/types"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  fileName: string
  preview: PreviewData | null
  loading: boolean
}

export function FilePreviewDialog({
  open,
  onOpenChange,
  fileName,
  preview,
  loading,
}: Props) {
  const { t } = useI18n()
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] w-[92vw] max-w-6xl overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="size-4" />
            {t("files.previewTitle", "文件预览")}
          </DialogTitle>
          <DialogDescription>{fileName}</DialogDescription>
        </DialogHeader>
        <div className="min-w-0">
          {loading ? (
            <div className="flex h-80 items-center justify-center">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <div className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                {t("common.loading", "加载中...")}
              </div>
            </div>
          ) : !preview ? (
            <div className="flex h-80 items-center justify-center text-sm text-muted-foreground">
              {t("files.previewError", "无法加载预览。")}
            </div>
          ) : preview.type === "csv" ? (
            <div className="max-h-[60vh] overflow-auto rounded-md border">
              <table className="text-sm">
                <thead className="sticky top-0 bg-muted">
                  <tr>
                    {preview.headers?.map((h) => (
                      <th
                        key={h}
                        className="whitespace-nowrap border-b border-border px-3 py-2 text-left text-xs font-medium text-muted-foreground"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {preview.rows?.map((row, i) => (
                    <tr key={i}>
                      {row.map((cell, j) => (
                        <td
                          key={j}
                          className="whitespace-nowrap px-3 py-1.5 text-xs text-muted-foreground"
                        >
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : preview.type === "pdf" ? (
            <iframe title={fileName} src={`data:application/pdf;base64,${preview.content}`} className="h-[60vh] w-full rounded-md border" />
          ) : preview.type === "html" ? (
            <iframe title={fileName} sandbox="" srcDoc={preview.content} className="h-[60vh] w-full rounded-md border bg-white" />
          ) : preview.type === "txt" ? (
            <div className="max-h-[60vh] overflow-auto rounded-md border bg-muted/30 p-4">
              <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-foreground">
                {preview.content}
              </pre>
            </div>
          ) : preview.type === "md" ? (
            <div className="max-h-[60vh] overflow-auto rounded-md border bg-background p-6">
              <iframe title={fileName} sandbox="" srcDoc={marked.parse(preview.content) as string} className="h-[55vh] w-full border-0 bg-white" />
            </div>
          ) : (
            <div className="flex h-80 flex-col items-center justify-center gap-3 text-center">
              <div className="flex size-12 items-center justify-center rounded-full bg-muted">
                <Table className="size-6 text-muted-foreground" />
              </div>
              <span className="text-sm text-muted-foreground">
                {preview.content}
              </span>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
