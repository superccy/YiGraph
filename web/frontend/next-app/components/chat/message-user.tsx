"use client"

import { User } from "lucide-react"
import type { ChatMessage } from "@/core/types"

export function MessageUser({ message }: { message: ChatMessage }) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <User className="size-4" />
      </div>
      <div className="flex-1">
        <div className="mb-1 text-xs font-medium text-muted-foreground">
          你
        </div>
        <div className="rounded-lg border border-border bg-card px-4 py-3 text-[15px] leading-relaxed text-foreground">
          {message.content}
        </div>
      </div>
    </div>
  )
}
