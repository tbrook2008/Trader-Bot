# Topstep AI Quantitative Trader (V2 Architecture)

An advanced, fully autonomous quantitative trading system optimized specifically for Prop Firm evaluations (Topstep Combines).

This system was entirely refactored from a Node.js prototype into a highly robust Python V2 architecture to maximize reliability, circumvent rate limits, and implement strict risk management protocols designed to pass the combine.

---

## 📈 V2 Architecture Upgrades

### 1. Direct TopstepX Integration
The bot now bypasses simulated proxy environments (like Alpaca paper trading) and authenticates directly to TopstepX.
- Utilizes a custom-built `TopstepXClient` that handles JWT authentication and automatic token refresh.
- Includes rate-limit bypassing architecture to gracefully fetch historical and live 1-minute ticks directly from the Topstep API.

### 2. Grid-Optimized Asset Selection
Based on a massive 90-day parameter grid-search, the bot was stripped of underperforming assets (Crude Oil, Gold, Dow).
- **Exclusively trades Micro E-Mini Futures:** MNQ and MES.
- **Dynamic Timeframes:** Operates on a 5-minute timeframe for MNQ and a 10-minute timeframe for MES.
- **Full NY Session Window:** The statistical modeling proved most effective when running across the entire New York session (09:30 AM to 03:45 PM ET).

### 3. Prop Firm "Holy Grail" Risk Manager
Topstep Combine accounts have extremely strict drawdown rules. The bot integrates hardware-level safety nets:
- **Hard Floor Disconnect:** The system constantly polls account equity. If equity approaches the catastrophic failure limit (e.g., $48,000), it prevents all further entries to ensure you don't violate the rule on a drawdown spike.
- **Daily Profit Caps:** When the daily PnL hits the safety ceiling (e.g., $1,450), the bot suspends itself to secure the gains and prevent late-day volatility givebacks.
- **EOD Flattening:** A cron-based kill switch automatically flattens all open positions at 4:45 PM ET to comply with Topstep's strict 4:59 PM EOD closure rules.
- **Pass Detection:** Monitors balance in real-time and gracefully terminates the bot permanently once the $53,000 passing threshold is breached.

### 4. Macro News Filter
Topstep forbids trading during high-impact news.
- The bot features an automated `NewsFilter` that dynamically pulls the ForexFactory economic calendar.
- Automatically initiates a "Trading Blackout" window during Red Folder events, liquidating positions before the event and pausing entries until the volatility window clears.

---

## 🚀 Quickstart

### 1. Installation
Clone the repository and install the dependencies:
```bash
git clone <your-repo-url>
cd "Trader Bot"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Authentication (.env)
You must configure the `.env` file in the root directory with your Topstep credentials:
```env
TOPSTEPX_USERNAME="your_topstep_email@example.com"
TOPSTEPX_API_KEY="your_api_key"
```

### 3. Running Locally
To launch the bot locally to monitor logs:
```bash
export PYTHONPATH=.
python3 -m bot.ivan_trader
```

### 4. Running on PM2 (Production)
For a 24/7 stable server deployment, launch the bot using PM2.
```bash
npx pm2 start "python3 -m bot.ivan_trader" --name ivan_trader
```
View the logs:
```bash
npx pm2 logs ivan_trader
```

---

## ⚖️ Disclaimer
*This software is for educational and research purposes only. Do not risk money which you are afraid to lose. USE AS AT YOUR OWN RISK. The authors assume no responsibility for your trading results or prop firm evaluations.*
