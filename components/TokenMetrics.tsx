import { useDexScreener } from '@/hooks/useDexScreener'

interface TokenMetricsProps {
    mint: string
    refreshInterval?: number
}

/**
 * Component that automatically fetches and displays token metrics from DexScreener
 * 
 * @example
 * ```tsx
 * <TokenMetrics 
 *   mint="YOUR_TOKEN_ADDRESS" 
 *   refreshInterval={30000} // Refresh every 30 seconds
 * />
 * ```
 */
export function TokenMetrics({ mint, refreshInterval = 30000 }: TokenMetricsProps) {
    const { metrics, loading, error, refetch } = useDexScreener({
        mint,
        autoFetch: true,
        refreshInterval
    })

    if (loading && !metrics) {
        return (
            <div className="p-4 bg-gray-100 rounded-lg">
                <p className="text-gray-600">Loading token metrics...</p>
            </div>
        )
    }

    if (error) {
        return (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-red-600">Error: {error}</p>
                <button
                    onClick={refetch}
                    className="mt-2 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
                >
                    Retry
                </button>
            </div>
        )
    }

    if (!metrics) {
        return (
            <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-yellow-800">No data available</p>
            </div>
        )
    }

    return (
        <div className="p-6 bg-white border border-gray-200 rounded-lg shadow-sm">
            <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-bold text-gray-900">Token Metrics</h3>
                <button
                    onClick={refetch}
                    className="text-sm text-blue-600 hover:text-blue-800"
                >
                    Refresh
                </button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <MetricItem
                    label="Market Cap (USD)"
                    value={`$${metrics.marketCapUsd.toLocaleString()}`}
                />
                <MetricItem
                    label="Market Cap (SOL)"
                    value={`${metrics.marketCapSol.toFixed(2)} SOL`}
                />
                <MetricItem
                    label="Liquidity"
                    value={`$${metrics.liquidityUsd.toLocaleString()}`}
                />
                <MetricItem
                    label="24h Volume"
                    value={`$${metrics.volume24h.toLocaleString()}`}
                />
                <MetricItem
                    label="Price (USD)"
                    value={`$${metrics.priceUsd.toFixed(8)}`}
                />
                <MetricItem
                    label="Price (Native)"
                    value={metrics.priceNative.toFixed(10)}
                />
            </div>
        </div>
    )
}

function MetricItem({ label, value }: { label: string; value: string }) {
    return (
        <div>
            <p className="text-xs text-gray-500 mb-1">{label}</p>
            <p className="text-sm font-semibold text-gray-900">{value}</p>
        </div>
    )
}
