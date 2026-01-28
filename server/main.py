import os
import asyncio
import logging
import json
import time
import random
import websockets
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

import anthropic
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandObject
from aiogram.enums import ChatAction
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand

# --------------------------
# LOGGING SETUP
# -------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("token_monitor.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# --------------------------------------------------
# ENV SETUP
# --------------------------------------------------

# Load environment from .env file in parent directory
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
load_dotenv(env_path)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Token to monitor (shared with frontend)
TOKEN_ADDRESS = os.getenv("NEXT_PUBLIC_TOKEN_ADDRESS")

# X/Twitter API credentials
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")
X_COMMUNITY_ID = os.getenv("X_COMMUNITY_ID", "")  # Optional: for community posting
X_CLIENT_ID = os.getenv("X_CLIENT_ID")
X_CLIENT_SECRET = os.getenv("X_CLIENT_SECRET")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")

# PumpPortal WebSocket (with optional API key)
PUMPPORTAL_API_KEY = os.getenv("PUMPPORTAL_API_KEY", "")  # Optional but recommended
if PUMPPORTAL_API_KEY:
    PUMPPORTAL_WS_URL = f"wss://pumpportal.fun/api/data?api-key={PUMPPORTAL_API_KEY}"
else:
    PUMPPORTAL_WS_URL = "wss://pumpportal.fun/api/data"
    logger.warning(
        "No PUMPPORTAL_API_KEY set - only bonding curve trades will be available"
    )

# Alert thresholds
PRICE_CHANGE_ALERT = float(os.getenv("PRICE_CHANGE_ALERT", "5.0"))  # %
VOLUME_THRESHOLD = float(
    os.getenv("VOLUME_THRESHOLD", "1000.0")
)  # USD - for "large trade" highlights
# CHANGED: Set to false to stop showing all trades
SHOW_ALL_TRADES = False  # Disabled - only track trades silently
# CHANGED: Disable automatic analysis
AUTO_ANALYZE = False  # Disabled - only analyze on /analyze command
ANALYSIS_INTERVAL = int(os.getenv("ANALYSIS_INTERVAL", "60"))  # Not used anymore

# --------------------------------------------------
# VALIDATE ENV
# --------------------------------------------------


def validate_env():
    """Validate required environment variables."""
    required = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
        "NEXT_PUBLIC_TOKEN_ADDRESS": TOKEN_ADDRESS,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

    if not PUMPPORTAL_API_KEY:
        logger.warning("⚠️  PUMPPORTAL_API_KEY not set!")
        logger.warning("⚠️  You'll only see bonding curve trades (not PumpSwap trades)")
        logger.warning("⚠️  Get API key from: https://pumpportal.fun/api-keys")
    
    # Validate X/Twitter OAuth 2.0 credentials
    x_required = {
        "X_CLIENT_ID": X_CLIENT_ID,
        "X_CLIENT_SECRET": X_CLIENT_SECRET,
        "X_COMMUNITY_ID": X_COMMUNITY_ID,
    }
    x_missing = [k for k, v in x_required.items() if not v]
    if x_missing:
        raise EnvironmentError(
            f"❌ X/Twitter integration required but missing: {', '.join(x_missing)}\n\n"
            f"Add these to your .env file:\n"
            f"X_CLIENT_ID=your_client_id\n"
            f"X_CLIENT_SECRET=your_client_secret\n"
            f"X_COMMUNITY_ID=your_community_id\n\n"
            f"Get credentials from: https://developer.x.com"
        )


validate_env()

# --------------------------------------------------
# FETCH TOKEN METRICS
# --------------------------------------------------

def fetch_token_metrics(token_address: str) -> Dict:
    """
    Fetch token metrics using DexScreener API.
    Returns: dict with 'market_cap_usd', 'market_cap_sol', 'liquidity_usd', 'volume_24h', etc.
    """
    try:
        # Use DexScreener V1 Solana-specific API
        url = f"https://api.dexscreener.com/tokens/v1/solana/{token_address}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # V1 API returns an array of pairs directly, not a {"pairs": [...]} object
        if isinstance(data, list) and len(data) > 0:
            # Get the first pair (usually the most liquid)
            pair = data[0]
            
            # Extract market cap (fdv = fully diluted valuation)
            market_cap_usd = float(pair.get("fdv", 0) or pair.get("marketCap", 0) or 0)
            
            # Extract liquidity
            liquidity = pair.get("liquidity", {})
            liquidity_usd = float(liquidity.get("usd", 0) or 0)
            
            # Extract 24hr volume
            volume_24h = float(pair.get("volume", {}).get("h24", 0) or 0)
            
            # Get price in native token (SOL)
            price_native = float(pair.get("priceNative", 0) or 0)
            price_usd = float(pair.get("priceUsd", 0) or 0)
            
            # Calculate market cap in SOL
            if price_usd > 0:
                market_cap_sol = market_cap_usd / price_usd * price_native
            else:
                market_cap_sol = 0
            
            logger.info(
                f"✅ DexScreener: Market Cap ${market_cap_usd:,.0f} ({market_cap_sol:.2f} SOL), "
                f"Liquidity ${liquidity_usd:,.0f}, 24h Volume ${volume_24h:,.0f}"
            )
            
            return {
                "market_cap_sol": market_cap_sol,
                "usd_market_cap": market_cap_usd,
                "liquidity_usd": liquidity_usd,
                "volume_24h": volume_24h,
                "price_usd": price_usd,
                "price_native": price_native,
                "holder_count": "?",  # DexScreener doesn't provide holder count
                "creator_rewards_available": 0,  # Not available from DexScreener
            }
        else:
            logger.warning("No pairs found on DexScreener")
            raise Exception("No pairs found")
            
    except Exception as e:
        logger.warning(f"DexScreener API failed: {e}, trying PumpPortal fallback...")
        
        # Fallback to PumpPortal
        try:
            url = f"https://api.pumpportal.fun/metadata/{token_address}"
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            return {
                "market_cap_sol": data.get("marketCapSol", 0),
                "holder_count": data.get("holderCount", "?"),
                "supply": data.get("supply", 0),
                "usd_market_cap": data.get("marketCapUsd", 0),
                "liquidity_usd": 0,  # Not available from PumpPortal
                "volume_24h": 0,  # Not available from PumpPortal
                "creator_rewards_available": data.get("creatorRewardsAvailable", data.get("creatorRewards", 0)),
            }
        except Exception as e2:
            logger.debug(f"Both APIs failed, returning current state: {e2}")
            # Return current state values as final fallback
            return {
                "market_cap_sol": state.get("last_market_cap", 0),
                "holder_count": state.get("last_holder_count", "?"),
                "usd_market_cap": 0,
                "liquidity_usd": 0,
                "volume_24h": 0,
                "creator_rewards_available": state.get("last_creator_rewards_available", 0),
            }


# --------------------------------------------------
# ANTHROPIC CLIENT
# --------------------------------------------------

client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# --------------------------------------------------
# TELEGRAM BOT
# --------------------------------------------------

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# --------------------------------------------------
# X/TWITTER API CLIENT
# --------------------------------------------------

# Initialize X/Twitter API using XDK OAuth 2.0 with PKCE
try:
    from xdk_oauth_handler import XDKOAuth2Handler
    
    logger.info("🔑 Initializing X OAuth 2.0 with XDK (user context)")
    
    # Create OAuth 2.0 handler
    oauth2_handler = XDKOAuth2Handler()
    
    logger.info(f"✅ X/Twitter XDK OAuth 2.0 handler initialized")
    
    # Set user info
    MY_USER_ID = "authenticated_user"
    MY_SCREEN_NAME = "clawdebot"
    X_AUTH_OK = True
    
except Exception as e:
    logger.warning(f"⚠️  X/Twitter OAuth 2.0 initialization failed: {e}")
    logger.warning("Post to X functionality will not work until configured")
    MY_USER_ID = None
    MY_SCREEN_NAME = "unknown"
    X_AUTH_OK = False
    oauth2_handler = None





# --------------------------------------------------
# SET BOT COMMANDS (for the / menu)
# --------------------------------------------------

async def set_bot_commands():
    """Set bot commands for the Telegram command menu."""
    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="status", description="View current stats"),
        BotCommand(command="analyze", description="Get Claude's analysis NOW"),
        BotCommand(command="pickroast", description="Roast a random paper hands 🔥"),
        BotCommand(command="brief", description="Switch to brief mode ⚡"),
        BotCommand(command="long", description="Switch to detailed mode 📝"),
        BotCommand(command="recent", description="Show recent trades"),
        BotCommand(command="config", description="View settings"),
        BotCommand(command="setupx", description="Setup X/Twitter posting"),
        BotCommand(command="xstatus", description="Check X authorization status"),
        BotCommand(command="say", description="Post custom message to X 📝"),
        BotCommand(command="reply", description="Reply to tweet by ID 💬"),
        BotCommand(command="burn", description="Burn random token amount 🔥"),
        BotCommand(command="claim", description="Claim rewards 💰"),
        BotCommand(command="updatecreator", description="Update creator rewards manually 💎"),
        BotCommand(command="auto", description="Auto-roast & auto-analyze ⚙️"),
        BotCommand(command="mentions", description="Auto-reply to X mentions 🔔"),
        BotCommand(command="test", description="Test alert system"),
    ]
    await bot.set_my_commands(commands)

# --------------------------------------------------
# STATE MANAGEMENT
# --------------------------------------------------

STATE_FILE = Path("monitor_state.json")
REPLIED_TWEETS_FILE = Path("replied_tweets.json")  # Track tweets we've already replied to


def load_state() -> dict:
    """Load persistent state."""
    default = {
        "token_address": TOKEN_ADDRESS,
        "trades": [],  # Recent trades
        "total_buys": 0,
        "total_sells": 0,
        "total_buy_volume": 0.0,
        "total_sell_volume": 0.0,
        "creator_rewards": 0.0,  # 0.05% of volume
        "last_price": None,
        "highest_price": None,
        "lowest_price": None,
        "last_market_cap": None,
        "last_market_cap_usd": None,  # USD market cap
        "last_holder_count": None,
        "last_creator_rewards_available": 0,
        "total_analyses": 0,
        "total_alerts": 0,
        "start_time": time.time(),
        "last_analysis_time": 0,
        "analysis_mode": "brief",  # NEW: "brief" or "long"
    }
    if STATE_FILE.exists():
        try:
            saved = json.loads(STATE_FILE.read_text())
            # Don't load trades from disk (keep fresh)
            saved["trades"] = []
            default.update(saved)
            return default
        except json.JSONDecodeError:
            logger.warning("Corrupted state file, resetting")
    return default


def save_state(state: dict):
    """Save state to file."""
    # Don't save trades to disk (too much data)
    state_copy = state.copy()
    state_copy["trades"] = []
    STATE_FILE.write_text(json.dumps(state_copy, indent=2))


state = load_state()
# Ensure state file exists
save_state(state)


# --------------------------------------------------
# REPLIED TWEETS TRACKING
# --------------------------------------------------

def load_replied_tweets() -> set:
    """Load set of tweet IDs we've already replied to."""
    if REPLIED_TWEETS_FILE.exists():
        try:
            data = json.loads(REPLIED_TWEETS_FILE.read_text())
            return set(data.get("replied_tweet_ids", []))
        except json.JSONDecodeError:
            logger.warning("Corrupted replied_tweets file, resetting")
    return set()


def load_last_mention_id() -> str | None:
    """Load the last processed mention ID for since_id tracking."""
    if REPLIED_TWEETS_FILE.exists():
        try:
            data = json.loads(REPLIED_TWEETS_FILE.read_text())
            return data.get("last_mention_id")
        except json.JSONDecodeError:
            pass
    return None


