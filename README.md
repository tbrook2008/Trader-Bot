# IvanTrades V2 — Context & Architecture

## 1. Project Vision
Python autonomous ICT trading bot for a $50K Topstep Combine. Uses real ICT Smart Money Concepts (sweep→MSS→OTE→FVG→rejection). No indicators. No VWAP. No RSI. Pure price action.

## 2. Architecture (V2)
- Authentication via /Auth/loginKey
- Bar fetching via /History/retrieveBars with caching (30s TTL)
- HTF bias detection (Dynamic: 30m swing structure for lower timeframes, 4H/240m structure for >=30m execution)
- PDH/PDL high-conviction detection (daily bars, unit=4)
- ICT setup detection: Sweep → MSS (60% body displacement) → OTE zone (50-85% fib retracement) → FVG → Rejection confirm
- Sector correlation check (blocks same-sector concurrent trades)
- Lunch hour exclusion (12-1 PM ET)
- Live order execution via /Order/place with bracket TP/SL
- Trailing stop (software-side BE at +1R)
- Position tracking via /Position/search primary, /Order/search fallback
- Live Telemetry: Pushes all closed trades (including entry/exit prices) to Supabase database.
- Discord Alerter: Pushes instant, color-coded trade results and daily startup checks to a Discord Webhook.

## 3. HOLY_GRAIL_CONFIGS (Per-Symbol Strategy Configs)

| Symbol | NAME | TIMEFRAME | LOOKBACK_BARS | RR_RATIO | MIN_RISK_ATR | MAX_RISK_ATR | MIN_FVG_ATR | TIME_WINDOW |
|--------|------|-----------|---------------|----------|--------------|--------------|-------------|-------------|
| **MNQ** | MNQ NY Runner | 3 | 20 | 1.0 | 0.5 | 3.0 | 0.25 | 09:30 - 15:30 |
| **MES** | MES Shield Sniper | 3 | 20 | 1.0 | 0.5 | 3.0 | 0.25 | 13:00 - 15:30 |

## 4. INSTRUMENT_CONFIG

| Symbol | Sector | Tick Size | Tick Value | Point Value | Sniper Window |
|--------|--------|-----------|------------|-------------|---------------|
| **MNQ** | equity_index | 0.25 | $0.50 | $2.00 | 09:30 - 15:30 |
| **MES** | equity_index | 0.25 | $1.25 | $5.00 | 13:00 - 15:30 |
| **MYM** | equity_index | 1.00 | $0.50 | $0.50 | 13:00 - 15:30 |
| **M2K** | equity_index | 0.10 | $0.50 | $5.00 | 13:00 - 15:30 |
| **NQ** | equity_index | 0.25 | $5.00 | $20.00 | 13:00 - 15:30 |
| **ES** | equity_index | 0.25 | $12.50 | $50.00 | 13:00 - 15:30 |
| **GC** | metals | 0.10 | $10.00 | $100.00 | 08:00 - 10:00 |
| **CL** | energy | 0.01 | $10.00 | $1000.00 | 09:00 - 11:30 |

## 5. Risk Management Layers (in order of precedence)
1. $53,000 goal → permanent shutdown (combine passed)
2. Dynamic Trailing Drawdown ($2k trailing floor, caps at $50k) → permanent shutdown (violation prevention)
3. Dynamic Drawdown Shield (Contract Scaling) → Scales contracts from 4 -> 2 -> 1 as balance approaches the trailing floor
4. $1,450 daily profit cap → pause until tomorrow
5. 3 consecutive losses → pause until next trading day (resumes at midnight ET)
6. EOD liquidation at 4:45 PM ET
7. News blackout (10 min before / 15 min after USD High Impact events via ForexFactory XML) with 10-minute fallback caching on API failure
8. Sector correlation block (no two trades in same sector simultaneously)
9. Pre-trade dollar risk check (balance - dollar_risk >= trailing_floor)
9. Lunch hour exclusion (12:00-1:00 PM ET)
10. Weekend closure (Friday 5PM - Sunday 6PM ET)

## 6. Key Files

| File | Purpose |
|------|---------|
| `bot/ivan_trader.py` | Main event loop, strategy configuration, setup detection, risk enforcement. |
| `bot/execution/topstep_client.py` | TopstepX REST API integration (auth, orders, positions, bars). |
| `bot/instrument_config.py` | Master dictionary for tick values, point values, and symbol sectors. |
| `bot/config.py` | General configuration constants and environment variable loading. |
| `bot/news_filter.py` | Scrapes ForexFactory for high-impact USD events to trigger news blackouts. |

