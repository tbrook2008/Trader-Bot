import pandas as pd
from datetime import datetime
import pytz

# The Holy Grail Config
CONFIG = {
    'TIMEFRAME': 1,
    'RR_RATIO': 1.0,
    'LOOKBACK_BARS': 30,
    'MAX_RISK_POINTS': 25.0,
    'MIN_FVG_POINTS': 3.0,
    'TIME_WINDOW': {'name': 'Afternoon Sniper', 'start_h': 13, 'start_m': 0, 'end_h': 15, 'end_m': 30}
}

def load_data():
    df = pd.read_csv('historical_mnq_90d.csv')
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
    df = df.sort_values('timestamp').reset_index(drop=True)
    return df

def run_simulation(df):
    trades_log = []
    in_position = False
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    side = None
    trade_start_time = None
    
    # We simulate tick-by-tick by just iterating bars since timeframe is 1m
    for i in range(CONFIG['LOOKBACK_BARS'], len(df)):
        bar = df.iloc[i]
        ts = bar['timestamp']
        
        # Check if in time window
        start_time = ts.replace(hour=CONFIG['TIME_WINDOW']['start_h'], minute=CONFIG['TIME_WINDOW']['start_m'], second=0)
        end_time = ts.replace(hour=CONFIG['TIME_WINDOW']['end_h'], minute=CONFIG['TIME_WINDOW']['end_m'], second=0)
        
        # End of day flat
        if in_position and (ts.hour >= 16 and ts.minute >= 45):
            exit_price = bar['close']
            pnl = (entry_price - exit_price) if side == 'sell' else (exit_price - entry_price)
            trades_log.append({
                'entry_time': trade_start_time,
                'exit_time': ts,
                'side': side,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl_points': pnl,
                'reason': 'EOD Close'
            })
            in_position = False
            continue
            
        if in_position:
            # Check stops and targets
            if side == 'sell':
                if bar['high'] >= stop_loss:
                    trades_log.append({
                        'entry_time': trade_start_time,
                        'exit_time': ts,
                        'side': side,
                        'entry_price': entry_price,
                        'exit_price': stop_loss,
                        'pnl_points': entry_price - stop_loss,
                        'reason': 'Stopped Out'
                    })
                    in_position = False
                elif bar['low'] <= take_profit:
                    trades_log.append({
                        'entry_time': trade_start_time,
                        'exit_time': ts,
                        'side': side,
                        'entry_price': entry_price,
                        'exit_price': take_profit,
                        'pnl_points': entry_price - take_profit,
                        'reason': 'Take Profit'
                    })
                    in_position = False
            elif side == 'buy':
                if bar['low'] <= stop_loss:
                    trades_log.append({
                        'entry_time': trade_start_time,
                        'exit_time': ts,
                        'side': side,
                        'entry_price': entry_price,
                        'exit_price': stop_loss,
                        'pnl_points': stop_loss - entry_price,
                        'reason': 'Stopped Out'
                    })
                    in_position = False
                elif bar['high'] >= take_profit:
                    trades_log.append({
                        'entry_time': trade_start_time,
                        'exit_time': ts,
                        'side': side,
                        'entry_price': entry_price,
                        'exit_price': take_profit,
                        'pnl_points': take_profit - entry_price,
                        'reason': 'Take Profit'
                    })
                    in_position = False
            continue
            
        if not (start_time <= ts <= end_time):
            continue
            
        # Check Setup
        window_df = df.iloc[i - CONFIG['LOOKBACK_BARS']:i].reset_index(drop=True)
        current_price = bar['close']
        
        # Bearish
        highest_idx = window_df['high'].idxmax()
        if highest_idx < len(window_df) - 2:
            sweep_high = window_df.loc[highest_idx, 'high']
            recent_close = window_df.iloc[-1]['close']
            if recent_close < window_df.loc[highest_idx, 'low']:
                for j in range(highest_idx, len(window_df)-2):
                    c1_low = window_df.loc[j, 'low']
                    c3_high = window_df.loc[j+2, 'high']
                    fvg_gap = c1_low - c3_high
                    if fvg_gap >= CONFIG['MIN_FVG_POINTS']:
                        entry_zone = (c3_high, c1_low)
                        sl = sweep_high
                        risk = sl - entry_zone[0]
                        if 2.0 <= risk <= CONFIG['MAX_RISK_POINTS']:
                            if current_price <= c1_low and current_price >= c3_high:
                                side = 'sell'
                                entry_price = current_price
                                stop_loss = sl
                                take_profit = entry_price - (risk * CONFIG['RR_RATIO'])
                                in_position = True
                                trade_start_time = ts
                                break
                                
        if in_position: continue
        
        # Bullish
        lowest_idx = window_df['low'].idxmin()
        if lowest_idx < len(window_df) - 2:
            sweep_low = window_df.loc[lowest_idx, 'low']
            recent_close = window_df.iloc[-1]['close']
            if recent_close > window_df.loc[lowest_idx, 'high']:
                for j in range(lowest_idx, len(window_df)-2):
                    c1_high = window_df.loc[j, 'high']
                    c3_low = window_df.loc[j+2, 'low']
                    fvg_gap = c3_low - c1_high
                    if fvg_gap >= CONFIG['MIN_FVG_POINTS']:
                        entry_zone = (c1_high, c3_low)
                        sl = sweep_low
                        risk = entry_zone[1] - sl
                        if 2.0 <= risk <= CONFIG['MAX_RISK_POINTS']:
                            if current_price >= c1_high and current_price <= c3_low:
                                side = 'buy'
                                entry_price = current_price
                                stop_loss = sl
                                take_profit = entry_price + (risk * CONFIG['RR_RATIO'])
                                in_position = True
                                trade_start_time = ts
                                break
                                
    return trades_log

def main():
    df = load_data()
    trades = run_simulation(df)
    
    print(f"Total Trades in 90 Days (Afternoon Sniper): {len(trades)}")
    print("\n================ LAST 10 TRADES ================\n")
    
    for i, t in enumerate(trades[-10:]):
        pnl_dollars = t['pnl_points'] * 2.0
        result = "🟢 WIN" if pnl_dollars > 0 else "🔴 LOSS"
        print(f"Trade #{len(trades) - 10 + i + 1} | {t['entry_time'].strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"Action: {t['side'].upper()} @ {t['entry_price']:.2f}")
        print(f"Exit:   {t['reason']} @ {t['exit_price']:.2f}")
        print(f"Result: {result} (${pnl_dollars:+.2f})")
        print("-" * 50)

if __name__ == "__main__":
    main()
