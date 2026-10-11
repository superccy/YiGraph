"use client"

import * as React from "react"
import cytoscape from "cytoscape"
import {
  ZoomIn,
  ZoomOut,
  Maximize,
  Maximize2,
  Download,
  Workflow,
  Loader2,
} from "lucide-react"
import { useI18n } from "@/core/i18n/i18n-provider"
import type { GraphData } from "@/core/types"
import { Button } from "@/components/ui/button"

interface Props {
  graphData: GraphData | null
  triplets: [string, string, string][]
  graphLoading: boolean
  onGenerate: () => void
}

const GROUP_PALETTE = [
  "#6366f1", "#ef4444", "#f59e0b", "#10b981", "#06b6d4",
  "#8b5cf6", "#ec4899", "#f97316", "#84cc16", "#14b8a6",
  "#3b82f6", "#e11d48", "#a855f7", "#22c55e", "#64748b",
]

const groupColorCache = new Map<string, string>()
let paletteIndex = 0

function getGroupColor(group: string | undefined): string {
  if (!group) return "#6366f1"
  if (groupColorCache.has(group)) return groupColorCache.get(group)!
  const color = GROUP_PALETTE[paletteIndex % GROUP_PALETTE.length]
  paletteIndex++
  groupColorCache.set(group, color)
  return color
}

export function GraphCanvas({ graphData, triplets, graphLoading, onGenerate }: Props) {
  const { t } = useI18n()
  const containerRef = React.useRef<HTMLDivElement>(null)
  const cyRef = React.useRef<cytoscape.Core | null>(null)

  React.useEffect(() => {
    if (!containerRef.current || !graphData) return

    if (cyRef.current) {
      cyRef.current.destroy()
      cyRef.current = null
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...graphData.nodes.map((n) => ({
          data: {
            id: n.id,
            label: n.label,
            group: n.group,
            color: n.color ?? getGroupColor(n.group),
          },
        })),
        ...graphData.edges.map((e) => ({
          data: {
            id: e.id,
            source: e.source,
            target: e.target,
            label: e.label,
          },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": (ele: cytoscape.NodeSingular) =>
              ele.data("color") || "#6366f1",
            label: "data(label)",
            "text-valign": "center",
            "text-halign": "center",
            color: "#1e293b",
            "font-size": "11px",
            width: 36,
            height: 36,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": "#94a3b8",
            "target-arrow-color": "#94a3b8",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": "10px",
            color: "#64748b",
          },
        },
      ],
      layout: {
        name: "cose",
        animate: true,
        animationDuration: 500,
        nodeRepulsion: () => 8000,
      },
    })

    cyRef.current = cy

    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [graphData])

  const handleZoomIn = () => cyRef.current?.zoom(cyRef.current.zoom() * 1.2)
  const handleZoomOut = () => cyRef.current?.zoom(cyRef.current.zoom() * 0.8)
  const handleFit = () => cyRef.current?.fit(undefined, 40)
  const handleFullscreen = () => {
    if (!containerRef.current) return
    const onFullscreenChange = () => {
      if (document.fullscreenElement) {
        setTimeout(() => cyRef.current?.fit(undefined, 40), 100)
      }
      document.removeEventListener("fullscreenchange", onFullscreenChange)
    }
    document.addEventListener("fullscreenchange", onFullscreenChange)
    containerRef.current.requestFullscreen()
  }
  const escapeCSV = (val: string) => {
    if (!val) return ""
    const s = String(val)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }

  const handleExport = () => {
    if (!triplets || triplets.length === 0) return
    const header = "Source,Relation,Target"
    const rows = triplets.map((t) =>
      [t[0], t[1], t[2]].map(escapeCSV).join(","),
    )
    const blob = new Blob(["﻿" + header + "\n" + rows.join("\n")], {
      type: "text/csv;charset=utf-8",
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "graph-triplets.csv"
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border bg-card">
      <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-foreground">
            {t("files.graphTitle", "知识图谱可视化")}
          </span>
          {!graphData && !graphLoading && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1.5 text-xs"
              onClick={onGenerate}
            >
              <Workflow className="size-3" />
              {t("files.generateGraph", "生成图谱")}
            </Button>
          )}
        </div>
        <div className="flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={handleZoomIn}
            title={t("files.zoomIn", "放大")}
          >
            <ZoomIn className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={handleZoomOut}
            title={t("files.zoomOut", "缩小")}
          >
            <ZoomOut className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={handleFit}
            title={t("files.fitScreen", "适应屏幕")}
          >
            <Maximize className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={handleFullscreen}
            title={t("files.fullscreen", "全屏")}
          >
            <Maximize2 className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={handleExport}
            title={t("files.exportCsv", "导出 CSV")}
          >
            <Download className="size-3.5" />
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        {graphLoading ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-5 animate-spin text-primary" />
            {t("files.generatingGraph", "正在生成知识图谱...")}
          </div>
        ) : graphData ? (
          <div ref={containerRef} className="h-full w-full bg-background" />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {t("files.generateHint", "点击\"生成图谱\"按钮可视化知识图谱")}
          </div>
        )}
      </div>
    </div>
  )
}