## 7. Topstep API Endpoints Used
- `/Auth/loginKey`
- `/Account/search`
- `/Contract/search`
- `/History/retrieveBars`
- `/Order/place`
- `/Order/search`
- `/Order/cancel`
- `/Position/search`
- `/Position/closeContract`

## 8. Environment Variables
- `TOPSTEPX_API_URL`
- `TOPSTEPX_USERNAME`
- `TOPSTEPX_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `DISCORD_WEBHOOK_URL`
- `PAPER_TRADING`

## 9. Running the Bot (Continuous Deployment)
The production environment for this bot is a **Windows PC**.
We use a continuous deployment script (`auto_updater.bat`) that polls the GitHub repository every 60 seconds. When new code is pushed to the `main` branch, the script automatically downloads the code, safely kills the running bot, and restarts it with the new updates.

To start the bot on the Windows node, open `cmd` and run:
```cmd
cd %USERPROFILE%\Desktop\topstep-trader-bot-v2
auto_updater.bat
```

## 10. Known Gotchas
- Daily bars fetch uses unit=4 (day) not unit=2 with unitNumber=1440
- `high_conviction` override (PDH/PDL) is currently unreachable due to pause logic architecture
- Trailing stop is software-side only (moves BE locally, calls flatten_all_positions)
- last_signals set clears daily and per-symbol on position close
- 30s bar cache TTL means setup detection may lag by up to 30s

## 11. Standing Protocol
Before ANY code change: read context.md. After ANY change: update context.md, commit with descriptive message, push to git.

## 12. Recent Changes Log
- Enabled LIVE trading mode (was offline)
- Pause instead of shutdown on max losses
- Bar fetch caching (30s TTL)
- Adaptive sleep (3s/10s/30s)
- Timezone fix on current_time_bucket()
- /Position/search primary position detection
- cancel_and_replace_stop() method
- Fixed daily bars to use unit=4
- HTF 30m swing structure bias
- PDH/PDL high-conviction detection
- OTE Fibonacci filter (50-85%)
- MSS 60% body displacement requirement
- Sector correlation check restored
- last_signals daily + per-symbol clearing
- MYM LOOKBACK_BARS 10→20
- BotConfig.NAME attribute
- Lunch hour exclusion (12-1 PM ET)
- Fixed REWARD_RISK_RATIO → RR_RATIO AttributeError
- Fixed tf_symbols/bars_data scope bug in trailing stop
- Fixed df_tf entry price fallback-to-0 bug
- Synchronized Grid Search Optimizer with Live Bot logic (HTF bias, MSS, OTE)
- Dynamic HTF bias structure (30m vs 4H depending on execution timeframe)
- Added 10-minute rate-limit backoff caching to the ForexFactory news calendar to prevent 429 API spam loops
- Integrated Supabase telemetry to push live trades to website
- Added Entry/Exit price tracking to trade_log.csv
- Added Dynamic Trailing Drawdown parsing to perfectly match Topstep's end-of-day trailing rule
- Built Dynamic Drawdown Shield to safely auto-scale contracts based on buffer size
- Optimized MES & MNQ configs for the new Shield (MNQ NY Runner & MES Shield Sniper)
- **Architectural Shift**: Migrated primary production environment to Windows. Added `auto_updater.bat` for continuous deployment.
- **Bug Fix**: Replaced Mac-specific `fcntl` singleton lock with Windows-compatible `msvcrt.locking`.
- **Feature**: Added Discord Webhook integration for instant push notifications of trades and account balances.
# Automated Execution Bot V2

## Features
- **Dynamic Risk Scaling**: Evaluates buffer over hard floor and trades up to 4 Micro contracts.
- **State Persistence**: Serializes state to `bot_state.json` to prevent duplicate signals across restarts (Machine Gun Re-Entry Prevention).
- **Rogue Position Detection**: Polls Topstep API out-of-band to catch missing fills or manually executed trades that could desync the state engine.

### Supabase Telemetry
- All closed trades are automatically synced to the `trade_history` table in Supabase.
- The telemetry payload includes the asset, side, entry/exit prices, net PnL, and the **current account balance** to allow remote monitoring without querying the Topstep API.
