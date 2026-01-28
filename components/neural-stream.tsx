"use client"

import { useEffect, useRef } from "react"
import type { BotAction } from "@/hooks/use-bot-stream"

interface NeuralStreamProps {
  actions?: BotAction[]
  isLive?: boolean
}

const fallbackMessages = [
  {
    timestamp: "—",
    message: "Waiting for bot connection...",
    type: "system" as const
  }
]

export function NeuralStream({ actions = [], isLive = false }: NeuralStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [actions])

  const getTypeColor = (type?: string) => {
    switch (type) {
      case "roast":
      case "auto_roast":
        return "text-[#ff5f56]"
      case "analyze":
      case "auto_analyze":
        return "text-[#28c840]"
      case "say":
        return "text-[#0a84ff]"
      case "burn":
        return "text-[#ff9f0a]"
      case "claim":
        return "text-[#f5a623]"
      case "auto_start":
      case "auto_stop":
        return "text-[#ff9f0a]"
      case "mention_reply":
      case "manual_reply":
        return "text-[#bf5af2]"
      default:
        return "text-foreground"
    }
  }

  const formatTimestamp = (ts: string) => {
    try {
      const date = new Date(ts)
      return date.toLocaleTimeString("en-US", { hour12: false })
    } catch {
      return ts
    }
  }

  const displayActions = actions.length > 0 ? actions : fallbackMessages.map((m, i) => ({
    timestamp: m.timestamp,
    type: m.type,
    description: m.message,
    details: {}
  }))

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-3">
          <span className="text-muted-foreground/50">~</span>
          <span className="text-foreground/90">neural_stream --tail -f</span>
          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-foreground/5 border border-border/30 text-foreground/70 text-[10px] tracking-wide ${isLive ? '' : 'opacity-50'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-[#28c840] animate-pulse' : 'bg-muted-foreground/40'}`} />
            {isLive ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
      </div>

      <div
        ref={scrollRef}
        className="h-64 overflow-y-auto space-y-2 pr-2"
      >
        {[...displayActions].reverse().slice(0, 15).map((action, index) => {
          const details = action.details as { roast_text?: string; analysis_text?: string; reply_text?: string; amount?: number }
          const hasTextContent = details?.roast_text || details?.analysis_text || details?.reply_text
          const textContent = details?.roast_text?.slice(0, 100) || details?.analysis_text?.slice(0, 100) || details?.reply_text?.slice(0, 100)
          const isOverflow = (details?.roast_text?.length ?? 0) > 100 || (details?.analysis_text?.length ?? 0) > 100 || (details?.reply_text?.length ?? 0) > 100

          return (
            <div key={`${action.timestamp}-${index}`} className="group py-2 border-b border-border/10 last:border-0">
              <div className="flex items-start gap-3 text-xs">
                <span className="text-muted-foreground/40 shrink-0 tabular-nums">
                  {formatTimestamp(action.timestamp)}
                </span>
                <span className={`${getTypeColor(action.type)} leading-relaxed`}>
                  {action.description}
                </span>
              </div>
              {action.details && Object.keys(action.details).length > 0 && hasTextContent && (
                <div className="mt-1 ml-16 text-xs text-muted-foreground/60 italic">
                  {textContent}{isOverflow ? '...' : ''}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
