import os
import time
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import logging
import pytz

from bot.execution.topstep_client import TopstepXClient
from bot.news_filter import NewsFilter
from bot.instrument_config import INSTRUMENT_CONFIG

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IvanTraderV2")

load_dotenv()
topstep = TopstepXClient()

# Directly scan the futures symbols now!
SYMBOLS = ["MNQ", "MES"]

class BaseConfig:
    # 2. Risk Management
    CONTRACT_QTY = 1
    MAX_CONSECUTIVE_LOSSES = 3
    USE_TRAILING_STOP = True
    TRAILING_ACTIVATION_RR = 1.0

class BotConfig(BaseConfig):
    def __init__(self, name, timeframe, lookback, rr_ratio, min_risk, max_risk, min_fvg, window):
        self.NAME = name
        self.TIMEFRAME = timeframe
        self.LOOKBACK_BARS = lookback
        self.RR_RATIO = rr_ratio
        self.MIN_RISK_ATR_MULTIPLIER = min_risk
        self.MAX_RISK_ATR_MULTIPLIER = max_risk
        self.MIN_FVG_ATR_MULTIPLIER = min_fvg
        self.TIME_WINDOW = window

HOLY_GRAIL_CONFIGS = {
    "MNQ": BotConfig("MNQ Full NY", 5, 15, 3.0, 0.5, 6.0, 1.0, {"start_h": 9, "start_m": 30, "end_h": 16, "end_m": 0}),
    "MES": BotConfig("MES Full NY", 10, 20, 3.0, 0.5, 6.0, 0.1, {"start_h": 9, "start_m": 30, "end_h": 16, "end_m": 0})
}

consecutive_losses = 0
in_position = {sym: False for sym in SYMBOLS}
balance_before_trade = {sym: None for sym in SYMBOLS}

_bars_cache = {}        # {timeframe: {symbol: [bars]}}
_bars_cache_ts = {}     # {timeframe: timestamp}

def check_rejection(bars_since_fvg, zone_low, zone_high, direction):
    if bars_since_fvg.empty:
        return False
    touched_zone = ((bars_since_fvg['high'] >= zone_low) & (bars_since_fvg['low'] <= zone_high)).any()
    if not touched_zone:
        return False
    last_close = bars_since_fvg.iloc[-1]['close']
    if direction == "sell":
        return last_close < zone_low
    else:
        return last_close > zone_high