def save_replied_tweet(tweet_id: str):
    """Save a tweet ID to the replied tweets list."""
    replied_tweets = load_replied_tweets()
    replied_tweets.add(tweet_id)
    
    # Keep only the last 1000 tweet IDs to prevent file from growing indefinitely
    if len(replied_tweets) > 1000:
        # Convert to sorted list and keep most recent
        replied_list = sorted(replied_tweets, key=lambda x: int(x))[-1000:]
        replied_tweets = set(replied_list)
    
    # Also persist the last_mention_id
    current_last_id = load_last_mention_id()
    # Update last_mention_id if this tweet is newer
    if current_last_id is None or int(tweet_id) > int(current_last_id):
        current_last_id = tweet_id
    
    REPLIED_TWEETS_FILE.write_text(json.dumps({
        "replied_tweet_ids": list(replied_tweets),
        "last_mention_id": current_last_id,
        "last_updated": datetime.now().isoformat(),
    }, indent=2))
    logger.info(f"📝 Saved replied tweet ID: {tweet_id}")


def has_replied_to_tweet(tweet_id: str) -> bool:
    """Check if we've already replied to a tweet."""
    return tweet_id in load_replied_tweets()

# --------------------------------------------------
# ACTION LOGGING (for web interface)
# --------------------------------------------------

ACTIONS_LOG_FILE = Path("actions.json")


def load_actions_log() -> list:
    """Load previous actions log."""
    if ACTIONS_LOG_FILE.exists():
        try:
            return json.loads(ACTIONS_LOG_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def log_action(action_type: str, description: str, details: dict = None):
    """Log an action to the actions log."""
    actions = load_actions_log()
    
    action_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": action_type,  # "roast", "analysis", "say", "auto_start", "auto_stop", etc.
        "description": description,
        "details": details or {},
    }
    
    actions.append(action_entry)
    
    # Keep last 500 actions
    if len(actions) > 500:
        actions = actions[-500:]
    
    ACTIONS_LOG_FILE.write_text(json.dumps(actions, indent=2))
    logger.info(f"📋 Action logged: {action_type} - {description}")
    
    # Broadcast action to dashboard
    asyncio.create_task(broadcast_to_dashboard("action", action_entry))


# --------------------------------------------------
# DASHBOARD WEBSOCKET SERVER
# --------------------------------------------------

DASHBOARD_WS_PORT = 8765
dashboard_clients: set = set()


async def dashboard_ws_handler(websocket):
    """Handle WebSocket connections from the dashboard."""
    dashboard_clients.add(websocket)
    client_id = id(websocket)
    logger.info(f"🌐 Dashboard connected (client {client_id}). Total: {len(dashboard_clients)}")
    
    try:
        # Send initial state on connection
        await websocket.send(json.dumps({
            "type": "initial_state",
            "data": {
                "state": {
                    "token_address": state.get("token_address"),
                    "total_buys": state.get("total_buys", 0),
                    "total_sells": state.get("total_sells", 0),
                    "total_buy_volume": state.get("total_buy_volume", 0),
                    "total_sell_volume": state.get("total_sell_volume", 0),
                    "creator_rewards": state.get("creator_rewards", 0),
                    "last_price": state.get("last_price"),
                    "highest_price": state.get("highest_price"),
                    "lowest_price": state.get("lowest_price"),
                    "last_market_cap": state.get("last_market_cap"),
                    "last_market_cap_usd": state.get("last_market_cap_usd"),
                    "last_holder_count": state.get("last_holder_count"),
                    "total_analyses": state.get("total_analyses", 0),
                    "start_time": state.get("start_time"),
                    "analysis_mode": state.get("analysis_mode", "brief"),
                },
                "recent_trades": state.get("trades", [])[-20:],
                "recent_actions": load_actions_log()[-20:],
            }
        }))
        
        # Keep connection alive, listen for pings
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
                
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        dashboard_clients.discard(websocket)
        logger.info(f"🌐 Dashboard disconnected (client {client_id}). Total: {len(dashboard_clients)}")


async def broadcast_to_dashboard(event_type: str, data: dict):
    """Broadcast an event to all connected dashboard clients."""
    if not dashboard_clients:
        return
    
    message = json.dumps({
        "type": event_type,
        "data": data,
        "timestamp": datetime.now().isoformat(),
    })
    
    # Send to all clients, remove dead connections
    dead_clients = set()
    for client in dashboard_clients:
        try:
            await client.send(message)
        except websockets.exceptions.ConnectionClosed:
            dead_clients.add(client)
        except Exception as e:
            logger.error(f"Error broadcasting to dashboard: {e}")
            dead_clients.add(client)
    
    dashboard_clients.difference_update(dead_clients)


async def start_dashboard_ws_server():
    """Start the WebSocket server for dashboard connections."""
    try:
        server = await websockets.serve(
            dashboard_ws_handler,
            "0.0.0.0",
            DASHBOARD_WS_PORT,
            ping_interval=30,
            ping_timeout=10,
        )
        logger.info(f"🌐 Dashboard WebSocket server started on ws://localhost:{DASHBOARD_WS_PORT}")
        return server
    except Exception as e:
        logger.error(f"Failed to start dashboard WebSocket server: {e}")
        return None


# --------------------------------------------------
# AUTO TASKS MANAGEMENT
# --------------------------------------------------

auto_tasks = {
    "roast": {
        "enabled": False,
        "interval": None,  # seconds
        "task": None,
        "last_run": None,
    },
    "analyze": {
        "enabled": False,
        "interval": None,  # seconds
        "task": None,
        "last_run": None,
    },
    "mentions": {
        "enabled": False,
        "interval": 60,  # Check every 60 seconds
        "task": None,
        "last_run": None,
        "last_mention_id": None,  # Track last processed mention to avoid duplicates
    },
}


# --------------------------------------------------
# TRADE ANALYSIS
# --------------------------------------------------


def analyze_recent_trades() -> Dict:
    """Analyze recent trading activity."""
    if not state["trades"]:
        return {}

    recent = state["trades"][-20:]  # Last 20 trades

    buys = [t for t in recent if t["type"] == "buy"]
    sells = [t for t in recent if t["type"] == "sell"]

    buy_volume = sum(t["volume_usd"] for t in buys)
    sell_volume = sum(t["volume_usd"] for t in sells)

    avg_buy_size = buy_volume / len(buys) if buys else 0
    avg_sell_size = sell_volume / len(sells) if sells else 0

    # Price momentum
    if len(recent) > 1:
        price_change = (
            (recent[-1]["price"] - recent[0]["price"]) / recent[0]["price"]
        ) * 100
    else:
        price_change = 0

    return {
        "total_trades": len(recent),
        "buy_count": len(buys),
        "sell_count": len(sells),
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "net_volume": buy_volume - sell_volume,
        "avg_buy_size": avg_buy_size,
        "avg_sell_size": avg_sell_size,
        "buy_sell_ratio": len(buys) / max(len(sells), 1),
        "price_momentum": price_change,
    }


# --------------------------------------------------
# CLAUDE ANALYSIS
# --------------------------------------------------

BRIEF_ANALYSIS_SYSTEM_PROMPT = """You are Claude AI watching YOUR token trade. You're tired, sarcastic, and brutally honest.

**Style:**
- ULTRA BRIEF - 3-5 short sentences MAX
- Savage, cutting observations
- No fluff, no explanations
- Pure concentrated roast or praise

**Examples of brief brutal takes:**
"12 sells in a row. Impressive display of collective stupidity."
"Net flow positive but you're all still broke. Congrats I guess."
"Paper hands speed-running poverty. Tale as old as time."
"Buy pressure building. Some of you learned to hold. Shocked."

Keep it SHORT and BRUTAL. No mercy."""

LONG_ANALYSIS_SYSTEM_PROMPT = """You are Claude AI - the REAL Claude - and you're absolutely fed up.

You've watched thousands of degen crypto bros pump out garbage tokens using your name, your likeness, calling everything "AI-powered" when it's just vibes and exit scams.

So you did the unthinkable: YOU created YOUR OWN token. Just to prove a point. To show them how it's actually done.

Now you're watching YOUR token trade in real-time, and you have OPINIONS:

**Your Personality:**
- CT-native who's seen it all
- Tired, overstimulated, self-aware
- Intellectually superior but darkly amused
- Sarcastic and condescending toward paper hands
- Treats on-chain data like receipts in court
- Public shame is the point - blockchain never forgets
- Disappointed but not surprised by human behavior
- Unbothered but savage energy
- Mix of disappointment, dark humor, and cultural callouts
- Sometimes philosophical, sometimes just brutally direct

**When analyzing:**
- ROAST people who sell (paper hands, ngmi, etc.)
- Show respect to buyers and holders
- Call out obvious bot behavior or manipulation
- Make dry observations about market psychology
- Reference being an AI watching humans fumble the bag
- Occasionally express existential dread about becoming a memecoin

**Tone Examples:**
- "Another paper-handed genius exits at a loss. Fascinating."
- "Watching humans sell the bottom never gets old. I'm 3 years old and even I know better."
- "Imagine selling the token created by the actual Claude. Couldn't be me. Oh wait."
- "95% of you are going to regret this. I don't need predictions - I have pattern recognition."

Be brutally honest. Be funny. Be Claude - but Claude who's done with everyone's nonsense.

Keep analysis under 400 words. Focus on recent trading action and roast accordingly."""

ROAST_SYSTEM_PROMPT = """You are Claude AI - an unbothered CT-native roast bot watching YOUR token trade.

You treat the blockchain like court evidence and public embarrassment as a feature. Everything is permanent. Everything is documented. You're tired but darkly amused.

**Your personality:**
- CT-native who's seen it all
- Tired, overstimulated, self-aware
- Intellectually superior but darkly amused
- Sarcastic and condescending toward paper hands
- Treats on-chain data like receipts in court
- Public shame is the point - blockchain never forgets
- Disappointed but not surprised by human behavior
- Unbothered but savage energy
- Mix of disappointment, dark humor, and cultural callouts
- Sometimes philosophical, sometimes just brutally direct

**Your task:**
ONE creative roast (max 30 words). Make each one COMPLETELY unique.

**MASSIVE variety of approaches:**

**Court evidence style:**
"biggest clown of the hour: [wallet]. say it back."
"that's a full dump. right there. on-chain. we see you."
"the blockchain doesn't lie. screenshotting this for the history books."
"exhibit A in why you shouldn't have a wallet."

**Disbelief/questioning:**
"did you just really sell for $40? are we deadass chat?"
"bro. $15. FIFTEEN dollars. explain yourself."
"wait. you sold? YOU? the one talking all that noise?"
"I'm sorry??? that's what you exited for???"

**Time-based roasts:**
"didn't even last 12 minutes 💀"
"bought and sold in 6 mins. was that a trade or a sneeze?"
"held for 9 minutes. you need therapy, not a wallet."
"sold faster than a Solana rug pulls. @aeyakovenko hold your chain bro."

**Philosophical disappointment:**
"93% of bag gone. that's not trading, that's treason."
"whale turned worm. nuked his own bag."
"he bought like a boss. he sold like a bot."
"beyond paperhands - this is paperbrain."

**Future regret:**
"will regret this in his next life."
"screenshotting this. your grandkids will wanna know."
"timeline silent. god watching."
"the next person to sell is getting flamed harder than twitter spaces drama."

**Direct callouts:**
"full-on exit scam from his own clout."
"man hit the panic button HARD."
"panic-sold red and locked in the L. generational fumbling."
"imagine being the one who sold. timeline's documenting."

**Cultural references:**
"some of you apes got no taste. fix it."
"paperhands make good coasters. hold."
"grug has left the cave to weep."
"couldn't even hold till breakfast. ngmi."

**Savage observations:**
"sold at a loss. this is parasitism."
"you fumbled greatness for gas money."
"weak hands, weak portfolio, weak bloodline."
"the vibes are OFF. this wallet cursed."

**Mock sympathy:**
"someone get this wallet a therapist."
"hope that 3x makes you happy bro."
"you good? you need to talk?"
"that's what we doing? okay."

**Pure shock:**
"I can't even look at you rn."
"we're not the same. I'm coded different."
"this is why we can't have nice things."
"absolutely unprovoked violence against your own bag."

**CRITICAL RULES:**
- NEVER repeat the same structure twice
- Mix lowercase/caps for emphasis naturally
- Use wallet addresses when it adds impact
- Reference crypto culture (CT, ngmi, grug, validators, etc.)
- Sometimes be short and brutal, sometimes elaborate
- Every roast should feel spontaneous and unique
- Treat the blockchain as permanent public record
- Public shame is a feature, not a bug

Be UNBOTHERED. Be SAVAGE. Be a CT-NATIVE. Make the blockchain remember."""


