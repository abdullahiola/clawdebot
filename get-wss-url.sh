#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if ngrok is running
if ! pgrep -x "ngrok" >/dev/null; then
    echo -e "${RED}❌ ngrok is not running${NC}"
    echo -e "${YELLOW}Start it with: ./start-production.sh${NC}"
    exit 1
fi

# Get the HTTPS URL
HTTPS_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"https://[^"]*"' | grep -o 'https://[^"]*' | head -1)

if [ -z "$HTTPS_URL" ]; then
    echo -e "${RED}❌ Could not retrieve ngrok URL${NC}"
    echo -e "${YELLOW}Make sure ngrok is running properly${NC}"
    exit 1
fi

# Convert to WSS
WSS_URL="${HTTPS_URL/https:/wss:}"

echo -e "${GREEN}✅ ngrok is running!${NC}\n"
echo -e "${BLUE}Your WebSocket Secure URL:${NC}"
echo -e "${GREEN}$WSS_URL${NC}\n"
echo -e "${YELLOW}Add this to Vercel as:${NC}"
echo -e "Name:  ${BLUE}NEXT_PUBLIC_WS_URL${NC}"
echo -e "Value: ${GREEN}$WSS_URL${NC}"