def detect_ict_setup(df, symbol, config):
    if len(df) < config.LOOKBACK_BARS:
        return None
        
    # Calculate ATR (14-period)
    df['prev_close'] = df['close'].shift(1)
    df['tr'] = df[['high', 'low', 'prev_close']].apply(
        lambda row: max(row['high'] - row['low'], 
                        abs(row['high'] - row['prev_close']) if pd.notna(row['prev_close']) else 0,
                        abs(row['low'] - row['prev_close']) if pd.notna(row['prev_close']) else 0), axis=1)
    df['atr'] = df['tr'].rolling(window=14).mean()
        
    recent_bars = df.tail(config.LOOKBACK_BARS).reset_index(drop=True)
    current_price = df.iloc[-1]['close']
    current_atr = recent_bars.iloc[-1]['atr']
    
    if pd.isna(current_atr) or current_atr == 0:
        return None
        
    min_fvg_pts = config.MIN_FVG_ATR_MULTIPLIER * current_atr
    min_risk_pts = config.MIN_RISK_ATR_MULTIPLIER * current_atr
    max_risk_pts = config.MAX_RISK_ATR_MULTIPLIER * current_atr
    
    # 1. Bearish Setup (Short)
    highest_idx = recent_bars['high'].idxmax()
    if highest_idx < len(recent_bars) - 2:
        sweep_high = recent_bars.loc[highest_idx, 'high']
        recent_close = recent_bars.iloc[-1]['close']
        if recent_close < recent_bars.loc[highest_idx, 'low']:
            for i in range(highest_idx, len(recent_bars)-2):
                c1_low = recent_bars.loc[i, 'low']
                c3_high = recent_bars.loc[i+2, 'high']
                
                fvg_gap = c1_low - c3_high
                if fvg_gap >= min_fvg_pts:
                    zone_low, zone_high = c3_high, c1_low
                    stop_loss = sweep_high
                    risk_points = stop_loss - zone_low
                    
                    if min_risk_pts <= risk_points <= max_risk_pts:
                        bars_since_fvg = recent_bars.iloc[i + 2:]
                        if check_rejection(bars_since_fvg, zone_low, zone_high, "sell"):
                            return {
                                "side": "sell",
                                "symbol": symbol,
                                "risk_points": risk_points,
                                "reason": f"Bearish Sweep -> Retrace -> Rej -> FVG (Gap: {fvg_gap:.2f}, Risk: {risk_points:.2f})",
                                "timestamp": recent_bars.loc[i+2, 'timestamp'] if 'timestamp' in recent_bars.columns else df.iloc[-1].get("timestamp", "0")
                            }

    # 2. Bullish Setup (Long)
    lowest_idx = recent_bars['low'].idxmin()
    if lowest_idx < len(recent_bars) - 2: 
        sweep_low = recent_bars.loc[lowest_idx, 'low']
        recent_close = recent_bars.iloc[-1]['close']
        if recent_close > recent_bars.loc[lowest_idx, 'high']:
            for i in range(lowest_idx, len(recent_bars)-2):
                c1_high = recent_bars.loc[i, 'high']
                c3_low = recent_bars.loc[i+2, 'low']
                
                fvg_gap = c3_low - c1_high
                if fvg_gap >= min_fvg_pts:
                    zone_low, zone_high = c1_high, c3_low
                    stop_loss = sweep_low
                    risk_points = zone_high - stop_loss
                    
                    if min_risk_pts <= risk_points <= max_risk_pts:
                        bars_since_fvg = recent_bars.iloc[i + 2:]
                        if check_rejection(bars_since_fvg, zone_low, zone_high, "buy"):
                            return {
                                "side": "buy",
                                "symbol": symbol,
                                "risk_points": risk_points,
                                "reason": f"Bullish Sweep -> Retrace -> Rej -> FVG (Gap: {fvg_gap:.2f}, Risk: {risk_points:.2f})",
                                "timestamp": recent_bars.loc[i+2, 'timestamp'] if 'timestamp' in recent_bars.columns else df.iloc[-1].get("timestamp", "0")
                            }
    return None

def get_eastern_time():
    return datetime.now(pytz.timezone('US/Eastern'))