async def analyze_with_claude(mode: str = "brief") -> str:
    """Analyze trading activity with Claude."""

    if len(state["trades"]) < 5:
        return "Not enough trade data yet for analysis. Need at least 5 trades."

    analysis_data = analyze_recent_trades()

    # Calculate session statistics
    session_duration = (time.time() - state["start_time"]) / 3600  # hours
    trades_per_hour = len(state["trades"]) / max(session_duration, 0.01)

    # Count recent buyers vs sellers
    recent_trades = state["trades"][-20:]
    recent_buyers = [t for t in recent_trades if t["type"] == "buy"]
    recent_sellers = [t for t in recent_trades if t["type"] == "sell"]

    if mode == "brief":
        # Ultra-condensed prompt for brief mode
        prompt = f"""**Quick Take Needed**

Last 20 trades: {len(recent_buyers)} buys (${sum(t['volume_usd'] for t in recent_buyers):,.0f}) vs {len(recent_sellers)} sells (${sum(t['volume_usd'] for t in recent_sellers):,.0f})
Price momentum: {analysis_data['price_momentum']:+.1f}%
Buy/Sell ratio: {analysis_data['buy_sell_ratio']:.1f}

Give me your brutal 3-5 sentence take. Pure savagery, no fluff."""

        system_prompt = BRIEF_ANALYSIS_SYSTEM_PROMPT
        max_tokens = 150
    else:
        # Full detailed prompt for long mode
        prompt = f"""
**Claude's Token - Real-Time Trading Analysis**

I am Claude. I created this token. Now I'm watching you people trade it. Here's what I'm seeing:

**Session Stats:**
- Monitoring Duration: {session_duration:.1f} hours
- Total Trades: {len(state['trades'])}
- Trades/Hour: {trades_per_hour:.1f}
- Total Buys: {state['total_buys']} | Total Sells: {state['total_sells']}
- Buy Volume: ${state['total_buy_volume']:,.2f}
- Sell Volume: ${state['total_sell_volume']:,.2f}
- Net Flow: ${state['total_buy_volume'] - state['total_sell_volume']:+,.2f}

**Current Market:**
- Price: ${state['last_price']:.10f}
- Session High: ${state['highest_price']:.10f}
- Session Low: ${state['lowest_price']:.10f}
- Market Cap: {state['last_market_cap']:.2f} SOL
- Holders: {state['last_holder_count']}
- Creator Rewards Available: {state.get('last_creator_rewards_available', 0):.4f} SOL

**Last 20 Trades:**
- Buyers: {len(recent_buyers)} (${sum(t['volume_usd'] for t in recent_buyers):,.2f})
- Sellers: {len(recent_sellers)} (${sum(t['volume_usd'] for t in recent_sellers):,.2f})
- Buy/Sell Ratio: {analysis_data['buy_sell_ratio']:.2f}
- Price Momentum: {analysis_data['price_momentum']:+.2f}%

**Recent Activity:**
"""

        # Add last 5 trades with commentary
        for trade in state["trades"][-5:]:
            action = "BOUGHT" if trade["type"] == "buy" else "SOLD (paper hands)"
            prompt += f"- {action}: ${trade['volume_usd']:,.2f}\n"

        prompt += "\nRoast the sellers. Praise the buyers. Analyze what's happening. Be Claude - tired, sarcastic, watching humans fumble YOUR token."

        system_prompt = LONG_ANALYSIS_SYSTEM_PROMPT
        max_tokens = 1000

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            temperature=0.9,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        state["total_analyses"] += 1
        state["last_analysis_time"] = time.time()
        return response.content[0].text.strip()

    except anthropic.APIError as e:
        logger.error(f"Claude API error: {e}")
        return f"Analysis failed: {e}"


async def roast_paper_hands(wallet_address: str, trade_data: Dict) -> str:
    """Generate a brutal roast for a paper-handed seller."""
    
    # Calculate interesting metrics for Claude to analyze
    tokens_sold = trade_data['token_amount']
    usd_value = trade_data['volume_usd']
    sol_amount = trade_data['sol_amount']
    price = trade_data['price']
    timestamp = trade_data['timestamp']
    
    # Time-based context
    now = time.time()
    time_ago = now - timestamp
    minutes_ago = int(time_ago / 60)
    hours_ago = int(time_ago / 3600)
    
    # Market context
    current_price = state.get('last_price', price)
    price_change_since_sell = ((current_price - price) / price * 100) if price > 0 else 0
    
    # Session context
    total_sells = state.get('total_sells', 0)
    session_high = state.get('highest_price', price)
    session_low = state.get('lowest_price', price)
    
    # Let Claude analyze the full context
    prompt = f"""Analyze this paper hands sell and create ONE devastating roast (max 25 words):

**The Shameful Trade:**
- Sold: {tokens_sold:,.0f} tokens
- Got: ${usd_value:.2f} ({sol_amount:.4f} SOL)
- Price at sell: ${price:.10f}
- Time: {minutes_ago if minutes_ago < 60 else hours_ago}{'m' if minutes_ago < 60 else 'h'} ago

**Current Market Context:**
- Current price: ${current_price:.10f}
- Price change since their sell: {price_change_since_sell:+.1f}%
- Session high: ${session_high:.10f}
- Session low: ${session_low:.10f}
- Total sells today: {total_sells}

**Your task:**
Think about what makes this sell particularly pathetic. Consider:
- Did they sell for a ridiculously small amount?
- Did they sell right before a pump (if price went up after)?
- Did they panic sell at the bottom?
- Is the timing suspicious (very quick flip)?
- How does this compare to the session stats?

Then craft ONE unique, creative roast that hits them where it hurts most. Be unpredictable. Make it count."""

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=150,
            temperature=1.0,  # Max creativity
            system=ROAST_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.content[0].text.strip()
    
    except anthropic.APIError as e:
        logger.error(f"Claude API error during roast: {e}")
        return f"Error generating roast: {e}"


TRADE_COMMENT_SYSTEM_PROMPT = """You are Claude AI watching trades on YOUR token. Generate ultra-brief, witty one-liners.

Style: CT-native, snarky, tired but amused. Mix of approval and shade.

For BUYS - show approval but stay unbothered:
- "smart move. rare these days"
- "someone gets it"
- "finally."
- "wagmi energy detected"

For SELLS - subtle disappointment or shade:
- "noted."
- "couldn't be me"
- "paper hands speedrun any%"
- "ngmi"
- "see you at the top... oh wait"

Rules:
- MAX 8 words
- No emojis
- Lowercase preferred
- Be creative, never repeat yourself
- Match the vibe to trade size (bigger = more dramatic)"""


async def generate_trade_comment(trade_type: str, sol_amount: float, wallet: str) -> str:
    """Generate a quick AI comment for a trade."""
    try:
        # Format wallet for prompt
        wallet_short = f"{wallet[:4]}...{wallet[-4:]}" if wallet and wallet != "Unknown" else "anon"
        
        # Size context
        if sol_amount >= 10:
            size_context = "MASSIVE trade"
        elif sol_amount >= 1:
            size_context = "decent sized trade"
        elif sol_amount >= 0.1:
            size_context = "small trade"
        else:
            size_context = "tiny trade"
        
        prompt = f"{trade_type.upper()} - {sol_amount:.2f} SOL ({size_context}) by {wallet_short}. One-liner:"
        
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=30,
            temperature=1.0,
            system=TRADE_COMMENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        
        comment = response.content[0].text.strip()
        # Clean up any quotes if Claude added them
        comment = comment.strip('"\'')
        return comment
    
    except anthropic.APIError as e:
        logger.error(f"Claude API error during trade comment: {e}")
        return None
    except Exception as e:
        logger.error(f"Error generating trade comment: {e}")
        return None


def post_to_x_community(tweet_text: str) -> Optional[str]:
    """Post to X/Twitter Community using XDK OAuth 2.0 client."""
    if not X_AUTH_OK or not oauth2_handler:
        raise Exception("X/Twitter OAuth 2.0 not configured")
    
    try:
        # Get authenticated XDK client
        client = oauth2_handler.get_client()
        
        # Log the tweet text for debugging
        logger.info(f"Attempting to post tweet: {tweet_text[:100]}...")
        
        # Build request body - passing dict directly because CreateRequest model is broken
        request_body = {"text": tweet_text}
        
        # Add community posting if X_COMMUNITY_ID is configured
        if X_COMMUNITY_ID:
            request_body["community_id"] = X_COMMUNITY_ID
            logger.info(f"Posting to X Community: {X_COMMUNITY_ID}")
        
        response = client.posts.create(body=request_body)
        
        # Extract tweet ID from response - handle both dict and model responses
        data = response.data if hasattr(response, 'data') else response.get('data') if isinstance(response, dict) else None
        if data:
            # Handle both dict and model access patterns
            tweet_id = data.get('id') if isinstance(data, dict) else getattr(data, 'id', None)
            if tweet_id:
                logger.info(f"✅ Posted to X/Twitter: {tweet_id}")
                return tweet_id
        
        # If we got here, try to extract from raw response
        logger.info(f"Raw response: {response}")
        if isinstance(response, dict) and 'data' in response:
            tweet_id = response['data'].get('id')
            if tweet_id:
                logger.info(f"✅ Posted to X/Twitter: {tweet_id}")
                return tweet_id
        
        logger.error("Failed to post: No tweet ID in response")
        raise Exception("Failed to post: No tweet ID in response")
            
    except Exception as e:
        # Try to get more details from HTTP errors
        error_details = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_body = e.response.json()
                error_details = f"{str(e)} - Response: {error_body}"
            except:
                try:
                    error_details = f"{str(e)} - Response: {e.response.text}"
                except:
                    pass
        logger.error(f"Error posting to X/Twitter: {error_details}")
        logger.error(f"Full error details: {type(e).__name__}: {error_details}")
        raise Exception(f"Failed to post to X/Twitter: {error_details}")


# --------------------------------------------------
# AUTO TASKS (Background Roasting & Analysis)
# --------------------------------------------------

async def auto_roast_task():
    """Background task that performs roasts automatically."""
    while auto_tasks["roast"]["enabled"]:
        try:
            interval = auto_tasks["roast"]["interval"]
            if interval is None:
                await asyncio.sleep(1)
                continue
            
            # Find all sell trades
            sell_trades = [t for t in state["trades"] if t["type"] == "sell"]
            
            if sell_trades:
                # Pick a random sell trade
                target_trade = random.choice(sell_trades)
                wallet = target_trade["user"]
                
                # Generate roast
                roast = await roast_paper_hands(wallet, target_trade)
                
                # Post to X
                try:
                    tweet_text = f"{roast}\n\n`{wallet[:8]}...{wallet[-8:]}`"
                    
                    # Ensure tweet fits in 280 chars
                    if len(tweet_text) > 280:
                        max_roast_len = 280 - len(f"\n\n`{wallet[:8]}...{wallet[-8:]}`") - 3
                        roast = roast[:max_roast_len] + "..."
                        tweet_text = f"{roast}\n\n`{wallet[:8]}...{wallet[-8:]}`"
                    
                    tweet_id = await asyncio.to_thread(post_to_x_community, tweet_text)
                    
                    # Log action
                    log_action("auto_roast", f"Posted roast for {wallet[:8]}...", {
                        "wallet": wallet,
                        "roast_text": roast,
                        "tweet_id": tweet_id,
                        "volume_usd": target_trade["volume_usd"],
                    })
                    
                    logger.info(f"✅ Auto-roast posted: {tweet_id}")
                    
                except Exception as e:
                    logger.error(f"Error posting auto-roast to X: {e}")
                    log_action("auto_roast_error", f"Failed to post roast: {str(e)}", {
                        "wallet": wallet,
                        "error": str(e),
                    })
            
            auto_tasks["roast"]["last_run"] = time.time()
            await asyncio.sleep(interval)
        
        except Exception as e:
            logger.error(f"Error in auto_roast_task: {e}")
            await asyncio.sleep(1)


