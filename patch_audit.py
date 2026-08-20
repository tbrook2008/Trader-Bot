import re

with open("bot/ivan_trader.py", "r") as f:
    content = f.read()

# 1. State Persistence for last_signals
state_load_patch = """
    consecutive_losses = state.get("consecutive_losses", 0)
    last_signals = set(state.get("last_signals", []))
"""
content = re.sub(r'consecutive_losses = state\.get\("consecutive_losses", 0\)\s*', state_load_patch, content)

# 2. Update save_state to include last_signals when starting new day
new_day_save = """save_state({
                    "current_date": current_date.strftime("%Y-%m-%d"),
                    "start_of_day_balance": start_of_day_balance,
                    "consecutive_losses": consecutive_losses,
                    "last_signals": list(last_signals)
                })"""
content = re.sub(r'save_state\(\{\s*"current_date": current_date\.strftime\("%Y-%m-%d"\),\s*"start_of_day_balance": start_of_day_balance,\s*"consecutive_losses": consecutive_losses\s*\}\)', new_day_save, content)

# 3. Update save_state when closing trade
close_trade_save = """save_state({
                                "current_date": current_date.strftime("%Y-%m-%d") if current_date else "",
                                "start_of_day_balance": start_of_day_balance,
                                "consecutive_losses": consecutive_losses,
                                "last_signals": list(last_signals)
                            })"""
content = re.sub(r'save_state\(\{\s*"current_date": current_date\.strftime\("%Y-%m-%d"\) if current_date else "",\s*"start_of_day_balance": start_of_day_balance,\s*"consecutive_losses": consecutive_losses\s*\}\)', close_trade_save, content)

# 4. Also need to save_state right after adding a new signal to last_signals
signal_add_patch = """last_signals.add(signal_hash)
                        save_state({
                            "current_date": current_date.strftime("%Y-%m-%d") if current_date else "",
                            "start_of_day_balance": start_of_day_balance,
                            "consecutive_losses": consecutive_losses,
                            "last_signals": list(last_signals)
                        })"""
content = content.replace("last_signals.add(signal_hash)", signal_add_patch)

# 5. Fix Rogue Position Polling
rogue_polling_old = """            # --- POSITION POLLING & PNL TRACKING ---
            any_in_position = False
            for symbol in SYMBOLS:
                if in_position[symbol]:
                    any_in_position = True
                    is_open = topstep.get_open_positions(symbol)
                    
                    # Prevent race condition"""

rogue_polling_new = """            # --- POSITION POLLING & PNL TRACKING ---
            any_in_position = False
            for symbol in SYMBOLS:
                try:
                    is_open = topstep.get_open_positions(symbol)
                except Exception as e:
                    logger.warning(f"Failed to check open positions for {symbol}: {e}")
                    is_open = in_position[symbol] # Fallback to our last known state

                if is_open and not in_position[symbol]:
                    logger.warning(f"⚠️ ROGUE OR DESYNCED POSITION DETECTED for {symbol}! Reconciling tracking state.")
                    in_position[symbol] = True
                    if balance_before_trade[symbol] is None:
                        balance_before_trade[symbol] = balance
                    # NOTE: We can't perfectly reconstruct trade_state, so PnL tracking might be slightly skewed until closed.

                if in_position[symbol]:
                    any_in_position = True
                    
                    # Prevent race condition"""
content = content.replace(rogue_polling_old, rogue_polling_new)

with open("bot/ivan_trader.py", "w") as f:
    f.write(content)

print("Patched successfully!")
