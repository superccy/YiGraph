import type { Dataset, PaginatedResponse } from "@/core/types"
import { getBaseUrl } from "./base"

interface BackendDataset {
  id: number
  name: string
  file_type: "text" | "graph"
  file_count: number
  created_at: string
}

function toDataset(b: BackendDataset): Dataset {
  return {
    id: String(b.id),
    name: b.name,
    fileType: b.file_type === "graph" ? "graph-data" : "raw-data",
    fileCount: b.file_count,
    createdAt: b.created_at,
  }
}

export async function getDatasets(
  search = "",
  page = 1,
  pageSize = 8,
): Promise<PaginatedResponse<Dataset>> {
  const res = await fetch(`${await getBaseUrl()}/api/knowledge_bases`)
  const json = await res.json()
  if (!json.success) throw new Error("获取数据集列表失败")

  const all: Dataset[] = (json.data as BackendDataset[]).map(toDataset)

  const q = search.trim().toLowerCase()
  const filtered = q ? all.filter((d) => d.name.toLowerCase().includes(q)) : all
  const total = filtered.length
  const start = (page - 1) * pageSize
  const data = filtered.slice(start, start + pageSize)
  return { data, total, page, pageSize }
}

export async function createDataset(input: {
  name: string
  fileType: Dataset["fileType"]
}): Promise<Dataset> {
  const res = await fetch(`${await getBaseUrl()}/api/knowledge_bases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: input.name,
      file_type: input.fileType === "graph-data" ? "graph" : "text",
    }),
  })
  const json = await res.json()
  if (!json.success) throw new Error(json.error ?? "创建数据集失败")

  // The existing create endpoint returns db_name, not the list record's ID.
  const { data } = await getDatasets(input.name, 1, Number.MAX_SAFE_INTEGER)
  const created = data.find((d) => d.name === input.name && d.fileType === input.fileType)
  if (!created) throw new Error("创建成功，但未取得数据集记录，请刷新列表。 / Refresh the dataset list.")
  return created
}

export async function deleteDataset(id: string): Promise<void> {
  const res = await fetch(`${await getBaseUrl()}/api/knowledge_bases/${id}`, {
    method: "DELETE",
  })
  const json = await res.json()
  if (!json.success) throw new Error(json.error ?? "删除数据集失败")
}
