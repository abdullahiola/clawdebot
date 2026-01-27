"use client"

import { useEffect, useRef, useState } from "react"
import type { BotAction } from "@/hooks/use-bot-stream"

interface AnalysisStreamProps {
    actions?: BotAction[]
    isLive?: boolean
}

export function AnalysisStream({ actions = [], isLive = false }: AnalysisStreamProps) {
    const scrollRef = useRef<HTMLDivElement>(null)
    const [isThinking, setIsThinking] = useState(true)
    const [dots, setDots] = useState("")

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
    }, [actions])

    // Animate thinking dots
    useEffect(() => {
        const interval = setInterval(() => {
            setDots(prev => prev.length >= 3 ? "" : prev + ".")
        }, 500)
        return () => clearInterval(interval)
    }, [])

    // Filter for analysis actions only
    const analysisActions = actions.filter(action =>
        action.type === "analyze" || action.type === "auto_analyze"
    )

    const formatTimestamp = (ts: string) => {
        try {
            const date = new Date(ts)
            return date.toLocaleTimeString("en-US", { hour12: false })
        } catch {
            return ts
        }
    }

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-3">
                    <span className="text-muted-foreground/50">~</span>
                    <span className="text-foreground/90">claude_analysis --stream</span>
                </div>
                <span className="text-muted-foreground/50 italic min-w-[80px] text-right">
                    thinking{dots}
                </span>
            </div>

            <div
                ref={scrollRef}
                className="h-64 overflow-y-auto space-y-3 pr-2"
            >
                {analysisActions.length === 0 ? (
                    <div className="text-muted-foreground/60 py-4 space-y-4 text-xs">
                        <div className="space-y-2">
                            <p className="text-foreground/80 font-medium">📊 Live Market Analysis</p>
                            <p className="text-xs leading-relaxed text-muted-foreground/50">
                                Awaiting analysis stream from Claude Sonnet 4...
                            </p>
                        </div>
                        <div className="pt-2 border-t border-border/20">
                            <p className="text-[10px] text-muted-foreground/40 italic">
                                Analysis will appear here automatically
                            </p>
                        </div>
                    </div>
                ) : (
                    analysisActions.slice(-5).reverse().map((action, index) => (
                        <div key={`${action.timestamp}-${index}`} className="group">
                            <div className="flex items-start gap-3 mb-2">
                                <span className="text-muted-foreground/40 shrink-0 tabular-nums text-[10px]">
                                    {formatTimestamp(action.timestamp)}
                                </span>
                                <span className="text-[#28c840] text-xs font-medium">
                                    {action.description}
                                </span>
                            </div>
                            {action.details && (action.details as { analysis_text?: string }).analysis_text && (
                                <div className="ml-0 pl-4 border-l-2 border-[#28c840]/20 text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap">
                                    {(action.details as { analysis_text?: string }).analysis_text}
                                </div>
                            )}
                        </div>
                    ))
                )}
            </div>
        </div>
    )
}
