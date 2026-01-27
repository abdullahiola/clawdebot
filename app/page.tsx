"use client"

import { TerminalWindow } from "@/components/terminal-window"
import { TokenMetrics } from "@/components/token-metrics"
import { NeuralStream } from "@/components/neural-stream"
import { ActivityLog } from "@/components/activity-log"
import { StatusBar } from "@/components/status-bar"
import { useBotStream } from "@/hooks/use-bot-stream"

export default function Home() {
  const { isConnected, state, trades, actions } = useBotStream()

  return (
    <main className="min-h-screen bg-background p-6 md:p-10">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Header */}
        <div className="text-center space-y-3 pt-4">
          <h1 className="text-3xl md:text-4xl font-mono text-foreground tracking-tight">
            ClaudeBot
          </h1>
          <p className="text-sm text-muted-foreground font-mono tracking-wide">
            Neural Network Token Dashboard
          </p>
        </div>

        {/* Status Bar */}
        <StatusBar />

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Token Metrics */}
          <TerminalWindow title="claudebot@solana: ~/metrics">
            <TokenMetrics
              marketCap={state?.lastMarketCap}
              holders={state?.lastHolderCount}
              totalBuys={state?.totalBuys ?? 0}
              totalSells={state?.totalSells ?? 0}
              totalBuyVolume={state?.totalBuyVolume ?? 0}
              totalSellVolume={state?.totalSellVolume ?? 0}
              creatorRewards={state?.creatorRewards ?? 0}
              isLive={isConnected}
            />
          </TerminalWindow>

          {/* Neural Stream */}
          <TerminalWindow title="claudebot@solana: ~/neural_stream">
            <NeuralStream
              actions={actions}
              isLive={isConnected}
            />
          </TerminalWindow>
        </div>

        {/* Activity Log - Full Width */}
        <TerminalWindow title="claudebot@solana: ~/logs">
          <ActivityLog
            trades={trades}
            isLive={isConnected}
          />
        </TerminalWindow>

        {/* Quick Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <QuickStat
            label="Net Flow"
            value={formatNetFlow((state?.totalBuyVolume ?? 0) - (state?.totalSellVolume ?? 0))}
            positive={(state?.totalBuyVolume ?? 0) >= (state?.totalSellVolume ?? 0)}
          />
          <QuickStat
            label="Total Trades"
            value={((state?.totalBuys ?? 0) + (state?.totalSells ?? 0)).toLocaleString()}
          />
          <QuickStat
            label="Status"
            value={isConnected ? "🟢 Live" : "⚫ Offline"}
          />
        </div>

        {/* Footer */}
        <footer className="text-center py-6 border-t border-border/30">
          <p className="text-xs text-muted-foreground/60 font-mono tracking-wide">
            Built with neural precision
          </p>
        </footer>
      </div>
    </main>
  )
}

function formatNetFlow(value: number): string {
  const sign = value >= 0 ? '+' : ''
  if (Math.abs(value) >= 1000000) return `${sign}$${(value / 1000000).toFixed(2)}M`
  if (Math.abs(value) >= 1000) return `${sign}$${(value / 1000).toFixed(1)}K`
  return `${sign}$${value.toFixed(0)}`
}

function QuickStat({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  return (
    <div className="bg-card/60 backdrop-blur-sm border border-border/40 rounded-xl p-5 font-mono transition-all hover:bg-card/80 hover:border-border/60">
      <div className="flex items-center gap-2 text-xs text-muted-foreground/70 mb-2">
        <span className="text-foreground/40">$</span>
        <span>{label.toLowerCase().replace(" ", "_")}</span>
      </div>
      <div className={`text-2xl font-medium ${positive !== undefined ? (positive ? 'text-[#28c840]' : 'text-[#ff5f56]') : 'text-foreground'}`}>
        {value}
      </div>
    </div>
  )
}
