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
    <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-3 bg-card/50 backdrop-blur-sm border border-border/40 rounded-xl text-xs font-mono">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground/60">Status</span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#28c840] shadow-sm shadow-[#28c840]/50" />
            <span className="text-foreground/90">Online</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground/60">Network</span>
          <span className="text-foreground/90">Solana</span>
        </div>
      </div>
      
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground/60">Session</span>
          <span className="text-foreground/90 tabular-nums">{formatSession(session)}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground/60">Time</span>
          <span className="text-foreground/90 tabular-nums">{time}</span>
        </div>
        <span className="text-muted-foreground/40">v0.5.0</span>
      </div>
    </div>
  )
}
