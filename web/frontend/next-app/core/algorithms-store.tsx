"use client"

import * as React from "react"
import type { Algorithm } from "./types"
import type { CategoryInfo } from "./api/algorithms"
import { useI18n } from "@/core/i18n/i18n-provider"
import { fetchAlgorithms, fetchCategories } from "./api/algorithms"

interface AlgorithmsContextValue {
  algorithms: Algorithm[]
  categories: CategoryInfo[]
  total: number
  loading: boolean
  search: string
  category: string
  setSearch: (s: string) => void
  setCategory: (c: string) => void
  addAlgorithm: (a: Algorithm) => Promise<void>
  getById: (id: string) => Algorithm | undefined
  refresh: () => Promise<void>
}

const AlgorithmsContext = React.createContext<AlgorithmsContextValue | null>(null)

export function AlgorithmsProvider({ children }: { children: React.ReactNode }) {
  const { lang } = useI18n()
  const [algorithms, setAlgorithms] = React.useState<Algorithm[]>([])
  const [categories, setCategories] = React.useState<CategoryInfo[]>([])
  const [total, setTotal] = React.useState(0)
  const [loading, setLoading] = React.useState(false)
  const [search, setSearch] = React.useState("")
  const [category, setCategory] = React.useState("")
  const [tick, setTick] = React.useState(0)
  const allCache = React.useRef<Algorithm[]>([])

  const refresh = React.useCallback(async () => {
    setLoading(true)
    const [algResult, cats] = await Promise.all([
      fetchAlgorithms({ search, category, lang }),
      fetchCategories({ lang }),
    ])
    setAlgorithms(algResult.data)
    setTotal(algResult.total)
    setCategories(cats)
    allCache.current = algResult.data
    setLoading(false)
  }, [search, category, lang])

  React.useEffect(() => {
    refresh()
  }, [refresh, tick])

  const addAlgorithm = React.useCallback(async (_a: Algorithm) => {
    // Algorithm is already created on the server by AddAlgorithmDialog
    setTick((n) => n + 1)
  }, [])

  const getById = React.useCallback(
    (id: string) => allCache.current.find((a) => a.id === id),
    [],
  )

  const value = React.useMemo(
    () => ({
      algorithms,
      categories,
      total,
      loading,
      search,
      category,
      setSearch,
      setCategory,
      addAlgorithm,
      getById,
      refresh,
    }),
    [
      algorithms,
      categories,
      total,
      loading,
      search,
      category,
      addAlgorithm,
      getById,
      refresh,
    ],
  )

  return (
    <AlgorithmsContext.Provider value={value}>{children}</AlgorithmsContext.Provider>
  )
}

export function useAlgorithms() {
  const ctx = React.useContext(AlgorithmsContext)
  if (!ctx) throw new Error("useAlgorithms must be used within AlgorithmsProvider")
  return ctx
}
