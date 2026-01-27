"use client"

import { useEffect, useState } from "react"

export function StatusBar() {
  const [time, setTime] = useState("")
  const [session, setSession] = useState(0)

  useEffect(() => {
    const updateTime = () => {
      setTime(new Date().toLocaleTimeString("en-US", { hour12: false }))
    }
    updateTime()
    const interval = setInterval(() => {
      updateTime()
      setSession((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  const formatSession = (seconds: number) => {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = seconds % 60
    return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Status */}
      <div className="bg-gradient-to-br from-[#28c840]/10 to-transparent border border-[#28c840]/30 rounded-lg p-4 backdrop-blur-sm">
        <div className="flex items-center gap-2 mb-1">
          <span className="w-2 h-2 rounded-full bg-[#28c840] shadow-lg shadow-[#28c840]/50 animate-pulse" />
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground/60 font-medium">Status</span>
        </div>
        <div className="text-lg font-mono font-semibold text-[#28c840]">Online</div>
      </div>

      {/* Network */}
      <div className="bg-card/60 backdrop-blur-sm border border-border/40 rounded-lg p-4 hover:border-border/60 transition-all">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground/60 font-medium mb-1">Network</div>
        <div className="text-lg font-mono font-semibold text-foreground/90 flex items-center gap-2">
          <span className="text-sm">⬡</span> Solana
        </div>
      </div>

      {/* Session Time */}
      <div className="bg-card/60 backdrop-blur-sm border border-border/40 rounded-lg p-4 hover:border-border/60 transition-all">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground/60 font-medium mb-1">Session</div>
        <div className="text-lg font-mono font-semibold text-foreground/90 tabular-nums">{formatSession(session)}</div>
      </div>
    </div>
  )
}
