#!/bin/bash
echo "📡 Connecting to remote trading server (165.227.200.194)..."
ssh -o StrictHostKeyChecking=no root@165.227.200.194 "tail -f /root/trader_bot/live_trader.log"
