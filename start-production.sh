#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting ClawdScan Production Server${NC}\n"

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo -e "${YELLOW}⚠️  ngrok not found!${NC}"
    echo "Install ngrok:"
    echo "  brew install ngrok    # macOS"
    echo ""
    echo "Then configure your auth token:"
    echo "  ngrok config add-authtoken YOUR_TOKEN_HERE"
    echo ""
    echo "Get your token from: https://dashboard.ngrok.com/get-started/your-authtoken"
    exit 1
fi

# Check if Python server is already running
if lsof -Pi :8765 -sTCP:LISTEN -t >/dev/null ; then
    echo -e "${GREEN}✅ Python server already running on port 8765${NC}"
else
    echo -e "${BLUE}📦 Starting Python WebSocket server...${NC}"
    cd server
    python3 main.py &
    PYTHON_PID=$!
    echo -e "${GREEN}✅ Python server started (PID: $PYTHON_PID)${NC}"
    cd ..
    
    # Wait for server to start
    sleep 3
fi

echo -e "${BLUE}🌐 Starting ngrok tunnel...${NC}"
echo ""

# Start ngrok using config file
if [ -f "ngrok.yml" ]; then
    ngrok start --config=ngrok.yml websocket
else
    # Fallback: start ngrok without config
    ngrok http 8765 --log=stdout
fi
