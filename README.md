# Autonomous AI Quantitative Trader

An advanced, fully autonomous quantitative trading system designed for Alpaca. This bot streams real-time data via WebSockets and executes trades using a robust statistical model based on VWAP (Volume Weighted Average Price) and Z-Score deviations.

This system is built entirely in **Python** (migrated from an earlier Node.js prototype) and is designed for stability, high-frequency data ingestion, and rigorous risk management.

---

## What It Does

The bot connects to Alpaca's live IEX WebSocket feed to monitor real-time 1-minute bars across a basket of equities (e.g., SPY, QQQ, AAPL, MSFT, NVDA). 

It utilizes a deterministic quantitative logic engine:
1. **VWAP Calculation:** Maintains an accurate daily Volume Weighted Average Price anchored to the market open.
2. **Z-Score Deviation:** Calculates the standard deviation of the asset's price from the VWAP.
3. **Execution Manager:** When the price hits an extreme statistical deviation (Z-Score > 3.0 or < -3.0), the bot identifies an exhaustion point and fires a mean-reversion trade.
4. **Position Sizing Guard:** Each trade is strictly capped at **10% of total equity** and dynamically checks live remaining Buying Power before entering to ensure the bot can seamlessly trade all 10 symbols concurrently without margin rejections.
5. **State Recovery on Boot:** The bot queries the live Alpaca API on startup and instantly re-injects any active open positions and their precise entry prices into the quantitative memory state, preventing orphaned trades.
6. **Dynamic Exits:** Positions are dynamically exited when the Z-Score normalizes (reverts to the mean or flips to the opposite side).
7. **Absolute Stop Loss & Hard Brackets:** A strict 2.0% absolute stop-loss mathematically cuts losses in the engine. Simultaneously, a hardware-level 2.0% stop-loss bracket order is attached on the broker side in case of server crashes.
8. **Volatility Guard:** If the Z-Score normalizes but the trade is losing money, the bot recognizes that volatility expanded (breaking the statistical setup) and immediately exits to cut the loss.

---

## Core Features

### Dynamic Margin Sizing
The bot is not hardcoded to a fixed cash amount. The `ExecutionManager` pulls real-time account data using `trading_client.get_account()`. 
- **Margin-Aware:** It calculates position sizing using a fixed risk profile (e.g., 0.5%) against your actual *live equity*, and then validates that order against your available *buying power*.
- **Protection:** If a trade's estimated cost exceeds your available margin, the bot dynamically scales down the share quantity to safely fit your account size.

### Hybrid Safety Brackets (OCO)
Alpaca's API limits trailing stops inside standard Bracket Orders. To guarantee safety against VPS crashes or API outages, the bot employs a "Hybrid" strategy:
- Every Market Order is wrapped in an OCO (One-Cancels-Other) Bracket containing a **+10% Take Profit** and **-5% Stop Loss**.
- These brackets exist solely as a **catastrophic safety net** living directly on Alpaca's exchange servers.
- During normal operations, the Python `ExecutionManager` acts as a dynamic software trailing stop. When the algorithm issues an `EXIT` signal, the bot sends a closing order which automatically cancels the resting safety bracket.

### Options Backtesting Engine
The repository includes `run_options_test.py`, a dedicated backtester that:
1. Dynamically queries for an active, At-The-Money (ATM) Call/Put Option.
2. Downloads historical 1-minute bars for *both* the underlying stock and the Option contract.
3. Simulates P&L by applying the VWAP entry/exit signals from the underlying equity directly onto the Option's price history.
> **Note:** To backtest options successfully, your Alpaca account must have a paid data subscription (Data Plus or Polygon.io) to access historical SIP options data.

---

## Architecture Overview

```text
Trader Bot/
├── bot/
│   ├── execution/
│   │   └── execution_manager.py     # Handles order routing, sizing, and bracket logic
│   ├── strategy/
│   │   └── mean_reversion.py        # VWAP and Z-Score math logic
│   └── live_trader.py               # Main WebSocket listener and orchestrator
├── data/
│   └── (local data storage)
├── run_backtest.py                  # Standard backtester for equities
├── run_stock_test.py                # Visual backtester for single stocks
├── run_options_test.py              # Options contract backtesting engine
├── requirements.txt                 # Python dependencies
└── .env                             # API Keys (not tracked in git)
```

---

## Quickstart

### 1. Requirements
- Python 3.10+
- An [Alpaca](https://alpaca.markets/) account (Paper or Live)

### 2. Installation
Clone the repository and install the dependencies:
```bash
git clone <your-repo-url>
cd "Trader Bot"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration
Copy the `.env.example` file to `.env`:
```bash
cp .env.example .env
```
Edit `.env` and add your Alpaca API keys. Set `ALPACA_MODE=paper` to use the paper trading environment.

### 4. Running the Backtester
To verify the math and strategy logic locally:
```bash
python3 run_stock_test.py
```

### 5. Running the Live Bot
To launch the live trading engine:
```bash
export PYTHONPATH=.
python3 -m bot.live_trader
```

---

## Cloud Deployment (VPS)

For stable 24/7 operation, deploy the bot to a cloud VPS and use `PM2` (or systemd) to daemonize the process and automatically restart it on failure.

**Starting with PM2:**
```bash
cd /path/to/trader_bot
export PYTHONPATH=.
pm2 start ./venv/bin/python3 --name python-trader --interpreter none -- -u -m bot.live_trader
pm2 save
```

**Checking Logs:**
```bash
pm2 logs python-trader
```

> **Warning:** Alpaca restricts data streams to **one connection per account**. If you attempt to run the bot locally while it is already running on the VPS, the connection will throw a `ValueError: connection limit exceeded` and crash. Ensure only one instance is running at a time.

---

## Disclaimer
*This software is for educational and research purposes only. Do not risk money which you are afraid to lose. USE AS AT YOUR OWN RISK. The authors assume no responsibility for your trading results.*
