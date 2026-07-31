import pandas as pd
import pytz
from datetime import datetime
from bot.ivan_trader import detect_ict_setup, AfternoonSniperConfig, ConsistentGrinderConfig

def main():
    print("🚀 Loading historical data for Dual-Strategy Backtest...")
    df_1m = pd.read_csv("historical_mnq_30d.csv")
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    
    # Convert UTC timestamps to US/Eastern to match live bot logic
    df_1m['timestamp'] = df_1m['timestamp'].dt.tz_convert('US/Eastern')
    df_1m.set_index('timestamp', inplace=True)
    
    print("⏳ Resampling to 3-minute bars...")
    df = df_1m.resample('3min').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    
    # Convert to list of dicts for ultra-fast loop
    bars = []
    for index, row in df.iterrows():
        bars.append({
            'timestamp': index,
            'high': row['high'],
            'low': row['low'],
            'close': row['close']
        })
        
    print(f"🔬 Simulating over {len(bars)} 3-minute bars (~30 days)...")
    
    balance = 48400.58
    start_of_day_balance = balance
    current_date = bars[0]['timestamp'].date()
    
    in_position = False
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    trade_side = ""
    active_strategy = ""
    
    trades = []
    wins = 0
    losses = 0
    consecutive_losses = 0
    max_consecutive_losses = 0
    
    # Precalculate for detect_ict_setup
    # We will just use the pandas-based one for simplicity, passing small slices
    # Wait, the pandas one takes a DataFrame, which is slow in a 10,000 bar loop.
    # Let's use the fast dict one from optimize.py
    
    def detect_ict_setup_fast(bars_slice, min_fvg, min_risk, max_risk):
        current_price = bars_slice[-1]['close']
        # Bearish
        highest_idx = 0
        highest_val = -float('inf')
        for i, b in enumerate(bars_slice):
            if b['high'] > highest_val:
                highest_val = b['high']
                highest_idx = i
                
        if highest_idx < len(bars_slice) - 2:
            sweep_high = highest_val
            if bars_slice[-1]['close'] < bars_slice[highest_idx]['low']:
                for i in range(highest_idx, len(bars_slice)-2):
                    c1_low = bars_slice[i]['low']
                    c3_high = bars_slice[i+2]['high']
                    fvg_gap = c1_low - c3_high
                    if fvg_gap >= min_fvg:
                        entry_zone = (c3_high, c1_low)
                        risk_points = sweep_high - entry_zone[0]
                        if min_risk <= risk_points <= max_risk:
                            if c3_high <= current_price <= c1_low:
                                return {"side": "sell", "risk_points": risk_points}
                                
        # Bullish
        lowest_idx = 0
        lowest_val = float('inf')
        for i, b in enumerate(bars_slice):
            if b['low'] < lowest_val:
                lowest_val = b['low']
                lowest_idx = i
                
        if lowest_idx < len(bars_slice) - 2:
            sweep_low = lowest_val
            if bars_slice[-1]['close'] > bars_slice[lowest_idx]['high']:
                for i in range(lowest_idx, len(bars_slice)-2):
                    c1_high = bars_slice[i]['high']
                    c3_low = bars_slice[i+2]['low']
                    fvg_gap = c3_low - c1_high
                    if fvg_gap >= min_fvg:
                        entry_zone = (c1_high, c3_low)
                        risk_points = entry_zone[1] - sweep_low
                        if min_risk <= risk_points <= max_risk:
                            if c1_high <= current_price <= c3_low:
                                return {"side": "buy", "risk_points": risk_points}
        return None

    # We need the maximum lookback to start
    max_lookback = max(AfternoonSniperConfig.LOOKBACK_BARS, ConsistentGrinderConfig.LOOKBACK_BARS)
    
    for i in range(max_lookback, len(bars)):
        current_bar = bars[i]
        dt = current_bar['timestamp']
        
        # Date change check
        if dt.date() != current_date:
            current_date = dt.date()
            start_of_day_balance = balance
            
        if balance >= 53000:
            print(f"🎉 GOAL REACHED at {dt}! Balance: ${balance:.2f}. Combine passed!")
            break
            
        if balance <= 48000:
            print(f"🛑 HARD FLOOR HIT at {dt}. Balance: ${balance:.2f}. Failed.")
            break
            
        daily_pnl = balance - start_of_day_balance
        if daily_pnl >= 1450:
            # Paused for the rest of the day
            continue
            
        if consecutive_losses >= 3:
            # Bot shuts down in real life, but for backtest we'll just stop
            print(f"🛑 MAXIMUM DRAWDOWN LIMIT HIT (3 losses) at {dt}. Balance: ${balance:.2f}")
            break
            
        if in_position:
            if trade_side == "buy":
                if current_bar['low'] <= stop_loss:
                    loss_pts = entry_price - stop_loss
                    dollar_loss = loss_pts * 2.0
                    balance -= dollar_loss
                    losses += 1
                    consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                    trades.append({'date': dt, 'strat': active_strategy, 'side': 'LONG', 'pnl': -dollar_loss, 'bal': balance})
                    in_position = False
                elif current_bar['high'] >= take_profit:
                    win_pts = take_profit - entry_price
                    dollar_win = win_pts * 2.0
                    balance += dollar_win
                    wins += 1
                    consecutive_losses = 0
                    trades.append({'date': dt, 'strat': active_strategy, 'side': 'LONG', 'pnl': dollar_win, 'bal': balance})
                    in_position = False
            elif trade_side == "sell":
                if current_bar['high'] >= stop_loss:
                    loss_pts = stop_loss - entry_price
                    dollar_loss = loss_pts * 2.0
                    balance -= dollar_loss
                    losses += 1
                    consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                    trades.append({'date': dt, 'strat': active_strategy, 'side': 'SHORT', 'pnl': -dollar_loss, 'bal': balance})
                    in_position = False
                elif current_bar['low'] <= take_profit:
                    win_pts = entry_price - take_profit
                    dollar_win = win_pts * 2.0
                    balance += dollar_win
                    wins += 1
                    consecutive_losses = 0
                    trades.append({'date': dt, 'strat': active_strategy, 'side': 'SHORT', 'pnl': dollar_win, 'bal': balance})
                    in_position = False
            continue
            
        setup = None
        active_config = None
        
        # Afternoon Sniper Check
        if 13 <= dt.hour <= 15:
            if dt.hour != 15 or dt.minute <= 30:
                window = bars[i-AfternoonSniperConfig.LOOKBACK_BARS:i+1]
                sniper_setup = detect_ict_setup_fast(
                    window, 
                    AfternoonSniperConfig.MIN_FVG_POINTS, 
                    AfternoonSniperConfig.MIN_RISK_POINTS, 
                    AfternoonSniperConfig.MAX_RISK_POINTS
                )
                if sniper_setup:
                    setup = sniper_setup
                    active_config = AfternoonSniperConfig
                    
        # Grinder Check
        if not setup:
            window = bars[i-ConsistentGrinderConfig.LOOKBACK_BARS:i+1]
            grinder_setup = detect_ict_setup_fast(
                window, 
                ConsistentGrinderConfig.MIN_FVG_POINTS, 
                ConsistentGrinderConfig.MIN_RISK_POINTS, 
                ConsistentGrinderConfig.MAX_RISK_POINTS
            )
            if grinder_setup:
                setup = grinder_setup
                active_config = ConsistentGrinderConfig
                
        if setup:
            dollar_risk = setup['risk_points'] * 2.0 * active_config.CONTRACT_QTY
            
            if (balance - dollar_risk) < 48000:
                # Skipped trade
                continue
                
            trade_side = setup['side']
            entry_price = current_bar['close']
            active_strategy = active_config.NAME
            
            if trade_side == "buy":
                stop_loss = entry_price - setup['risk_points']
                take_profit = entry_price + (setup['risk_points'] * active_config.RR_RATIO)
            else:
                stop_loss = entry_price + setup['risk_points']
                take_profit = entry_price - (setup['risk_points'] * active_config.RR_RATIO)
                
            in_position = True

    print("\n✅ Simulation Complete.")
    print("="*60)
    print(f"Final Balance    : ${balance:.2f} (Started: $48,400.58)")
    print(f"Total Trades     : {len(trades)}")
    print(f"Total Wins       : {wins}")
    print(f"Total Losses     : {losses}")
    print(f"Win Rate         : {(wins/len(trades)*100) if trades else 0:.1f}%")
    print(f"Max Consec Losses: {max_consecutive_losses}")
    
    print("\nTrade Log (Last 10):")
    for t in trades[-10:]:
        print(f"{t['date'].strftime('%Y-%m-%d %H:%M')} | {t['strat'][:10]:<10} | {t['side']:<5} | PnL: ${t['pnl']:>6.2f} | Bal: ${t['bal']:.2f}")

if __name__ == "__main__":
    main()
