import { getBaseUrl } from "./base"
import type { FeedbackEntry } from "../types"

export async function submitFeedback(entry: Omit<FeedbackEntry, "timestamp">) {
  const baseUrl = await getBaseUrl()
  const res = await fetch(`${baseUrl}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  })
  if (!res.ok) {
    throw new Error(`Feedback submission failed: ${res.status}`)
  }
  return res.json()
}
