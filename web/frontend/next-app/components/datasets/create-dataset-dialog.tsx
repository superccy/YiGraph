"use client"

import * as React from "react"
import { Database, GitGraph } from "lucide-react"
import type { FileType } from "@/core/types"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useI18n } from "@/core/i18n/i18n-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreate: (input: { name: string; fileType: FileType }) => Promise<void>
}

export function CreateDatasetDialog({ open, onOpenChange, onCreate }: Props) {
  const { t } = useI18n()
  const [name, setName] = React.useState("")
  const [fileType, setFileType] = React.useState<FileType>("raw-data")
  const [submitting, setSubmitting] = React.useState(false)

  React.useEffect(() => {
    if (!open) {
      setName("")
      setFileType("raw-data")
    }
  }, [open])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    setSubmitting(true)
    await onCreate({ name: trimmed, fileType })
    setSubmitting(false)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("datasets.createButton", "创建数据集")}</DialogTitle>
          <DialogDescription>
            {t("datasets.createDesc", "创建一个新的数据集以组织和管理您的图数据文件。")}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="flex flex-col gap-4 py-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="ds-name">{t("datasets.name", "名称")}</Label>
              <Input
                id="ds-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("datasets.namePlaceholder", "输入数据集名称")}
                disabled={submitting}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="ds-type">{t("datasets.fileType", "文件类型")}</Label>
              <Select
                value={fileType}
                onValueChange={(v) => setFileType(v as FileType)}
                disabled={submitting}
              >
                <SelectTrigger id="ds-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="raw-data">
                    <div className="flex items-center gap-2">
                      <Database className="size-4" />
                      <span>{t("datasets.rawData", "原始数据")}</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="graph-data">
                    <div className="flex items-center gap-2">
                      <GitGraph className="size-4" />
                      <span>{t("datasets.graphData", "图数据")}</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("common.cancel", "取消")}
            </Button>
            <Button type="submit" disabled={submitting || !name.trim()}>
              {submitting ? t("common.loading", "创建中...") : t("datasets.createButton", "创建")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
