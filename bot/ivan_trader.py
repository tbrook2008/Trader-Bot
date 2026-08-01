import os
import sys
import time
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import logging
import pytz

# Ensure the parent directory is in the Python path so 'from bot...' imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    def __init__(self, name, TIMEFRAME, LOOKBACK_BARS, RR_RATIO, MIN_RISK_ATR_MULTIPLIER, MAX_RISK_ATR_MULTIPLIER, MIN_FVG_ATR_MULTIPLIER, TIME_WINDOW):
        self.NAME = name
        self.TIMEFRAME = TIMEFRAME
        self.LOOKBACK_BARS = LOOKBACK_BARS
        self.RR_RATIO = RR_RATIO
        self.MIN_RISK_ATR_MULTIPLIER = MIN_RISK_ATR_MULTIPLIER
        self.MAX_RISK_ATR_MULTIPLIER = MAX_RISK_ATR_MULTIPLIER
        self.MIN_FVG_ATR_MULTIPLIER = MIN_FVG_ATR_MULTIPLIER
        self.TIME_WINDOW = TIME_WINDOW

HOLY_GRAIL_CONFIGS = {
    "MNQ": BotConfig(
        "MNQ NY Afternoon",
        TIMEFRAME=15,
        RR_RATIO=1.0,
        LOOKBACK_BARS=20,
        MIN_RISK_ATR_MULTIPLIER=0.5,
        MAX_RISK_ATR_MULTIPLIER=5.0,
        MIN_FVG_ATR_MULTIPLIER=0.5,
        TIME_WINDOW={"start_h": 13, "start_m": 0, "end_h": 15, "end_m": 30}
    ),
    "MES": BotConfig(
        "MES NY Afternoon",
        TIMEFRAME=3,
        RR_RATIO=1.0,
        LOOKBACK_BARS=15,
        MIN_RISK_ATR_MULTIPLIER=0.5,
        MAX_RISK_ATR_MULTIPLIER=6.0,
        MIN_FVG_ATR_MULTIPLIER=0.25,
        TIME_WINDOW={"start_h": 13, "start_m": 0, "end_h": 15, "end_m": 30}
    )
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

def detect_ict_setup(df, df_30m, df_1d, symbol, config):
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
        
    # --- HTF Bias ---
    htf_bias = None
    if df_30m is not None and not df_30m.empty and len(df_30m) >= 20:
        last_20_30m = df_30m.tail(20).reset_index(drop=True)
        # Find the last 3 swing highs and 3 swing lows on the 30m chart
        # A swing high = higher than both neighbors; swing low = lower than both neighbors
        swing_highs = []
        swing_lows = []
        for k in range(1, len(last_20_30m) - 1):
            if last_20_30m.iloc[k]['high'] > last_20_30m.iloc[k-1]['high'] and last_20_30m.iloc[k]['high'] > last_20_30m.iloc[k+1]['high']:
                swing_highs.append(last_20_30m.iloc[k]['high'])
            if last_20_30m.iloc[k]['low'] < last_20_30m.iloc[k-1]['low'] and last_20_30m.iloc[k]['low'] < last_20_30m.iloc[k+1]['low']:
                swing_lows.append(last_20_30m.iloc[k]['low'])
        
        # Bullish structure: last 2 swing highs are Higher Highs AND last 2 swing lows are Higher Lows
        # Bearish structure: last 2 swing highs are Lower Highs AND last 2 swing lows are Lower Lows
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            hh = swing_highs[-1] > swing_highs[-2]
            hl = swing_lows[-1] > swing_lows[-2]
            lh = swing_highs[-1] < swing_highs[-2]
            ll = swing_lows[-1] < swing_lows[-2]
            if hh and hl:
                htf_bias = "buy"
            elif lh and ll:
                htf_bias = "sell"
            else:
                htf_bias = None  # Ranging — allow both directions
        else:
            htf_bias = None  # Not enough structure data
        
    # --- PDH / PDL ---
    pdh, pdl = None, None
    if df_1d is not None and not df_1d.empty and len(df_1d) >= 2:
        # Use the previous completed day (-2 because -1 is the current forming day)
        pdh = df_1d.iloc[-2]['high']
        pdl = df_1d.iloc[-2]['low']
        
    min_fvg_pts = config.MIN_FVG_ATR_MULTIPLIER * current_atr
    min_risk_pts = config.MIN_RISK_ATR_MULTIPLIER * current_atr
    max_risk_pts = config.MAX_RISK_ATR_MULTIPLIER * current_atr
    
    # 1. Bearish Setup (Short)
    if htf_bias in [None, "sell"]:
        highest_idx = recent_bars['high'].idxmax()
        if highest_idx < len(recent_bars) - 2:
            sweep_high = recent_bars.loc[highest_idx, 'high']
            sweep_low_threshold = recent_bars.loc[highest_idx, 'low']
            
            # Find MSS Displacement
            mss_idx = None
            for j in range(highest_idx + 1, len(recent_bars)):
                if recent_bars.loc[j, 'close'] < sweep_low_threshold:
                    c = recent_bars.loc[j]
                    body = abs(c['close'] - c['open'])
                    crange = c['high'] - c['low']
                    if crange > 0 and (body / crange) >= 0.60:
                        mss_idx = j
                        break
                        
            if mss_idx is not None:
                for i in range(highest_idx, len(recent_bars)-2):
                    c1_low = recent_bars.loc[i, 'low']
                    c3_high = recent_bars.loc[i+2, 'high']
                    fvg_gap = c1_low - c3_high
                    if fvg_gap >= min_fvg_pts:
                        zone_low, zone_high = c3_high, c1_low
                        stop_loss = sweep_high
                        risk_points = stop_loss - zone_low
                        
                        if min_risk_pts <= risk_points <= max_risk_pts:
                            # Fibonacci OTE Filter
                            swing_low = recent_bars.loc[highest_idx:i+2, 'low'].min()
                            move_range = sweep_high - swing_low
                            fib_618 = sweep_high - (move_range * 0.618)
                            fib_790 = sweep_high - (move_range * 0.790)
                            
                            # Price must currently be in the OTE zone
                            # OTE zone: strict ICT 61.8%-79% retracement
                            if fib_790 <= current_price <= fib_618:
                                bars_since_fvg = recent_bars.iloc[i + 2:]
                                if check_rejection(bars_since_fvg, zone_low, zone_high, "sell"):
                                    conviction = pdh is not None and abs(sweep_high - pdh) <= (0.5 * current_atr)
                                    return {
                                        "side": "sell",
                                        "symbol": symbol,
                                        "risk_points": risk_points,
                                        "high_conviction": conviction,
                                        "reason": f"Bearish Sweep (OTE+MSS) -> Retrace -> Rej -> FVG (Gap: {fvg_gap:.2f}, Risk: {risk_points:.2f})",
                                        "timestamp": recent_bars.loc[i+2, 'timestamp'] if 'timestamp' in recent_bars.columns else df.iloc[-1].get("timestamp", "0")
                                    }

    # 2. Bullish Setup (Long)
    if htf_bias in [None, "buy"]:
        lowest_idx = recent_bars['low'].idxmin()
        if lowest_idx < len(recent_bars) - 2: 
            sweep_low = recent_bars.loc[lowest_idx, 'low']
            sweep_high_threshold = recent_bars.loc[lowest_idx, 'high']
            
            # Find MSS Displacement
            mss_idx = None
            for j in range(lowest_idx + 1, len(recent_bars)):
                if recent_bars.loc[j, 'close'] > sweep_high_threshold:
                    c = recent_bars.loc[j]
                    body = abs(c['close'] - c['open'])
                    crange = c['high'] - c['low']
                    if crange > 0 and (body / crange) >= 0.60:
                        mss_idx = j
                        break
                        
            if mss_idx is not None:
                for i in range(lowest_idx, len(recent_bars)-2):
                    c1_high = recent_bars.loc[i, 'high']
                    c3_low = recent_bars.loc[i+2, 'low']
                    fvg_gap = c3_low - c1_high
                    if fvg_gap >= min_fvg_pts:
                        zone_low, zone_high = c1_high, c3_low
                        stop_loss = sweep_low
                        risk_points = zone_high - stop_loss
                        
                        if min_risk_pts <= risk_points <= max_risk_pts:
                            # Fibonacci OTE Filter
                            swing_high = recent_bars.loc[lowest_idx:i+2, 'high'].max()
                            move_range = swing_high - sweep_low
                            fib_618 = sweep_low + (move_range * 0.618)
                            fib_790 = sweep_low + (move_range * 0.790)
                            
                            # OTE zone: strict ICT 61.8%-79% retracement
                            if fib_618 <= current_price <= fib_790:
                                bars_since_fvg = recent_bars.iloc[i + 2:]
                                if check_rejection(bars_since_fvg, zone_low, zone_high, "buy"):
                                    conviction = pdl is not None and abs(sweep_low - pdl) <= (0.5 * current_atr)
                                    return {
                                        "side": "buy",
                                        "symbol": symbol,
                                        "risk_points": risk_points,
                                        "high_conviction": conviction,
                                        "reason": f"Bullish Sweep (OTE+MSS) -> Retrace -> Rej -> FVG (Gap: {fvg_gap:.2f}, Risk: {risk_points:.2f})",
                                        "timestamp": recent_bars.loc[i+2, 'timestamp'] if 'timestamp' in recent_bars.columns else df.iloc[-1].get("timestamp", "0")
                                    }
    return None

def get_eastern_time():
    return datetime.now(pytz.timezone('US/Eastern'))

def main():
    global consecutive_losses, in_position, balance_before_trade
    
    logger.info("🦅 IvanTrades Automated Execution Bot Started (Multi-Asset V2 LIVE)")
    logger.info("🟢 LIVE MODE ACTIVE: Trades will be sent directly to Topstep.")
    
    if not topstep.authenticate():
        logger.error("Could not authenticate Topstep. Check .env keys.")
        exit(1)

    # Reconcile state on startup — in case of restart while a trade is live
    for symbol in SYMBOLS:
        if topstep.get_open_positions(symbol):
            in_position[symbol] = True
            bal = topstep.get_account_balance()
            while bal is None:
                logger.warning("Could not fetch balance during reconcile, retrying...")
                time.sleep(2)
                bal = topstep.get_account_balance()
            balance_before_trade[symbol] = bal
            logger.warning(f"⚠️ STARTUP RECONCILE: Found existing open position for {symbol}. Resuming tracking.")

    news_filter = NewsFilter()
    last_signals = set()
    start_of_day_balance = None
    current_date = None
    trade_state = {}
    
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
                last_signals.clear()
                logger.info("🔄 Daily signal dedup set cleared for new trading day.")
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
                        # Clear signals for this symbol so the same FVG zone can be re-entered after a close
                        last_signals = {s for s in last_signals if f"-{symbol}-" not in s}
                        
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
                        if symbol in trade_state:
                            del trade_state[symbol]
                            
                    elif is_open and symbol in trade_state:
                        # Local Trailing Stop at +1R
                        entry = trade_state[symbol]['entry']
                        side = trade_state[symbol]['side']
                        risk = trade_state[symbol]['risk']
                        # Try to get latest price from cache (may not be available on first loop)
                        try:
                            tf = HOLY_GRAIL_CONFIGS[symbol].TIMEFRAME if symbol in HOLY_GRAIL_CONFIGS else 1
                            cached_bars = _bars_cache.get(tf, {}).get(symbol, [])
                            if cached_bars and entry != 0:
                                curr_price = cached_bars[-1]['close']
                                pnl_pts = (curr_price - entry) if side == "buy" else (entry - curr_price)
                                
                                if pnl_pts >= risk and not trade_state[symbol]['be_activated']:
                                    trade_state[symbol]['be_activated'] = True
                                    logger.info(f"🛡️ Trailing Stop: {symbol} hit +1R ({pnl_pts:.2f} pts). Stop moved to Break-Even locally!")
                                    
                                if trade_state[symbol]['be_activated'] and pnl_pts <= 0:
                                    logger.warning(f"🛡️ Trailing Stop Hit: Flattening {symbol} at Break-Even!")
                                    topstep.flatten_all_positions([symbol])
                                    cid = topstep.get_contract_id(symbol)
                                    if cid:
                                        topstep.cancel_orphaned_brackets(cid)
                                    in_position[symbol] = False
                                    # Clear signals for this symbol so the same FVG zone can be re-entered after a close
                                    last_signals = {s for s in last_signals if f"-{symbol}-" not in s}
                                    if balance_before_trade[symbol] is not None:
                                        logger.info(f"📈 Trade for {symbol} stopped at BE (${balance - balance_before_trade[symbol]:.2f}).")
                                    balance_before_trade[symbol] = None
                                    del trade_state[symbol]
                        except Exception as trail_err:
                            logger.debug(f"Trailing stop check skipped: {trail_err}")
                
            # 1. Check for Weekend / Maintenance closures
            # Weekend closure (Friday 5:00 PM ET to Sunday 6:00 PM ET)
            if (et_now.weekday() == 4 and et_now.hour >= 17) or \
               (et_now.weekday() == 5) or \
               (et_now.weekday() == 6 and et_now.hour < 18):
                logger.info("⏸️ Market is closed for the weekend. Bot sleeping until Sunday 6:00 PM ET...")
                time.sleep(3600) # Sleep for an hour and check again
                continue

            # Check Topstep EOD 4:59 PM Rule (We liquidate at 4:45 PM to be safe)
            if (et_now.hour == 16 and et_now.minute >= 45) or (et_now.hour == 17):
                if any_in_position:
                    logger.critical("⚠️ EOD LIQUIDATION: 4:45 PM Hard Stop reached. Flattening all positions to avoid Topstep violation!")
                    if topstep.flatten_all_positions(SYMBOLS):
                        for sym in SYMBOLS:
                            in_position[sym] = False
                logger.warning("Market is in the 5:00 PM - 6:00 PM daily maintenance window. Bot pausing until 6:00 PM ET...")
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
                
            # Fetch Market Data
            current_ts = time.time()
            tf_symbols = {}
            for symbol in SYMBOLS:
                if in_position[symbol]: continue
                config = HOLY_GRAIL_CONFIGS.get(symbol)
                if not config: continue
                tf = config.TIMEFRAME
                if tf not in tf_symbols: tf_symbols[tf] = []
                tf_symbols[tf].append(symbol)
                
            # Always ensure we fetch 30m, 240m (4H) and 1440m (1D) for HTF and PDH/PDL
            all_syms_to_fetch = [s for syms in tf_symbols.values() for s in syms]
            if all_syms_to_fetch:
                tf_symbols[30] = list(set(all_syms_to_fetch))
                tf_symbols[240] = list(set(all_syms_to_fetch))
                tf_symbols[1440] = list(set(all_syms_to_fetch))
                
            bars_data = {}
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
                    
                # Sector Correlation Check: block new trades if same sector already has an open position
                if symbol in INSTRUMENT_CONFIG:
                    sym_sector = INSTRUMENT_CONFIG[symbol]['sector']
                    sector_blocked = any(
                        in_position[other] and other in INSTRUMENT_CONFIG and
                        INSTRUMENT_CONFIG[other]['sector'] == sym_sector
                        for other in SYMBOLS if other != symbol
                    )
                    if sector_blocked:
                        continue
                setup = None
                df_tf = None
                active_config = HOLY_GRAIL_CONFIGS.get(symbol)
                
                if not active_config:
                    continue
                
                # 3. Dynamic Session Priority Check (Time Window from Holy Grail Config)
                is_active_session = False
                h, m = et_now.hour, et_now.minute
                curr_mins = h * 60 + m
                
                # Lunch Hour Exclusion (12:00 PM to 1:00 PM ET)
                if 12 * 60 <= curr_mins < 13 * 60:
                    is_active_session = False
                else:
                    windows = active_config.TIME_WINDOWS if hasattr(active_config, 'TIME_WINDOWS') else [active_config.TIME_WINDOW]
                    for w in windows:
                        start_mins = w["start_h"] * 60 + w["start_m"]
                        end_mins = w["end_h"] * 60 + w["end_m"]
                        if start_mins <= curr_mins <= end_mins:
                            is_active_session = True
                            break
                        
                if is_active_session:
                    tf = active_config.TIMEFRAME
                    if tf in bars_data and symbol in bars_data[tf] and bars_data[tf][symbol]:
                        df_tf = pd.DataFrame(bars_data[tf][symbol])
                        htf = 240 if tf >= 30 else 30
                        df_htf = pd.DataFrame(bars_data.get(htf, {}).get(symbol, []))
                        df_1d = pd.DataFrame(bars_data.get(1440, {}).get(symbol, []))
                        setup = detect_ict_setup(df_tf, df_htf, df_1d, symbol, active_config)
                        
                # 5. Execution with Hard Floor Protection
                if setup:
                    signal_hash = f"{setup['side']}-{setup['symbol']}-{setup.get('timestamp')}-HolyGrail"
                    
                    if signal_hash not in last_signals:
                        last_signals.add(signal_hash)
                        
                        if consecutive_losses >= 3 and not setup.get('high_conviction'):
                            logger.warning(f"🛑 Max daily losses reached (3). Setup lacked high conviction (PDH/PDL). Skipping {symbol}.")
                            continue
                            
                        # Dynamic risk math based on INSTRUMENT_CONFIG
                        point_val = INSTRUMENT_CONFIG[setup['symbol']]["point_value"] if setup['symbol'] in INSTRUMENT_CONFIG else 2.0
                        tick_sz = INSTRUMENT_CONFIG[setup['symbol']]["tick_size"] if setup['symbol'] in INSTRUMENT_CONFIG else 0.25
                        
                        dollar_risk = setup['risk_points'] * point_val * active_config.CONTRACT_QTY
                        
                        if (balance - dollar_risk) < 48000:
                            logger.warning(f"🛡️ SAFETY PROTECT: Holy Grail signalled trade, but risking ${dollar_risk:.2f} would drop balance (${balance:.2f}) below $48,000. Skipping!")
                            continue
                            
                        logger.info("=" * 60)
                        logger.info(f"🚨 [LIVE] EXECUTING TRADE: {setup['side'].upper()} {setup['symbol']} | Strategy: {active_config.NAME}")
                        logger.info(f"📝 Setup: {setup['reason']}")
                        
                        futures_ticks = int(setup['risk_points'] / tick_sz)
                        target_ticks = int(futures_ticks * active_config.RR_RATIO)
                        futures_ticks = max(4, futures_ticks)
                        logger.info(f"Live Order -> Stop Loss: {int(setup['risk_points'] / tick_sz)} Ticks | Take Profit: {int(setup['risk_points'] * active_config.RR_RATIO / tick_sz)} Ticks")
                        
                        # LIVE MODE
                        logger.info(f"💰 Risk: ${dollar_risk:.2f} | R:R: 1:{active_config.RR_RATIO}")
                        
                        if topstep.place_market_order(setup['symbol'], setup['side'], active_config.CONTRACT_QTY, 
                                                      int(setup['risk_points'] * active_config.RR_RATIO / tick_sz), 
                                                      int(setup['risk_points'] / tick_sz)):
                            in_position[setup['symbol']] = True
                            balance_before_trade[setup['symbol']] = balance
                            trade_state[setup['symbol']] = {
                                'entry': df_tf.iloc[-1]['close'],
                                'side': setup['side'],
                                'risk': setup['risk_points'],
                                'be_activated': False
                            }
                            logger.info(f"✅ Trade placed successfully for {setup['symbol']}. Pre-trade balance snapshot: ${balance:.2f}")
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
