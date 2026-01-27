# Production Deployment Guide

## Overview

Your ClawdScan app consists of:
- **Next.js Frontend** - Deployed on Vercel
- **Python WebSocket Server** - Runs on your local machine (port 8765)

To connect them, we'll expose your local Python server using **ngrok**.

---

## Setup Instructions

### 1. Install ngrok

```bash
brew install ngrok
```

Or download from: https://ngrok.com/download

### 2. Get ngrok Auth Token

1. Sign up at https://dashboard.ngrok.com/signup
2. Copy your auth token from: https://dashboard.ngrok.com/get-started/your-authtoken
3. Configure it:

```bash
ngrok config add-authtoken 38qusGrBr5ouc0VGsmFK3XblCET_4gwwbKyPkD1CAsYVoSwMA
```

### 3. Update ngrok.yml

Edit `ngrok.yml` and replace `YOUR_NGROK_AUTH_TOKEN_HERE` with your actual token.

### 4. Start the Production Server

```bash
./start-production.sh
```

This will:
- ✅ Start your Python WebSocket server (port 8765)
- ✅ Start ngrok tunnel
- ✅ Display your public WebSocket URL

### 5. Copy the ngrok URL

You'll see output like:

```
Forwarding  https://abc123.ngrok.io -> http://localhost:8765
```

Copy the `https://abc123.ngrok.io` URL.

### 6. Update Vercel Environment Variables

1. Go to your Vercel dashboard: https://vercel.com/dashboard
2. Select your ClawdScan project
3. Go to **Settings** → **Environment Variables**
4. Add or update:

```
NEXT_PUBLIC_WS_URL = wss://abc123.ngrok.io
```

> **Important:** Use `wss://` (secure WebSocket) instead of `https://`

5. Click **Save**
6. **Redeploy** your site for changes to take effect

---

## How to Use

### Starting the Server

Every time you want your Vercel site to work:

1. Run `./start-production.sh`
2. Keep the terminal window open
3. Your Vercel deployment will now connect to your local Python server

### Stopping the Server

Press `Ctrl+C` in the terminal running ngrok.

To stop the Python server:

```bash
# Find the process
lsof -i :8765

# Kill it (replace PID with actual process ID)
kill -9 PID
```

---

## Alternative: Static ngrok Domain (Recommended for Long-term)

With ngrok's free tier, the URL changes every time you restart. For a static URL:

1. **Upgrade to ngrok paid plan** ($8/month) for a static domain
2. Or use **CloudFlare Tunnel** (free, permanent URLs)
3. Or deploy Python server to cloud (AWS, DigitalOcean, Railway, etc.)

### Using CloudFlare Tunnel (Free Alternative)

```bash
# Install
brew install cloudflared

# Login
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create clawdscan

# Run tunnel
cloudflared tunnel --url http://localhost:8765
```

---

## Troubleshooting

### Frontend can't connect to WebSocket

**Check:**
1. Python server is running (`lsof -i :8765`)
2. ngrok is running and showing "online"
3. Vercel environment variable is set correctly with `wss://` prefix
4. You redeployed Vercel after updating env variables

### ngrok says "command not found"

Install ngrok first:
```bash
brew install ngrok
```

### Python server won't start

**Check for port conflicts:**
```bash
lsof -i :8765
```

If something is using port 8765, kill it:
```bash
kill -9 $(lsof -t -i:8765)
```

### Vercel deployment still uses localhost

Make sure:
1. Environment variable is set in Vercel dashboard (not just `.env` file)
2. Variable name is exactly `NEXT_PUBLIC_WS_URL`
3. You **redeployed** after setting the variable

---

## Local Development

For local development, you don't need ngrok:

```bash
# Terminal 1: Start Python server
cd server
python main.py

# Terminal 2: Start Next.js
npm run dev
```

The `.env` file already has `NEXT_PUBLIC_WS_URL="ws://localhost:8765"` for local development.

---

## Security Notes

- ngrok free tier URLs are public - anyone with the URL can access your WebSocket
- Consider adding authentication to your WebSocket connections for production
- Monitor ngrok bandwidth usage (free tier has limits)
- For production, deploy Python server to cloud for better security and reliability

---

## Need Help?

- ngrok docs: https://ngrok.com/docs
- Vercel env variables: https://vercel.com/docs/environment-variables
- CloudFlare Tunnel: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
