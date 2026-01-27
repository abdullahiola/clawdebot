"use client"

import type { ReactNode } from "react"

interface TerminalWindowProps {
  title?: string
  children: ReactNode
  className?: string
}

export function TerminalWindow({ title = "Terminal", children, className = "" }: TerminalWindowProps) {
  return (
    <div className={`rounded-xl overflow-hidden border border-border/50 bg-card/80 backdrop-blur-xl shadow-2xl shadow-black/20 ${className}`}>
      {/* Modern macOS title bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-secondary/30 border-b border-border/50">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-[#ff5f57] shadow-sm shadow-[#ff5f57]/50 hover:brightness-110 transition-all cursor-pointer" />
          <div className="w-3 h-3 rounded-full bg-[#febc2e] shadow-sm shadow-[#febc2e]/50 hover:brightness-110 transition-all cursor-pointer" />
          <div className="w-3 h-3 rounded-full bg-[#28c840] shadow-sm shadow-[#28c840]/50 hover:brightness-110 transition-all cursor-pointer" />
        </div>
        <span className="flex-1 text-center text-[11px] text-muted-foreground/70 font-mono tracking-tight">{title}</span>
        <div className="w-14" />
      </div>
      {/* Terminal content */}
      <div className="p-5 font-mono text-sm leading-relaxed">{children}</div>
    </div>
  )
}