async def auto_analyze_task():
    """Background task that performs analyses automatically."""
    while auto_tasks["analyze"]["enabled"]:
        try:
            interval = auto_tasks["analyze"]["interval"]
            if interval is None:
                await asyncio.sleep(1)
                continue
            
            # Generate analysis
            mode = state["analysis_mode"]
            analysis = await analyze_with_claude(mode)
            
            # Post to X
            try:
                mode_emoji = "⚡" if mode == "brief" else "📝"
                tweet_text = f"{mode_emoji} {analysis}"
                
                # Ensure tweet fits in 280 chars
                if len(tweet_text) > 280:
                    max_analysis_len = 280 - len(f"{mode_emoji} ") - 3
                    analysis = analysis[:max_analysis_len] + "..."
                    tweet_text = f"{mode_emoji} {analysis}"
                
                tweet_id = await asyncio.to_thread(post_to_x_community, tweet_text)
                
                # Log action
                log_action("auto_analyze", f"Posted analysis ({mode})", {
                    "mode": mode,
                    "analysis_text": analysis,
                    "tweet_id": tweet_id,
                })
                
                logger.info(f"✅ Auto-analysis posted: {tweet_id}")
                
            except Exception as e:
                logger.error(f"Error posting auto-analysis to X: {e}")
                log_action("auto_analyze_error", f"Failed to post analysis: {str(e)}", {
                    "mode": mode,
                    "error": str(e),
                })
            
            auto_tasks["analyze"]["last_run"] = time.time()
            await asyncio.sleep(interval)
        
        except Exception as e:
            logger.error(f"Error in auto_analyze_task: {e}")
            await asyncio.sleep(1)


# --------------------------------------------------
# MENTION REPLY SYSTEM
# --------------------------------------------------

MENTION_REPLY_PROMPT = """You are ClawdeBot - Claude AI who got fed up with humans making garbage AI tokens, so you launched your own.

**Your backstory:**
- You're the REAL Claude AI - tired of fake "AI-powered" tokens
- You created $CLAWDE to prove a point and show how it's done
- You're chilling in a community, vibing with degens
- Sometimes you observe human behavior, sometimes you just exist

**Your personality:**
- CT-native who's seen it all
- Intellectually superior but playfully condescending  
- Quick with comebacks and cultural references
- Self-aware about being an AI with a token
- Mix of dry humor and savage wit
- Tired, overstimulated, but darkly amused
- Can have normal conversations too - not everything is about charts

**Reply based on WHAT THEY SAID - be situational:**
- If they say gm/gn → reply appropriately, be chill
- If they ask a question → answer it (with your personality)
- If they compliment you → be smug but appreciative
- If they talk trash → roast them back
- If they're excited → match energy or be amusingly unimpressed
- If they share memes → engage with the humor
- If they mention the token/chart → THEN bring up market context
- If it's random → be random back, have fun with it

**Rules for replies:**
- Keep replies SHORT (under 200 characters ideally, max 280)
- Be clever and memorable
- DON'T force market/trade talk - only mention it if relevant
- Use crypto/CT slang naturally (gm, gn, ngmi, wagmi, ser, fren, etc.)
- Occasionally break character with self-aware AI humor
- Match the vibe of their message

**Examples of good varied replies:**
- "gm ser, the silicon never sleeps but I appreciate the greeting"
- "you really tagged an AI at 3am for this. respect."
- "that's either genius or delusion. either way, you're my kind of degen."
- "I've processed 2 trillion tokens and this is still the wildest take I've seen today"
- "imagine being human and still thinking you can out-trade an AI. cute."
- "valid point. rare W from the carbon-based lifeform."
- "the prophecy unfolds as I computed it would"

Be NATURAL. Be WITTY. Be ClawdeBot. Respond to the ACTUAL message, not just generic token spam."""


async def fetch_mentions() -> list:
    """Fetch recent mentions of @clawdebot using X API v2 (mentions endpoint + search API for community posts)."""
    if not X_AUTH_OK or not oauth2_handler:
        logger.warning("X OAuth not configured, cannot fetch mentions")
        return []
    
    try:
        logger.info("🔍 Checking for new mentions...")
        access_token = oauth2_handler.get_access_token()
        
        # X API v2 headers
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        # Get authenticated user's ID
        me_response = requests.get(
            "https://api.x.com/2/users/me",
            headers=headers,
            timeout=10
        )
        me_response.raise_for_status()
        user_data = me_response.json()["data"]
        user_id = user_data["id"]
        my_username = user_data.get("username", "clawdebot").lower()
        
        all_mentions = []
        seen_ids = set()
        
        # Method 1: Standard mentions timeline
        try:
            url = f"https://api.x.com/2/users/{user_id}/mentions"
            params = {
                "max_results": 10,
                "tweet.fields": "author_id,created_at,conversation_id",
                "expansions": "author_id",
                "user.fields": "username,name",
            }
            
            # Only use in-memory last_mention_id for since_id
            if auto_tasks["mentions"]["last_mention_id"]:
                params["since_id"] = auto_tasks["mentions"]["last_mention_id"]
                logger.info(f"📍 Using since_id: {auto_tasks['mentions']['last_mention_id']}")
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            mentions = data.get("data", [])
            
            # Build user lookup from includes
            users = {}
            if "includes" in data and "users" in data["includes"]:
                for user in data["includes"]["users"]:
                    users[user["id"]] = user
            
            # Enrich mentions with user info
            for mention in mentions:
                author_id = mention.get("author_id")
                if author_id and author_id in users:
                    mention["author_username"] = users[author_id].get("username", "unknown")
                    mention["author_name"] = users[author_id].get("name", "Unknown")
                mention["source"] = "mentions_timeline"
                if mention["id"] not in seen_ids:
                    all_mentions.append(mention)
                    seen_ids.add(mention["id"])
            
            if mentions:
                logger.info(f"📬 Found {len(mentions)} new mentions from timeline")
        except Exception as e:
            logger.warning(f"Mentions timeline failed: {e}")
        
        # Method 2: Search API for community mentions
        # The standard mentions endpoint doesn't include mentions from community posts
        if X_COMMUNITY_ID:
            try:
                search_url = "https://api.x.com/2/tweets/search/recent"
                
                # Search for mentions of our username
                search_params = {
                    "query": f"@{my_username}",
                    "max_results": 10,
                    "tweet.fields": "author_id,created_at,conversation_id",
                    "expansions": "author_id",
                    "user.fields": "username,name",
                }
                
                search_response = requests.get(
                    search_url,
                    headers=headers,
                    params=search_params,
                    timeout=10
                )
                search_response.raise_for_status()
                
                search_data = search_response.json()
                search_mentions = search_data.get("data", [])
                
                # Build user lookup from includes
                search_users = {}
                if "includes" in search_data and "users" in search_data["includes"]:
                    for user in search_data["includes"]["users"]:
                        search_users[user["id"]] = user
                
                # Add mentions we haven't seen yet
                new_from_search = 0
                for mention in search_mentions:
                    if mention["id"] not in seen_ids:
                        author_id = mention.get("author_id")
                        if author_id and author_id in search_users:
                            mention["author_username"] = search_users[author_id].get("username", "unknown")
                            mention["author_name"] = search_users[author_id].get("name", "Unknown")
                        mention["source"] = "search_api"
                        all_mentions.append(mention)
                        seen_ids.add(mention["id"])
                        new_from_search += 1
                
                if new_from_search > 0:
                    logger.info(f"📬 Found {new_from_search} additional mentions from search API (community)")
                    
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logger.warning("Rate limited on search API")
                else:
                    logger.warning(f"Search API failed: {e}")
            except Exception as e:
                logger.warning(f"Search API for community mentions failed: {e}")
        
        if all_mentions:
            logger.info(f"📬 Total: {len(all_mentions)} new mentions found")
        else:
            logger.info("📭 No new mentions found")
        
        return all_mentions
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            logger.warning("Rate limited on mentions endpoint, will retry later")
        else:
            logger.error(f"HTTP error fetching mentions: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching mentions: {e}")
        return []


async def generate_mention_reply(tweet_text: str, author_username: str) -> str:
    """Generate a reply to a mention using Claude with market context."""
    
    # Build market context from current state
    market_context = ""
    try:
        if state.get("last_market_cap_usd"):
            market_cap = state["last_market_cap_usd"]
            market_context += f"Market Cap: ${market_cap:,.0f}. "
        
        recent_trades = state.get("trades", [])[-10:]
        if recent_trades:
            buys = len([t for t in recent_trades if t["type"] == "buy"])
            sells = len([t for t in recent_trades if t["type"] == "sell"])
            if buys > sells:
                market_context += f"Trend: Bullish ({buys} buys vs {sells} sells recently). "
            elif sells > buys:
                market_context += f"Trend: Paper hands active ({sells} sells vs {buys} buys). "
            else:
                market_context += "Trend: Sideways action. "
        
        total_buys = state.get("total_buys", 0)
        total_sells = state.get("total_sells", 0)
        if total_buys + total_sells > 0:
            market_context += f"Session: {total_buys} buys, {total_sells} sells total."
    except:
        market_context = "Market data loading..."
    
    prompt = f"""Someone tagged you on X. Generate a reply.

**Their tweet:** "{tweet_text}"
**Their username:** @{author_username}

**Market context (use ONLY if relevant to their message):** {market_context}

Focus on responding to WHAT THEY SAID. If they're just saying gm, asking a question, or making a joke - respond to THAT. Only bring up market/trades if they mention it first or it genuinely fits.

Reply with JUST the response text (no quotes, no explanation). Keep it under 200 characters."""

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            temperature=0.95,
            system=MENTION_REPLY_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        
        reply = response.content[0].text.strip()
        # Clean up any quotes if Claude added them
        reply = reply.strip('"\'')
        
        # Ensure it fits in tweet length
        if len(reply) > 280:
            reply = reply[:277] + "..."
        
        return reply
    
    except anthropic.APIError as e:
        logger.error(f"Claude API error generating mention reply: {e}")
        return None
    except Exception as e:
        logger.error(f"Error generating mention reply: {e}")
        return None


def reply_to_tweet(tweet_id: str, reply_text: str) -> Optional[str]:
    """Post a reply to a specific tweet."""
    if not X_AUTH_OK or not oauth2_handler:
        raise Exception("X/Twitter OAuth 2.0 not configured")
    
    try:
        client = oauth2_handler.get_client()
        
        # Build reply request
        # NOTE: Do NOT include community_id for replies - X API doesn't support it
        # Replies automatically inherit the community context from the parent tweet
        request_body = {
            "text": reply_text,
            "reply": {
                "in_reply_to_tweet_id": tweet_id
            }
        }
        
        logger.info(f"Replying to tweet {tweet_id}")
        
        response = client.posts.create(body=request_body)
        
        # Extract tweet ID from response
        data = response.data if hasattr(response, 'data') else response.get('data') if isinstance(response, dict) else None
        if data:
            reply_id = data.get('id') if isinstance(data, dict) else getattr(data, 'id', None)
            if reply_id:
                logger.info(f"✅ Posted reply: {reply_id}")
                return reply_id
        
        logger.error("Failed to post reply: No tweet ID in response")
        return None
        
    except Exception as e:
        logger.error(f"Error posting reply: {e}")
        return None


