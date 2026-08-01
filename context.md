# IvanTrades V2 — Context & Architecture

## 1. Project Vision
Python autonomous ICT trading bot for a $50K Topstep Combine. Uses real ICT Smart Money Concepts (sweep→MSS→OTE→FVG→rejection). No indicators. No VWAP. No RSI. Pure price action.

## 2. Architecture (V2)
- Authentication via /Auth/loginKey
- Bar fetching via /History/retrieveBars with caching (30s TTL)
- HTF bias detection (30m swing structure)
- PDH/PDL high-conviction detection (daily bars, unit=4)
- ICT setup detection: Sweep → MSS (60% body displacement) → OTE zone (50-85% fib retracement) → FVG → Rejection confirm
- Sector correlation check (blocks same-sector concurrent trades)
- Lunch hour exclusion (12-1 PM ET)
- Live order execution via /Order/place with bracket TP/SL
- Trailing stop (software-side BE at +1R)
- Position tracking via /Position/search primary, /Order/search fallback

## 3. HOLY_GRAIL_CONFIGS (Per-Symbol Strategy Configs)

| Symbol | NAME | TIMEFRAME | LOOKBACK_BARS | RR_RATIO | MIN_RISK_ATR | MAX_RISK_ATR | MIN_FVG_ATR | TIME_WINDOW |
|--------|------|-----------|---------------|----------|--------------|--------------|-------------|-------------|
| **MNQ** | MNQ NY Afternoon | 15 | 20 | 1.0 | 0.5 | 5.0 | 0.5 | 13:00 - 15:30 |
| **MES** | MES NY Open | 5 | 30 | 1.0 | 0.5 | 5.0 | 0.5 | 08:30 - 11:30 |
| **MYM** | MYM NY Afternoon | 15 | 20 | 1.5 | 0.5 | 3.0 | 1.0 | 13:00 - 15:30 |

## 4. INSTRUMENT_CONFIG

| Symbol | Sector | Tick Size | Tick Value | Point Value | Sniper Window |
|--------|--------|-----------|------------|-------------|---------------|
| **MNQ** | equity_index | 0.25 | $0.50 | $2.00 | 13:00 - 15:30 |
| **MES** | equity_index | 0.25 | $1.25 | $5.00 | 13:00 - 15:30 |
| **MYM** | equity_index | 1.00 | $0.50 | $0.50 | 13:00 - 15:30 |
| **M2K** | equity_index | 0.10 | $0.50 | $5.00 | 13:00 - 15:30 |
| **NQ** | equity_index | 0.25 | $5.00 | $20.00 | 13:00 - 15:30 |
| **ES** | equity_index | 0.25 | $12.50 | $50.00 | 13:00 - 15:30 |
| **GC** | metals | 0.10 | $10.00 | $100.00 | 08:00 - 10:00 |
| **CL** | energy | 0.01 | $10.00 | $1000.00 | 09:00 - 11:30 |

## 5. Risk Management Layers (in order of precedence)
1. $53,000 goal → permanent shutdown (combine passed)
2. $48,000 hard floor → permanent shutdown (violation prevention)
3. $1,450 daily profit cap → pause until tomorrow
4. 3 consecutive losses → pause until next trading day (resumes at midnight ET)
5. EOD liquidation at 4:45 PM ET
6. News blackout (10 min before / 15 min after USD High Impact events via ForexFactory XML)
7. Sector correlation block (no two trades in same sector simultaneously)
8. Pre-trade dollar risk check (balance - dollar_risk >= $48,000)
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
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `PAPER_TRADING`

## 9. Running the Bot
```bash
cd ~/Desktop/topstep-trader-bot-v2
python3 -m bot.ivan_trader
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
