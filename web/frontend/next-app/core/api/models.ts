import type { Model, PaginatedResponse } from "@/core/types"

import { getBaseUrl } from "./base"

interface BackendModel {
  id: number
  name: string
  base_url: string
  created_at?: string
}

function toModel(b: BackendModel): Model {
  return {
    id: String(b.id),
    name: b.name,
    baseUrl: b.base_url,
    createdAt: b.created_at ?? new Date().toISOString(),
  }
}

export async function getModels(
  search = "",
  page = 1,
  pageSize = 10,
): Promise<PaginatedResponse<Model>> {
  const res = await fetch(`${await getBaseUrl()}/api/models`)
  const json = await res.json()
  if (!json.success) throw new Error("获取模型列表失败")

  const all: Model[] = (json.data as BackendModel[]).map(toModel)

  const q = search.trim().toLowerCase()
  const filtered = q
    ? all.filter((m) => m.name.toLowerCase().includes(q))
    : all
  const total = filtered.length
  const start = (page - 1) * pageSize
  const data = filtered.slice(start, start + pageSize)
  return { data, total, page, pageSize }
}

export async function createModel(input: {
  name: string
  baseUrl: string
  apiKey: string
}): Promise<Model> {
  const res = await fetch(`${await getBaseUrl()}/api/models`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: input.name,
      base_url: input.baseUrl,
      api_key: input.apiKey,
    }),
  })
  const json = await res.json()
  if (!json.success) throw new Error(json.message ?? json.error ?? "创建模型失败")

  const b = json.data as BackendModel
  return toModel(b)
}

export async function deleteModel(id: string): Promise<void> {
  const res = await fetch(`${await getBaseUrl()}/api/models/${id}`, { method: "DELETE" })
  const json = await res.json()
  if (!json.success) throw new Error(json.error ?? "删除模型失败")
}
