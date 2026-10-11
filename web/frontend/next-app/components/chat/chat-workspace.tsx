"use client"

import * as React from "react"
import { useChat } from "@/core/chat-store"
import { useAlgorithms } from "@/core/algorithms-store"
import { useDatasets } from "@/core/datasets-store"
import { useModels } from "@/core/models-store"
import { ChatHistory } from "./chat-history"
import { ChatMain } from "./chat-main"
import type { Algorithm, ChatMessage, SubProblem, WorkflowPlan, Clarification } from "@/core/types"
import type { ChatSettings } from "./chat-input"
import type { NodeExecutionContent } from "@/core/api/chat"
import { isChatConnected, isChatBusy, matchAlgorithm, sendChatRequest, subscribeChatState, getChatState } from "@/core/api/chat"
import {
  createAdapterState,
  processChatEvent,
  convertOldDagToPlan,
} from "@/core/chat-adapter"

// 理解阶段进度条定时器（每个消息独立；模块级——切页/重挂载不影响进行中的动画）
const progressTimers = new Map<string, ReturnType<typeof setInterval>>()

export function ChatWorkspace() {
  const chatState = React.useSyncExternalStore(subscribeChatState, getChatState, () => "offline" as const)
  const {
    sessions,
    activeSession,
    activeId,
    createSession,
    selectSession,
    deleteSession,
    appendMessage,
    renameSession,
    updatePlan,
  } = useChat()
  const { algorithms, getById } = useAlgorithms()
  const { datasets } = useDatasets()
  const { models } = useModels()

  const [settings, setSettings] = React.useState<ChatSettings>({
    model: "",
    dataset: "",
    expertMode: false,
    interactiveMode: false,
  })

  /** 每个助手消息的后端 step_id → 前端节点 id 映射（dag 事件建立，执行事件消费） */
  const idMapsRef = React.useRef(new Map<string, Map<string, string>>())

  // Auto-select first model / dataset
  React.useEffect(() => {
    if (!settings.model && models.length > 0) {
      setSettings((s) => ({ ...s, model: models[0].id }))
    }
  }, [models, settings.model])

  React.useEffect(() => {
    if (!settings.dataset && datasets.length > 0) {
      setSettings((s) => ({ ...s, dataset: datasets[0].id }))
    }
  }, [datasets, settings.dataset])

  React.useEffect(() => {
    if (!activeId && sessions[0]) selectSession(sessions[0].id)
  }, [activeId, sessions, selectSession])

  function startUnderstandingProgress(sessionId: string, msgId: string) {
    const key = `${sessionId}-${msgId}`
    if (progressTimers.has(key)) return
    let p = 0
    const timer = setInterval(() => {
      p += 0.035
      if (p >= 0.9) {
        p = 0.9
        const t = progressTimers.get(key)
        if (t) {
          clearInterval(t)
          progressTimers.delete(key)
        }
      }
      updatePlan(sessionId, msgId, (plan) => ({
        ...plan,
        progress: { ...plan.progress, understanding: p },
      }))
    }, 350)
    progressTimers.set(key, timer)
  }

  function finishUnderstandingProgress(sessionId: string, msgId: string) {
    const key = `${sessionId}-${msgId}`
    const t = progressTimers.get(key)
    if (t) {
      clearInterval(t)
      progressTimers.delete(key)
    }
    updatePlan(sessionId, msgId, (plan) => ({
      ...plan,
      progress: { ...plan.progress, understanding: 1 },
    }))
  }

  /** 通过 WebSocket 发送并处理流式响应 */
  const handleSubmitViaWS = React.useCallback(
    (question: string, sessionId: string, assistantMsgId: string,
      context: NonNullable<WorkflowPlan["context"]>, pending?: Clarification) => {

      const adapter = createAdapterState()

      sendChatRequest(
        {
          message: question,
          conversation_id: sessionId,
          clarification_id: pending?.clarification_id,
          dag_id: context.dagToken,
          model: context.model,
          dataset: context.dataset,
          dataset_type: context.dataset_type,
          mode: context.mode ?? "normal",
          expert_mode: context.expert_mode ?? false,
        },
        async (event) => {
          const result = processChatEvent(event, adapter)

          switch (result.kind) {
            case "clarification":
              finishUnderstandingProgress(sessionId, assistantMsgId)
              updatePlan(sessionId, assistantMsgId, (p) => ({ ...p,
                phase: "waiting_clarification", clarification: result.clarification,
                nodes: [], edges: [], subProblems: [], markdown: undefined,
              }))
              break
            case "intent_ready":
              updatePlan(sessionId, assistantMsgId, (p) => ({ ...p,
                phase: "understanding", clarification: undefined, error: undefined,
              }))
              break
            case "thinking": {
              startUnderstandingProgress(sessionId, assistantMsgId)
              updatePlan(sessionId, assistantMsgId, (p) => ({
                ...p,
                phase: "understanding" as const,
                understanding: adapter.thinkingText,
              }))
              break
            }

            case "subproblems": {
              finishUnderstandingProgress(sessionId, assistantMsgId)
              const subProblems: SubProblem[] = result.subqueries.map(
                (q, i) => ({
                  id: `sp-${i + 1}`,
                  title: q.query,
                  rationale: "",
                  algorithmId: "",
                }),
              )
              updatePlan(sessionId, assistantMsgId, (p) => ({
                ...p,
                phase: "decomposing" as const,
                subProblems,
                progress: {
                  ...p.progress,
                  understanding: 1,
                  decomposing: 0,
                  selecting: 0,
                },
              }))
              // 真实子问题列表已到：走完拆解进度（UI 按进度逐条揭示真实条目）
              animatePhase(sessionId, assistantMsgId, "decomposing", updatePlan)
              break
            }

            case "algorithm_selected": {
              const sel = result.selection
              updatePlan(sessionId, assistantMsgId, (p) => {
                // 按子问题原文匹配（与 adapter.subqueries 顺序一致）
                const subProblems = p.subProblems.map((sp, i) => {
                  const q = adapter.subqueries[i]
                  if (!q || q.query !== sel.question) return sp
                  const algo = sel.algorithm
                    ? matchAlgorithm(sel.algorithm, algorithms)
                    : undefined
                  const taskLabel =
                    sel.task_type === "graph_query"
                      ? "Graph Query / 图查询"
                      : sel.task_type === "numeric_analysis"
                        ? "Numeric Analysis / 数值分析"
                        : undefined
                  return {
                    ...sp,
                    algorithmId: algo?.id ?? "",
                    rationale: algo
                      ? `${algo.displayName}（${algo.name}）：${algo.summary}`
                      : (taskLabel ?? sp.rationale),
                  }
                })
                const total = Math.max(1, adapter.subqueries.length)
                const done = Math.min(adapter.stepAlgorithms.size, total)
                return {
                  ...p,
                  phase: "selecting" as const,
                  subProblems,
                  progress: {
                    ...p.progress,
                    selecting: done / total,
                  },
                }
              })
              break
            }

            case "dag": {
              finishUnderstandingProgress(sessionId, assistantMsgId)
              const planData = convertOldDagToPlan(
                result.dag,
                adapter.thinkingText,
                algorithms,
                adapter.stepAlgorithms,
              )
              idMapsRef.current.set(assistantMsgId, planData.idMap)

              // dag-ready：拆解/选算法过程已由上面的真实事件流驱动
              updatePlan(sessionId, assistantMsgId, (p) => ({
                ...p,
                phase: "dag-ready" as const,
                understanding: planData.understanding,
                subProblems: planData.subProblems,
                nodes: planData.nodes,
                edges: planData.edges,
                progress: { understanding: 1, decomposing: 1, selecting: 1 },
              }))
              break
            }

            case "node_update": {
              applyNodeUpdateEvent(
                updatePlan,
                sessionId,
                assistantMsgId,
                idMapsRef.current.get(assistantMsgId),
                result.content,
                getById,
              )
              break
            }

            case "result_text": {
              updatePlan(sessionId, assistantMsgId, (p) => ({
                ...p,
                markdown: (p.markdown ?? "") + result.text + "\n\n",
              }))
              break
            }

            case "stream_end": {
              finishUnderstandingProgress(sessionId, assistantMsgId)
              if (adapter.clarification || adapter.error) break
              if (!adapter.dag || adapter.resultParagraphs.length > 0) {
                updatePlan(sessionId, assistantMsgId, (p) => ({
                  ...p,
                  phase: "executed" as const,
                  nodeDetailsUnavailable: !adapter.nodeEventsSeen,
                }))
              }
              break
            }

            case "error": {
              finishUnderstandingProgress(sessionId, assistantMsgId)
              updatePlan(sessionId, assistantMsgId, (p) => ({
                ...p,
                phase: pending && !result.restartRequired ? "waiting_clarification" as const : "blocked" as const,
                clarification: pending && !result.restartRequired ? pending : undefined,
                error: result.message,
                understanding: p.understanding || `错误：${result.message}`,
              }))
              break
            }
          }
        },
      )
    },
    [algorithms, models, datasets, settings, getById, updatePlan],
  )

  /** 用户点击"确认执行" */
  const handleExecute = React.useCallback(
    (messageId: string) => {
      if (!activeId || isChatBusy()) return

      const session = sessions.find((s) => s.id === activeId)
      const msg = session?.messages.find((m) => m.id === messageId)
      const plan = msg?.plan
      if (!plan) return

      // 交互模式（提交时记录在 plan 上）且后端在线 → 发给后端执行
      if (isChatConnected() && plan.interactive) {
        const model = models.find((m) => m.id === settings.model)
        const dataset = datasets.find((d) => d.id === settings.dataset)
        const adapter = createAdapterState()

        // 立即给用户反馈：切到执行阶段，节点全标为等待
        updatePlan(activeId, messageId, (p) => ({
          ...p,
          phase: "executing" as const,
          nodeDetailsUnavailable: true,
          nodes: p.nodes.map((n) => ({ ...n, status: "pending" as const })),
        }))

        sendChatRequest(
          {
            dag_confirm: "yes",
            conversation_id: activeId,
            dag_id: plan.context?.dagToken ?? sessionIdToDagId(activeId, messageId),
            model: plan.context?.model ?? model?.name ?? settings.model,
            dataset: plan.context?.dataset ?? dataset?.name ?? settings.dataset,
            dataset_type: plan.context?.dataset_type ?? (dataset?.fileType === "graph-data" ? "graph" : "text"),
            mode: "interact",
          },
          async (event) => {
            const result = processChatEvent(event, adapter)

            if (result.kind === "thinking") {
              updatePlan(activeId, messageId, (p) => ({
                ...p,
                understanding:
                  p.understanding +
                  "\n\n" +
                  String(result.text ?? ""),
              }))
              return
            }

            if (result.kind === "result_text") {
              updatePlan(activeId, messageId, (p) => ({
                ...p,
                markdown: (p.markdown ?? "") + result.text + "\n\n",
              }))
              return
            }

            if (result.kind === "node_update") {
              applyNodeUpdateEvent(
                updatePlan,
                activeId,
                messageId,
                idMapsRef.current.get(messageId),
                result.content,
                getById,
              )
              return
            }

            if (result.kind === "stream_end") {
              updatePlan(activeId, messageId, (p) => ({
                ...p,
                phase: "executed" as const,
                nodeDetailsUnavailable: !adapter.nodeEventsSeen,
              }))
            }

            if (result.kind === "error") {
              updatePlan(activeId, messageId, (p) => ({
                ...p,
                phase: "executed" as const,
                error: result.message,
              }))
            }
          },
        )
        return
      }

      // 后端未连接或非交互模式：不执行客户端模拟，直接提示
      updatePlan(activeId, messageId, (p) => ({
        ...p,
        phase: "executed" as const,
        error: "后端服务未连接，无法执行该分析。请确认后端已启动后重试。",
      }))
    },
    [activeId, algorithms, getById, sessions, settings, models, datasets, updatePlan],
  )

  /** 用户手动调整 DAG 节点位置：整张覆盖表写回 plan（随会话持久化） */
  const handleLayoutChange = React.useCallback(
    (
      messageId: string,
      layout: Record<string, { x: number; y: number }>,
    ) => {
      if (!activeId) return
      updatePlan(activeId, messageId, (p) => ({ ...p, layout }))
    },
    [activeId, updatePlan],
  )

  /** 修改 DAG */
  const handleModifyDag = React.useCallback(
    (originalMsgId: string, modificationText: string) => {
      if (!activeId || isChatBusy()) return

      const originalPlan = sessions.find((s) => s.id === activeId)?.messages.find((m) => m.id === originalMsgId)?.plan
      const userMsg: ChatMessage = {
        id: `m-${Date.now()}-u`,
        role: "user",
        content: modificationText,
        createdAt: new Date().toISOString(),
      }
      appendMessage(activeId, userMsg)

      const plan: WorkflowPlan = {
        understanding: "",
        subProblems: [],
        nodes: [],
        edges: [],
        phase: "understanding",
        progress: { understanding: 0, decomposing: 0, selecting: 0 },
        interactive: true,
        context: originalPlan?.context,
      }

      const assistantMsgId = `m-${Date.now()}-a`
      const assistantMsg: ChatMessage = {
        id: assistantMsgId,
        role: "assistant",
        content: "",
        createdAt: new Date().toISOString(),
        plan,
      }
      appendMessage(activeId, assistantMsg)

      if (isChatConnected()) {
        const model = models.find((m) => m.id === settings.model)
        const dataset = datasets.find((d) => d.id === settings.dataset)
        const adapter = createAdapterState()

        sendChatRequest(
          {
            is_dag_modification: true,
            conversation_id: activeId,
            modifications: modificationText,
            dag_id: originalPlan?.context?.dagToken ?? sessionIdToDagId(activeId, originalMsgId),
            message: modificationText,
            model: originalPlan?.context?.model ?? model?.name ?? settings.model,
            dataset: originalPlan?.context?.dataset ?? dataset?.name ?? settings.dataset,
            dataset_type: originalPlan?.context?.dataset_type ?? (dataset?.fileType === "graph-data" ? "graph" : "text"),
            mode: "interact",
          },
          async (event) => {
            const result = processChatEvent(event, adapter)

            switch (result.kind) {
              case "thinking":
                startUnderstandingProgress(activeId, assistantMsgId)
                updatePlan(activeId, assistantMsgId, (p) => ({
                  ...p,
                  phase: "understanding" as const,
                  understanding: adapter.thinkingText,
                }))
                break

              case "subproblems": {
                finishUnderstandingProgress(activeId, assistantMsgId)
                const subProblems: SubProblem[] = result.subqueries.map(
                  (q, i) => ({
                    id: `sp-${i + 1}`,
                    title: q.query,
                    rationale: "",
                    algorithmId: "",
                  }),
                )
                updatePlan(activeId, assistantMsgId, (p) => ({
                  ...p,
                  phase: "decomposing" as const,
                  subProblems,
                  progress: {
                    ...p.progress,
                    understanding: 1,
                    decomposing: 0,
                    selecting: 0,
                  },
                }))
                // 修改后的真实子问题列表已到：走完拆解进度（UI 按进度逐条揭示）
                animatePhase(activeId, assistantMsgId, "decomposing", updatePlan)
                break
              }

              case "algorithm_selected": {
                const sel = result.selection
                updatePlan(activeId, assistantMsgId, (p) => {
                  // 按子问题原文匹配（与 adapter.subqueries 顺序一致）
                  const subProblems = p.subProblems.map((sp, i) => {
                    const q = adapter.subqueries[i]
                    if (!q || q.query !== sel.question) return sp
                    const algo = sel.algorithm
                      ? matchAlgorithm(sel.algorithm, algorithms)
                      : undefined
                    const taskLabel =
                      sel.task_type === "graph_query"
                        ? "Graph Query / 图查询"
                        : sel.task_type === "numeric_analysis"
                          ? "Numeric Analysis / 数值分析"
                          : undefined
                    return {
                      ...sp,
                      algorithmId: algo?.id ?? "",
                      rationale: algo
                        ? `${algo.displayName}（${algo.name}）：${algo.summary}`
                        : (taskLabel ?? sp.rationale),
                    }
                  })
                  const total = Math.max(1, adapter.subqueries.length)
                  const done = Math.min(adapter.stepAlgorithms.size, total)
                  return {
                    ...p,
                    phase: "selecting" as const,
                    subProblems,
                    progress: {
                      ...p.progress,
                      selecting: done / total,
                    },
                  }
                })
                break
              }

              case "dag": {
                finishUnderstandingProgress(activeId, assistantMsgId)
                const planData = convertOldDagToPlan(
                  result.dag,
                  adapter.thinkingText,
                  algorithms,
                  adapter.stepAlgorithms,
                )
                idMapsRef.current.set(assistantMsgId, planData.idMap)

                // dag-ready：拆解/选算法过程已由上面的真实事件流驱动
                updatePlan(activeId, assistantMsgId, (p) => ({
                  ...p,
                  phase: "dag-ready" as const,
                  understanding: planData.understanding,
                  subProblems: planData.subProblems,
                  nodes: planData.nodes,
                  edges: planData.edges,
                  progress: { understanding: 1, decomposing: 1, selecting: 1 },
                }))
                break
              }

              case "result_text":
                updatePlan(activeId, assistantMsgId, (p) => ({
                  ...p,
                  markdown: (p.markdown ?? "") + result.text + "\n\n",
                }))
                break

              case "stream_end":
                finishUnderstandingProgress(activeId, assistantMsgId)
                break

              case "error":
                finishUnderstandingProgress(activeId, assistantMsgId)
                updatePlan(activeId, assistantMsgId, (p) => ({
                  ...p,
                  phase: "executed" as const,
                error: result.message,
                  understanding: p.understanding || `错误：${result.message}`,
                }))
                break
            }
          },
        )
      } else {
        // 后端未连接：无法修订 DAG，直接提示
        updatePlan(activeId, assistantMsgId, (p) => ({
          ...p,
          phase: "executed" as const,
          error: "后端服务未连接，无法修改 DAG。请确认后端已启动后重试。",
        }))
      }
    },
    [
      activeId,
      algorithms,
      appendMessage,
      models,
      datasets,
      settings,
      sessions,
      updatePlan,
    ],
  )

  /** 提交问题 */
  const handleSubmit = React.useCallback(
    async (question: string) => {
      if (isChatBusy() || !isChatConnected()) return
      let sessionId = activeId
      if (!sessionId) sessionId = createSession(truncate(question, 28))
      const current = sessions.find((s) => s.id === sessionId)
      const pendingMessage = current?.messages.slice().reverse().find(
        (m) => m.plan?.phase === "waiting_clarification" && m.plan.clarification,
      )
      const pendingPlan = pendingMessage?.plan
      if (pendingMessage) updatePlan(sessionId, pendingMessage.id, (p) => ({ ...p, phase: "clarified" }))
      if (
        current &&
        current.messages.length === 0 &&
        !current.title
      ) {
        renameSession(sessionId, truncate(question, 28))
      }

      const userMsg: ChatMessage = {
        id: `m-${Date.now()}-u`,
        role: "user",
        content: question,
        createdAt: new Date().toISOString(),
      }
      appendMessage(sessionId, userMsg)

      // 初始的空 plan（phase: understanding, progress 全 0）
      // interactive 记录提交时刻的模式：切页重挂载后 settings 会重置，
      // 按钮显示与执行决策以这里为准
      const plan: WorkflowPlan = {
        understanding: "",
        subProblems: [],
        nodes: [],
        edges: [],
        phase: "checking_intent",
        progress: { understanding: 0, decomposing: 0, selecting: 0 },
        interactive: pendingPlan?.interactive ?? (settings.interactiveMode || settings.expertMode),
      }

      const assistantMsgId = `m-${Date.now()}-a`
      const assistantMsg: ChatMessage = {
        id: assistantMsgId,
        role: "assistant",
        content: "",
        createdAt: new Date().toISOString(),
        plan,
      }
      plan.context = pendingPlan?.context ? { ...pendingPlan.context, dagToken: sessionIdToDagId(sessionId, assistantMsgId) } : {
        model: models.find((m) => m.id === settings.model)?.name ?? settings.model,
        dataset: datasets.find((d) => d.id === settings.dataset)?.name ?? settings.dataset,
        dataset_type: datasets.find((d) => d.id === settings.dataset)?.fileType === "graph-data" ? "graph" : "text",
        dagToken: sessionIdToDagId(sessionId, assistantMsgId),
        mode: settings.interactiveMode ? "interact" : "normal",
        expert_mode: settings.expertMode,
      }
      appendMessage(sessionId, assistantMsg)

      // 判断后端是否可用
      if (isChatConnected()) {
        handleSubmitViaWS(question, sessionId, assistantMsgId, plan.context, pendingPlan?.clarification)
      } else {
        // 后端未连接：不进行客户端模拟，直接提示
        updatePlan(sessionId, assistantMsgId, (p) => ({
          ...p,
          phase: "executed" as const,
          error: "后端服务未连接，无法开始分析。请确认后端已启动后重试。",
        }))
      }
    },
    [
      activeId,
      algorithms,
      appendMessage,
      createSession,
      handleSubmitViaWS,
      settings,
      models,
      datasets,
      renameSession,
      sessions,
      updatePlan,
    ],
  )

  const awaitingContext = activeSession?.messages.slice().reverse().find(
    (m) => m.plan?.phase === "waiting_clarification" && m.plan.clarification,
  )?.plan?.context
  const displaySettings: ChatSettings = awaitingContext ? {
    model: models.find((m) => m.name === awaitingContext.model)?.id ?? "",
    dataset: datasets.find((d) => d.name === awaitingContext.dataset)?.id ?? "",
    expertMode: awaitingContext.expert_mode ?? false,
    interactiveMode: awaitingContext.mode === "interact",
  } : settings

  return (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      <ChatHistory
        sessions={sessions}
        activeId={activeId}
        onSelect={selectSession}
        onCreate={() => createSession()}
        onDelete={deleteSession}
      />
      <ChatMain
        chatState={chatState}
        session={activeSession}
        onSubmit={handleSubmit}
        onExecute={handleExecute}
        onModify={handleModifyDag}
        onLayoutChange={handleLayoutChange}
        settings={displaySettings}
        lockSettings={!!awaitingContext}
        onSettingsChange={setSettings}
        datasets={datasets}
        models={models}
      />
    </div>
  )
}

