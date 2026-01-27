"use client"

import { useEffect, useState, useRef, useCallback } from 'react'

export interface BotState {
    tokenAddress: string | null
    totalBuys: number
    totalSells: number
    totalBuyVolume: number
    totalSellVolume: number
    lastPrice: number | null
    highestPrice: number | null
    lowestPrice: number | null
    lastMarketCap: number | null
    lastHolderCount: number | null
    lastCreatorRewardsAvailable: number
    creatorRewards: number
    totalAnalyses: number
    startTime: number | null
    analysisMode: string
}

export interface Trade {
    timestamp: number
    type: 'buy' | 'sell'
    price: number
    sol_amount: number
    volume_usd: number
    token_amount: number
    market_cap_sol: number
    holder_count: number | string
    user: string
    signature: string
    aiComment?: string
}

export interface BotAction {
    timestamp: string
    type: string
    description: string
    details: Record<string, unknown>
}

interface WebSocketMessage {
    type: 'initial_state' | 'trade' | 'action' | 'state_update' | 'pong'
    data: unknown
    timestamp?: string
}

// Use environment variable for production, fallback to localhost for development
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8765'
const RECONNECT_DELAY = 3000
const MAX_RECONNECT_DELAY = 30000

export function useBotStream() {
    const [isConnected, setIsConnected] = useState(false)
    const [state, setState] = useState<BotState | null>(null)
    const [trades, setTrades] = useState<Trade[]>([])
    const [actions, setActions] = useState<BotAction[]>([])
    const [error, setError] = useState<string | null>(null)

    const wsRef = useRef<WebSocket | null>(null)
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
    const reconnectDelayRef = useRef(RECONNECT_DELAY)
    const mountedRef = useRef(true)

    // Fetch initial state from API (fallback when bot is offline)
    const fetchInitialState = useCallback(async () => {
        try {
            const [botRes, actionsRes] = await Promise.all([
                fetch('/api/bot'),
                fetch('/api/actions'),
            ])

            if (botRes.ok) {
                const botData = await botRes.json()
                if (botData.state) {
                    setState(botData.state)
                }
            }

            if (actionsRes.ok) {
                const actionsData = await actionsRes.json()
                if (actionsData.actions) {
                    setActions(actionsData.actions)
                }
            }
        } catch (err) {
            console.error('Failed to fetch initial state:', err)
        }
    }, [])

    const connect = useCallback(() => {
        if (!mountedRef.current) return

        // Clean up existing connection
        if (wsRef.current) {
            wsRef.current.close()
        }

        try {
            const ws = new WebSocket(WS_URL)
            wsRef.current = ws

            ws.onopen = () => {
                if (!mountedRef.current) return
                console.log('🌐 Dashboard connected to bot')
                setIsConnected(true)
                setError(null)
                reconnectDelayRef.current = RECONNECT_DELAY
            }

            ws.onmessage = (event) => {
                if (!mountedRef.current) return
                try {
                    const message: WebSocketMessage = JSON.parse(event.data)

                    switch (message.type) {
                        case 'initial_state': {
                            const data = message.data as {
                                state: BotState
                                recent_trades: Trade[]
                                recent_actions: BotAction[]
                            }
                            setState(data.state)
                            setTrades(data.recent_trades || [])
                            setActions(data.recent_actions || [])
                            break
                        }

                        case 'trade': {
                            const trade = message.data as Trade
                            setTrades(prev => [...prev.slice(-49), trade])
                            break
                        }

                        case 'action': {
                            const action = message.data as BotAction
                            setActions(prev => [action, ...prev.slice(0, 49)])
                            break
                        }

                        case 'state_update': {
                            const update = message.data as Partial<BotState>
                            setState(prev => prev ? { ...prev, ...update } : null)
                            break
                        }

                        case 'pong':
                            // Heartbeat response, ignore
                            break
                    }
                } catch (err) {
                    console.error('Failed to parse WebSocket message:', err)
                }
            }

            ws.onclose = () => {
                if (!mountedRef.current) return
                console.log('🌐 Dashboard disconnected from bot')
                setIsConnected(false)

                // Schedule reconnect
                reconnectTimeoutRef.current = setTimeout(() => {
                    if (mountedRef.current) {
                        reconnectDelayRef.current = Math.min(
                            reconnectDelayRef.current * 1.5,
                            MAX_RECONNECT_DELAY
                        )
                        connect()
                    }
                }, reconnectDelayRef.current)
            }

            ws.onerror = (err) => {
                console.error('WebSocket error:', err)
                setError('Failed to connect to bot')
            }
        } catch (err) {
            console.error('Failed to create WebSocket:', err)
            setError('Failed to connect to bot')

            // Try API fallback
            fetchInitialState()
        }
    }, [fetchInitialState])

    useEffect(() => {
        mountedRef.current = true

        // Try to connect to WebSocket
        connect()

        // Also fetch from API as fallback
        fetchInitialState()

        return () => {
            mountedRef.current = false
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current)
            }
            if (wsRef.current) {
                wsRef.current.close()
            }
        }
    }, [connect, fetchInitialState])

    return {
        isConnected,
        state,
        trades,
        actions,
        error,
    }
}
