// Production uses the Flask origin; a separate dev server needs an explicit URL.
const baseUrl = (process.env.NEXT_PUBLIC_BACKEND_URL ?? "").replace(/\/+$/, "")
let backendLive = false

export async function getBaseUrl(): Promise<string> { return baseUrl }
export function getBaseUrlSync(): string { return baseUrl }
export function isBackendLive(): boolean { return backendLive }

export async function probeBackend(timeoutMs = 3000): Promise<string | null> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${baseUrl}/api/health`, { cache: "no-store", signal: controller.signal })
    const data = response.ok ? await response.json() : null
    backendLive = data?.status === "healthy"
    return backendLive ? baseUrl : null
  } catch {
    backendLive = false
    return null
  } finally { clearTimeout(timer) }
}
