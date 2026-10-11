import { ModelsManager } from "@/components/models/models-manager"

export const metadata = {
  title: "模型管理 · 易图",
  description: "配置和管理 AI 模型接入信息",
}

export default function ModelsPage() {
  return <ModelsManager />
}
