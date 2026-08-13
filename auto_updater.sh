#!/bin/bash

echo "Starting Topstep Bot Auto-Updater..."

while true; do
    # Fetch latest from remote
    git fetch origin main > /dev/null 2>&1
    
    # Check if there are updates
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/main)
    
    if [ $LOCAL != $REMOTE ]; then
        echo "Updates found! Pulling latest code..."
        git pull origin main
        
        # If the bot is already running, kill it so it can restart with new code
        if [ ! -z "$BOT_PID" ]; then
            echo "Restarting bot..."
            kill $BOT_PID
            wait $BOT_PID 2>/dev/null
        fi
    fi
    
    # If bot is not running, start it
    if [ -z "$BOT_PID" ] || ! kill -0 $BOT_PID 2>/dev/null; then
        echo "Starting bot..."
        python3 -m bot.ivan_trader &
        BOT_PID=$!
    fi
    
    # Wait 60 seconds before checking again
    sleep 60
done
