import os
import requests
import asyncio
import aiohttp
from typing import Dict, Optional, Set
from dotenv import load_dotenv
import json

load_dotenv()

# Configuration
TOKEN_ADDRESS = os.getenv("TOKEN_ADDRESS", "YOUR_TOKEN_ADDRESS_HERE")
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")  # Get free key at birdeye.so


class DexScreenerAPI:
    """DexScreener API - Most reliable, no API key needed."""

    @staticmethod
    async def get_token_data(token_address: str) -> Dict:
        """Get token data from DexScreener."""
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}",
                            "source": "dexscreener",
                        }

                    result = await response.json()
                    pairs = result.get("pairs", [])

                    if not pairs:
                        return {
                            "success": False,
                            "error": "Token not found on any DEX",
                            "source": "dexscreener",
                        }

                    # Get the highest liquidity pair
                    pair = max(
                        pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0))
                    )

                    return {
                        "success": True,
                        "source": "dexscreener",
                        "token_address": token_address,
                        "name": pair.get("baseToken", {}).get("name", "Unknown"),
                        "symbol": pair.get("baseToken", {}).get("symbol", "Unknown"),
                        "price_usd": float(pair.get("priceUsd", 0)),
                        "price_native": float(
                            pair.get("priceNative", 0)
                        ),  # Price in SOL
                        "market_cap": (
                            float(pair.get("marketCap", 0))
                            if pair.get("marketCap")
                            else 0
                        ),
                        "liquidity_usd": float(pair.get("liquidity", {}).get("usd", 0)),
                        "liquidity_base": float(
                            pair.get("liquidity", {}).get("base", 0)
                        ),
                        "liquidity_quote": float(
                            pair.get("liquidity", {}).get("quote", 0)
                        ),
                        "volume_24h": float(pair.get("volume", {}).get("h24", 0)),
                        "volume_6h": float(pair.get("volume", {}).get("h6", 0)),
                        "volume_1h": float(pair.get("volume", {}).get("h1", 0)),
                        "price_change_24h": float(
                            pair.get("priceChange", {}).get("h24", 0)
                        ),
                        "price_change_6h": float(
                            pair.get("priceChange", {}).get("h6", 0)
                        ),
                        "price_change_1h": float(
                            pair.get("priceChange", {}).get("h1", 0)
                        ),
                        "txns_24h_buys": pair.get("txns", {})
                        .get("h24", {})
                        .get("buys", 0),
                        "txns_24h_sells": pair.get("txns", {})
                        .get("h24", {})
                        .get("sells", 0),
                        "dex": pair.get("dexId", "Unknown"),
                        "pair_address": pair.get("pairAddress", ""),
                        "pair_created_at": pair.get("pairCreatedAt", 0),
                        "url": pair.get("url", ""),
                        "raw_data": pair,
                    }

        except Exception as e:
            return {"success": False, "error": str(e), "source": "dexscreener"}


