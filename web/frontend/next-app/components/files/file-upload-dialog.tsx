"use client"
import * as React from "react"
import { Upload, X } from "lucide-react"
import type { UploadConfig } from "@/core/types"
import { useI18n } from "@/core/i18n/i18n-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { formatSize } from "@/core/utils"

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onUpload: (files: File[], config: UploadConfig) => Promise<void>
  isGraphDataset: boolean
}

export function FileUploadDialog({ open, onOpenChange, onUpload, isGraphDataset }: Props) {
  const { t, lang } = useI18n()
  const [files, setFiles] = React.useState<File[]>([])
  const [config, setConfig] = React.useState<UploadConfig>({ directed: true })
  const [uploading, setUploading] = React.useState(false)
  const [error, setError] = React.useState("")
  const label = (zh: string, en: string) => lang === "zh-CN" ? zh : en
  React.useEffect(() => {
    if (!open) { setFiles([]); setConfig({ directed: true }); setError("") }
  }, [open])
  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return
    setFiles((previous) => {
      const all = [...previous]
      for (const file of Array.from(incoming)) if (!all.some((f) => f.name === file.name)) all.push(file)
      return all
    })
  }
  async function submit() {
    setError(""); setUploading(true)
    try { await onUpload(files, config); onOpenChange(false) }
    catch (err) { setError(err instanceof Error ? err.message : String(err)) }
    finally { setUploading(false) }
  }
  const field = (key: keyof UploadConfig, title: string, required = false) => (
    <div className="flex flex-col gap-1.5" key={key}>
      <Label htmlFor={`upload-${key}`} className="text-xs">{title}{required ? " *" : ""}</Label>
      <Input id={`upload-${key}`} value={String(config[key] ?? "")} disabled={uploading}
        onChange={(e) => setConfig((c) => ({ ...c, [key]: e.target.value }))} className="h-8 text-sm" />
    </div>
  )
  const fileSelect = (key: "vertexFileName" | "edgeFileName", title: string) => (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={`upload-${key}`} className="text-xs">{title}</Label>
      <select id={`upload-${key}`} value={config[key] ?? ""} disabled={uploading}
        onChange={(e) => setConfig((c) => ({ ...c, [key]: e.target.value }))} className="h-8 rounded-md border bg-background px-2 text-sm">
        <option value="">{label("请选择", "Select")}</option>
        {files.map((file) => <option key={file.name} value={file.name}>{file.name}</option>)}
      </select>
    </div>
  )
  return (
    <Dialog open={open} onOpenChange={(value) => { if (!uploading) onOpenChange(value) }}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("files.uploadTitle", "上传文件")}</DialogTitle>
          <DialogDescription>{isGraphDataset ? label("选择一个边文件及可选的一个顶点文件，并填写图配置。", "Select an edge file and an optional vertex file, then configure the graph.") : t("files.uploadDesc", "支持拖拽上传，一次可选择多个文件。")}</DialogDescription>
        </DialogHeader>
        <div onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); if (!uploading) addFiles(e.dataTransfer.files) }} className="rounded-md border-2 border-dashed p-4">
          <Label htmlFor="upload-files">{t("files.browseFiles", "浏览文件")}</Label>
          <input id="upload-files" type="file" multiple disabled={uploading} onChange={(e) => addFiles(e.target.files)} className="mt-2 block w-full text-sm" />
          {files.map((file) => <div key={file.name} className="mt-2 flex items-center gap-2 text-sm">
            <span className="min-w-0 flex-1 truncate">{file.name} · {formatSize(file.size)}</span>
            <button aria-label={`${label("移除", "Remove")} ${file.name}`} disabled={uploading} onClick={() => setFiles((all) => all.filter((f) => f.name !== file.name))}><X className="size-4" /></button>
          </div>)}
        </div>
        {isGraphDataset && <div className="grid grid-cols-2 gap-3 rounded-md border p-4">
          {field("graphName", label("图名称", "Graph name"), true)}
          {fileSelect("edgeFileName", label("边文件 *", "Edge file *"))}
          {fileSelect("vertexFileName", label("顶点文件（可选）", "Vertex file (optional)"))}
          {field("vertexIdField", label("顶点 ID 字段", "Vertex ID column"), !!config.vertexFileName)}
          {field("vertexLabelField", label("顶点名称字段", "Vertex name column"))}
          {field("vertexPropertiesField", label("顶点属性字段（逗号分隔）", "Vertex property columns (comma separated)"))}
          {field("edgeSourceField", label("边源节点字段", "Edge source column"), true)}
          {field("edgeTargetField", label("边目标节点字段", "Edge target column"), true)}
          {field("edgeRelationField", label("边关系字段", "Edge relation column"))}
          {field("edgeWeightField", label("边权重字段", "Edge weight column"))}
          <label className="col-span-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={config.directed ?? true} disabled={uploading} onChange={(e) => setConfig((c) => ({ ...c, directed: e.target.checked }))} />{label("有向图", "Directed graph")}</label>
        </div>}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button variant="outline" disabled={uploading} onClick={() => onOpenChange(false)}>{t("files.cancel", "取消")}</Button>
          <Button disabled={!files.length || uploading} onClick={submit} className="gap-2"><Upload className="size-4" />{uploading ? t("files.uploading", "上传中...") : t("files.upload", "上传")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
