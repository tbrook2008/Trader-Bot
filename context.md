# V2 Python/Topstep ATR-Based ICT Bot Architecture Context

## 1. Project Vision
Python autonomous ICT trading bot for $50K Topstep Combine. Refactored from a Node.js prototype into a highly robust Python V2 architecture to maximize reliability, handle direct API execution, and implement strict prop firm risk management.

## 2. Current Architecture (V2) - Data Flow
*   **Authentication & Market Data:** `TopstepXClient` authenticates via `/Auth/loginKey` (handling 401 token expiry automatically) and fetches live/historical bars directly via `/History/retrieveBars`.
*   **Execution Core:** `bot/ivan_trader.py` runs `HOLY_GRAIL_CONFIGS` which applies per-symbol, ATR-normalized `BotConfig` definitions during specified `TIME_WINDOW`s.
*   **ICT Setup Detection:** Uses a precise structural pattern: Sweep -> Retrace -> Rejection -> FVG. 
    *   **ATR-Normalized:** Minimum FVG gap and risk bounds are calculated as multipliers of a 14-period ATR (rather than fixed points).
*   **Correlation & Exposure:** Pre-trade checks against `INSTRUMENT_CONFIG` block new entries if the bot already has an open position in the same sector (e.g., `equity_index`).
*   **Deduplication:** FVG timestamp-based hashing (`side-symbol-timestamp-configNAME`) prevents revenge trading or double-entries on the same setup.
*   **News Filter:** `bot/news_filter.py` parses the ForexFactory XML feed, converted to US/Eastern, dynamically tracking USD High Impact (Red Folder) events.
*   **Order Execution:** Submits market bracket orders (entry, SL, TP) directly to Topstep via `/Order/place`.
*   **Position Tracking:** Real-time net position validation primarily via `/Position/search`, with a robust fallback to `/Order/search` working orders if the position endpoint fails.

## 3. Strategy Details (HOLY_GRAIL_CONFIGS)
Active primarily on Micro E-Mini Futures with Full NY Session exposure:

*   **MNQ (Micro Nasdaq):**
    *   Strategy: `MNQ Full NY`
    *   Timeframe: 5 min
    *   Lookback: 15 bars
    *   Risk/Reward: 3.0
    *   Risk Bounds: 0.5x to 6.0x ATR
    *   Min FVG Size: 1.0x ATR
    *   Time Window: 09:30 - 16:00 ET

*   **MES (Micro S&P 500):**
    *   Strategy: `MES Full NY`
    *   Timeframe: 10 min
    *   Lookback: 20 bars
    *   Risk/Reward: 3.0
    *   Risk Bounds: 0.5x to 6.0x ATR
    *   Min FVG Size: 0.1x ATR
    *   Time Window: 09:30 - 16:00 ET

## 4. INSTRUMENT_CONFIG

| Symbol | Sector | Tick Size | Tick Value | Point Value | Sniper Window (ET) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **MNQ** | `equity_index` | 0.25 | $0.50 | $2.00 | 13:00 - 15:30 |
| **MES** | `equity_index` | 0.25 | $1.25 | $5.00 | 13:00 - 15:30 |
| **MYM** | `equity_index` | 1.00 | $0.50 | $0.50 | 13:00 - 15:30 |
| **M2K** | `equity_index` | 0.10 | $0.50 | $5.00 | 13:00 - 15:30 |
| **NQ** | `equity_index` | 0.25 | $5.00 | $20.00 | 13:00 - 15:30 |
| **ES** | `equity_index` | 0.25 | $12.50 | $50.00 | 13:00 - 15:30 |
| **GC** | `metals` | 0.10 | $10.00 | $100.00 | 08:00 - 10:00 |
| **CL** | `energy` | 0.01 | $10.00 | $1000.00| 09:00 - 11:30 |

## 5. Risk Management Layers (Order of Precedence)
1.  **$48,000 Hard Floor:** If account equity dips below $48K, permanent shutdown prevents combine failure.
2.  **$53,000 Goal:** If balance >= $53,000, combine is passed, permanent shutdown.
3.  **$1,450 Daily Profit Cap:** Halts execution to lock in daily wins; resumes the next trading day.
4.  **MAX_CONSECUTIVE_LOSSES = 3:** Pauses bot execution until the next trading day (does NOT permanently exit).
5.  **EOD Liquidation:** Hard stop at 4:45 PM ET flattens all open positions and cancels working orders to comply with Topstep rules.
6.  **News Blackout:** Auto-flattens and halts entries 10 minutes before and 15 minutes after USD High Impact events.
7.  **Pre-Trade Dollar Risk Check:** Verifies that a generated signal's absolute dollar risk won't breach the $48K hard floor before entering.
8.  **Sector Exposure Block:** Prevents correlated overlapping trades (e.g., won't enter MNQ if already long MES).

## 6. Key Files Table
| File | Path | Description |
| :--- | :--- | :--- |
| **Execution Core** | `bot/ivan_trader.py` | Main loop, setup detection, risk checks. |
| **Topstep API Client** | `bot/execution/topstep_client.py` | Handles authentication, market data, and order routing. |
| **Instrument Config** | `bot/instrument_config.py` | Defines tick sizes, point values, and sectors for symbol matrix. |
| **News Filter** | `bot/news_filter.py` | ForexFactory XML parser and blackout logic. |
| **Global Config** | `bot/config.py` | Global tunable parameters (legacy Alpaca vars exist but V2 uses Topstep direct). |
| **Documentation** | `README.md` | General project overview. |

## 7. Running the Bot
```bash
cd Desktop/topstep-trader-bot-v2
export PYTHONPATH=.
python3 -m bot.ivan_trader
```

## 8. Topstep API Endpoints Used
*   `/Auth/loginKey`
*   `/Account/search`
*   `/Contract/search`
*   `/History/retrieveBars`
*   `/Order/place`
*   `/Order/search`
*   `/Order/cancel`
*   `/Position/search`
*   `/Position/closeContract`

## 9. Environment Variables
Stored in `.env`:
*   `TOPSTEPX_USERNAME`
*   `TOPSTEPX_API_KEY`
*   `TOPSTEPX_API_URL` (Optional, defaults to `https://api.topstepx.com/api`)

## 10. Standing Protocol
*   **Before any change:** Read `context.md` to understand system constraints.
*   **After any change:** Update `context.md`, commit with descriptive message, push to git.

## 11. Known Issues / Gotchas
*   **Token Expiry:** Topstep JWTs expire. `TopstepXClient` gracefully catches 401s on endpoints (bars, positions, orders) and re-authenticates automatically.
*   **Position Check Race Conditions:** `/Position/search` is the source of truth, but it can sometimes lag or fail. The client uses an order-based fallback search (`/Order/search`) to infer positions if the primary endpoint acts up.
*   **Trailing Stops:** Full bracket replacement is tricky; current implementation cancels the old stop-loss order but relies on the underlying logic to track intended new levels.
*   **News Filter Timestamps:** ForexFactory returns times in UTC, which the bot must accurately convert and localize to US/Eastern (`pytz.timezone('US/Eastern')`) to align with Topstep exchange time.
