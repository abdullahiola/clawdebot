"use client"

import { useState } from "react"
import type { Trade } from "@/hooks/use-bot-stream"

interface ActivityLogProps {
  trades?: Trade[]
  isLive?: boolean
}

export function ActivityLog({ trades = [], isLive = false }: ActivityLogProps) {
  const [activeTab, setActiveTab] = useState<'activity' | 'pinned'>('activity')

  const formatTimestamp = (ts: number) => {
    try {
      const date = new Date(ts * 1000)
      return date.toLocaleTimeString("en-US", { hour12: false })
    } catch {
      return "—"
    }
  }

  const formatWallet = (wallet: string) => {
    if (!wallet || wallet === 'Unknown') return 'anon'
    return `${wallet.slice(0, 4)}...${wallet.slice(-4)}`
  }

  const formatTradeMessage = (trade: Trade) => {
    const wallet = formatWallet(trade.user)
    const action = trade.type === 'buy' ? 'bought' : 'sold'
    const amount = trade.sol_amount.toFixed(2)
    return `${wallet} ${action} ${amount} SOL`
  }

  // Reverse so most recent is first
  const recentTrades = [...trades].reverse().slice(0, 20)

  return (
    <div className="space-y-3">
      {/* Tab Header */}
      <div className="flex items-center gap-4 text-xs border-b border-border/20 pb-2">
        <button
          onClick={() => setActiveTab('activity')}
          className={`flex items-center gap-2 transition-colors ${activeTab === 'activity'
            ? 'text-foreground'
            : 'text-muted-foreground/50 hover:text-muted-foreground'
            }`}
        >
          <span className="text-muted-foreground/50">~</span>
          <span>activity_log</span>
          {isLive && activeTab === 'activity' && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[#28c840]/10 text-[#28c840] text-[10px]">
              <span className="w-1 h-1 rounded-full bg-[#28c840] animate-pulse" />
              LIVE
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('pinned')}
          className={`flex items-center gap-2 transition-colors ${activeTab === 'pinned'
            ? 'text-foreground'
            : 'text-muted-foreground/50 hover:text-muted-foreground'
            }`}
        >
          <span className="text-muted-foreground/50">~</span>
          <span>pinned</span>
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'activity' ? (
        <div className="h-64 overflow-y-auto space-y-0 font-mono text-xs">
          {recentTrades.length === 0 ? (
            <div className="text-muted-foreground/50 py-4 text-center">
              No trades recorded yet. Waiting for activity...
            </div>
          ) : (
            recentTrades.map((trade, index) => {
              const isBuy = trade.type === 'buy'
              return (
                <div
                  key={`${trade.signature || trade.timestamp}-${index}`}
                  className="py-3 border-b border-border/10 last:border-0 hover:bg-foreground/[0.02] transition-colors"
                >
                  {/* Trade Message */}
                  <div className="flex items-center gap-3">
                    <span className="text-muted-foreground/40 w-16 tabular-nums">
                      {formatTimestamp(trade.timestamp)}
                    </span>
                    <span className={`${isBuy ? 'text-[#28c840]' : 'text-[#ff5f56]'}`}>
                      {formatTradeMessage(trade)}
                    </span>
                  </div>
                  {/* AI Comment - handle both snake_case from backend and camelCase */}
                  {(trade.aiComment || (trade as Record<string, unknown>).ai_comment) && (
                    <div className="ml-[76px] mt-1.5 text-muted-foreground/70 italic text-[11px]">
                      "{trade.aiComment || (trade as Record<string, unknown>).ai_comment}"
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
      ) : (
        <div className="h-64 overflow-y-auto font-mono text-xs">
          <div className="text-muted-foreground/70 py-4 space-y-3">
            <p className="text-foreground/80">📌 Pinned Messages</p>
            <p>This section is reserved for important announcements and pinned content.</p>
            <p className="text-muted-foreground/50 text-[10px]">
              // TODO: Add your pinned content here
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
