# Python Alpaca Trader — Context for Future AI Agents

This document provides essential context for any AI agent continuing development or maintenance of this system. Read this **before** making any changes.

---

## Project Vision & Evolution

This project originally started as a Node.js-based application targeting Topstep Prop Firms with complex LLM (Ollama/Gemini) integration. **That architecture has been deprecated and archived.** 

The current system is a **pure Python** quantitative trading engine integrated directly with **Alpaca**. It is designed to be fully autonomous, executing deterministic mathematical strategies without LLM overhead.

---

## Current Architecture

The codebase is built on three core pillars:

1. **Market Data Streaming (`bot/live_trader.py`)**
   - Connects to Alpaca's `wss://stream.data.alpaca.markets/v2/iex`.
   - Subscribes to 1-minute bars for a configurable basket of equities (e.g., SPY, QQQ, NVDA).
   - Feeds incoming bars synchronously into the strategy engine.

2. **Strategy Engine (`bot/strategy/mean_reversion.py`)**
   - **VWAP Calculation:** Maintains a cumulative Volume Weighted Average Price for each symbol, resetting at the start of each trading day (09:30 AM ET).
   - **Z-Score Trigger:** Calculates the standard deviation of the asset's price from its VWAP.
   - **Signals:** Fires a `LONG` signal when Z-Score < -2.0, and a `SHORT` signal when Z-Score > 2.0. Signals `EXIT` when the Z-Score reverts to the opposite side of the mean.

3. **Execution Manager (`bot/execution/execution_manager.py`)**
   - **Dynamic Margin Sizing:** Queries `trading_client.get_account()` live to determine current equity and buying power. Sizes positions to risk exactly 0.5% of total equity.
   - **Order Routing:** Safely converts logic signals into Alpaca `MarketOrderRequest` payloads.
   - **Hybrid Safety Brackets:** Since Alpaca does not support trailing stops inside brackets, the bot injects a wide OCO bracket (+10% Target, -5% Stop Loss) along with the market entry. This rests on the exchange as a catastrophic fail-safe in case the VPS disconnects. Normal exits are handled dynamically by the strategy engine, which cleanly cancels the safety bracket upon closing the position.

---

## Key Files

| File | Purpose |
|------|---------|
| `bot/live_trader.py` | Entry point. Establishes the WebSocket connection and orchestrates data flow. |
| `bot/strategy/mean_reversion.py` | Core mathematical engine (VWAP, standard deviation, Z-Score). |
| `bot/execution/execution_manager.py` | Bridges strategy signals to live Alpaca orders, calculates sizing, manages safety brackets. |
| `run_backtest.py` | Backtester evaluating strategy performance across historical data. |
| `run_options_test.py` | Dedicated backtester for mapping equity signals to Options contract data. |
| `archive/` | Contains all legacy Node.js and Topstep-related code. Do not use. |

---

## Deployment & Hosting

The bot is currently deployed on a remote Linux VPS (DigitalOcean). 

**Lifecycle Management:**
The bot is daemonized using **PM2**. It must be run with the proper `PYTHONPATH` context to locate the `bot/` module.

```bash
# Correct way to restart the bot on the VPS:
cd /root/trader_bot
export PYTHONPATH=.
pm2 restart python-trader || pm2 start ./venv/bin/python3 --name python-trader --interpreter none -- -u -m bot.live_trader
```

**Connection Limits:**
Alpaca enforces a strict limit of **1 active WebSocket connection** per account. If you attempt to run `python3 -m bot.live_trader` locally while the VPS is running, one of them will crash with `ValueError: connection limit exceeded`.

---

## Known Limitations

- **Options Data Restrictions:** The `run_options_test.py` backtester is fully functional, but the Alpaca Free Tier API keys block access to historical SIP options data. The user must upgrade to a paid data plan (e.g., Alpaca Data Plus) to execute options backtests.
- **Crypto Shorting:** Alpaca does not allow shorting of cryptocurrencies. If crypto pairs are added to the symbol basket, the Execution Manager must be updated to ignore `SHORT` signals for those specific assets.
