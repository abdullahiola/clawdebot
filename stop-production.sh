#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${RED}🛑 Stopping ClawdScan Production Server${NC}\n"

# Kill Python server on port 8765
if lsof -Pi :8765 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}Stopping Python WebSocket server...${NC}"
    lsof -ti:8765 | xargs kill -9 2>/dev/null
    echo -e "${GREEN}✅ Python server stopped${NC}"
else
    echo -e "${YELLOW}⚠️  No Python server running on port 8765${NC}"
fi

# Kill ngrok processes
if pgrep -x "ngrok" >/dev/null; then
    echo -e "${YELLOW}Stopping ngrok tunnel...${NC}"
    pkill -9 ngrok
    echo -e "${GREEN}✅ ngrok stopped${NC}"
else
    echo -e "${YELLOW}⚠️  No ngrok processes found${NC}"
fi

echo -e "\n${GREEN}✅ All production services stopped${NC}"