class BirdeyeAPI:
    """Birdeye API - Provides holder count (requires free API key)."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def get_token_overview(self, token_address: str) -> Dict:
        """Get token overview including holder count."""
        if not self.api_key:
            return {
                "success": False,
                "error": "No API key provided. Get free key at: https://birdeye.so",
                "source": "birdeye",
            }

        url = (
            f"https://public-api.birdeye.so/defi/token_overview?address={token_address}"
        )
        headers = {"X-API-KEY": self.api_key, "x-chain": "solana"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}",
                            "source": "birdeye",
                        }

                    result = await response.json()

                    if not result.get("success"):
                        return {
                            "success": False,
                            "error": result.get("message", "Unknown error"),
                            "source": "birdeye",
                        }

                    data = result.get("data", {})

                    return {
                        "success": True,
                        "source": "birdeye",
                        "token_address": token_address,
                        "holder_count": data.get("holder", 0),
                        "price_usd": data.get("price", 0),
                        "market_cap": data.get("mc", 0),
                        "liquidity": data.get("liquidity", 0),
                        "volume_24h": data.get("v24hUSD", 0),
                        "raw_data": data,
                    }

        except Exception as e:
            return {"success": False, "error": str(e), "source": "birdeye"}


class HolderTracker:
    """Track unique holders from WebSocket trades."""

    def __init__(self):
        self.unique_wallets: Set[str] = set()

    def add_wallet(self, wallet_address: str):
        """Add a wallet to the unique set."""
        if wallet_address and wallet_address != "Unknown":
            self.unique_wallets.add(wallet_address)

    def get_holder_count(self) -> int:
        """Get estimated holder count from tracked wallets."""
        return len(self.unique_wallets)

    def reset(self):
        """Reset the tracker."""
        self.unique_wallets.clear()


# =============================================================================
# COMBINED DATA FETCHER
# =============================================================================


class TokenDataFetcher:
    """Fetch token data with multiple fallbacks."""

    def __init__(self, birdeye_api_key: Optional[str] = None):
        self.dexscreener = DexScreenerAPI()
        self.birdeye = BirdeyeAPI(birdeye_api_key) if birdeye_api_key else None
        self.holder_tracker = HolderTracker()

    async def get_complete_data(
        self, token_address: str, include_holders: bool = True
    ) -> Dict:
        """
        Get complete token data from all available sources.

        Args:
            token_address: Token mint address
            include_holders: Whether to fetch holder count (requires Birdeye API key)

        Returns:
            Combined data from all sources
        """
        # Always fetch from DexScreener (most reliable)
        dex_data = await self.dexscreener.get_token_data(token_address)

        if not dex_data["success"]:
            return dex_data

        result = {
            "success": True,
            "token_address": token_address,
            "sources": ["dexscreener"],
            "data": dex_data,
        }

        # Try to get holder count from Birdeye if API key available
        if include_holders and self.birdeye:
            birdeye_data = await self.birdeye.get_token_overview(token_address)
            if birdeye_data["success"]:
                result["sources"].append("birdeye")
                result["data"]["holder_count"] = birdeye_data["holder_count"]
                result["data"]["birdeye_data"] = birdeye_data

        # Add tracked holder count if available
        tracked_holders = self.holder_tracker.get_holder_count()
        if tracked_holders > 0:
            result["data"]["tracked_holders"] = tracked_holders
            result["sources"].append("websocket_tracking")

        return result


# =============================================================================
# SIMPLE USAGE FUNCTIONS
# =============================================================================


async def get_token_data(
    token_address: str, birdeye_api_key: Optional[str] = None
) -> Dict:
    """
    Simple function to get comprehensive token data.

    Args:
        token_address: Token mint address
        birdeye_api_key: Optional Birdeye API key for holder count

    Returns:
        Token data dictionary
    """
    fetcher = TokenDataFetcher(birdeye_api_key)
    return await fetcher.get_complete_data(token_address)


async def get_price_and_market_cap(token_address: str) -> tuple:
    """
    Get just price and market cap (fastest, no API key needed).

    Returns:
        (price_usd, market_cap) or (None, None) if failed
    """
    data = await DexScreenerAPI.get_token_data(token_address)

    if data["success"]:
        return (data["price_usd"], data["market_cap"])
    else:
        return (None, None)


# =============================================================================
# INTEGRATION FOR YOUR BOT
# =============================================================================


async def fetch_market_data_for_bot(
    token_address: str, birdeye_api_key: Optional[str] = None
) -> Dict:
    """
    Fetch market data formatted for your trading bot.

    Usage in your bot:
        data = await fetch_market_data_for_bot(TOKEN_ADDRESS, BIRDEYE_API_KEY)
        if data["success"]:
            state["last_price"] = data["price_usd"]
            state["last_market_cap"] = data["market_cap_sol"]
            state["last_holder_count"] = data.get("holder_count", "?")
    """
    fetcher = TokenDataFetcher(birdeye_api_key)
    result = await fetcher.get_complete_data(token_address)

    if not result["success"]:
        return result

    data = result["data"]

    # Format for bot compatibility
    return {
        "success": True,
        "price_usd": data["price_usd"],
        "price_sol": data["price_native"],
        "market_cap_usd": data["market_cap"],
        "market_cap_sol": (
            data["market_cap"] / data["price_usd"] * data["price_native"]
            if data["price_usd"] > 0
            else 0
        ),
        "holder_count": data.get("holder_count", data.get("tracked_holders", "?")),
        "liquidity_usd": data["liquidity_usd"],
        "volume_24h": data["volume_24h"],
        "price_change_24h": data["price_change_24h"],
        "txns_24h_buys": data["txns_24h_buys"],
        "txns_24h_sells": data["txns_24h_sells"],
        "dex": data["dex"],
        "sources": result["sources"],
        "raw": data,
    }


# =============================================================================
# EXAMPLES
# =============================================================================


async def example_basic():
    """Example: Basic usage with DexScreener only."""
    print("=" * 60)
    print("BASIC USAGE - DexScreener (No API Key Needed)")
    print("=" * 60)

    data = await DexScreenerAPI.get_token_data(TOKEN_ADDRESS)

    if data["success"]:
        print(f"\n✅ Token: {data['name']} ({data['symbol']})")
        print(f"📊 Price: ${data['price_usd']:.8f}")
        print(f"💰 Market Cap: ${data['market_cap']:,.0f}")
        print(f"💧 Liquidity: ${data['liquidity_usd']:,.0f}")
        print(f"📈 Volume 24h: ${data['volume_24h']:,.0f}")
        print(f"📊 Price Change 24h: {data['price_change_24h']:+.2f}%")
        print(
            f"🔄 Transactions 24h: {data['txns_24h_buys']} buys / {data['txns_24h_sells']} sells"
        )
        print(f"🌐 DEX: {data['dex']}")
        print(f"🔗 URL: {data['url']}")
    else:
        print(f"\n❌ Error: {data['error']}")


async def example_with_holders():
    """Example: With holder count (requires Birdeye API key)."""
    print("\n" + "=" * 60)
    print("WITH HOLDER COUNT - Birdeye API")
    print("=" * 60)

    if not BIRDEYE_API_KEY:
        print("\n⚠️  No BIRDEYE_API_KEY set")
        print(
            "Get free API key at: https://docs.birdeye.so/docs/authentication-api-keys"
        )
        print("Add to .env: BIRDEYE_API_KEY=your_key_here")
        return

    fetcher = TokenDataFetcher(BIRDEYE_API_KEY)
    result = await fetcher.get_complete_data(TOKEN_ADDRESS)

    if result["success"]:
        data = result["data"]
        print(f"\n✅ Data from: {', '.join(result['sources'])}")
        print(f"\nToken: {data['name']} ({data['symbol']})")
        print(f"Price: ${data['price_usd']:.8f}")
        print(f"Market Cap: ${data['market_cap']:,.0f}")

        if "holder_count" in data:
            print(f"👥 Holders: {data['holder_count']:,}")
        else:
            print(f"👥 Holders: Not available (add BIRDEYE_API_KEY)")
    else:
        print(f"\n❌ Error: {result['error']}")


async def example_simple_price():
    """Example: Just get price and market cap (fastest)."""
    print("\n" + "=" * 60)
    print("SIMPLE - Just Price & Market Cap")
    print("=" * 60)

    price, market_cap = await get_price_and_market_cap(TOKEN_ADDRESS)

    if price is not None:
        print(f"\n💵 Price: ${price:.8f}")
        print(f"📊 Market Cap: ${market_cap:,.0f}")
    else:
        print("\n❌ Could not fetch data")


async def example_bot_integration():
    """Example: Bot integration format."""
    print("\n" + "=" * 60)
    print("BOT INTEGRATION FORMAT")
    print("=" * 60)

    data = await fetch_market_data_for_bot(TOKEN_ADDRESS, BIRDEYE_API_KEY)

    if data["success"]:
        print(f"\n✅ Ready for bot integration")
        print(f"Sources: {', '.join(data['sources'])}")
        print(f"\nBot-friendly data:")
        print(f"  price_usd: {data['price_usd']}")
        print(f"  price_sol: {data['price_sol']}")
        print(f"  market_cap_usd: {data['market_cap_usd']}")
        print(f"  market_cap_sol: {data['market_cap_sol']:.2f}")
        print(f"  holder_count: {data['holder_count']}")
        print(f"  liquidity_usd: {data['liquidity_usd']}")
        print(f"  volume_24h: {data['volume_24h']}")
    else:
        print(f"\n❌ Error: {data['error']}")


# =============================================================================
# RUN EXAMPLES
# =============================================================================


async def main():
    if TOKEN_ADDRESS == "YOUR_TOKEN_ADDRESS_HERE":
        print("⚠️  Please set TOKEN_ADDRESS in your .env file!")
        return

    # Basic usage (works without any API keys)
    await example_basic()

    # Simple price check
    await example_simple_price()

    # With holder count (needs Birdeye API key)
    await example_with_holders()

    # Bot integration format
    await example_bot_integration()


if __name__ == "__main__":
    asyncio.run(main())
