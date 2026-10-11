"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { ArrowUp, Loader2, Plus } from "lucide-react"
import { useI18n } from "@/core/i18n/i18n-provider"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/core/utils"
import type { Dataset, Model } from "@/core/types"

export interface ChatSettings {
  model: string
  dataset: string
  expertMode: boolean
  interactiveMode: boolean
}

interface ChatInputProps {
  onSubmit: (q: string) => void
  disabled?: boolean
  lockSettings?: boolean
  settings: ChatSettings
  onSettingsChange: (s: ChatSettings) => void
  datasets: Dataset[]
  models: Model[]
}

export function ChatInput({
  onSubmit,
  disabled,
  lockSettings = false,
  settings,
  onSettingsChange,
  datasets,
  models,
}: ChatInputProps) {
  const { t } = useI18n()
  const router = useRouter()
  const [value, setValue] = React.useState("")
  const ref = React.useRef<HTMLTextAreaElement>(null)
  const [modelOpen, setModelOpen] = React.useState(false)

  React.useEffect(() => {
    if (!ref.current) return
    ref.current.style.height = "0px"
    ref.current.style.height = `${Math.min(ref.current.scrollHeight, 200)}px`
  }, [value])

  function submit() {
    const v = value.trim()
    if (!v || disabled) return
    onSubmit(v)
    setValue("")
  }

  return (
    <div className="border-t border-border bg-background/80 px-6 py-4 backdrop-blur">
      <div className="mx-auto mb-3 flex max-w-4xl flex-wrap items-center gap-3">
        <Select
          disabled={lockSettings}
          value={settings.model}
          onValueChange={(v) => onSettingsChange({ ...settings, model: v })}
          open={modelOpen}
          onOpenChange={setModelOpen}
        >
          <SelectTrigger className="h-8 w-[150px] text-xs">
            <SelectValue placeholder={t("chat.selectModel", "选择模型")} />
          </SelectTrigger>
          <SelectContent>
            {models.length === 0 ? (
              <div className="px-2 py-1.5 text-xs text-muted-foreground">
                {t("chat.noModels", "暂无模型")}
              </div>
            ) : (
              models.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.name}
                </SelectItem>
              ))
            )}
            <SelectSeparator />
            <div
              role="button"
              tabIndex={0}
              onClick={() => { setModelOpen(false); router.push("/models") }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  setModelOpen(false); router.push("/models")
                }
              }}
              className="relative flex w-full cursor-pointer items-center gap-2 rounded-sm py-1.5 pl-2 pr-2 text-sm text-primary outline-none hover:bg-accent focus:bg-accent"
            >
              <Plus className="size-3.5" />
              {t("chat.configureModels", "配置模型")}
            </div>
          </SelectContent>
        </Select>

        <Select
          disabled={lockSettings}
          value={settings.dataset}
          onValueChange={(v) => onSettingsChange({ ...settings, dataset: v })}
        >
          <SelectTrigger className="h-8 w-[180px] text-xs">
            <SelectValue placeholder={t("chat.selectDataset", "选择数据集")} />
          </SelectTrigger>
          <SelectContent>
            {datasets.length === 0 ? (
              <div className="px-2 py-1.5 text-xs text-muted-foreground">
                {t("chat.noDatasets", "暂无数据集")}
              </div>
            ) : (
              datasets.map((d) => (
                <SelectItem key={d.id} value={d.id}>
                  {d.name}
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-1.5">
          <Switch
            id="expert-mode"
            checked={settings.expertMode}
            disabled={lockSettings || settings.interactiveMode}
            onCheckedChange={(v) => onSettingsChange({ ...settings, expertMode: v })}
          />
          <label
            htmlFor="expert-mode"
            className={cn("select-none text-xs", settings.interactiveMode ? "text-muted-foreground/50" : "text-muted-foreground")}
          >
            {t("chat.expertMode", "专家模式")}
          </label>
        </div>

        <div className="flex items-center gap-1.5">
          <Switch
            id="interactive-mode"
            checked={settings.interactiveMode}
            disabled={lockSettings || settings.expertMode}
            onCheckedChange={(v) => onSettingsChange({ ...settings, interactiveMode: v })}
          />
          <label
            htmlFor="interactive-mode"
            className={cn("select-none text-xs", settings.expertMode ? "text-muted-foreground/50" : "text-muted-foreground")}
          >
            {t("chat.interactiveMode", "交互模式")}
          </label>
        </div>
      </div>

      <div
        className={cn(
          "mx-auto flex max-w-4xl items-end gap-2 rounded-2xl border border-border bg-card p-2 shadow-sm transition-colors",
          !disabled && "focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/15",
        )}
      >
        <Textarea
          ref={ref}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() }
          }}
          rows={1}
          placeholder={disabled ? t("chat.busyPlaceholder", "系统正在思考或执行中，请稍候…") : t("chat.placeholder", "描述你的分析目标，例如：在好友图中找出最有影响力的 KOL")}
          className="min-h-9 flex-1 resize-none border-0 bg-transparent px-2 py-2 text-[15px] leading-6 shadow-none focus-visible:ring-0"
          disabled={disabled}
        />
        <Button
          type="button"
          size="icon"
          className="size-9 shrink-0 rounded-xl"
          onClick={submit}
          disabled={disabled || !value.trim()}
          aria-label={t("chat.send", "发送")}
        >
          {disabled ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
        </Button>
      </div>
      <div className="mx-auto mt-2 flex max-w-4xl items-center justify-between text-[11px] text-muted-foreground">
        <span>{t("chat.shortcut", "按 Enter 发送，Shift+Enter 换行")}</span>
        <span>{t("chat.autoPlan", "易图 会基于当前算法库自动规划最佳工作流")}</span>
      </div>
    </div>
  )
}
