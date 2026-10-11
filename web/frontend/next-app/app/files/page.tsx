import { Suspense } from "react"
import { FilesManager } from "@/components/files/files-manager"

export const metadata = {
  title: "文件管理 · 易图",
  description: "管理数据集中的文件，上传、解析、预览与可视化",
}

export default function FilesPage() {
  return (
    <Suspense>
      <FilesManager />
    </Suspense>
  )
}
