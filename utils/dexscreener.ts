// Direct DexScreener API utilities for frontend

export interface DexScreenerPair {
    chainId: string
    dexId: string
    url: string
    pairAddress: string
    baseToken: {
        address: string
        name: string
        symbol: string
    }
    quoteToken: {
        address: string
        name: string
        symbol: string
    }
    priceNative: string
    priceUsd: string
    liquidity?: {
        usd: number
        base: number
        quote: number
    }
    fdv?: number
    marketCap?: number
    volume?: {
        h24: number
        h6?: number
        h1?: number
        m5?: number
    }
    priceChange?: {
        h1?: number
        h6?: number
        h24?: number
        m5?: number
    }
}

export interface DexScreenerResponse {
    schemaVersion: string
    pairs: DexScreenerPair[]
}

export interface PumpPortalMetadata {
    marketCapSol: number
    marketCapUsd: number
    holderCount: number
    supply: number
    creatorRewardsAvailable?: number
    creatorRewards?: number
}

export interface TokenMetrics {
    marketCapUsd: number
    marketCapSol: number
    liquidityUsd: number
    volume24h: number
    priceUsd: number
    priceNative: number
    holderCount?: number
    creatorRewards?: number
}

/**
 * Fetch token data directly from DexScreener API (Latest version)
 * @param mint - Solana token mint address
 * @returns DexScreener pair data or null if not found
 */
export async function fetchDexScreenerData(mint: string): Promise<DexScreenerPair | null> {
    try {
        // Use the LATEST DexScreener API endpoint
        const response = await fetch(`https://api.dexscreener.com/latest/dex/tokens/${mint}`, {
            headers: {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        })

        if (!response.ok) {
            console.warn(`DexScreener API returned ${response.status} for ${mint}`)
            return null
        }

        const data: DexScreenerResponse = await response.json()

        // Return the pair with highest liquidity (most accurate pricing)
        if (data.pairs && data.pairs.length > 0) {
            // Sort by liquidity to get the most liquid pair
            const sortedPairs = data.pairs.sort((a, b) => {
                const liquidityA = a.liquidity?.usd || 0
                const liquidityB = b.liquidity?.usd || 0
                return liquidityB - liquidityA
            })

            console.log(`[DexScreener] Found ${data.pairs.length} pairs, using most liquid: ${sortedPairs[0].dexId}`)
            return sortedPairs[0]
        }

        return null
    } catch (error) {
        console.error('[DexScreener] API error:', error)
        return null
    }
}

/**
 * Fetch metadata from PumpPortal API (for creator rewards and holder count)
 * @param mint - Solana token mint address
 * @returns PumpPortal metadata or null if not found
 */
export async function fetchPumpPortalData(mint: string): Promise<PumpPortalMetadata | null> {
    try {
        // Use the correct Pump.fun API endpoint
        const response = await fetch(`https://frontend-api.pump.fun/coins/${mint}`, {
            headers: {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0'
            }
        })

        if (!response.ok) {
            console.warn(`Pump.fun API returned ${response.status} for ${mint}`)
            return null
        }

        const data = await response.json()

        console.log('[Pump.fun] Successfully fetched metadata:', {
            holderCount: data.total_holders || data.holderCount,
            creatorRewards: data.creator_coins_available || data.creatorRewardsAvailable
        })

        // Map the API response to our interface
        return {
            marketCapSol: data.usd_market_cap / (data.price_per_sol || 130) || 0,  // Convert USD to SOL
            marketCapUsd: data.usd_market_cap || 0,
            holderCount: data.total_holders || data.holderCount || 0,
            supply: data.total_supply || data.supply || 0,
            creatorRewardsAvailable: data.creator_coins_available || 0,
            creatorRewards: data.creator_coins_available || 0
        }
    } catch (error) {
        console.error('[Pump.fun] API error:', error)
        return null
    }
}

/**
 * Extract token metrics from DexScreener pair data
 * Optionally merge with PumpPortal data for holder count and creator rewards
 */
export function extractTokenMetrics(
    pair: DexScreenerPair | null,
    pumpPortal?: PumpPortalMetadata | null
): TokenMetrics {
    if (!pair) {
        return {
            marketCapUsd: 0,
            marketCapSol: 0,
            liquidityUsd: 0,
            volume24h: 0,
            priceUsd: 0,
            priceNative: 0,
            holderCount: pumpPortal?.holderCount || 0,
            creatorRewards: pumpPortal?.creatorRewardsAvailable || pumpPortal?.creatorRewards || 0
        }
    }

    // Extract market cap (fdv = fully diluted valuation)
    const marketCapUsd = parseFloat(String(pair.fdv || pair.marketCap || 0))

    // Extract liquidity
    const liquidityUsd = pair.liquidity?.usd || 0

    // Extract 24hr volume
    const volume24h = pair.volume?.h24 || 0

    // Get prices
    const priceUsd = parseFloat(pair.priceUsd || '0')
    const priceNative = parseFloat(pair.priceNative || '0')

    // Calculate market cap in SOL
    let marketCapSol = 0
    if (priceUsd > 0 && priceNative > 0) {
        marketCapSol = (marketCapUsd / priceUsd) * priceNative
    }

    return {
        marketCapUsd,
        marketCapSol,
        liquidityUsd,
        volume24h,
        priceUsd,
        priceNative,
        holderCount: pumpPortal?.holderCount,
        creatorRewards: pumpPortal?.creatorRewardsAvailable || pumpPortal?.creatorRewards || 0
    }
}

/**
 * Fetch and extract token metrics from both DexScreener and PumpPortal
 * @param mint - Solana token mint address
 * @returns Combined token metrics object
 */
export async function getTokenMetrics(mint: string): Promise<TokenMetrics> {
    // Fetch from both APIs in parallel
    const [pair, pumpPortal] = await Promise.all([
        fetchDexScreenerData(mint),
        fetchPumpPortalData(mint)
    ])

    return extractTokenMetrics(pair, pumpPortal)
}