/** 把一条真实节点执行事件应用到对应节点（经 dag 事件的 idMap 定位） */
function applyNodeUpdateEvent(
  updatePlan: ReturnType<typeof useChat>["updatePlan"],
  sessionId: string,
  messageId: string,
  idMap: Map<string, string> | undefined,
  content: NodeExecutionContent,
  getById: (id: string) => Algorithm | undefined,
) {
  updatePlan(sessionId, messageId, (p) => {
    const nodeId = resolveNodeId(idMap, content, p.nodes)
    if (!nodeId) return p
    return {
      ...p,
      phase:
        p.phase === "dag-ready" || p.phase === "executing"
          ? "executing"
          : p.phase,
      nodes: p.nodes.map((n) => {
        if (n.id !== nodeId) return n
        if (content.status === "running") {
          return {
            ...n,
            status: "running" as const,
            error: undefined,
            startedAtMs: n.startedAtMs ?? Date.now(),
          }
        }
        if (content.status === "failed") {
          return {
            ...n,
            status: "error" as const,
            error: content.error,
            finishedAtMs: Date.now(),
          }
        }
        // success：携带后端下发的结构化输出
        const algo = getById(n.algorithmId)
        return {
          ...n,
          status: "done" as const,
          error: undefined,
          finishedAtMs: Date.now(),
          result: {
            summary: algo
              ? `完成 ${algo.displayName}（${algo.name}）计算`
              : content.question
                ? `完成子任务「${content.question}」的执行`
                : "子任务执行完成",
            outputs: (content.outputs ?? []).map((o) => ({
              id: o.output_id,
              source: o.source,
              kind: o.task_type,
              description: o.description,
              fields: o.fields,
              value: o.value,
              truncated: o.truncated,
              total: o.total,
              path: o.path,
            })),
          },
        }
      }),
    }
  })
}

