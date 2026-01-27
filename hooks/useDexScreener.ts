import { useState, useEffect, useCallback } from 'react'
import { getTokenMetrics, DexScreenerPair, TokenMetrics } from '@/utils/dexscreener'

export interface UseDexScreenerOptions {
    /** Auto-fetch on mount */
    autoFetch?: boolean
    /** Auto-refresh interval in milliseconds (0 = disabled) */
    refreshInterval?: number
    /** Token mint address */
    mint?: string
}

export interface UseDexScreenerReturn {
    data: DexScreenerPair | null
    metrics: TokenMetrics | null
    loading: boolean
    error: string | null
    refetch: () => Promise<void>
}

/**
 * React hook to fetch and auto-update DexScreener data
 * 
 * @example
 * ```tsx
 * const { data, metrics, loading, error } = useDexScreener({
 *   mint: 'YOUR_TOKEN_MINT_ADDRESS',
 *   autoFetch: true,
 *   refreshInterval: 30000 // Refresh every 30 seconds
 * })
 * ```
 */
export function useDexScreener(options: UseDexScreenerOptions = {}): UseDexScreenerReturn {
    const { autoFetch = true, refreshInterval = 0, mint } = options

    const [data, setData] = useState<DexScreenerPair | null>(null)
    const [metrics, setMetrics] = useState<TokenMetrics | null>(null)
    const [loading, setLoading] = useState<boolean>(false)
    const [error, setError] = useState<string | null>(null)

    const refetch = useCallback(async () => {
        if (!mint) {
            setError('No mint address provided')
            return
        }

        setLoading(true)
        setError(null)

        try {
            // Use getTokenMetrics which fetches from both DexScreener and PumpPortal
            const tokenMetrics = await getTokenMetrics(mint)

            if (!tokenMetrics || tokenMetrics.marketCapUsd === 0) {
                setError('Token not found')
                setData(null)
                setMetrics(null)
                return
            }

            // We don't need the raw pair data anymore, just set metrics
            setData(null)
            setMetrics(tokenMetrics)
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Failed to fetch data'
            setError(errorMessage)
            console.error('[useDexScreener] Error:', err)
        } finally {
            setLoading(false)
        }
    }, [mint])

    // Auto-fetch on mount or when mint changes
    useEffect(() => {
        if (autoFetch && mint) {
            refetch()
        }
    }, [autoFetch, mint, refetch])

    // Auto-refresh interval
    useEffect(() => {
        if (!refreshInterval || refreshInterval <= 0 || !mint) {
            return
        }

        const intervalId = setInterval(() => {
            refetch()
        }, refreshInterval)

        return () => clearInterval(intervalId)
    }, [refreshInterval, mint, refetch])

    return {
        data,
        metrics,
        loading,
        error,
        refetch
    }
}
