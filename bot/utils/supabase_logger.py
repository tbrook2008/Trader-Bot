import os
import json
import logging
from datetime import datetime
import urllib.request

logger = logging.getLogger("SupabaseLogger")

def push_trade_to_supabase(symbol, side, entry_price, exit_price, pnl, balance):
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.warning("Supabase credentials missing. Skipping cloud sync.")
        return

    url = f"{supabase_url}/rest/v1/trade_history"
    
    payload = {
        "bot_name": "Topstep Bot",
        "trade_date": datetime.utcnow().isoformat() + "Z",
        "asset": symbol,
        "side": side,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pnl": pnl
    }
    
    data = json.dumps(payload).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("apikey", supabase_key)
    req.add_header("Authorization", f"Bearer {supabase_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    
    try:
        with urllib.request.urlopen(req) as response:  # nosec B310
            if response.status >= 200 and response.status < 300:
                logger.info(f"✅ Synced trade to Supabase: {symbol} PnL: ${pnl:.2f}")
            else:
                logger.error(f"Failed to sync trade to Supabase: HTTP {response.status}")
    except Exception as e:
        logger.error(f"Supabase request error: {e}")