/**
 * 事件 step_id → 前端节点 id。
 * 优先 idMap；查不到（如被跳过的根节点）用 question 文本匹配 label；
 * 仍找不到返回 null（忽略该事件，避免误标到别的节点）。
 */
function resolveNodeId(
  idMap: Map<string, string> | undefined,
  content: NodeExecutionContent,
  nodes: WorkflowPlan["nodes"],
): string | null {
  const mapped = idMap?.get(String(content.step_id))
  if (mapped) return mapped
  if (content.question) {
    const byLabel = nodes.find((n) => n.label === content.question)
    if (byLabel) return byLabel.id
  }
  return idMap ? null : `n-${content.step_id}`
}

async function animatePhase(
  sessionId: string,
  messageId: string,
  phase: "understanding" | "decomposing" | "selecting",
  updatePlan: ReturnType<typeof useChat>["updatePlan"],
) {
  updatePlan(sessionId, messageId, (p) => ({ ...p, phase }))
  // 前 16 步到 0.9，最后第 17 步跳到 1.0
  const mainSteps = 16
  for (let i = 1; i <= mainSteps; i++) {
    await sleep(65)
    updatePlan(sessionId, messageId, (p) => ({
      ...p,
      progress: { ...p.progress, [phase]: (i / mainSteps) * 0.9 },
    }))
  }
  // 在 0.9 停顿一小段
  await sleep(400)
  updatePlan(sessionId, messageId, (p) => ({
    ...p,
    progress: { ...p.progress, [phase]: 1 },
  }))
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

function truncate(s: string, n: number) {
  const t = s.trim()
  return t.length > n ? `${t.slice(0, n)}…` : t
}

function sessionIdToDagId(sessionId: string, messageId: string): string {
  return `dag-${sessionId}-${messageId}`
}
