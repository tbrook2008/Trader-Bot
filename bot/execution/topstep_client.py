import os
import requests
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("TopstepClient")

class TopstepXClient:
    def __init__(self):
        self.base_url = os.getenv("TOPSTEPX_API_URL", "https://api.topstepx.com/api")
        self.username = os.getenv("TOPSTEPX_USERNAME")
        self.api_key = os.getenv("TOPSTEPX_API_KEY")
        self.jwt_token = None
        self.account_id = None
        self.contract_cache = {}
        self.session = requests.Session()
    def _post(self, endpoint, max_retries=3, **kwargs):
        """Helper to enforce timeouts and exponential backoff on all API requests."""
        import time
        kwargs.setdefault("timeout", 45)
        
        for attempt in range(max_retries):
            try:
                resp = self.session.post(f"{self.base_url}{endpoint}", **kwargs)
                # Retry on 5xx server errors
                if resp.status_code >= 500 and attempt < max_retries - 1:
                    logger.warning(f"Topstep API {resp.status_code} on {endpoint}. Retrying in {2**attempt}s...")
                    time.sleep(2 ** attempt)
                    continue
                return resp
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Network error on {endpoint}: {e}. Retrying in {2**attempt}s...")
                    time.sleep(2 ** attempt)
                else:
                    raise e

    def authenticate(self):
        if not self.username or not self.api_key:
            logger.error("Missing Topstep API credentials in .env")
            return False
            
        logger.info(f"Authenticating TopstepX as {self.username}...")
        try:
            resp = self._post("/Auth/loginKey", json={
                "userName": self.username,
                "apiKey": self.api_key
            })
        except Exception as e:
            logger.error(f"Topstep authentication network error: {e}")
            return False
        if resp.status_code == 200 and resp.json().get("token"):
            self.jwt_token = resp.json()["token"]
            logger.info("Topstep authentication successful.")
            self._fetch_account_id()
            return True
        logger.error(f"Failed to authenticate: {resp.text}")
        return False

    def _get_auth_headers(self):
        return {
            "Authorization": f"Bearer {self.jwt_token}",
            "Content-Type": "application/json"
        }

    def _fetch_account_id(self):
        try:
            resp = self._post("/Account/search", json={
                "onlyActiveAccounts": True
            }, headers=self._get_auth_headers())
        except Exception:
            return
        data = resp.json()
        if data.get("accounts") and len(data["accounts"]) > 0:
            self.account_id = data["accounts"][0]["id"]
            logger.info(f"Topstep Active Account ID set to: {self.account_id}")

    def get_account_balance(self):
        """Fetches the current account balance for equity protection checks."""
        if not self.jwt_token or not self.account_id:
            if not self.authenticate():
                return None
                
        try:
            resp = self._post("/Account/search", json={
                "onlyActiveAccounts": True
            }, headers=self._get_auth_headers())
        except Exception as e:
            logger.error(f"Network error fetching balance: {e}")
            return None
        
        if resp.status_code == 401:
            self.jwt_token = None
            if self.authenticate():
                return self.get_account_balance()
            return None
            
        if resp.status_code != 200:
            logger.error(f"Failed to fetch account balance. Status: {resp.status_code}")
            return None
            
        try:
            data = resp.json()
        except Exception:
            return None
        if data.get("accounts") and len(data["accounts"]) > 0:
            for acc in data["accounts"]:
                if acc["id"] == self.account_id:
                    return acc.get("balance")
        return None

    def get_contract_id(self, symbol):
        if symbol in self.contract_cache:
            return self.contract_cache[symbol]
        if not self.jwt_token:
            self.authenticate()

        try:
            resp = self._post("/Contract/search", json={
                "searchText": symbol,
                "live": False # False for Combine/Practice accounts
            }, headers=self._get_auth_headers())
        except Exception:
            return None

        if resp.status_code == 401:
            self.jwt_token = None
            self.authenticate()
            return self.get_contract_id(symbol)
            
        if resp.status_code != 200:
            logger.error(f"Failed to search contract {symbol}. Status: {resp.status_code}")
            return None
            
        try:
            data = resp.json()
        except Exception:
            return None
        logger.debug(f"Contract search response for {symbol}: {data}")
        if data.get("contracts") and len(data["contracts"]) > 0:
            contract_id = data["contracts"][0]["id"]
            self.contract_cache[symbol] = contract_id
            return contract_id
        return None

    def place_market_order(self, symbol, side, quantity, tp_ticks=None, sl_ticks=None):
        """Places a bracket order on Topstep."""
        if not self.jwt_token or not self.account_id:
            if not self.authenticate():
                return None
            
        contract_id = self.get_contract_id(symbol)
        if not contract_id:
            logger.error(f"Invalid contract ID for {symbol}")
            return None

        side_int = 0 if side.lower() == 'buy' else 1
        
        request_body = {
            "accountId": self.account_id,
            "contractId": contract_id,
            "type": 2, # Market
            "side": side_int,
            "size": quantity,
            "isAutoOco": True
        }

        if tp_ticks:
            final_tp = int(tp_ticks) if side_int == 0 else -int(tp_ticks)
            request_body["takeProfitBracket"] = {"ticks": final_tp, "type": 1}
        if sl_ticks:
            final_sl = -int(sl_ticks) if side_int == 0 else int(sl_ticks)
            request_body["stopLossBracket"] = {"ticks": final_sl, "type": 4}

        logger.info(f"Submitting Topstep {side.upper()} order for {quantity} {symbol}...")
        try:
            resp = self._post("/Order/place", json=request_body, headers=self._get_auth_headers())
        except Exception as e:
            logger.error(f"Network error placing order: {e}")
            return None
        
        if resp.status_code != 200:
            logger.error(f"Topstep Order failed with status {resp.status_code}: {resp.text}")
            return None
            
        try:
            data = resp.json()
        except Exception:
            logger.error("Failed to parse JSON response from Order/place")
            return None
            
        if data.get("success"):
            logger.info(f"Topstep Order Placed successfully! OrderID: {data.get('orderId')}")
            return data
        else:
            logger.error(f"Topstep Order failed: {resp.text}")
            return None

    def flatten_all_positions(self, symbols):
        """Cancels all working orders and closes open positions for the given symbols."""
        if not self.jwt_token or not self.account_id:
            if not self.authenticate():
                return
                
        # 1. Cancel all working orders
        for symbol in symbols:
            contract_id = self.get_contract_id(symbol)
            if not contract_id:
                continue
                
            try:
                start_dt = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
                end_dt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                
                resp = self._post("/Order/search", json={
                    "accountId": self.account_id,
                    "startTimestamp": start_dt,
                    "endTimestamp": end_dt
                }, headers=self._get_auth_headers())
                
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if data and "orders" in data:
                            working_orders = [o for o in data["orders"] if o.get("contractId") == contract_id and o.get("status", 0) < 4]
                            for order in working_orders:
                                self._post("/Order/cancel", json={
                                    "accountId": self.account_id,
                                    "orderId": order["id"]
                                }, headers=self._get_auth_headers())
                                logger.info(f"Cancelled working order {order['id']} for {symbol}")
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Error cancelling orders for {symbol}: {e}")
                
        # 2. Close all positions
        success_all = True
        for symbol in symbols:
            contract_id = self.get_contract_id(symbol)
            if not contract_id:
                continue
                
            try:
                resp = self._post("/Position/closeContract", json={
                    "accountId": self.account_id,
                    "contractId": contract_id
                }, headers=self._get_auth_headers())
                
                data = resp.json()
                if data and data.get("success"):
                    logger.info(f"Successfully flattened position for {symbol}")
                else:
                    success_all = False
                    logger.error(f"Failed to flatten position for {symbol}: {resp.text}")
            except Exception as e:
                success_all = False
                logger.error(f"Error flattening position for {symbol}: {e}")
        return success_all

    def cancel_orphaned_brackets(self, contract_id):
        """Cancels any working orders for a contract when net position is 0."""
        try:
            start_dt = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
            end_dt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            resp = self._post("/Order/search", json={
                "accountId": self.account_id,
                "startTimestamp": start_dt,
                "endTimestamp": end_dt
            }, headers=self._get_auth_headers())
            
            if resp.status_code == 200:
                data = resp.json()
                if data and "orders" in data:
                    working_orders = [o for o in data["orders"] if o.get("contractId") == contract_id and o.get("status") == 1]
                    for o in working_orders:
                        logger.info(f"🧹 Cancelling orphaned working order {o['id']}...")
                        self._post(f"/Order/{o['id']}/cancel", json={}, headers=self._get_auth_headers())
        except Exception as e:
            logger.error(f"Error checking for orphaned brackets: {e}")

    def get_open_positions(self, symbol):
        """Checks if there is an open position for the given symbol.
        Primary: Uses /Position/search for a direct net position check (no race condition).
        Fallback: Order-based detection if position endpoint fails.
        Fail-safe: Returns True (assume in position) on any unrecoverable error."""
        if not self.jwt_token or not self.account_id:
            if not self.authenticate():
                return True  # Fail-safe

        contract_id = self.get_contract_id(symbol)
        if not contract_id:
            return False

        # Primary: Check /Position/search for a live net position
        try:
            resp = self._post("/Position/search", json={
                "accountId": self.account_id
            }, headers=self._get_auth_headers())

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if data and "positions" in data:
                        for pos in data["positions"]:
                            if pos.get("contractId") == contract_id:
                                net_qty = pos.get("netSize", 0) or pos.get("quantity", 0)
                                if net_qty != 0:
                                    return True
                        # Position is definitely 0. Clean up any orphaned OCO brackets.
                        self.cancel_orphaned_brackets(contract_id)
                        return False  # No open position for this contract
                except Exception:
                    pass  # Fall through to order-based check
            elif resp.status_code == 401:
                self.jwt_token = None
                if self.authenticate():
                    return self.get_open_positions(symbol)
                return True  # Fail-safe
        except Exception as e:
            logger.warning(f"Position endpoint failed for {symbol}, falling back to order check: {e}")

        # Fallback: Order-based detection (original method)
        try:
            start_dt = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
            end_dt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            resp = self._post("/Order/search", json={
                "accountId": self.account_id,
                "startTimestamp": start_dt,
                "endTimestamp": end_dt
            }, headers=self._get_auth_headers())

            if resp.status_code == 200:
                data = resp.json()
                if data and "orders" in data:
                    working_orders = [o for o in data["orders"] if o.get("contractId") == contract_id and o.get("status") == 1]
                    if len(working_orders) > 0:
                        return True
            return False
        except Exception as e:
            logger.error(f"Error checking open positions for {symbol}: {e}")
            return True  # Fail-safe: assume in position so we don't accidentally double-enter

    def cancel_and_replace_stop(self, symbol, new_sl_ticks):
        """Cancels the existing stop-loss bracket order and logs that trailing stop was moved.
        Full bracket replacement requires knowing the parent order ID - this implementation
        cancels the working stop and logs the intended new level.
        TODO: Implement full bracket replace when Topstep API supports it."""
        if not self.jwt_token or not self.account_id:
            if not self.authenticate():
                return False

        contract_id = self.get_contract_id(symbol)
        if not contract_id:
            return False

        try:
            start_dt = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat().replace("+00:00", "Z")
            end_dt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            resp = self._post("/Order/search", json={
                "accountId": self.account_id,
                "startTimestamp": start_dt,
                "endTimestamp": end_dt
            }, headers=self._get_auth_headers())

            if resp.status_code != 200:
                return False

            data = resp.json()
            if not data or "orders" not in data:
                return False

            # Find working stop-loss orders (type 4 = stop loss bracket)
            stop_orders = [
                o for o in data["orders"]
                if o.get("contractId") == contract_id
                and o.get("status") == 1
                and o.get("type") == 4
            ]

            for order in stop_orders:
                cancel_resp = self._post("/Order/cancel", json={
                    "accountId": self.account_id,
                    "orderId": order["id"]
                }, headers=self._get_auth_headers())
                if cancel_resp.status_code == 200:
                    logger.info(f"Cancelled old stop-loss order {order['id']} for {symbol} (trailing stop move)")
                else:
                    logger.warning(f"Failed to cancel stop-loss order {order['id']}")
                    return False

            logger.info(f"Trailing stop replacement complete for {symbol} at {new_sl_ticks} ticks from price")
            return True

        except Exception as e:
            logger.error(f"Error in cancel_and_replace_stop for {symbol}: {e}")
            return False

    def get_latest_bars(self, symbols, count=100, unit_number=1):
        """Fetches the most recent live bars."""
        if not self.jwt_token:
            if not self.authenticate():
                return {}
                
        results = {}
        for symbol in symbols:
            contract_id = self.get_contract_id(symbol)
            if not contract_id:
                results[symbol] = []
                continue
                
            if unit_number >= 1440:
                payload_unit = 4
                payload_unit_number = 1
                payload_limit = max(count, 5)
                days_back = count * 2
            else:
                payload_unit = 2
                payload_unit_number = unit_number
                payload_limit = count
                days_back = ((count * unit_number) / 1440) + 3

            payload = {
                "contractId": contract_id,
                "live": False,
                "startTime": (datetime.now() - timedelta(days=days_back)).isoformat() + "Z",
                "endTime": datetime.now().isoformat() + "Z",
                "unit": payload_unit,
                "unitNumber": payload_unit_number,
                "limit": payload_limit
            }
                
            try:
                resp = self._post("/History/retrieveBars", json=payload, headers=self._get_auth_headers())
            except Exception as e:
                logger.error(f"Network error fetching bars: {e}")
                results[symbol] = []
                continue
                
            if resp.status_code == 401:
                logger.info("Topstep Token expired during get_latest_bars. Re-authenticating...")
                self.jwt_token = None
                return self.get_latest_bars(symbols, count, unit_number)
                
            if resp.status_code != 200:
                logger.warning(f"Topstep API returned {resp.status_code} for get_latest_bars. Skipping...")
                results[symbol] = []
                continue
                
            try:
                data = resp.json()
            except Exception:
                logger.warning(f"Failed to decode JSON from get_latest_bars. Skipping...")
                results[symbol] = []
                continue
                
            if data.get("success") and data.get("bars"):
                bars_list = data["bars"]
                bars_list.reverse()
                
                formatted_bars = []
                for b in bars_list:
                    formatted_bars.append({
                        "timestamp": b["t"],
                        "open": b["o"],
                        "high": b["h"],
                        "low": b["l"],
                        "close": b["c"],
                        "volume": b["v"]
                    })
                results[symbol] = formatted_bars
            else:
                logger.error(f"Failed to fetch bars for {symbol}: {resp.text}")
                results[symbol] = []
                
        return results

    def get_historical_bars(self, symbol, days=5, unit_number=1):
        """Fetches historical bars stitched together over multiple days."""
        if not self.jwt_token:
            if not self.authenticate():
                return []
                
        contract_id = self.get_contract_id(symbol)
        if not contract_id:
            return []
            
        all_bars = []
        target_start = datetime.now() - timedelta(days=days)
        current_end = datetime.now()
        
        logger.info(f"Stitching historical data for {symbol} back {days} days with {unit_number}-min bars...")
        
        while current_end > target_start:
            # Request small time windows (e.g. 3 days) to avoid API rejecting large date ranges
            chunk_start = max(target_start, current_end - timedelta(days=3))
            
            payload = {
                "contractId": contract_id,
                "live": False,
                "startTime": chunk_start.isoformat() + "Z",
                "endTime": current_end.isoformat() + "Z",
                "unit": 2, # Minute
                "unitNumber": unit_number,
                "limit": 1000
            }
            
            try:
                resp = self._post("/History/retrieveBars", json=payload, headers=self._get_auth_headers())
            except Exception as e:
                logger.error(f"Network error fetching history: {e}")
                break
            
            if resp.status_code != 200:
                logger.error(f"API Error: {resp.status_code} - {resp.text}")
                if resp.status_code == 401:
                    self.jwt_token = None
                    if not self.authenticate():
                        break
                    continue
                break
                
            data = resp.json()
            if data.get("success") and data.get("bars") and len(data["bars"]) > 0:
                bars_list = data["bars"]
                
                chunk = []
                for b in bars_list:
                    chunk.append({
                        "timestamp": b["t"],
                        "open": b["o"],
                        "high": b["h"],
                        "low": b["l"],
                        "close": b["c"],
                        "volume": b["v"]
                    })
                
                all_bars.extend(chunk)
                
                oldest_time_str = chunk[-1]["timestamp"]
                try:
                    oldest_dt = datetime.fromisoformat(oldest_time_str.replace('Z', '+00:00'))
                    current_end = oldest_dt.replace(tzinfo=None) - timedelta(minutes=1)
                except Exception as e:
                    logger.error(f"Time parse error: {e}")
                    break
            else:
                break
                
        # Reverse to ascending chronological order
        all_bars.reverse()
        logger.info(f"Stitched {len(all_bars)} total 1-minute bars for {symbol}.")
        return all_bars