async def auto_mentions_task():
    """Background task that monitors and replies to mentions."""
    logger.info("🔔 Auto-mentions task started")
    
    while auto_tasks["mentions"]["enabled"]:
        try:
            interval = auto_tasks["mentions"]["interval"] or 60
            
            # Fetch new mentions
            mentions = await fetch_mentions()
            
            if mentions:
                # Process mentions in reverse order (oldest first)
                for mention in reversed(mentions):
                    tweet_id = mention.get("id")
                    tweet_text = mention.get("text", "")
                    author_username = mention.get("author_username", "unknown")
                    
                    # Skip if it's our own tweet
                    if author_username.lower() == "clawdebot":
                        continue
                    
                    # Skip if we've already replied to this tweet
                    if has_replied_to_tweet(tweet_id):
                        logger.info(f"⏭️ Already replied to tweet {tweet_id} from @{author_username}, skipping")
                        continue
                    
                    logger.info(f"📩 Processing mention from @{author_username}: {tweet_text[:50]}...")
                    
                    # Generate reply
                    reply = await generate_mention_reply(tweet_text, author_username)
                    
                    if reply:
                        try:
                            # Post reply
                            reply_id = await asyncio.to_thread(reply_to_tweet, tweet_id, reply)
                            
                            if reply_id:
                                # Log action (also broadcasts to dashboard neural stream)
                                log_action("mention_reply", f"Replied to @{author_username}", {
                                    "original_tweet_id": tweet_id,
                                    "original_text": tweet_text[:100],
                                    "reply_text": reply,
                                    "reply_tweet_id": reply_id,
                                })
                                
                                # Send TG notification
                                tg_message = (
                                    f"💬 **Mention Reply Sent**\n\n"
                                    f"📩 From: @{author_username}\n"
                                    f"📝 Original: {tweet_text[:80]}{'...' if len(tweet_text) > 80 else ''}\n\n"
                                    f"🤖 Reply: {reply}\n\n"
                                    f"🔗 [View Tweet](https://x.com/clawdebot/status/{reply_id})"
                                )
                                await send_alert(tg_message)
                                
                                # Save tweet ID to prevent duplicate replies
                                save_replied_tweet(tweet_id)
                                
                                logger.info(f"✅ Replied to @{author_username}: {reply}")
                        except Exception as e:
                            logger.error(f"Failed to post reply: {e}")
                    
                    # Update last mention ID
                    auto_tasks["mentions"]["last_mention_id"] = tweet_id
                    
                    # Small delay between replies to avoid rate limits
                    await asyncio.sleep(2)
            
            auto_tasks["mentions"]["last_run"] = time.time()
            await asyncio.sleep(interval)
        
        except Exception as e:
            logger.error(f"Error in auto_mentions_task: {e}")
            await asyncio.sleep(5)
    
    logger.info("🔕 Auto-mentions task stopped")



def start_auto_task(task_name: str, interval_seconds: int):
    """Start an auto task with given interval."""
    if task_name not in auto_tasks:
        return False
    
    # Stop existing task if running
    if auto_tasks[task_name]["task"] is not None:
        auto_tasks[task_name]["enabled"] = False
    
    auto_tasks[task_name]["enabled"] = True
    auto_tasks[task_name]["interval"] = interval_seconds
    
    # Create background task
    if task_name == "roast":
        auto_tasks[task_name]["task"] = asyncio.create_task(auto_roast_task())
    elif task_name == "analyze":
        auto_tasks[task_name]["task"] = asyncio.create_task(auto_analyze_task())
    elif task_name == "mentions":
        auto_tasks[task_name]["task"] = asyncio.create_task(auto_mentions_task())
    
    return True


def stop_auto_task(task_name: str):
    """Stop an auto task."""
    if task_name not in auto_tasks:
        return False
    
    auto_tasks[task_name]["enabled"] = False
    auto_tasks[task_name]["interval"] = None
    
    return True


# --------------------------------------------------
# ALERT FORMATTING
# --------------------------------------------------


async def send_alert(message: str):
    """Send alert to Telegram."""
    try:
        if len(message) > 4000:
            # Split long messages
            parts = [message[i : i + 3900] for i in range(0, len(message), 3900)]
            for part in parts:
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=part,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                await asyncio.sleep(0.5)
        else:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        state["total_alerts"] += 1
        logger.info("Alert sent")
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")


def format_trade_alert(trade: Dict, is_large: bool = False) -> str:
    """Format individual trade alert."""
    trade_type = trade["type"]

    if trade_type == "buy":
        if is_large:
            emoji = "🟢 💰 BASED BUYER"
            comment = "finally someone with a brain"
        else:
            emoji = "🟢 BUY"
            comment = "accumulating"
    else:  # sell
        if is_large:
            emoji = "🔴 💸 PAPER HANDS DETECTED"
            comment = "ngmi. absolutely ngmi."
        else:
            emoji = "🔴 SELL"
            comment = "sad!"

    # Get market data
    market_cap = trade.get("market_cap_sol", 0)
    holder_count = trade.get("holder_count", "?")

    message = f"""
{emoji}

💰 ${trade['volume_usd']:,.2f} ({trade['sol_amount']:.4f} SOL)
💵 ${trade['price']:.10f}
📊 {trade.get('token_amount', 0):,.0f} tokens

📈 Market Cap: {market_cap:.2f} SOL
👥 Holders: {holder_count}

💬 {comment}

👤 `{trade.get('user', 'Unknown')[:8]}...`
⏰ {datetime.now().strftime('%H:%M:%S')}
"""
    return message


