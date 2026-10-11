"use client"

import * as React from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { useI18n } from "@/core/i18n/i18n-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

interface CreateModelDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreate: (input: {
    name: string
    baseUrl: string
    apiKey: string
  }) => Promise<void>
}

export function CreateModelDialog({
  open,
  onOpenChange,
  onCreate,
}: CreateModelDialogProps) {
  const { t } = useI18n()
  const [name, setName] = React.useState("")
  const [baseUrl, setBaseUrl] = React.useState("")
  const [apiKey, setApiKey] = React.useState("")
  const [submitting, setSubmitting] = React.useState(false)

  React.useEffect(() => {
    if (open) {
      setName("")
      setBaseUrl("")
      setApiKey("")
      setSubmitting(false)
    }
  }, [open])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !baseUrl.trim() || !apiKey.trim()) return

    setSubmitting(true)
    try {
      await onCreate({
        name: name.trim(),
        baseUrl: baseUrl.trim(),
        apiKey: apiKey.trim(),
      })
      onOpenChange(false)
    } catch {
      // error handled by store
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("models.addTitle", "添加新模型")}</DialogTitle>
          <DialogDescription>
            {t("models.addDesc", "填写模型信息，系统将自动验证 API 连通性。")}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="model-name">{t("models.name", "模型名称")}</Label>
              <Input
                id="model-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("models.namePlaceholder", "例如：GPT-4-Turbo")}
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="model-url">{t("models.baseUrl", "Base URL")}</Label>
              <Input
                id="model-url"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={t("models.urlPlaceholder", "https://api.openai.com/v1")}
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="model-key">{t("models.apiKey", "API Key")}</Label>
              <Input
                id="model-key"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={t("models.keyPlaceholder", "sk-...")}
                required
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("models.cancel", "取消")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? t("models.submitting", "验证中…") : t("models.submit", "添加模型")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
