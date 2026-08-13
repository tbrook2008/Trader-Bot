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
        webhook_url = webhook_url.strip().strip('"').strip("'")
    
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
        webhook_url = webhook_url.strip().strip('"').strip("'")
    
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

def push_hourly_summary(balance, daily_pnl, hard_floor, active_positions):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_url:
        webhook_url = webhook_url.strip().strip('"').strip("'")
    
    if not webhook_url:
        return
        
    buffer = balance - hard_floor
    positions_str = ", ".join(active_positions) if active_positions else "None"
    
    embed = {
        "title": "📊 Hourly Status Dashboard",
        "color": 0xFFA500, # Orange for status
        "fields": [
            {"name": "Live Balance", "value": f"${balance:.2f}", "inline": True},
            {"name": "Daily P&L", "value": f"${daily_pnl:.2f}", "inline": True},
            {"name": "Active Positions", "value": positions_str, "inline": False},
            {"name": "Hard Floor", "value": f"${hard_floor:.2f}", "inline": True},
            {"name": "Drawdown Buffer", "value": f"${buffer:.2f} before fail", "inline": True},
        ],
        "footer": {"text": f"Topstep Bot | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"}
    }
    
    payload = {
        "username": "Topstep Bot",
        "embeds": [embed]
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "DiscordBot (Python)")
    
    try:
        urllib.request.urlopen(req)
        logger.info("Sent hourly summary to Discord.")
    except Exception as e:
        logger.error(f"Discord hourly summary request error: {e}")
