import type { Algorithm } from "@/core/types"
import { io, type Socket } from "socket.io-client"
import { getBaseUrlSync } from "./base"

// --- 后端 chat_response 事件格式 ---

export interface ChatResponse {
  type: "thinking" | "result" | "stream_end"
  contentType?:
    | "text"
    | "dag"
    | "code"
    | "clarification"
    | "intent_ready"
    | "subproblems"
    | "algorithm_selected"
    | "node_status"
    | "node_result"
  content?: unknown
  error?: string
  restart_required?: boolean
  /** 标记为占位提示（如开头的 "Analyzing your question..."），真实文本到达后应被替换 */
  placeholder?: boolean
  /** 同一请求内单调递增的事件序号（重放去重用） */
  seq?: number
}

export interface OldDagNode {
  id: string
  label: string
  tasktype: string
}

export interface OldDagEdge {
  from: string
  to: string
}

export interface OldDag {
  nodes: OldDagNode[]
  edges: OldDagEdge[]
}

/** subproblems 事件：拆解出的子问题列表（与后端 subquery_plan 一致） */
export interface OldSubquery {
  id: string
  query: string
  depends_on: string[]
}

export interface SubproblemsContent {
  subqueries: OldSubquery[]
}

/** algorithm_selected 事件：单个子问题选定的算法 */
export interface AlgorithmSelectedContent {
  step_id: number
  question: string
  task_type: string
  algorithm?: string | null
}

/** node_status / node_result 事件：单节点执行状态与结果（真实后端执行时下发） */
export interface NodeExecutionContent {
  /** 后端 step_id，经 DAG 事件的 idMap 映射到前端节点 id */
  step_id: number
  status: "running" | "success" | "failed"
  question?: string
  task_type?: string
  algorithm?: string | null
  /** 失败原因（status === "failed" 时） */
  error?: string
  /** 仅 node_result 携带：截断后的结构化输出 */
  outputs?: NodeOutputPayload[]
}

/** 后端单个 StepOutputItem 的原始（已截断）视图 */
export interface NodeOutputPayload {
  output_id: number
  source: string
  task_type?: string
  description?: string
  fields?: { key: string; type: string; desc?: string; truncated?: boolean; total?: number }[]
  value: unknown
  truncated?: boolean
  total?: number
  path?: string | null
}

// --- 发送参数 ---

export interface ChatRequest {
  conversation_id?: string
  clarification_id?: string
  message?: string
  model: string
  dataset: string
  dataset_type?: string
  mode?: "normal" | "interact"
  expert_mode?: boolean
  dag_confirm?: "yes" | "no"
  is_dag_modification?: boolean
  dag_id?: string
  modifications?: string
  request_id?: string
}

// --- 回调 ---

export type ChatStreamCallback = (event: ChatResponse) => void

// The paper backend broadcasts chat_response without request IDs.
// Keep one request active and never replay a calculation after disconnection.
let socket: Socket | null = null
let activeCallback: ChatStreamCallback | null = null
let currentDagToken: string | null = null
let chatState: "offline" | "ready" | "busy" = "offline"
const listeners = new Set<() => void>()
function notifyState() {
  chatState = !socket?.connected ? "offline" : activeCallback ? "busy" : "ready"
  for (const listener of listeners) listener()
}
export function subscribeChatState(listener: () => void): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}
export function getChatState() { return chatState }

export function ensureChatConnection(): Socket {
  if (!socket) {
    socket = io(getBaseUrlSync() || undefined, { autoConnect: true, reconnection: true })
    socket.on("connect", notifyState)
    socket.on("chat_response", (event: ChatResponse) => {
      const callback = activeCallback
      if (!callback) return
      if (event.type === "stream_end" || event.error) activeCallback = null
      notifyState()
      callback(event)
    })
    socket.on("disconnect", () => {
      const callback = activeCallback
      activeCallback = null
      currentDagToken = null
      notifyState()
      callback?.({ type: "stream_end", error: "连接中断，请确认服务状态后重新发起分析。 / Connection interrupted; retry after checking the server." })
    })
  }
  return socket
}

export function isChatConnected(): boolean { return ensureChatConnection().connected }
export function isChatBusy(): boolean { return activeCallback !== null }
export function isCurrentDag(token?: string): boolean { return !!token && currentDagToken === token }

export function sendChatRequest(params: ChatRequest, callback: ChatStreamCallback): void {
  const connection = ensureChatConnection()
  if (activeCallback) {
    callback({ type: "stream_end", error: "已有分析正在执行，请等待结束。 / An analysis is already running." })
    return
  }
  if (!connection.connected) {
    callback({ type: "stream_end", error: "聊天服务未连接，请稍后重试。 / Chat service is disconnected." })
    return
  }
  if ((params.dag_confirm || params.is_dag_modification) && !isCurrentDag(params.dag_id)) {
    callback({ type: "stream_end", error: "此方案已不再是当前分析，请重新生成方案。 / Regenerate this plan before executing or modifying it." })
    return
  }
  if (!params.dag_confirm && !params.is_dag_modification) currentDagToken = params.dag_id ?? null
  activeCallback = callback
  notifyState()
  connection.emit("chat_request", params)
}

// --- 解析 tasktype 提取算法名 ---

/**
 * 从 tasktype 字符串中提取算法名。
 * 格式示例:
 *   "Graph Algorithm (pagerank)"    → "pagerank"
 *   "Graph Algorithm"               → null
 *   "Numeric Analysis"              → null
 */
export function parseAlgorithmName(tasktype: string): string | null {
  const m = tasktype.match(/\(([^)]+)\)/)
  return m ? m[1].trim() : null
}


export function matchAlgorithm(
  name: string,
  algorithms: Algorithm[],
): Algorithm | undefined {
  // 精确匹配 name
  let a = algorithms.find((x) => x.name === name)
  if (a) return a
  // id 匹配（可能带 run_ 前缀）
  a = algorithms.find((x) => x.id === name || x.id === `run_${name}`)
  if (a) return a
  // 常见别名映射
  const aliases: Record<string, string> = {
    betweenness: "betweenness_centrality",
    closeness: "closeness_centrality",
    pagerank: "pagerank",
    hits: "hits",
    louvain: "louvain_communities",
    "label-propagation": "label_propagation_communities",
    label_propagation: "label_propagation_communities",
    dijkstra: "dijkstra_path",
    "floyd-warshall": "floyd_warshall",
    bfs: "bfs_tree",
    dfs: "dfs_tree",
    "connected-components": "connected_components",
    "max-flow": "maximum_flow",
    "min-cut": "minimum_cut",
    clustering: "clustering",
    jaccard: "jaccard_coefficient",
    "is-bipartite": "is_bipartite",
    mst: "minimum_spanning_tree",
    "topological-sort": "topological_sort",
    "greedy-color": "greedy_color",
    "is-isomorphic": "is_isomorphic",
    "find-cycle": "find_cycle",
    "max-weight-matching": "max_weight_matching",
    assortativity: "degree_assortativity_coefficient",
    diameter: "diameter",
    "global-efficiency": "global_efficiency",
    "cartesian-product": "cartesian_product",
  }
  const resolved = aliases[name] ?? aliases[name.replace(/-/g, "_")]
  if (resolved) {
    return (
      algorithms.find((x) => x.name === resolved) ??
      algorithms.find((x) => x.id === `run_${resolved}`)
    )
  }
  return undefined
}
