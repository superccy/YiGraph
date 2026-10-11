
"use client"

import * as React from "react"
import type { Model } from "./types"
import * as modelsApi from "./api/models"

interface ModelsContextValue {
  models: Model[]
  total: number
  page: number
  pageSize: number
  totalPages: number
  loading: boolean
  search: string
  setSearch: (s: string) => void
  setPage: (p: number) => void
  createModel: (input: {
    name: string
    baseUrl: string
    apiKey: string
  }) => Promise<void>
  deleteModel: (id: string) => Promise<void>
  refresh: () => Promise<void>
}

const ModelsContext = React.createContext<ModelsContextValue | null>(null)

export function ModelsProvider({ children }: { children: React.ReactNode }) {
  const [models, setModels] = React.useState<Model[]>([])
  const [total, setTotal] = React.useState(0)
  const [page, setPage] = React.useState(1)
  const [pageSize] = React.useState(10)
  const [loading, setLoading] = React.useState(false)
  const [search, setSearch] = React.useState("")
  const [tick, setTick] = React.useState(0)

  const refresh = React.useCallback(async () => {
    setLoading(true)
    const result = await modelsApi.getModels(search, page, pageSize)
    setModels(result.data)
    setTotal(result.total)
    setLoading(false)
  }, [search, page, pageSize])

  React.useEffect(() => {
    refresh()
  }, [refresh, tick])

  const createModel = React.useCallback(
    async (input: { name: string; baseUrl: string; apiKey: string }) => {
      await modelsApi.createModel(input)
      setPage(1)
      setTick((n) => n + 1)
    },
    [],
  )

  const deleteModel = React.useCallback(async (id: string) => {
    await modelsApi.deleteModel(id)
    setPage(1)
    setTick((n) => n + 1)
  }, [])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const value = React.useMemo(
    () => ({
      models,
      total,
      page,
      pageSize,
      totalPages,
      loading,
      search,
      setSearch,
      setPage,
      createModel,
      deleteModel,
      refresh,
    }),
    [
      models,
      total,
      page,
      pageSize,
      totalPages,
      loading,
      search,
      createModel,
      deleteModel,
      refresh,
    ],
  )

  return (
    <ModelsContext.Provider value={value}>{children}</ModelsContext.Provider>
  )
}

export function useModels() {
  const ctx = React.useContext(ModelsContext)
  if (!ctx) throw new Error("useModels must be used within ModelsProvider")
  return ctx
}
