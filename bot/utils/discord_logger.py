import os
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime

logger = logging.getLogger("DiscordLogger")

def push_trade_to_discord(symbol, side, entry_price, exit_price, pnl, balance=None):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_url:
        webhook_url = webhook_url.strip()
    
    if not webhook_url:
        logger.debug("Discord webhook URL missing. Skipping Discord sync.")
        return

    color = 0x00FF00 if pnl >= 0 else 0xFF0000 # Green for win, Red for loss
    title = f"✅ WIN: {symbol}" if pnl >= 0 else f"❌ LOSS: {symbol}"
    
    embed = {
        "title": title,
        "color": color,
        "fields": [
            {"name": "Side", "value": side, "inline": True},
            {"name": "PnL", "value": f"${pnl:.2f}", "inline": True},
            {"name": "Entry", "value": f"{entry_price}", "inline": True},
            {"name": "Exit", "value": f"{exit_price}", "inline": True},
        ],
        "footer": {"text": f"Topstep Bot | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"}
    }
    
    if balance is not None:
        embed["fields"].append({"name": "Current Balance", "value": f"${balance:.2f}", "inline": False})
        
    payload = {
        "username": "Topstep Bot",
        "embeds": [embed]
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "DiscordBot (Python)")
    
    try:
        with urllib.request.urlopen(req) as response:
            if response.status >= 200 and response.status < 300:
                logger.info(f"🚀 Synced trade to Discord: {symbol}")
            else:
                logger.error(f"Failed to sync to Discord: HTTP {response.status}")
    except urllib.error.HTTPError as e:
        logger.error(f"Discord request error (HTTP {e.code}): {e.read().decode('utf-8', errors='ignore')}")
    except Exception as e:
        logger.error(f"Discord request error: {e}")

def push_message_to_discord(message, title="Bot Status", color=0x0099FF):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_url:
        webhook_url = webhook_url.strip()
    
    if not webhook_url:
        return

    payload = {
        "username": "Topstep Bot",
        "embeds": [{
            "title": title,
            "description": message,
            "color": color,
            "footer": {"text": f"Topstep Bot | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"}
        }]
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "DiscordBot (Python)")
    
    try:
        urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        logger.error(f"Discord status request error (HTTP {e.code}): {e.read().decode('utf-8', errors='ignore')}")
    except Exception as e:
        logger.error(f"Discord status request error: {e}")
