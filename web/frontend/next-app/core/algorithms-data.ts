import type { CategoryInfo } from "./api/algorithms"

export function getCategoryLabel(categories: CategoryInfo[], cat: string): string {
  return categories.find((c) => c.id === cat)?.label ?? cat
}
