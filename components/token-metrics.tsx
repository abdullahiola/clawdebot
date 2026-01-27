"use client"

import { useEffect, useState } from "react"

interface TokenMetricsProps {
  marketCap?: number | null
  holders?: number | null
  totalBuys?: number
  totalSells?: number
  totalBuyVolume?: number
  totalSellVolume?: number
  creatorRewards?: number
  isLive?: boolean
}

export function TokenMetrics({
  marketCap,
  holders,
  totalBuys = 0,
  totalSells = 0,
  totalBuyVolume = 0,
  totalSellVolume = 0,
  creatorRewards = 0,
  isLive = false
}: TokenMetricsProps) {
  const [blinkVisible, setBlinkVisible] = useState(true)

  useEffect(() => {
    const interval = setInterval(() => {
      setBlinkVisible((prev) => !prev)
    }, 500)
    return () => clearInterval(interval)
  }, [])

  const formatMarketCap = (mc: number | null | undefined) => {
    if (!mc) return "—"
    if (mc >= 1000) return `${(mc / 1000).toFixed(2)}K SOL`
    return `${mc.toFixed(2)} SOL`
  }

  const formatVolume = (vol: number) => {
    if (vol >= 1000000) return `$${(vol / 1000000).toFixed(2)}M`
    if (vol >= 1000) return `$${(vol / 1000).toFixed(1)}K`
    return `$${vol.toFixed(0)}`
  }

  const netFlow = totalBuyVolume - totalSellVolume

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
        <span className={`${blinkVisible ? "opacity-100" : "opacity-0"} text-foreground/60 text-xs`}>|</span>
      </div>

      <div className="space-y-3">
        <div className="flex justify-between items-center py-2 border-b border-border/20">
          <span className="text-muted-foreground/60 text-xs uppercase tracking-wider">Market Cap</span>
          <span className="text-foreground text-lg tabular-nums">{formatMarketCap(marketCap)}</span>
        </div>
        <div className="flex justify-between items-center py-2 border-b border-border/20">
          <span className="text-muted-foreground/60 text-xs uppercase tracking-wider">Holders</span>
          <span className="text-foreground text-lg tabular-nums">{holders?.toLocaleString() ?? "—"}</span>
        </div>
        <div className="flex justify-between items-center py-2 border-b border-border/20">
          <span className="text-muted-foreground/60 text-xs uppercase tracking-wider">Creator Rewards</span>
          <span className="text-[#f5a623] text-lg tabular-nums">{formatVolume(creatorRewards)}</span>
        </div>
        <div className="flex justify-between items-center py-2 border-b border-border/20">
          <span className="text-muted-foreground/60 text-xs uppercase tracking-wider">Buys / Sells</span>
          <span className="text-foreground text-lg tabular-nums">
            <span className="text-[#28c840]">{totalBuys}</span>
            <span className="text-muted-foreground/40"> / </span>
            <span className="text-[#ff5f56]">{totalSells}</span>
          </span>
        </div>
        <div className="flex justify-between items-center py-2">
          <span className="text-muted-foreground/60 text-xs uppercase tracking-wider">Net Flow</span>
          <span className={`text-lg tabular-nums ${netFlow >= 0 ? 'text-[#28c840]' : 'text-[#ff5f56]'}`}>
            {netFlow >= 0 ? '+' : ''}{formatVolume(netFlow)}
          </span>
        </div>
      </div>
    </div>
  )
}
