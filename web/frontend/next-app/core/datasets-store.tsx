"use client"

import * as React from "react"
import type { Dataset } from "./types"
import * as datasetsApi from "./api/datasets"

interface DatasetsContextValue {
  datasets: Dataset[]
  total: number
  page: number
  pageSize: number
  totalPages: number
  loading: boolean
  search: string
  setSearch: (s: string) => void
  setPage: (p: number) => void
  createDataset: (input: { name: string; fileType: Dataset["fileType"] }) => Promise<void>
  deleteDataset: (id: string) => Promise<void>
  refresh: () => Promise<void>
}

const DatasetsContext = React.createContext<DatasetsContextValue | null>(null)

export function DatasetsProvider({ children }: { children: React.ReactNode }) {
  const [datasets, setDatasets] = React.useState<Dataset[]>([])
  const [total, setTotal] = React.useState(0)
  const [page, setPage] = React.useState(1)
  const [pageSize] = React.useState(8)
  const [loading, setLoading] = React.useState(false)
  const [search, setSearch] = React.useState("")
  const [tick, setTick] = React.useState(0)

  const refresh = React.useCallback(async () => {
    setLoading(true)
    const result = await datasetsApi.getDatasets(search, page, pageSize)
    setDatasets(result.data)
    setTotal(result.total)
    setLoading(false)
  }, [search, page, pageSize])

  React.useEffect(() => {
    refresh()
  }, [refresh, tick])

  const createDataset = React.useCallback(
    async (input: { name: string; fileType: Dataset["fileType"] }) => {
      await datasetsApi.createDataset(input)
      setPage(1)
      setTick((n) => n + 1)
    },
    [],
  )

  const deleteDataset = React.useCallback(async (id: string) => {
    await datasetsApi.deleteDataset(id)
    setPage(1)
    setTick((n) => n + 1)
  }, [])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const value = React.useMemo(
    () => ({
      datasets,
      total,
      page,
      pageSize,
      totalPages,
      loading,
      search,
      setSearch,
      setPage,
      createDataset,
      deleteDataset,
      refresh,
    }),
    [
      datasets,
      total,
      page,
      pageSize,
      totalPages,
      loading,
      search,
      createDataset,
      deleteDataset,
      refresh,
    ],
  )

  return (
    <DatasetsContext.Provider value={value}>{children}</DatasetsContext.Provider>
  )
}

export function useDatasets() {
  const ctx = React.useContext(DatasetsContext)
  if (!ctx) throw new Error("useDatasets must be used within DatasetsProvider")
  return ctx
}