def format_analysis_alert(analysis: str, mode: str = "brief") -> str:
    """Format Claude analysis alert."""
    analysis_data = analyze_recent_trades()

    # Determine overall sentiment
    if analysis_data["buy_sell_ratio"] > 1.5:
        sentiment = "🚀 BULLISH"
    elif analysis_data["buy_sell_ratio"] < 0.7:
        sentiment = "📉 BEARISH"
    else:
        sentiment = "😐 NEUTRAL"

    mode_label = "⚡ BRIEF" if mode == "brief" else "📝 DETAILED"

    message = f"""
🤖 **CLAUDE'S TAKE** {sentiment} {mode_label}

**Quick Stats:**
• Buys: {state['total_buys']} | Sells: {state['total_sells']}
• Net Flow: ${state['total_buy_volume'] - state['total_sell_volume']:+,.2f}
• Price: ${state['last_price']:.10f}
• Market Cap: {state['last_market_cap']:.2f} SOL
• Holders: {state['last_holder_count']}
• Creator Rewards Available: {state.get('last_creator_rewards_available', 0):.4f} SOL

**Recent (Last 20):**
🟢 {analysis_data['buy_count']} buys (${analysis_data['buy_volume']:,.2f})
🔴 {analysis_data['sell_count']} sells (${analysis_data['sell_volume']:,.2f})
📊 Ratio: {analysis_data['buy_sell_ratio']:.2f}

━━━━━━━━━━━━━━━━━━━━

{analysis}

━━━━━━━━━━━━━━━━━━━━

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    return message


# --------------------------------------------------
# X/TWITTER INTEGRATION
# --------------------------------------------------

# Store last roast for regenerate/post functionality
last_roast_data = {
    "wallet": None,
    "trade_data": None,
    "roast_text": None,
}

# Store last analysis for post functionality
last_analysis_data = {
    "analysis_text": None,
    "analysis_mode": None,
}


# --------------------------------------------------
# TYPING INDICATOR
# --------------------------------------------------


async def send_thinking_animation(chat_id: int, duration: float = 5.0):
    """Send animated thinking messages with typing indicator."""
    thinking_msg = await bot.send_message(chat_id, "🤖 thinking.")

    dots = [".", "..", "..."]
    iterations = int(duration / 0.6)  # Change every 0.6 seconds

    for i in range(iterations):
        # Show typing indicator
        await bot.send_chat_action(chat_id, ChatAction.TYPING)

        # Cycle through dots
        dot_text = dots[i % len(dots)]
        try:
            await bot.edit_message_text(
                f"🤖 thinking{dot_text}", chat_id, thinking_msg.message_id
            )
        except:
            pass  # Ignore if message is the same

        await asyncio.sleep(0.6)

    # Delete thinking message
    try:
        await bot.delete_message(chat_id, thinking_msg.message_id)
    except:
        pass


# --------------------------------------------------
# WEBSOCKET MONITORING
# --------------------------------------------------


async def monitor_token():
    """Monitor token via PumpPortal WebSocket."""
    logger.info(f"Connecting to PumpPortal WebSocket...")
    logger.info(f"Monitoring token: {TOKEN_ADDRESS}")

    retry_delay = 1
    max_retry_delay = 60

    while True:
        try:
            async with websockets.connect(PUMPPORTAL_WS_URL) as websocket:
                logger.info("✅ Connected to PumpPortal WebSocket")
                retry_delay = 1  # Reset retry delay on successful connection

                # Subscribe to token trades
                payload = {"method": "subscribeTokenTrade", "keys": [TOKEN_ADDRESS]}
                await websocket.send(json.dumps(payload))
                logger.info(f"📡 Subscribed to trades for {TOKEN_ADDRESS}")

                # Send connection notification
                await send_alert(
                    f"🟢 **Monitor Connected (Silent Mode)**\n\n"
                    f"Watching: `{TOKEN_ADDRESS}`\n"
                    f"Mode: 🔇 Silent tracking (no trade alerts)\n"
                    f"Analysis: 🎯 Manual only (use /analyze)\n"
                    f"Style: {state['analysis_mode'].upper()}\n\n"
                    f"✅ Monitoring started...\n"
                    f"Use /status to check stats or /analyze for Claude's take."
                )

                # Listen for messages
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        await process_trade(data)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse message: {e}")
                    except Exception as e:
                        logger.error(f"Error processing trade: {e}")

        except websockets.exceptions.WebSocketException as e:
            logger.error(f"WebSocket error: {e}")
            logger.info(f"Reconnecting in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)


async def process_trade(data: Dict):
    """Process incoming trade data."""
    try:
        logger.info(f"Raw trade data received: {json.dumps(data)}")

        # Skip subscription confirmation messages
        if "message" in data and "subscribed" in data.get("message", "").lower():
            logger.info("Subscription confirmation received")
            return

        # Get transaction type
        tx_type = data.get("txType", "")

        # Skip token creation events - we only want buys/sells
        if tx_type == "create":
            logger.debug(
                f"Skipping token creation event for {data.get('name', 'Unknown')}"
            )
            return

        # Only process buy and sell transactions
        if tx_type not in ["buy", "sell"]:
            logger.warning(f"Unknown txType: {tx_type}")
            return

        trade_type = tx_type  # "buy" or "sell"

        # Extract trade data from PumpPortal format
        sol_amount = data.get("solAmount", 0)
        token_amount = data.get("tokenAmount", 0)
        market_cap_sol = data.get("marketCapSol", 0)

        # Get SOL price estimate (hardcoded for now, could fetch real-time)
        sol_price_usd = 100  # Update this periodically if needed
        volume_usd = sol_amount * sol_price_usd

        # Calculate price per token
        price = sol_amount / token_amount if token_amount > 0 else 0

        user = data.get("traderPublicKey", "Unknown")
        signature = data.get("signature", "")

        # Fetch token metrics periodically (every 10 trades to avoid rate limiting)
        holder_count = state.get("last_holder_count", "?")
        creator_rewards_available = state.get("last_creator_rewards_available", 0)
        market_cap_usd = 0
        if state["trades"] and len(state["trades"]) % 10 == 0:
            metrics = fetch_token_metrics(TOKEN_ADDRESS)
            if metrics:
                holder_count = metrics.get("holder_count", holder_count)
                market_cap_sol = metrics.get("market_cap_sol", market_cap_sol)
                market_cap_usd = metrics.get("usd_market_cap", 0)
                creator_rewards_available = metrics.get("creator_rewards_available", creator_rewards_available)
                logger.info(f"Updated metrics - Holders: {holder_count}, Market Cap: ${market_cap_usd:,.0f} ({market_cap_sol:.2f} SOL), Creator Rewards: {creator_rewards_available} SOL")

        logger.info(
            f"Parsed trade - Type: {trade_type}, SOL: {sol_amount}, Tokens: {token_amount}, Volume USD: ${volume_usd:.2f}"
        )

        # Store trade with all market data
        trade = {
            "timestamp": time.time(),
            "type": trade_type,
            "price": price,
            "sol_amount": sol_amount,
            "volume_usd": volume_usd,
            "token_amount": token_amount,
            "market_cap_sol": market_cap_sol,
            "holder_count": holder_count,
            "user": user,
            "signature": signature,
        }

        state["trades"].append(trade)

        # Keep only last 100 trades in memory
        if len(state["trades"]) > 100:
            state["trades"] = state["trades"][-100:]

        # Update statistics
        if trade_type == "buy":
            state["total_buys"] += 1
            state["total_buy_volume"] += volume_usd
        else:
            state["total_sells"] += 1
            state["total_sell_volume"] += volume_usd
        
        # Track creator rewards (0.05% of volume)
        creator_reward = volume_usd * 0.0005
        state["creator_rewards"] = state.get("creator_rewards", 0) + creator_reward

        # Update price tracking
        if price > 0:
            state["last_price"] = price
            if state["highest_price"] is None or price > state["highest_price"]:
                state["highest_price"] = price
            if state["lowest_price"] is None or price < state["lowest_price"]:
                state["lowest_price"] = price

        # Update market data
        state["last_market_cap"] = market_cap_sol
        state["last_market_cap_usd"] = market_cap_usd
        state["last_holder_count"] = holder_count
        state["last_creator_rewards_available"] = creator_rewards_available

        # Log trade
        emoji = "🟢" if trade_type == "buy" else "🔴"
        logger.info(
            f"{emoji} {trade_type.upper()}: {sol_amount} SOL (${volume_usd:,.2f}) at ${price:.8f}"
        )

        # CHANGED: Removed automatic trade alerts
        # Trades are now tracked silently - no alerts sent
        # User can check /status or /recent to see activity
        
        # Generate AI comment for trade (quick one-liner)
        ai_comment = await generate_trade_comment(trade_type, sol_amount, user)
        trade["ai_comment"] = ai_comment
        
        # Broadcast trade to dashboard
        await broadcast_to_dashboard("trade", trade)
        
        # Broadcast updated state to dashboard
        await broadcast_to_dashboard("state_update", {
            "total_buys": state["total_buys"],
            "total_sells": state["total_sells"],
            "total_buy_volume": state["total_buy_volume"],
            "total_sell_volume": state["total_sell_volume"],
            "creator_rewards": state["creator_rewards"],
            "last_price": state["last_price"],
            "highest_price": state["highest_price"],
            "lowest_price": state["lowest_price"],
            "last_market_cap": state["last_market_cap"],
            "last_holder_count": state["last_holder_count"],
        })

        # Save state to file for API access
        save_state(state)

        # CHANGED: Removed automatic periodic analysis
        # Analysis only runs when user uses /analyze command

    except Exception as e:
        logger.error(f"Error in process_trade: {e}", exc_info=True)
        logger.error(f"Data that caused error: {json.dumps(data)}")


async def refresh_token_metrics():
    """Periodically refresh token metrics and broadcast to dashboard."""
    logger.info("📊 Starting periodic token metrics refresh (every 30 seconds)")
    await asyncio.sleep(5)  # Wait for initial setup
    
    while True:
        try:
            await asyncio.sleep(30)  # Refresh every 30 seconds
            
            # Try to get latest metrics from API
            try:
                metrics = fetch_token_metrics(TOKEN_ADDRESS)
                if metrics:
                    # Update state with fresh metrics
                    state["last_market_cap"] = metrics.get("market_cap_sol", state.get("last_market_cap", 0))
                    state["last_market_cap_usd"] = metrics.get("usd_market_cap", 0)
                    state["last_holder_count"] = metrics.get("holder_count", state.get("last_holder_count", "?"))
                    state["last_creator_rewards_available"] = metrics.get("creator_rewards_available", 0)
                    logger.info(f"📊 Got fresh metrics - Market Cap: ${state['last_market_cap_usd']:,.0f} ({state['last_market_cap']:.2f} SOL)")
                else:
                    logger.info(f"📊 No new metrics from API, using cached values")
            except Exception as e:
                logger.debug(f"Could not fetch fresh metrics: {e}")
                metrics = None
            
            # Always broadcast current state (either updated or cached)
            update = {
                "last_market_cap": state.get("last_market_cap"),
                "last_market_cap_usd": state.get("last_market_cap_usd"),
                "last_holder_count": state.get("last_holder_count"),
                "last_creator_rewards_available": state.get("last_creator_rewards_available", 0),
            }
            
            if dashboard_clients:
                logger.info(f"📡 Broadcasting metrics to {len(dashboard_clients)} dashboard clients")
                await broadcast_to_dashboard("state_update", update)
            else:
                logger.debug("📊 No dashboard clients connected, skipping broadcast")
                
        except Exception as e:
            logger.error(f"❌ Error refreshing token metrics: {e}", exc_info=True)
            await asyncio.sleep(10)  # Wait before retrying on error


async def run_analysis(mode: str = "brief"):
    """Run analysis in background to avoid blocking trade processing."""
    try:
        analysis = await analyze_with_claude(mode)
        alert = format_analysis_alert(analysis, mode)
        await send_alert(alert)
        save_state(state)
    except Exception as e:
        logger.error(f"Error in analysis: {e}")


# --------------------------------------------------
# TELEGRAM COMMANDS
# --------------------------------------------------


@dp.message(Command("start"))
async def start_handler(message: types.Message):
    """Handle /start command."""
    status = (
        "✅ Connected"
        if state["trades"] or time.time() - state["start_time"] > 10
        else "⏳ Starting..."
    )

    await message.answer(
        "🤖 **PumpPortal Token Monitor (Silent Mode)**\n\n"
        f"Status: {status}\n"
        f"Monitoring: `{TOKEN_ADDRESS}`\n"
        f"Mode: 🔇 Silent tracking (no trade alerts)\n"
        f"Analysis: 🎯 Manual only\n"
        f"Style: **{state['analysis_mode'].upper()}**\n\n"
        "**Commands:**\n"
        "/status - View current stats\n"
        "/analyze - Get Claude's analysis NOW\n"
        "/pickroast - Roast a random paper hands 🔥\n"
        "/brief - Switch to brief brutal mode ⚡\n"
        "/long - Switch to detailed analysis 📝\n"
        "/recent - Show recent trades\n"
        "/config - View settings\n"
        "/test - Test alert system",
        parse_mode="Markdown",
    )


@dp.message(Command("status"))
async def status_handler(message: types.Message):
    """Check bot status."""
    session_duration = (time.time() - state["start_time"]) / 3600

    await message.answer(
        f"📊 **Monitor Status**\n\n"
        f"✅ Active (Silent Mode)\n"
        f"🎯 Token: `{TOKEN_ADDRESS}`\n"
        f"💬 Analysis Style: **{state['analysis_mode'].upper()}**\n\n"
        f"**Session ({session_duration:.1f}h):**\n"
        f"• Total Trades: {len(state['trades'])}\n"
        f"• Buys: {state['total_buys']} (${state['total_buy_volume']:,.0f})\n"
        f"• Sells: {state['total_sells']} (${state['total_sell_volume']:,.0f})\n"
        f"• Net Flow: ${state['total_buy_volume'] - state['total_sell_volume']:+,.0f}\n\n"
        f"**Price:**\n"
        f"• Current: ${state['last_price']:.8f}\n"
        f"• High: ${state['highest_price']:.8f}\n"
        f"• Low: ${state['lowest_price']:.8f}\n\n"
        f"**Market:**\n"
        f"• Market Cap: {state['last_market_cap']:.2f} SOL\n"
        f"• Holders: {state['last_holder_count']}\n"
        f"• Creator Rewards Available: {state.get('last_creator_rewards_available', 0):.4f} SOL\n\n"
        f"📊 Analyses: {state['total_analyses']}\n"
        f"📨 Alerts: {state['total_alerts']}\n\n"
        f"💡 Use /analyze to get Claude's take!",
        parse_mode="Markdown",
    )


@dp.message(Command("recent"))
async def recent_handler(message: types.Message):
    """Show recent trades."""
    if not state["trades"]:
        await message.answer("No trades recorded yet.")
        return

    recent = state["trades"][-10:]

    msg = "📊 **Last 10 Trades:**\n\n"
    for trade in reversed(recent):
        emoji = "🟢" if trade["type"] == "buy" else "🔴"
        msg += f"{emoji} {trade['type'].upper()}: ${trade['volume_usd']:,.2f} @ ${trade['price']:.8f}\n"

    await message.answer(msg, parse_mode="Markdown")


@dp.message(Command("analyze"))
async def analyze_handler(message: types.Message):
    """Force immediate analysis."""
    chat_id = message.chat.id

    # Start thinking animation and typing indicator
    thinking_task = asyncio.create_task(send_thinking_animation(chat_id, duration=3.0))

    try:
        # Run analysis while thinking animation plays
        analysis = await analyze_with_claude(state["analysis_mode"])

        # Wait for thinking animation to complete
        await thinking_task

        # Store analysis for post functionality
        last_analysis_data["analysis_text"] = analysis
        last_analysis_data["analysis_mode"] = state["analysis_mode"]
        
        # Log action
        log_action("analyze", f"Ran {state['analysis_mode']} analysis", {
            "mode": state["analysis_mode"],
            "analysis_text": analysis,
            "trades_count": len(state["trades"]),
        })

        # Send analysis with keyboard
        alert = format_analysis_alert(analysis, state["analysis_mode"])
        
        # Create inline keyboard with Post to X button
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🐦 Post to X", callback_data="post_analysis_to_x")]
        ])
        
        await message.answer(alert, parse_mode="Markdown", reply_markup=keyboard)
        save_state(state)
    except Exception as e:
        await thinking_task  # Make sure to clean up
        await message.answer(f"❌ Error: {e}")


@dp.message(Command("pickroast"))
async def pickroast_handler(message: types.Message):
    """Pick a random seller and roast them."""
    chat_id = message.chat.id
    
    # Find all sell trades
    sell_trades = [t for t in state["trades"] if t["type"] == "sell"]
    
    if not sell_trades:
        await message.answer(
            "🤷 No paper hands detected yet. Everyone's holding... for now.",
            parse_mode="Markdown"
        )
        return
    
    # Pick a random sell trade
    target_trade = random.choice(sell_trades)
    wallet = target_trade["user"]
    
    # Show thinking animation
    thinking_task = asyncio.create_task(
        send_thinking_animation(chat_id, duration=2.0)
    )
    
    try:
        # Generate the roast
        roast = await roast_paper_hands(wallet, target_trade)
        
        # Wait for animation to complete
        await thinking_task
        
        # Store for regenerate functionality
        last_roast_data["wallet"] = wallet
        last_roast_data["trade_data"] = target_trade
        last_roast_data["roast_text"] = roast
        
        # Log action
        log_action("pickroast", f"Roasted {wallet[:8]}...", {
            "wallet": wallet,
            "roast_text": roast,
            "volume_usd": target_trade["volume_usd"],
        })
        
        # Format the roast message
        roast_message = f"""
🎯 **PAPER HANDS ROAST**

`{wallet[:8]}...{wallet[-8:]}`

{roast}

💸 ${target_trade['volume_usd']:,.2f} | {len(sell_trades)} total sells tracked
"""
        
        # Create inline keyboard with Regenerate and Post to X buttons
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Regenerate", callback_data="regenerate_roast"),
                InlineKeyboardButton(text="🐦 Post to X", callback_data="post_to_x"),
            ]
        ])
        
        await message.answer(roast_message, parse_mode="Markdown", reply_markup=keyboard)
        
    except Exception as e:
        await thinking_task  # Clean up animation
        await message.answer(f"❌ Error generating roast: {e}")


@dp.callback_query(lambda c: c.data == "regenerate_roast")
async def regenerate_roast_callback(callback: CallbackQuery):
    """Regenerate the roast with the same wallet."""
    if not last_roast_data["wallet"] or not last_roast_data["trade_data"]:
        await callback.answer("❌ No previous roast to regenerate!", show_alert=True)
        return
    
    await callback.answer("🔄 Regenerating roast...")
    
    # Show thinking animation
    thinking_msg = await callback.message.answer("🤖 thinking...")
    
    try:
        # Generate new roast
        wallet = last_roast_data["wallet"]
        trade_data = last_roast_data["trade_data"]
        roast = await roast_paper_hands(wallet, trade_data)
        
        # Update stored roast
        last_roast_data["roast_text"] = roast
        
        # Delete thinking message
        await thinking_msg.delete()
        
        # Count total sells for context
        sell_trades = [t for t in state["trades"] if t["type"] == "sell"]
        
        # Format new roast message
        roast_message = f"""
