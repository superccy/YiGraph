"use client"

import * as React from "react"
import type { Dataset, FileItem, GraphData, PreviewData, UploadConfig } from "./types"
import * as datasetsApi from "./api/datasets"
import * as filesApi from "./api/files"

interface FilesContextValue {
  datasetList: Dataset[]
  activeDatasetId: string | null
  activeDataset: Dataset | null
  files: FileItem[]
  graphData: GraphData | null
  triplets: [string, string, string][]
  graphLoading: boolean
  loading: boolean
  selectDataset: (id: string) => void
  generateGraph: () => Promise<void>
  uploadFiles: (
    datasetId: string,
    files: File[],
    fileType: string,
    config?: UploadConfig,
  ) => Promise<void>
  deleteFile: (fileName: string) => Promise<void>
  parseFile: (fileName: string) => Promise<void>
  previewFile: (fileName: string) => Promise<PreviewData>
  refreshFiles: () => Promise<void>
}

const FilesContext = React.createContext<FilesContextValue | null>(null)

export function FilesProvider({ children }: { children: React.ReactNode }) {
  const [datasetList, setDatasetList] = React.useState<Dataset[]>([])
  const [activeDatasetId, setActiveDatasetId] = React.useState<string | null>(null)
  const [files, setFiles] = React.useState<FileItem[]>([])
  const [graphData, setGraphData] = React.useState<GraphData | null>(null)
  const [triplets, setTriplets] = React.useState<[string, string, string][]>([])
  const [graphLoading, setGraphLoading] = React.useState(false)
  const [loading, setLoading] = React.useState(false)
  const pollingRef = React.useRef<ReturnType<typeof setInterval> | null>(null)

  const activeDataset = React.useMemo(
    () => datasetList.find((d) => d.id === activeDatasetId) ?? null,
    [datasetList, activeDatasetId],
  )

  const loadDatasets = React.useCallback(async () => {
    const result = await datasetsApi.getDatasets("", 1, 100)
    setDatasetList(result.data)
  }, [])

  React.useEffect(() => {
    void loadDatasets().catch(console.error)
  }, [loadDatasets])

  const refreshFiles = React.useCallback(async () => {
    if (!activeDatasetId) return
    setLoading(true)
    try {
      const fileList = await filesApi.getFiles(activeDatasetId)
      setFiles(fileList)
    } finally { setLoading(false) }
  }, [activeDatasetId])

  const generateGraph = React.useCallback(async () => {
    if (!activeDatasetId || !activeDataset) return
    setGraphLoading(true)
    setGraphData(null)
    setTriplets([])
    const fileNames = files.map((f) => f.name)
    const result = await filesApi.getGraphData(activeDatasetId, activeDataset.name, fileNames)
    if (result) {
      setGraphData(result.graph)
      setTriplets(result.triplets)
    }
    setGraphLoading(false)
  }, [activeDatasetId, activeDataset, files])

  React.useEffect(() => {
    if (activeDatasetId) void refreshFiles().catch(console.error)
  }, [activeDatasetId, refreshFiles])

  const startPolling = React.useCallback(() => {
    if (pollingRef.current || !activeDatasetId) return
    pollingRef.current = setInterval(async () => {
      const statusMap = await filesApi.getParseStatus(activeDatasetId!)
      setFiles((prev) =>
        prev.map((f) => {
          const s = statusMap[f.name]
          if (!s) return f
          return { ...f, parseStatus: s.status, progress: s.progress }
        }),
      )
    }, 5000)
  }, [activeDatasetId])

  const stopPolling = React.useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }, [])

  React.useEffect(() => {
    const hasParsing = files.some((f) => f.parseStatus === "parsing")
    if (hasParsing) startPolling()
    else stopPolling()
    return stopPolling
  }, [files, startPolling, stopPolling])

  const selectDataset = React.useCallback((id: string) => {
    setActiveDatasetId(id)
    setGraphData(null)
    setTriplets([])
    setFiles([])
  }, [])

  const uploadFiles = React.useCallback(
    async (
      datasetId: string,
      files: File[],
      fileType: string,
      config?: UploadConfig,
    ) => {
      await filesApi.uploadFiles(datasetId, files, fileType, config)
      if (datasetId === activeDatasetId) await refreshFiles()
      await loadDatasets()
    },
    [activeDatasetId, refreshFiles, loadDatasets],
  )

  const deleteFile = React.useCallback(
    async (fileName: string) => {
      if (!activeDatasetId) return
      await filesApi.deleteFile(activeDatasetId, fileName)
      await refreshFiles()
    },
    [activeDatasetId, refreshFiles],
  )

  const parseFile = React.useCallback(
    async (fileName: string) => {
      if (!activeDatasetId) return
      await filesApi.parseFile(activeDatasetId, fileName)
      await refreshFiles()
    },
    [activeDatasetId, refreshFiles],
  )

  const previewFile = React.useCallback(
    async (fileName: string) => {
      if (!activeDatasetId) throw new Error("未选择数据集")
      return filesApi.previewFile(activeDatasetId, fileName)
    },
    [activeDatasetId],
  )

  const value = React.useMemo<FilesContextValue>(
    () => ({
      datasetList,
      activeDatasetId,
      activeDataset,
      files,
      graphData,
      triplets,
      graphLoading,
      loading,
      selectDataset,
      generateGraph,
      uploadFiles,
      deleteFile,
      parseFile,
      previewFile,
      refreshFiles,
    }),
    [
      datasetList,
      activeDatasetId,
      activeDataset,
      files,
      graphData,
      triplets,
      graphLoading,
      loading,
      selectDataset,
      generateGraph,
      uploadFiles,
      deleteFile,
      parseFile,
      previewFile,
      refreshFiles,
    ],
  )

  return (
    <FilesContext.Provider value={value}>{children}</FilesContext.Provider>
  )
}

export function useFiles() {
  const ctx = React.useContext(FilesContext)
  if (!ctx) throw new Error("useFiles must be used within FilesProvider")
  return ctx
}