def main():
    global consecutive_losses, in_position, balance_before_trade
    
    logger.info("🦅 IvanTrades Automated Execution Bot Started (Multi-Asset V2)")
    
    if not topstep.authenticate():
        logger.error("Could not authenticate Topstep. Check .env keys.")
        exit(1)

    # Reconcile state on startup — in case of restart while a trade is live
    for symbol in SYMBOLS:
        if topstep.get_open_positions(symbol):
            in_position[symbol] = True
            balance_before_trade[symbol] = topstep.get_account_balance()
            logger.warning(f"⚠️ STARTUP RECONCILE: Found existing open position for {symbol}. Resuming tracking.")

    news_filter = NewsFilter()
    last_signal = ""
    start_of_day_balance = None
    current_date = None
    
    while True:
        try:
            # 1. Account Equity & Goal Checks
            balance = topstep.get_account_balance()
            if balance is None:
                logger.warning("Could not fetch account balance, retrying...")
                time.sleep(10)
                continue
                
            et_now = get_eastern_time()
            if current_date != et_now.date():
                current_date = et_now.date()
                start_of_day_balance = balance
                # Reset tracking at start of new day
                consecutive_losses = 0
                logger.info(f"📅 New trading day ({current_date}). Starting balance: ${start_of_day_balance:.2f}")
                
            # --- POSITION POLLING & PNL TRACKING ---
            any_in_position = False
            for symbol in SYMBOLS:
                if in_position[symbol]:
                    any_in_position = True
                    is_open = topstep.get_open_positions(symbol)
                    if not is_open:
                        logger.info(f"🔄 Topstep reports no working orders for {symbol}. Position closed!")
                        in_position[symbol] = False
                        
                        # Track trade outcome based on balance delta
                        if balance_before_trade[symbol] is not None:
                            trade_pnl = balance - balance_before_trade[symbol]
                            if trade_pnl < 0:
                                consecutive_losses += 1
                                logger.warning(f"📉 Trade for {symbol} resulted in a loss (${trade_pnl:.2f}). Consecutive losses: {consecutive_losses}")
                            else:
                                consecutive_losses = 0
                                logger.info(f"📈 Trade for {symbol} resulted in a win (${trade_pnl:.2f}). Consecutive losses reset.")
                        balance_before_trade[symbol] = None
                
            # Check Topstep EOD 4:59 PM Rule (We liquidate at 4:45 PM to be safe)
            if (et_now.hour == 16 and et_now.minute >= 45) or (et_now.hour == 17):
                if any_in_position:
                    logger.critical("⚠️ EOD LIQUIDATION: 4:45 PM Hard Stop reached. Flattening all positions to avoid Topstep violation!")
                    if topstep.flatten_all_positions(SYMBOLS):
                        for sym in SYMBOLS:
                            in_position[sym] = False
                logger.warning("Market is in the 5:00 PM - 6:00 PM maintenance window. Bot pausing until 6:00 PM ET...")
                time.sleep(300) # Sleep 5 minutes
                continue
                
            # Check News Filter
            is_blackout, event_title = news_filter.is_news_blackout(et_now)
            if is_blackout:
                if any_in_position:
                    logger.critical(f"⚠️ FORCE CLOSING POSITIONS DUE TO NEWS EVENT: {event_title}")
                    if topstep.flatten_all_positions(SYMBOLS):
                        for sym in SYMBOLS:
                            in_position[sym] = False
                logger.warning(f"📰 News Blackout Active for: {event_title}. Pausing execution...")
                time.sleep(30)
                continue
                
            daily_pnl = balance - start_of_day_balance
            
            if balance >= 53000:
                logger.critical(f"🎉 GOAL REACHED! Balance: ${balance:.2f}. Combine passed! Shutting down.")
                break
                
            if balance <= 48000:
                logger.critical(f"🛑 HARD FLOOR HIT. Balance: ${balance:.2f}. Shutting down to prevent violation.")
                break
                
            if daily_pnl >= 1450:
                logger.info(f"💵 Daily Profit Cap Reached (${daily_pnl:.2f}). Pausing until tomorrow.")
                time.sleep(3600) # Sleep an hour, loop will re-check date
                continue
                
            if consecutive_losses >= BaseConfig.MAX_CONSECUTIVE_LOSSES:
                logger.critical("🛑 MAXIMUM DRAWDOWN LIMIT HIT. Pausing bot until next trading day.")
                while True:
                    time.sleep(300)
                    et_check = get_eastern_time()
                    if et_check.date() != current_date:
                        consecutive_losses = 0
                        logger.info("🌅 New trading day detected. Resuming trading.")
                        break
                continue
                
            # 2. Fetch Market Data dynamically based on configured timeframes
            tf_symbols = {}
            for sym in SYMBOLS:
                tf = HOLY_GRAIL_CONFIGS[sym].TIMEFRAME if sym in HOLY_GRAIL_CONFIGS else 1
                if tf not in tf_symbols:
                    tf_symbols[tf] = []
                tf_symbols[tf].append(sym)
                
            bars_data = {}
            current_ts = time.time()
            for tf, syms in tf_symbols.items():
                if tf in _bars_cache_ts and current_ts - _bars_cache_ts[tf] < 30:
                    bars_data[tf] = _bars_cache[tf]
                else:
                    # Get enough bars to cover the longest lookback plus buffer for ATR
                    fetched = topstep.get_latest_bars(syms, count=60, unit_number=tf)
                    _bars_cache[tf] = fetched
                    _bars_cache_ts[tf] = current_ts
                    bars_data[tf] = fetched
            
            for symbol in SYMBOLS:
                if in_position[symbol]:
                    continue
                    
                # Correlation Sector Exposure Check
                if symbol in INSTRUMENT_CONFIG:
                    sym_sector = INSTRUMENT_CONFIG[symbol]["sector"]
                    sector_blocked = False
                    for other_sym in SYMBOLS:
                        if in_position[other_sym] and other_sym in INSTRUMENT_CONFIG and INSTRUMENT_CONFIG[other_sym]["sector"] == sym_sector:
                            sector_blocked = True
                            break
                    if sector_blocked:
                        continue
                    
                setup = None
                active_config = HOLY_GRAIL_CONFIGS.get(symbol)
                
                if not active_config:
                    continue
                
                # 3. Dynamic Session Priority Check (Time Window from Holy Grail Config)
                is_active_session = False
                window = active_config.TIME_WINDOW
                h, m = et_now.hour, et_now.minute
                start_mins = window["start_h"] * 60 + window["start_m"]
                end_mins = window["end_h"] * 60 + window["end_m"]
                curr_mins = h * 60 + m
                if start_mins <= curr_mins <= end_mins:
                    is_active_session = True
                        
                if is_active_session:
                    tf = active_config.TIMEFRAME
                    if tf in bars_data and symbol in bars_data[tf] and bars_data[tf][symbol]:
                        df_tf = pd.DataFrame(bars_data[tf][symbol])
                        setup = detect_ict_setup(df_tf, symbol, active_config)
                        
                # 5. Execution with Hard Floor Protection
                if setup:
                    signal_hash = f"{setup['side']}-{setup['symbol']}-{setup.get('timestamp')}-{active_config.NAME}"
                    
                    if signal_hash != last_signal:
                        # Dynamic risk math based on INSTRUMENT_CONFIG
                        point_val = INSTRUMENT_CONFIG[setup['symbol']]["point_value"] if setup['symbol'] in INSTRUMENT_CONFIG else 2.0
                        tick_sz = INSTRUMENT_CONFIG[setup['symbol']]["tick_size"] if setup['symbol'] in INSTRUMENT_CONFIG else 0.25
                        
                        dollar_risk = setup['risk_points'] * point_val * active_config.CONTRACT_QTY
                        
                        if (balance - dollar_risk) < 48000:
                            logger.warning(f"🛡️ SAFETY PROTECT: {active_config.NAME} signalled trade, but risking ${dollar_risk:.2f} would drop balance (${balance:.2f}) below $48,000. Skipping!")
                            last_signal = signal_hash
                            continue
                            
                        logger.info("=" * 60)
                        logger.info(f"🚨 EXECUTING TRADE: {setup['side'].upper()} {setup['symbol']} | Strategy: {active_config.NAME}")
                        logger.info(f"📝 Setup: {setup['reason']}")
                        
                        futures_ticks = int(setup['risk_points'] / tick_sz)
                        target_ticks = int(futures_ticks * active_config.RR_RATIO)
                        futures_ticks = max(4, futures_ticks)
                            
                        logger.info(f"Order -> Stop Loss: {futures_ticks} Ticks | Take Profit: {target_ticks} Ticks")
                        
                        res = topstep.place_market_order(
                            symbol=setup['symbol'],
                            side=setup['side'],
                            quantity=active_config.CONTRACT_QTY,
                            tp_ticks=target_ticks,
                            sl_ticks=futures_ticks
                        )
                        if res:
                            in_position[setup['symbol']] = True
                            balance_before_trade[setup['symbol']] = balance
                            logger.info(f"💰 Pre-trade balance snapshot: ${balance:.2f}")
                        
                        last_signal = signal_hash
                        
            any_in_pos = any(in_position[s] for s in SYMBOLS)
            if any_in_pos:
                time.sleep(3)
            elif 9 <= et_now.hour < 16:
                time.sleep(10)  # Active session
            else:
                time.sleep(30)  # Off-hours
            
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(10)

def current_time_bucket():
    return get_eastern_time().strftime("%H:%M")

if __name__ == "__main__":
    main()