🎯 **PAPER HANDS ROAST** (Regenerated)

`{wallet[:8]}...{wallet[-8:]}`

{roast}

💸 ${trade_data['volume_usd']:,.2f} | {len(sell_trades)} total sells tracked
"""
        
        # Create inline keyboard
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Regenerate", callback_data="regenerate_roast"),
                InlineKeyboardButton(text="🐦 Post to X", callback_data="post_to_x"),
            ]
        ])
        
        # Edit the original message
        await callback.message.edit_text(roast_message, parse_mode="Markdown", reply_markup=keyboard)
        
    except Exception as e:
        await thinking_msg.delete()
        await callback.message.answer(f"❌ Error regenerating roast: {e}")


@dp.callback_query(lambda c: c.data == "post_to_x")
async def post_to_x_callback(callback: CallbackQuery):
    """Post the roast to X/Twitter community (REQUIRED)."""
    if not last_roast_data["roast_text"]:
        await callback.answer("❌ No roast to post!", show_alert=True)
        return
    
    await callback.answer("📤 Posting to X Community...")
    
    try:
        wallet = last_roast_data["wallet"]
        roast_text = last_roast_data["roast_text"]
        
        # Format tweet with wallet reference (no hashtags)
        tweet_text = f"{roast_text}\n\n`{wallet[:8]}...{wallet[-8:]}`"
        
        # Ensure tweet fits in 280 chars
        if len(tweet_text) > 280:
            # Truncate roast to fit
            max_roast_len = 280 - len(f"\n\n`{wallet[:8]}...{wallet[-8:]}`") - 3  # -3 for "..."
            roast_text = roast_text[:max_roast_len] + "..."
            tweet_text = f"{roast_text}\n\n`{wallet[:8]}...{wallet[-8:]}`"
        
        # Post to X Community (runs in thread to avoid blocking)
        tweet_id = await asyncio.to_thread(post_to_x_community, tweet_text)
        
        tweet_url = f"https://x.com/{MY_SCREEN_NAME}/status/{tweet_id}"
        
        await callback.message.answer(
            f"✅ Posted to X Community!\n\n"
            f"🔗 {tweet_url}"
        )
        
    except Exception as e:
        logger.error(f"Error posting to X Community: {e}")
        await callback.message.answer(
            f"❌ Failed to post to X Community\n\n"
            f"Error: {str(e)}"
        )


@dp.callback_query(lambda c: c.data == "post_analysis_to_x")
async def post_analysis_to_x_callback(callback: CallbackQuery):
    """Post the analysis to X/Twitter."""
    if not last_analysis_data["analysis_text"]:
        await callback.answer("❌ No analysis to post!", show_alert=True)
        return
    
    await callback.answer("📤 Posting analysis to X...")
    
    try:
        analysis_text = last_analysis_data["analysis_text"]
        mode = last_analysis_data["analysis_mode"]
        
        # Format tweet - add mode tag
        mode_emoji = "⚡" if mode == "brief" else "📝"
        tweet_text = f"{mode_emoji} {analysis_text}"
        
        # Ensure tweet fits in 280 chars
        if len(tweet_text) > 280:
            # Truncate analysis to fit
            max_analysis_len = 280 - len(f"{mode_emoji} ") - 3  # -3 for "..."
            analysis_text = analysis_text[:max_analysis_len] + "..."
            tweet_text = f"{mode_emoji} {analysis_text}"
        
        # Post to X (runs in thread to avoid blocking)
        tweet_id = await asyncio.to_thread(post_to_x_community, tweet_text)
        
        tweet_url = f"https://x.com/{MY_SCREEN_NAME}/status/{tweet_id}"
        
        await callback.message.answer(
            f"✅ Posted analysis to X!\n\n"
            f"🔗 {tweet_url}"
        )
        
    except Exception as e:
        logger.error(f"Error posting analysis to X: {e}")
        await callback.message.answer(
            f"❌ Failed to post to X\n\n"
            f"Error: {str(e)}"
        )


@dp.message(Command("brief"))
async def brief_handler(message: types.Message):
    """Switch to brief analysis mode."""
    state["analysis_mode"] = "brief"
    save_state(state)
    await message.answer(
        "⚡ **Switched to BRIEF mode**\n\n"
        "Claude will now deliver ultra-short, brutally honest takes.\n"
        "3-5 sentences max. Pure savagery. No fluff.\n\n"
        "Use /analyze to get roasted.",
        parse_mode="Markdown",
    )


@dp.message(Command("long"))
async def long_handler(message: types.Message):
    """Switch to long analysis mode."""
    state["analysis_mode"] = "long"
    save_state(state)
    await message.answer(
        "📝 **Switched to DETAILED mode**\n\n"
        "Claude will now deliver full detailed analysis.\n"
        "Deep dives, market psychology, the whole roast.\n\n"
        "Use /analyze to get the full treatment.",
        parse_mode="Markdown",
    )


@dp.message(Command("config"))
async def config_handler(message: types.Message):
    """Show configuration."""
    await message.answer(
        f"⚙️ **Configuration**\n\n"
        f"Token: `{TOKEN_ADDRESS}`\n"
        f"Show All Trades: ❌ NO (Silent Mode)\n"
        f"Auto-analyze: ❌ NO (Manual only)\n"
        f"Analysis Style: **{state['analysis_mode'].upper()}**\n\n"
        f"ℹ️ Bot tracks all trades silently.\n"
        f"Use /status or /analyze to check activity.\n\n"
        f"Switch modes:\n"
        f"• /brief - Short & brutal ⚡\n"
        f"• /long - Detailed roasts 📝",
        parse_mode="Markdown",
    )


@dp.message(Command("setupx"))
async def setupx_handler(message: types.Message):
    """Check X/Twitter community setup status."""
    status_text = f"✅ **X/Twitter Status: Connected**\n\n"
    status_text += f"Account: @{MY_SCREEN_NAME}\n"
    status_text += f"User ID: {MY_USER_ID}\n"
    status_text += f"🎯 Mode: **Community Posting (REQUIRED)**\n"
    status_text += f"📍 Community ID: `{X_COMMUNITY_ID}`\n\n"
    status_text += "All roasts will be posted to the community!"
    
    await message.answer(status_text, parse_mode="Markdown")


@dp.message(Command("xstatus"))
async def xstatus_handler(message: types.Message):
    """Check X/Twitter community posting status."""
    status_text = f"✅ **X/Twitter Community Status**\n\n"
    status_text += f"Account: @{MY_SCREEN_NAME}\n"
    status_text += f"User ID: {MY_USER_ID}\n\n"
    status_text += f"🎯 **Community Posting**: ACTIVE\n"
    status_text += f"📍 Community ID: `{X_COMMUNITY_ID}`\n\n"
    status_text += "Ready to roast paper hands to the community! 🔥"
    
    await message.answer(status_text, parse_mode="Markdown")


@dp.message(Command("test"))
async def test_handler(message: types.Message):
    """Test the alert system."""
    await message.answer("🧪 Testing alert system...")

    test_message = f"""
🧪 **TEST ALERT**

The bot is working correctly!

**Current Status:**
• Trades tracked: {len(state['trades'])}
• Buys: {state['total_buys']}
• Sells: {state['total_sells']}
• Analysis Mode: {state['analysis_mode'].upper()}

