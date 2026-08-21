# Automated Quantitative Execution Engine (Topstep)

## 1. Project Vision
An institutional-grade, autonomous quantitative execution engine built for Topstep futures trading. Designed for continuous deployment, the system executes a proprietary Smart Money Concepts (SMC) algorithm focusing on liquidity sweeps, market structure shifts, and optimal trade entry (OTE) zones.

## 2. System Architecture
- **Environment**: Continuous deployment via `auto_updater.bat` on a dedicated Windows node.
- **Execution API**: Full integration with the TopstepX REST API (`/Auth/loginKey`, `/History/retrieveBars`, `/Order/place`, `/Position/search`).
- **Telemetry & Monitoring**:
  - Live trades pushed to a cloud PostgreSQL database (Supabase) for remote monitoring.
  - Critical alerts, daily startup checks, and trade summaries pushed instantly via Discord Webhooks.
- **State Engine**: Atomic state persistence (`bot_state.json`) prevents duplicate signal generation across hot-reloads and ensures robust pause-gate tracking.

## 3. Risk Management Infrastructure (Multi-Layer Defense)
The engine is protected by a strict, cascading sequence of risk-management layers:
1. **Goal Capture**: Immediate and permanent shutdown upon reaching the profit target.
2. **Trailing Drawdown Floor**: Dynamic EOD floor calculation synced perfectly to broker logic. Permanent shutdown on breach.
3. **Dynamic Drawdown Shield**: Auto-scales contract sizing (e.g., 4 → 2 → 1) as the account approaches the trailing floor.
4. **Pre-Trade Dollar Risk Check**: Derives true dollar risk from the tick-rounded stop-loss limit, blocking execution if the risk would violate the remaining daily loss buffer.
5. **Consistency Rule Cap**: Pauses execution once the daily profit cap is reached.
6. **Loss-Streak Breaker**: Hardware-pause until the next trading day upon 3 consecutive losses.
7. **Volatility & Event Filters**:
   - Automated news blackout (10m pre / 15m post high-impact events) via ForexFactory XML feed.
   - Sector correlation blocks (prevents simultaneous exposure in the same market sector).
   - Lunch hour liquidity exclusion.
   - End-of-Day auto-liquidation.

## 4. Key Files
| File | Purpose |
|------|---------|
| `bot/ivan_trader.py` | Main event loop, proprietary setup detection, and core risk enforcement engine. |
| `bot/execution/topstep_client.py` | TopstepX REST API client wrapper. |
| `bot/instrument_config.py` | Master dictionary for tick sizes, point values, and market sector mappings. |
| `bot/news_filter.py` | Scrapes macroeconomic event calendars to trigger trading blackouts. |
| `bot/utils/` | Contains telemetry modules for Discord and Supabase integration. |

## 5. Recent Infrastructure Patches
- Rewrote the trailing drawdown computation to track peak balance via atomic local state rather than file I/O scans.
- Hardened database and file logging with multi-channel Discord alert fail-safes.
- Refactored PnL attribution logic to support synchronous multi-sector position closing.
- Re-architected risk arithmetic to build dollar-risk calculations exclusively from tick-rounded stop floor values.
- Removed unreachable legacy blocks and archived legacy configurations.

## 6. Known Limitations
- 30s bar cache TTL means setup detection may lag real-time by up to 30 seconds.
- Trailing stops are managed software-side (moves BE locally via API cancel-and-replace).
