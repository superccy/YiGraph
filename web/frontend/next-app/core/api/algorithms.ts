// ============================================================
// 算法库 API 层
// ============================================================

import { getBaseUrl } from "./base"
import type { Algorithm, AlgorithmCategory, Lang } from "@/core/types"

export interface CategoryInfo {
  id: AlgorithmCategory
  label: string
  count: number
}

export async function fetchAlgorithms(params: {
  search?: string
  category?: string
  lang?: Lang
}): Promise<{ data: Algorithm[]; total: number }> {
  const { search = "", category = "", lang = "zh-CN" } = params

  const url = new URL(`${await getBaseUrl()}/api/algorithms`, window.location.origin)
  if (search) url.searchParams.set("search", search)
  if (category) url.searchParams.set("category", category)
  url.searchParams.set("lang", lang)

  const res = await fetch(url.toString())
  const json = await res.json()

  if (!json.success) {
    throw new Error(json.error ?? "Failed to fetch algorithms")
  }

  return { data: json.data as Algorithm[], total: json.total as number }
}

export async function fetchCategories(params?: { lang?: Lang }): Promise<CategoryInfo[]> {
  const lang = params?.lang ?? "zh-CN"

  const url = new URL(`${await getBaseUrl()}/api/algorithms/categories`, window.location.origin)
  url.searchParams.set("lang", lang)

  const res = await fetch(url.toString())
  const json = await res.json()

  if (!json.success) {
    throw new Error(json.error ?? "Failed to fetch categories")
  }

  return json.data as CategoryInfo[]
}

export async function createAlgorithm(input: {
  name: string
  lang?: Lang
  overwrite?: boolean
}): Promise<Algorithm> {
  const base = await getBaseUrl()
  const res = await fetch(`${base}/api/algorithms`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: input.name,
      lang: input.lang ?? "zh-CN",
      overwrite: input.overwrite ?? false,
    }),
  })

  const json = await res.json()

  if (!json.success) {
    throw new Error(json.error ?? "Failed to create algorithm")
  }

  return json.data as Algorithm
}

export async function getAlgorithmById(
  id: string,
  lang?: Lang,
): Promise<Algorithm | undefined> {
  const base = await getBaseUrl()
  const url = new URL(`${base}/api/algorithms/${encodeURIComponent(id)}`, window.location.origin)
  url.searchParams.set("lang", lang ?? "zh-CN")

  const res = await fetch(url.toString())

  if (res.status === 404) return undefined

  const json = await res.json()

  if (!json.success) return undefined

  return json.data as Algorithm
}