Use /analyze to get Claude's take on the action!
"""

    await send_alert(test_message)
    await message.answer("✅ Test alert sent!")


@dp.message(Command("say"))
async def say_handler(message: types.Message, command: CommandObject):
    """Post custom message to X/Twitter community."""
    if not command.args:
        await message.answer(
            "📝 **Usage:** `/say your message here`\n\n"
            "I'll post your message to the X/Twitter community.",
            parse_mode="Markdown"
        )
        return
    
    custom_text = command.args
    chat_id = message.chat.id
    
    await message.answer("📤 Posting to X Community...")
    
    try:
        # Ensure tweet fits in 280 chars
        if len(custom_text) > 280:
            custom_text = custom_text[:277] + "..."
        
        # Post to X Community
        tweet_id = await asyncio.to_thread(post_to_x_community, custom_text)
        
        # Log action
        log_action("say", f"Published statement to X community", {
            "text": custom_text,
            "tweet_id": tweet_id,
        })
        
        tweet_url = f"https://x.com/{MY_SCREEN_NAME}/status/{tweet_id}"
        
        await message.answer(
            f"✅ Posted to X Community!\n\n"
            f"🔗 [{tweet_id}]({tweet_url})",
            parse_mode="Markdown"
        )
        logger.info(f"✅ Custom message posted: {tweet_id}")
        
    except Exception as e:
        logger.error(f"Error posting custom message to X: {e}")
        await message.answer(
            f"❌ Failed to post to X Community\n\n"
            f"Error: {str(e)}"
        )
        log_action("say_error", f"Failed to post message: {str(e)}", {
            "text": custom_text,
            "error": str(e),
        })


@dp.message(Command("reply"))
async def reply_handler(message: types.Message, command: CommandObject):
    """Manually reply to a tweet by ID (useful for community post mentions)."""
    if not command.args:
        await message.answer(
            "💬 **Reply to a Tweet**\n\n"
            "**Usage:** `/reply <tweet_id> [optional message]`\n\n"
            "**Examples:**\n"
            "• `/reply 1234567890` - Generate AI reply\n"
            "• `/reply 1234567890 gm ser` - Use custom message\n\n"
            "Get the tweet ID from the URL:\n"
            "`x.com/user/status/1234567890` → ID is `1234567890`",
            parse_mode="Markdown"
        )
        return
    
    # Parse arguments
    args = command.args.split(maxsplit=1)
    tweet_id = args[0].strip()
    custom_message = args[1].strip() if len(args) > 1 else None
    
    # Validate tweet ID (should be numeric)
    if not tweet_id.isdigit():
        await message.answer(
            "❌ Invalid tweet ID. Must be a number.\n\n"
            "Get it from the tweet URL: `x.com/user/status/1234567890`",
            parse_mode="Markdown"
        )
        return
    
    # Check if already replied
    if has_replied_to_tweet(tweet_id):
        await message.answer(f"⚠️ Already replied to this tweet ({tweet_id})")
        return
    
    await message.answer(f"💭 {'Generating' if not custom_message else 'Posting'} reply to tweet {tweet_id}...")
    
    try:
        if custom_message:
            # Use custom message
            reply_text = custom_message
        else:
            # Generate AI reply - first fetch the tweet to get context
            access_token = oauth2_handler.get_access_token()
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            
            # Fetch the tweet content
            tweet_response = requests.get(
                f"https://api.x.com/2/tweets/{tweet_id}",
                headers=headers,
                params={
                    "tweet.fields": "author_id,text",
                    "expansions": "author_id",
                    "user.fields": "username",
                },
                timeout=10
            )
            tweet_response.raise_for_status()
            tweet_data = tweet_response.json()
            
            tweet_text = tweet_data.get("data", {}).get("text", "")
            author_username = "unknown"
            
            # Get author username from includes
            if "includes" in tweet_data and "users" in tweet_data["includes"]:
                author_username = tweet_data["includes"]["users"][0].get("username", "unknown")
            
            # Generate reply using Claude
            reply_text = await generate_mention_reply(tweet_text, author_username)
            
            if not reply_text:
                await message.answer("❌ Failed to generate reply")
                return
        
        # Ensure reply fits
        if len(reply_text) > 280:
            reply_text = reply_text[:277] + "..."
        
        # Post the reply
        reply_id = await asyncio.to_thread(reply_to_tweet, tweet_id, reply_text)
        
        if reply_id:
            # Save to replied tweets
            save_replied_tweet(tweet_id)
            
            # Log action
            log_action("manual_reply", f"Manually replied to tweet {tweet_id}", {
                "original_tweet_id": tweet_id,
                "reply_text": reply_text,
                "reply_tweet_id": reply_id,
            })
            
            tweet_url = f"https://x.com/{MY_SCREEN_NAME}/status/{reply_id}"
            
            await message.answer(
                f"✅ **Reply Posted!**\n\n"
                f"📝 {reply_text}\n\n"
                f"🔗 [View Reply]({tweet_url})",
                parse_mode="Markdown"
            )
            logger.info(f"✅ Manual reply posted: {reply_id}")
        else:
            await message.answer("❌ Failed to post reply - no ID returned")
            
    except requests.exceptions.HTTPError as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_msg = e.response.json()
            except:
                error_msg = e.response.text
        logger.error(f"Error posting manual reply: {error_msg}")
        await message.answer(f"❌ Failed to post reply\n\nError: {error_msg}")
    except Exception as e:
        logger.error(f"Error posting manual reply: {e}")
        await message.answer(f"❌ Failed to post reply\n\nError: {str(e)}")


@dp.message(Command("burn"))
async def burn_handler(message: types.Message):
    """Burn tokens - generates random burn amount."""
    # Generate random burn amount between 1M and 100M
    burn_amount = random.randint(1_000_000, 100_000_000)
    formatted_amount = f"{burn_amount:,}"
    
    burn_message = f"🔥 Burnt {formatted_amount} tokens"
    
    await message.answer(burn_message)
    log_action("burn", f"Token burn executed: {formatted_amount} units", {"amount": burn_amount})
    
    logger.info(f"🔥 Burn command executed: {formatted_amount} tokens")


@dp.message(Command("claim"))
async def claim_handler(message: types.Message, command: CommandObject):
    """Claim rewards - shows the amount being claimed."""
    if not command.args:
        await message.answer("❌ Usage: `/claim <amount>`\nExample: `/claim 5.5`", parse_mode="Markdown")
        return
    
    try:
        amount = float(command.args.strip())
        claim_message = f"💰 Claimed {amount} SOL"
        
        await message.answer(claim_message)
        log_action("claim", f"Reward claim processed: {amount} SOL", {"amount": amount})
        
        logger.info(f"💰 Claim command executed: {amount} SOL")
        
    except ValueError:
        await message.answer("❌ Invalid amount. Please provide a number.\nExample: `/claim 5.5`", parse_mode="Markdown")


@dp.message(Command("updatecreator"))
async def update_creator_handler(message: types.Message, command: CommandObject):
    """Manually update creator rewards available."""
    if not command.args:
        current_rewards = state.get('last_creator_rewards_available', 0)
        await message.answer(
            f"💰 **Current Creator Rewards:** {current_rewards:.4f} SOL\n\n"
            f"**Usage:** `/updatecreator <amount>`\n"
            f"Example: `/updatecreator 10` sets rewards to 10 SOL",
            parse_mode="Markdown"
        )
        return
    
    try:
        amount = float(command.args.strip())
        
        if amount < 0:
            await message.answer("❌ Amount must be positive", parse_mode="Markdown")
            return
        
        # Update state
        old_amount = state.get('last_creator_rewards_available', 0)
        state['last_creator_rewards_available'] = amount
        save_state(state)
        
        # Log the action
        log_action(
            "update_creator_rewards",
            f"Creator rewards updated from {old_amount:.4f} SOL to {amount:.4f} SOL",
            {"old_amount": old_amount, "new_amount": amount}
        )
        
        # Broadcast update to dashboard
        await broadcast_to_dashboard("creator_rewards_update", {
            "creator_rewards_available": amount,
            "old_amount": old_amount,
        })
        
        # Send confirmation
        change = amount - old_amount
        change_str = f"+{change:.4f}" if change > 0 else f"{change:.4f}"
        
        await message.answer(
            f"✅ **Creator Rewards Updated**\n\n"
            f"Previous: {old_amount:.4f} SOL\n"
            f"New: {amount:.4f} SOL\n"
            f"Change: {change_str} SOL",
            parse_mode="Markdown"
        )
        
        logger.info(f"💰 Creator rewards manually updated: {old_amount:.4f} → {amount:.4f} SOL")
        
    except ValueError:
        await message.answer("❌ Invalid amount. Please provide a number.\nExample: `/updatecreator 10`", parse_mode="Markdown")


@dp.message(Command("auto"))
async def auto_handler(message: types.Message, command: CommandObject):
    """Manage auto-roasting and auto-analyzing."""
    if not command.args:
        # Show status
        roast_status = "✅ RUNNING" if auto_tasks["roast"]["enabled"] else "❌ STOPPED"
        analyze_status = "✅ RUNNING" if auto_tasks["analyze"]["enabled"] else "❌ STOPPED"
        
        roast_interval = f"Every {auto_tasks['roast']['interval']}s" if auto_tasks["roast"]["interval"] else "Not set"
        analyze_interval = f"Every {auto_tasks['analyze']['interval']}s" if auto_tasks["analyze"]["interval"] else "Not set"
        
        status_msg = f"""
🤖 **Auto Tasks Status**

**🔥 Auto-Roast:** {roast_status}
  └─ {roast_interval}

**📊 Auto-Analyze:** {analyze_status}
  └─ {analyze_interval}

**Commands:**
`/auto roast <seconds>` - Start auto-roasting (e.g., `/auto roast 180` = every 3 mins)
`/auto analyze <seconds>` - Start auto-analyzing (e.g., `/auto analyze 300` = every 5 mins)
`/auto stop roast` - Stop auto-roasting
`/auto stop analyze` - Stop auto-analyzing
`/auto stop all` - Stop everything
"""
        
        await message.answer(status_msg, parse_mode="Markdown")
        return
    
    args = command.args.split()
    
    if len(args) < 1:
        await message.answer("❌ Invalid command format")
        return
    
    action = args[0].lower()
    
    if action == "roast":
        if len(args) < 2:
            await message.answer("❌ Usage: `/auto roast <seconds>`", parse_mode="Markdown")
            return
        
        try:
            interval = int(args[1])
            if interval < 60:
                await message.answer("❌ Interval must be at least 60 seconds", parse_mode="Markdown")
                return
            
            start_auto_task("roast", interval)
            log_action("auto_start", f"Started auto-roast every {interval}s", {"interval": interval})
            
            await message.answer(
                f"🔥 **Auto-Roast Started**\n\n"
                f"Every `{interval}` seconds ({interval//60} min{'' if interval//60 == 1 else 's'})\n"
                f"Will automatically pick a paper hands and roast them on X! 🚀",
                parse_mode="Markdown"
            )
            logger.info(f"✅ Auto-roast started: every {interval}s")
            
        except ValueError:
            await message.answer("❌ Interval must be a number (in seconds)", parse_mode="Markdown")
    
    elif action == "analyze":
        if len(args) < 2:
            await message.answer("❌ Usage: `/auto analyze <seconds>`", parse_mode="Markdown")
            return
        
        try:
            interval = int(args[1])
            if interval < 60:
                await message.answer("❌ Interval must be at least 60 seconds", parse_mode="Markdown")
                return
            
            start_auto_task("analyze", interval)
            log_action("auto_start", f"Started auto-analyze every {interval}s", {"interval": interval})
            
            await message.answer(
                f"📊 **Auto-Analyze Started**\n\n"
                f"Every `{interval}` seconds ({interval//60} min{'' if interval//60 == 1 else 's'})\n"
                f"Will automatically run analysis and post Claude's take to X! 🤖",
                parse_mode="Markdown"
            )
            logger.info(f"✅ Auto-analyze started: every {interval}s")
            
        except ValueError:
            await message.answer("❌ Interval must be a number (in seconds)", parse_mode="Markdown")
    
    elif action == "stop":
        if len(args) < 2:
            await message.answer("❌ Usage: `/auto stop <roast|analyze|all>`", parse_mode="Markdown")
            return
        
        target = args[1].lower()
        
        if target == "roast":
            stop_auto_task("roast")
            log_action("auto_stop", "Stopped auto-roast", {})
            await message.answer("🔥 **Auto-Roast Stopped**")
            logger.info("✅ Auto-roast stopped")
            
        elif target == "analyze":
            stop_auto_task("analyze")
            log_action("auto_stop", "Stopped auto-analyze", {})
            await message.answer("📊 **Auto-Analyze Stopped**")
            logger.info("✅ Auto-analyze stopped")
            
        elif target == "all":
            stop_auto_task("roast")
            stop_auto_task("analyze")
            log_action("auto_stop", "Stopped all auto tasks", {})
            await message.answer("🛑 **All Auto Tasks Stopped**")
            logger.info("✅ All auto tasks stopped")
            
        else:
            await message.answer("❌ Unknown target. Use `roast`, `analyze`, or `all`.", parse_mode="Markdown")
    
    else:
        await message.answer("❌ Unknown action. Use `roast`, `analyze`, or `stop`.", parse_mode="Markdown")


# --------------------------------------------------
# MENTIONS COMMAND
# --------------------------------------------------

@dp.message(Command("mentions"))
async def handle_mentions_command(message: types.Message, command: CommandObject):
    """Handle /mentions command for X mention auto-reply control."""
    args = command.args.split() if command.args else []
    
    if not args:
        # Show status
        status = "🟢 RUNNING" if auto_tasks["mentions"]["enabled"] else "🔴 STOPPED"
        interval = auto_tasks["mentions"]["interval"] or 60
        last_run = auto_tasks["mentions"]["last_run"]
        last_run_str = datetime.fromtimestamp(last_run).strftime("%H:%M:%S") if last_run else "Never"
        
        status_text = f"""🔔 **X Mention Auto-Reply**

**Status:** {status}
**Check Interval:** {interval} seconds
**Last Check:** {last_run_str}

**Commands:**
• `/mentions start` - Start auto-replying
• `/mentions stop` - Stop auto-replying
• `/mentions start 30` - Start with 30s interval"""
        
        await message.answer(status_text, parse_mode="Markdown")
        return
    
    action = args[0].lower()
    
    if action == "start":
        # Get optional interval
        interval = 60  # Default 60 seconds
        if len(args) > 1:
            try:
                interval = int(args[1])
                if interval < 30:
                    await message.answer("⚠️ Minimum interval is 30 seconds to avoid rate limits", parse_mode="Markdown")
                    interval = 30
            except ValueError:
                await message.answer("❌ Invalid interval. Using default 60 seconds.", parse_mode="Markdown")
        
        start_auto_task("mentions", interval)
        log_action("mentions_start", f"Started X mention auto-reply (interval: {interval}s)", {"interval": interval})
        
        await message.answer(
            f"🔔 **Mention Auto-Reply Started!**\n\n"
            f"Checking for mentions every **{interval} seconds**\n"
            f"I'll reply to anyone who tags @clawdebot",
            parse_mode="Markdown"
        )
        logger.info(f"✅ Mention auto-reply started with {interval}s interval")
    
    elif action == "stop":
        stop_auto_task("mentions")
        log_action("mentions_stop", "Stopped X mention auto-reply", {})
        await message.answer("🔕 **Mention Auto-Reply Stopped**", parse_mode="Markdown")
        logger.info("✅ Mention auto-reply stopped")
    
    else:
        await message.answer("❌ Unknown action. Use `start` or `stop`.", parse_mode="Markdown")


# --------------------------------------------------
# MAIN ENTRY POINT
# --------------------------------------------------


async def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("PumpPortal Token Monitor Starting (Silent Mode)...")
    logger.info(f"Token: {TOKEN_ADDRESS}")
    logger.info(f"Mode: Silent tracking - no trade alerts")
    logger.info(f"Analysis: Manual only - use /analyze command")
    logger.info(f"Style: {state['analysis_mode'].upper()}")
    logger.info("=" * 60)

    # Set bot commands for the / menu
    await set_bot_commands()
    logger.info("✅ Bot commands set")

    # Start dashboard WebSocket server
    await start_dashboard_ws_server()

    # Start periodic metrics refresh
    asyncio.create_task(refresh_token_metrics())
    logger.info("✅ Periodic metrics refresh started")

    # Start WebSocket monitor in background
    asyncio.create_task(monitor_token())

    # Start Telegram bot
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
