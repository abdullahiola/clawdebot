#!/usr/bin/env python3
"""
Test script to fetch market cap, liquidity, and 24hr volume from DexScreener API
Usage: python test_dexscreener.py <solana_token_mint_address>
"""

import sys
import requests
from typing import Dict
import json


def fetch_token_data(mint_address: str) -> Dict:
    """
    Fetch token metrics from DexScreener V1 Solana API
    Returns: dict with market_cap, liquidity, and volume_24h
    """
    url = f"https://api.dexscreener.com/tokens/v1/solana/{mint_address}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    
    # V1 API returns an array of pairs directly, not a {"pairs": [...]} object
    if not isinstance(data, list) or len(data) == 0:
        raise Exception("No trading pairs found for this token")
    
    # Get the first pair (usually the most liquid)
    pair = data[0]
    
    # Extract key metrics
    market_cap_usd = float(pair.get("fdv", 0) or pair.get("marketCap", 0) or 0)
    
    liquidity = pair.get("liquidity", {})
    liquidity_usd = float(liquidity.get("usd", 0) or 0)
    
    volume = pair.get("volume", {})
    volume_24h = float(volume.get("h24", 0) or 0)

    
    price_usd = float(pair.get("priceUsd", 0) or 0)
    price_native = float(pair.get("priceNative", 0) or 0)
    
    # Additional metrics
    price_change_24h = pair.get("priceChange", {}).get("h24", 0)
    dex_name = pair.get("dexId", "Unknown")
    pair_address = pair.get("pairAddress", "")
    
    return {
        "market_cap_usd": market_cap_usd,
        "liquidity_usd": liquidity_usd,
        "volume_24h": volume_24h,
        "price_usd": price_usd,
        "price_native_sol": price_native,
        "price_change_24h": price_change_24h,
        "dex": dex_name,
        "pair_address": pair_address,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_dexscreener.py <solana_token_mint_address>")
        print("\nExample:")
        print("  python test_dexscreener.py EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
        sys.exit(1)
    
    mint_address = sys.argv[1]
    
    print(f"\n🔍 Fetching data for token: {mint_address}\n")
    
    try:
        data = fetch_token_data(mint_address)
        
        print("=" * 60)
        print("TOKEN METRICS")
        print("=" * 60)
        print(f"💰 Market Cap:       ${data['market_cap_usd']:,.2f}")
        print(f"💧 Liquidity:        ${data['liquidity_usd']:,.2f}")
        print(f"📊 24hr Volume:      ${data['volume_24h']:,.2f}")
        print(f"💵 Price (USD):      ${data['price_usd']:.8f}")
        print(f"🪙 Price (SOL):      {data['price_native_sol']:.8f} SOL")
        print(f"📈 24hr Change:      {data['price_change_24h']:.2f}%")
        print(f"🔄 DEX:              {data['dex']}")
        print(f"🔗 Pair Address:     {data['pair_address']}")
        print("=" * 60)
        
        print("\n📄 Raw JSON Response:")
        print(json.dumps(data, indent=2))
        
    except Exception as e:
        print(f"❌ Error fetching token data: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
