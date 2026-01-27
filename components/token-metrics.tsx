"use client"

import { useEffect, useState } from "react"
import { useDexScreener } from "@/hooks/useDexScreener"

interface TokenMetricsProps {
  // WebSocket data props (for backward compatibility)
  marketCap?: number | null
  holders?: number | null
  creatorRewards?: number
  isLive?: boolean

  // Direct DexScreener fetch props
  tokenAddress?: string
  enableDirectFetch?: boolean
  refreshInterval?: number
}

export function TokenMetrics({
  marketCap,
  holders,
  creatorRewards = 0,
  isLive = false,
  tokenAddress,
  enableDirectFetch = false,
  refreshInterval = 30000
}: TokenMetricsProps) {
  const [blinkVisible, setBlinkVisible] = useState(true)

  // Direct DexScreener fetch (if enabled)
  const { metrics, loading, error } = useDexScreener({
    mint: enableDirectFetch ? tokenAddress : undefined,
    autoFetch: enableDirectFetch,
    refreshInterval: enableDirectFetch ? refreshInterval : 0
  })

  useEffect(() => {
    const interval = setInterval(() => {
      setBlinkVisible((prev) => !prev)
    }, 500)
    return () => clearInterval(interval)
  }, [])

  // Use DexScreener metrics for market data, WebSocket for holders and creator rewards
  const displayMarketCap = enableDirectFetch ? metrics?.marketCapUsd : marketCap
  const displayLiquidity = enableDirectFetch ? metrics?.liquidityUsd : undefined
  const displayVolume24h = enableDirectFetch ? metrics?.volume24h : undefined
  // Always use WebSocket data for holders and creator rewards (claimed, not available)
  const displayHolders = holders
  const displayCreatorRewards = creatorRewards
  const dataSource = enableDirectFetch ? (loading ? "⟳" : "DexScreener") : "WebSocket"

  const formatMarketCap = (mc: number | null | undefined) => {
    if (!mc) return "—"
    if (mc >= 1000000) return `$${(mc / 1000000).toFixed(2)}M`
    if (mc >= 1000) return `$${(mc / 1000).toFixed(1)}K`
    return `$${mc.toFixed(0)}`
  }

  const formatVolume = (vol: number | undefined | null) => {
    if (!vol) return "—"
    if (vol >= 1000000) return `$${(vol / 1000000).toFixed(2)}M`
    if (vol >= 1000) return `$${(vol / 1000).toFixed(1)}K`
    return `$${vol.toFixed(0)}`
  }


  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground/50">$</span>
        <span className="text-foreground/90">get_token_metrics</span>
        {isLive && (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[#28c840]/10 text-[#28c840] text-[10px]">
            <span className="w-1 h-1 rounded-full bg-[#28c840] animate-pulse" />
            LIVE
          </span>
        )}
        {enableDirectFetch && (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-500 text-[10px]">
            {dataSource}
          </span>
        )}
        {error && (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-red-500/10 text-red-500 text-[10px]">
            API Error
          </span>
        )}
        <span className={`${blinkVisible ? "opacity-100" : "opacity-0"} text-foreground/60 text-xs`}>|</span>
      </div>

      <div className="space-y-3">
        <div className="flex justify-between items-center py-2 border-b border-border/20">
          <span className="text-muted-foreground/60 text-xs uppercase tracking-wider">Market Cap</span>
          <span className="text-foreground text-lg tabular-nums">{formatMarketCap(displayMarketCap)}</span>
        </div>

        {enableDirectFetch && displayLiquidity !== undefined && (
          <div className="flex justify-between items-center py-2 border-b border-border/20">
            <span className="text-muted-foreground/60 text-xs uppercase tracking-wider">Liquidity</span>
            <span className="text-foreground text-lg tabular-nums">{formatVolume(displayLiquidity)}</span>
          </div>
        )}

        {enableDirectFetch && displayVolume24h !== undefined && (
          <div className="flex justify-between items-center py-2 border-b border-border/20">
            <span className="text-muted-foreground/60 text-xs uppercase tracking-wider">24h Volume</span>
            <span className="text-foreground text-lg tabular-nums">{formatVolume(displayVolume24h)}</span>
          </div>
        )}

        <div className="flex justify-between items-center py-2 border-b border-border/20">
          <span className="text-muted-foreground/60 text-xs uppercase tracking-wider">Holders</span>
          <span className="text-foreground text-lg tabular-nums">{displayHolders?.toLocaleString() ?? "—"}</span>
        </div>
        <div className="flex justify-between items-center py-2">
          <span className="text-muted-foreground/60 text-xs uppercase tracking-wider">Creator Rewards</span>
          <span className="text-[#f5a623] text-lg tabular-nums">{formatVolume(displayCreatorRewards)}</span>
        </div>
      </div>
    </div>
  )
}
