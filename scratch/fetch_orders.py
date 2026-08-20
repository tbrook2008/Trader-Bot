import sys
import os
import json
from datetime import datetime, timezone, timedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.execution.topstep_client import TopstepXClient

def fetch_history():
    topstep = TopstepXClient()
    if not topstep.authenticate():
        print("Auth failed")
        return

    # Aug 10 00:00:00 to Aug 11 00:00:00
    start_dt = "2026-08-10T00:00:00Z"
    end_dt = "2026-08-11T00:00:00Z"

    resp = topstep._post("/Order/search", json={
        "accountId": topstep.account_id,
        "startTimestamp": start_dt,
        "endTimestamp": end_dt
    }, headers=topstep._get_auth_headers())

    if resp.status_code == 200:
        orders = resp.json().get("orders", [])
        print(f"Found {len(orders)} orders on Aug 10.")
        for o in sorted(orders, key=lambda x: x.get('timestamp', '')):
            print(f"[{o.get('timestamp')}] {o.get('side')} {o.get('quantity')} {o.get('contractName')} | Type: {o.get('type')} | Status: {o.get('status')} | Price: {o.get('fillPrice') or o.get('price')} | Bracket: {o.get('isAutoOco')}")
    else:
        print(f"Failed to fetch orders: {resp.text}")

if __name__ == "__main__":
    fetch_history()
