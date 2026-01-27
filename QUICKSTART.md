# 🚀 Quick Start - Production Deployment

## You're Ready to Deploy! ✅

All code changes are complete. Here's what you need to do:

## Step-by-Step Guide

### 1️⃣ Install ngrok

```bash
brew install ngrok
```

### 2️⃣ Get ngrok Auth Token

- Sign up: https://dashboard.ngrok.com/signup
- Get token: https://dashboard.ngrok.com/get-started/your-authtoken
- Configure:

```bash
ngrok config add-authtoken YOUR_TOKEN_HERE
```

### 3️⃣ Update ngrok.yml

Edit `ngrok.yml` and replace `YOUR_NGROK_AUTH_TOKEN_HERE` with your token.

### 4️⃣ Start Server

```bash
./start-production.sh
```

**You'll see:**
```
Forwarding  https://abc123.ngrok.io -> http://localhost:8765
```

**Copy this URL!** 👆

### 5️⃣ Update Vercel

1. Go to: https://vercel.com/dashboard
2. Select your ClawdScan project
3. **Settings** → **Environment Variables**
4. Add:
   - **Name:** `NEXT_PUBLIC_WS_URL`
   - **Value:** `wss://abc123.ngrok.io` (change `https` to `wss`)
5. **Save**
6. **Redeploy** your site

### 6️⃣ Test

Visit your Vercel URL - your dashboard should now connect to your local server! 🎉

---

## Important Notes

- Keep the ngrok terminal window open (closing = disconnection)
- Free ngrok URLs change when you restart
- Your Python server must be running for the site to work

---

## Files Created

- ✅ `ngrok.yml` - ngrok configuration
- ✅ `start-production.sh` - Automated startup script
- ✅ `DEPLOYMENT.md` - Full documentation
- ✅ `.env.local.example` - Environment template

## Files Modified

- ✅ `hooks/use-bot-stream.ts` - Now uses env variable
- ✅ `.env` - Added `NEXT_PUBLIC_WS_URL`

---

## Need Help?

See [DEPLOYMENT.md](DEPLOYMENT.md) for:
- Detailed instructions
- Troubleshooting
- Alternative solutions (CloudFlare Tunnel)
- Cloud deployment options
