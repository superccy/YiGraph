"use client"

import * as React from "react"
import {
  Play,
  Wrench,
  Workflow,
  Info,
  CheckCircle2,
  Loader2,
  Circle,
  ThumbsUp,
  ThumbsDown,
  RotateCcw,
} from "lucide-react"
import type { DagEdge, DagNode, WorkflowPlan } from "@/core/types"
import { useI18n } from "@/core/i18n/i18n-provider"
import { useAlgorithms } from "@/core/algorithms-store"
import { submitFeedback } from "@/core/api/feedback"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { cn } from "@/core/utils"
import { AlgorithmInfoModal } from "./algorithm-info-modal"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"


export function DagPanel({
  plan,
  userQuestion,
  onExecute,
  onModify,
  onLayoutChange,
  interactive,
}: {
  plan: WorkflowPlan
  userQuestion: string
  onExecute: () => void
  onModify: (modificationText: string) => void
  onLayoutChange: (layout: Record<string, { x: number; y: number }>) => void
  interactive: boolean
}) {
  const { t } = useI18n()
  const [infoId, setInfoId] = React.useState<string | null>(null)
  const [modifyOpen, setModifyOpen] = React.useState(false)
  const [modifyText, setModifyText] = React.useState("")
  const [feedback, setFeedback] = React.useState<"like" | "dislike" | null>(null)
  const phase = plan.phase
  const readyToExecute = phase === "dag-ready" && interactive
  const layout = plan.layout ?? {}
  const hasCustomLayout = Object.keys(layout).length > 0

  const handleFeedback = (type: "like" | "dislike") => {
    if (feedback) return
    setFeedback(type)
    const dagSummary = JSON.stringify({
      nodes: plan.nodes.map((n) => ({ id: n.id, label: n.label, algorithmId: n.algorithmId })),
      edges: plan.edges.map((e) => ({ source: e.source, target: e.target })),
    })
    submitFeedback({
      userQuestion,
      analysisOutput: dagSummary,
      type: "dag",
      feedback: type,
    }).catch(() => {
      setFeedback(null)
    })
  }

  return (
    <Card className="overflow-hidden p-0">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2">
          <Workflow className="size-4 text-primary" />
          <span className="text-sm font-semibold">{t("dag.panelTitle", "工作流 DAG")}</span>
          <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
            {plan.nodes.length} {t("dag.nodes", "节点")} · {plan.edges.length} {t("dag.edges", "边")}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Info className="size-3" />
          {t("dag.inspectHint", "点击算法节点查看详情")}
          {hasCustomLayout && (
            <>
              <span className="mx-1 text-border">|</span>
              <button
                onClick={() => onLayoutChange({})}
                className="flex items-center gap-1 rounded px-1 py-0.5 transition-colors hover:bg-muted hover:text-foreground"
              >
                <RotateCcw className="size-3" />
                {t("dag.resetLayout", "重置布局")}
              </button>
            </>
          )}
          <span className="mx-1 text-border">|</span>
          <button
            onClick={() => handleFeedback("like")}
            disabled={feedback !== null}
            className={cn(
              "rounded p-0.5 transition-colors",
              feedback === "like"
                ? "text-primary"
                : "text-muted-foreground hover:text-primary",
              feedback !== null && feedback !== "like" && "opacity-40",
            )}
          >
            <ThumbsUp className={cn("size-3", feedback === "like" && "fill-primary")} />
          </button>
          <button
            onClick={() => handleFeedback("dislike")}
            disabled={feedback !== null}
            className={cn(
              "rounded p-0.5 transition-colors",
              feedback === "dislike"
                ? "text-destructive"
                : "text-muted-foreground hover:text-destructive",
              feedback !== null && feedback !== "dislike" && "opacity-40",
            )}
          >
            <ThumbsDown className={cn("size-3", feedback === "dislike" && "fill-destructive")} />
          </button>
        </div>
      </div>

      <div className="relative">
        <DagCanvas
          plan={plan}
          onInspect={setInfoId}
          onMoveNode={(nodeId, pos) =>
            onLayoutChange({ ...layout, [nodeId]: pos })
          }
        />
      </div>

      {readyToExecute && (
        <div className="flex items-center justify-between gap-3 border-t border-border bg-muted/30 px-5 py-3">
          <p className="text-xs text-muted-foreground">
            {t("dag.readyHint", "规划完成。请确认执行或修改 DAG。")}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              className="gap-1.5"
              onClick={() => {
                setModifyText("")
                setModifyOpen(true)
              }}
            >
              <Wrench className="size-4" />
              {t("dag.modifyDag", "修改 DAG")}
            </Button>
            <Button className="gap-1.5" onClick={onExecute}>
              <Play className="size-4" />
              {t("dag.confirmExecute", "确定执行")}
            </Button>
          </div>
        </div>
      )}

      {phase === "executing" && (
        <div className="flex items-center gap-2 border-t border-border bg-primary/5 px-5 py-3 text-xs text-primary">
          <Loader2 className="size-3.5 animate-spin" />
          {t("dag.executing", "执行中")}
        </div>
      )}

      {phase === "executed" && (
        <div className="flex items-center gap-2 border-t border-border bg-accent/10 px-5 py-3 text-xs text-accent-foreground">
          <CheckCircle2 className="size-3.5" />
          {t("dag.executed", "执行完成")}
        </div>
      )}

      <AlgorithmInfoModal
        algorithmId={infoId}
        onClose={() => setInfoId(null)}
      />

      <Dialog open={modifyOpen} onOpenChange={setModifyOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("dag.modifyTitle", "修改工作流 DAG")}</DialogTitle>
            <DialogDescription>
              {t("dag.modifyDesc", "请输入您的 DAG 修改建议")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Textarea
              id="dag-modify-text"
              placeholder={t("dag.modifyPlaceholder", "描述您想要如何调整这个工作流…")}
              value={modifyText}
              onChange={(e) => setModifyText(e.target.value)}
              rows={4}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setModifyOpen(false)}>
              {t("common.cancel", "取消")}
            </Button>
            <Button
              onClick={() => {
                if (modifyText.trim()) {
                  onModify(modifyText.trim())
                  setModifyOpen(false)
                }
              }}
              disabled={!modifyText.trim()}
            >
              {t("common.confirm", "确认")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

/* -------------------------------- Canvas --------------------------------- */

interface Pos {
  x: number
  y: number
  h: number
}

const NODE_W = 200
const NODE_MIN_H = 78
const COL_GAP = 260
const ROW_GAP = 32
const CANVAS_MIN_W = 400
const CANVAS_MIN_H = 200
const CANVAS_PAD = 20
/** 超过该位移才判定为拖动，避免和"点击算法详情"冲突 */
const DRAG_THRESHOLD_PX = 4
// 长标签换行的高度估算参数：中文每字约 14px，节点内可用宽度约 172px
const LABEL_CHARS_PER_LINE = 10
const LABEL_LINE_HEIGHT = 20
const NODE_BASE_H = 58

/** 根据标签长度估算节点高度（标签会换行显示） */
function estimateNodeHeight(label: string): number {
  const lines = Math.max(
    1,
    Math.ceil((label?.length ?? 0) / LABEL_CHARS_PER_LINE),
  )
  return Math.max(NODE_MIN_H, NODE_BASE_H + (lines - 1) * LABEL_LINE_HEIGHT)
}

/** 将一列节点自上而下堆叠，返回列底部的 y 坐标 */
function stackColumn(
  items: DagNode[],
  x: number,
  startY: number,
  positions: Record<string, Pos>,
): number {
  let y = startY
  for (const n of items) {
    const h = estimateNodeHeight(n.label)
    positions[n.id] = { x, y, h }
    y += h + ROW_GAP
  }
  return y - ROW_GAP
}

function computeLayout(
  nodes: DagNode[],
  edges: DagEdge[],
): Record<string, Pos> {
  const positions: Record<string, Pos> = {}

  // 后端 DAG 模式：根据拓扑自动分列
  const incoming = new Set<string>()
  const outgoing = new Set<string>()
  edges.forEach((e) => {
    outgoing.add(e.source)
    incoming.add(e.target)
  })

  const sources = nodes.filter(
    (n) => !incoming.has(n.id),
  )
  const sinks = nodes.filter(
    (n) => !outgoing.has(n.id),
  )
  const intermediates = nodes.filter(
    (n) => incoming.has(n.id) && outgoing.has(n.id),
  )

  stackColumn(sources, 20, 20, positions)
  stackColumn(intermediates, 20 + COL_GAP, 20, positions)
  stackColumn(sinks, 20 + COL_GAP * 2, 20, positions)

  return positions
}

interface DragSession {
  id: string
  pointerId: number
  startX: number
  startY: number
  originX: number
  originY: number
  moved: boolean
}

function DagCanvas({
  plan,
  onInspect,
  onMoveNode,
}: {
  plan: WorkflowPlan
  onInspect: (algoId: string) => void
  onMoveNode: (nodeId: string, pos: { x: number; y: number }) => void
}) {
  const { getById } = useAlgorithms()

  // 自动布局（按拓扑分列）
  const basePositions = React.useMemo(
    () => computeLayout(plan.nodes, plan.edges),
    [plan.nodes, plan.edges],
  )

  // 拖动预览：拖动过程中只更新本地坐标，松手后才写回 plan.layout
  const [drag, setDrag] = React.useState<{
    id: string
    x: number
    y: number
  } | null>(null)
  const dragRef = React.useRef<DragSession | null>(null)
  const dragPosRef = React.useRef<{ id: string; x: number; y: number } | null>(null)
  const rafRef = React.useRef<number | null>(null)
  const suppressClickRef = React.useRef(false)

  // plan.layout（已保存的手动位置）覆盖自动布局，拖动预览再覆盖两者
  const positions = React.useMemo(() => {
    const next: Record<string, Pos> = {}
    for (const [id, p] of Object.entries(basePositions)) {
      const saved = plan.layout?.[id]
      next[id] = saved ? { ...p, x: saved.x, y: saved.y } : p
    }
    if (drag && next[drag.id]) {
      next[drag.id] = { ...next[drag.id], x: drag.x, y: drag.y }
    }
    return next
  }, [basePositions, plan.layout, drag])

  // 卸载时取消挂起的帧回调
  React.useEffect(
    () => () => {
      if (rafRef.current !== null) window.cancelAnimationFrame(rafRef.current)
    },
    [],
  )

  const handlePointerDown =
    (nodeId: string) => (e: React.PointerEvent<HTMLDivElement>) => {
      if (e.pointerType === "mouse" && e.button !== 0) return
      // 节点内的链接/按钮保持原生点击行为，不作为拖动把手
      const target = e.target as HTMLElement | null
      if (target?.closest("button, a, input, textarea, select")) return
      const pos = positions[nodeId]
      if (!pos) return
      e.currentTarget.setPointerCapture(e.pointerId)
      dragRef.current = {
        id: nodeId,
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        originX: pos.x,
        originY: pos.y,
        moved: false,
      }
      suppressClickRef.current = false
    }

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const session = dragRef.current
    if (!session || session.pointerId !== e.pointerId) return
    const dx = e.clientX - session.startX
    const dy = e.clientY - session.startY
    if (!session.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return
    session.moved = true
    dragPosRef.current = {
      id: session.id,
      x: Math.max(0, session.originX + dx),
      y: Math.max(0, session.originY + dy),
    }
    // 每帧最多提交一次，避免 pointermove 高频重渲染
    if (rafRef.current === null) {
      rafRef.current = window.requestAnimationFrame(() => {
        rafRef.current = null
        setDrag(dragPosRef.current)
      })
    }
  }

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const session = dragRef.current
    if (!session || session.pointerId !== e.pointerId) return
    dragRef.current = null
    if (rafRef.current !== null) {
      window.cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    const finalPos = dragPosRef.current
    dragPosRef.current = null
    setDrag(null)
    if (!session.moved) {
      // 未超过阈值：保持普通点击行为
      suppressClickRef.current = false
      return
    }
    // 拖动结束后抑制随之而来的 click，避免误开算法详情弹窗
    suppressClickRef.current = true
    if (finalPos) onMoveNode(session.id, { x: finalPos.x, y: finalPos.y })
  }

  const handleClickCapture = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!suppressClickRef.current) return
    suppressClickRef.current = false
    e.preventDefault()
    e.stopPropagation()
  }

  // 根据实际布局（含拖动预览）计算画布尺寸，拖出右下角时画布随之扩展
  const allPos = Object.values(positions)
  const width =
    Math.max(...allPos.map((p) => p.x + NODE_W), CANVAS_MIN_W) + CANVAS_PAD
  const height =
    Math.max(...allPos.map((p) => p.y + p.h), CANVAS_MIN_H) + CANVAS_PAD

  return (
    <div className="bg-dots w-full overflow-auto">
      <div
        className="relative"
        style={{ width: `${width}px`, height: `${height}px` }}
      >
        {/* Edges */}
        <svg
          className="absolute inset-0"
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          aria-hidden="true"
        >
          <defs>
            <marker
              id="arrow"
              markerWidth="10"
              markerHeight="10"
              refX="9"
              refY="5"
              orient="auto"
            >
              <path d="M0,0 L10,5 L0,10 z" className="fill-border" />
            </marker>
            <marker
              id="arrow-active"
              markerWidth="10"
              markerHeight="10"
              refX="9"
              refY="5"
              orient="auto"
            >
              <path d="M0,0 L10,5 L0,10 z" fill="var(--primary)" />
            </marker>
          </defs>
          {plan.edges.map((edge) => (
            <EdgePath
              key={edge.id}
              edge={edge}
              nodes={plan.nodes}
              positions={positions}
            />
          ))}
        </svg>

        {/* Nodes */}
        {plan.nodes.map((node) => {
          const pos = positions[node.id]
          if (!pos) return null
          const algo = getById(node.algorithmId)
          const noAlgo = !node.algorithmId
          return (
            <DagNodeBox
              key={node.id}
              node={node}
              algoName={algo?.name ?? (noAlgo ? "" : node.algorithmId)}
              algoDisplayName={
                algo?.displayName ??
                (noAlgo ? (node.taskType ?? "") : node.algorithmId)
              }
              noAlgorithm={noAlgo}
              x={pos.x}
              y={pos.y}
              dragging={drag?.id === node.id}
              onPointerDown={handlePointerDown(node.id)}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
              onClickCapture={handleClickCapture}
              onInspect={() => onInspect(node.algorithmId)}
            />
          )
        })}
      </div>
    </div>
  )
}

function EdgePath({
  edge,
  nodes,
  positions,
}: {
  edge: DagEdge
  nodes: DagNode[]
  positions: Record<string, Pos>
}) {
  const from = positions[edge.source]
  const to = positions[edge.target]
  if (!from || !to) return null
  const sourceNode = nodes.find((n) => n.id === edge.source)
  const targetNode = nodes.find((n) => n.id === edge.target)
  const x1 = from.x + NODE_W
  const y1 = from.y + from.h / 2
  const x2 = to.x
  const y2 = to.y + to.h / 2
  const midX = (x1 + x2) / 2
  const d = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`

  const isFlowing =
    sourceNode?.status === "done" && targetNode?.status === "running"
  const isActive =
    sourceNode?.status === "done" || sourceNode?.status === "running"

  return (
    <path
      d={d}
      fill="none"
      className={cn(
        isFlowing
          ? "stroke-primary edge-flow"
          : isActive
            ? "stroke-primary/60"
            : "stroke-border",
      )}
      strokeWidth={1.8}
      markerEnd={isActive ? "url(#arrow-active)" : "url(#arrow)"}
    />
  )
}

function DagNodeBox({
  node,
  algoName,
  algoDisplayName,
  noAlgorithm,
  x,
  y,
  dragging,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
  onClickCapture,
  onInspect,
}: {
  node: DagNode
  algoName: string
  algoDisplayName: string
  noAlgorithm?: boolean
  x: number
  y: number
  dragging?: boolean
  onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => void
  onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => void
  onPointerUp: (e: React.PointerEvent<HTMLDivElement>) => void
  onPointerCancel: (e: React.PointerEvent<HTMLDivElement>) => void
  onClickCapture: (e: React.MouseEvent<HTMLDivElement>) => void
  onInspect: () => void
}) {
  const { t } = useI18n()
  const roleLabel = t("dag.subtask", "子任务")
  const statusBg =
    node.status === "done"
      ? "border-accent/40 bg-accent/10"
      : node.status === "running"
        ? "border-primary/50 bg-primary/5"
        : node.status === "error"
          ? "border-destructive/50 bg-destructive/10"
          : "border-border bg-card"
  const Icon =
    node.status === "done"
      ? CheckCircle2
      : node.status === "running"
        ? Loader2
        : Circle
  const iconColor =
    node.status === "done"
      ? "text-accent"
      : node.status === "running"
        ? "text-primary"
        : "text-muted-foreground"

  return (
    <div
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onClickCapture={onClickCapture}
      className={cn(
        "absolute flex touch-none select-none flex-col rounded-lg border px-3 py-2 shadow-sm transition-colors",
        statusBg,
        dragging
          ? "z-20 cursor-grabbing shadow-md ring-2 ring-primary/30"
          : "cursor-grab",
      )}
      style={{
        left: `${x}px`,
        top: `${y}px`,
        width: `${NODE_W}px`,
        minHeight: `${NODE_MIN_H}px`,
      }}
      title={t("dag.dragNode", "拖动节点调整布局")}
    >
      <div className="flex items-center gap-2">
        <Icon
          className={cn(
            "size-3.5 shrink-0",
            iconColor,
            node.status === "running" && "animate-spin",
          )}
        />
        <span className="truncate text-[11px] font-medium text-muted-foreground">
          {roleLabel}
        </span>
        <span className="ml-auto rounded bg-muted px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
          {node.id}
        </span>
      </div>
      <div className="mt-1 break-words text-sm font-semibold leading-snug text-foreground">
        {node.label}
      </div>
      {noAlgorithm ? (
        <span className="mt-auto text-[11px] text-muted-foreground leading-tight">
          {algoDisplayName || t("dag.noAlgoTask", "—")}
        </span>
      ) : (
        <button
          onClick={onInspect}
          className="mt-auto flex items-start gap-1 self-start rounded text-[11px] text-primary underline-offset-2 hover:underline text-left"
        >
          <span className="font-mono break-all leading-tight">{algoName}</span>
          <span className="text-muted-foreground break-words leading-tight">· {algoDisplayName}</span>
        </button>
      )}
    </div>
  )
}
