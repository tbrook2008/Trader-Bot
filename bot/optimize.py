import pandas as pd
import itertools
from datetime import datetime

# Define the grid of parameters to test
PARAM_GRID = {
    'TIMEFRAME': [1, 2, 3, 5, 10],           
    'RR_RATIO': [1.0, 1.5, 2.0, 3.0],          
    'LOOKBACK_BARS': [10, 15, 20],      
    'MAX_RISK_POINTS': [10.0, 15.0, 20.0, 30.0],
    'TIME_WINDOW': [
        {'name': 'Morning Trend', 'start_h': 13, 'start_m': 45, 'end_h': 15, 'end_m': 30},
        {'name': 'Afternoon', 'start_h': 18, 'start_m': 0, 'end_h': 19, 'end_m': 30},
        {'name': 'All Day', 'start_h': 0, 'start_m': 0, 'end_h': 23, 'end_m': 59}
    ]
}

def detect_ict_setup_fast(bars_slice, config_params, symbol="MNQ"):
    """Ultra-fast ICT scanner using native python dicts."""
    min_fvg = 0.25
    min_risk = 2.0
    max_risk = config_params['MAX_RISK_POINTS']
    
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


def simulate_backtest_fast(bars_list, config_params, symbol="MNQ"):
    """Runs a highly optimized offline simulation."""
    lookback = config_params['LOOKBACK_BARS']
    rr_ratio = config_params['RR_RATIO']
    time_window = config_params['TIME_WINDOW']
    
    st_h, st_m = time_window['start_h'], time_window['start_m']
    en_h, en_m = time_window['end_h'], time_window['end_m']
    start_minutes = st_h * 60 + st_m
    end_minutes = en_h * 60 + en_m
    
    trades = []
    net_points = 0
    wins = 0
    losses = 0
    consecutive_losses = 0
    max_consecutive_losses = 0
    
    in_position = False
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    trade_side = ""
    
    # Pre-calculate valid times to avoid date parsing in loop
    valid_time_mask = []
    for b in bars_list:
        dt = b['timestamp']
        m = dt.hour * 60 + dt.minute
        valid_time_mask.append(start_minutes <= m <= end_minutes)
    
    for i in range(lookback, len(bars_list)):
        current_bar = bars_list[i]
        
        if in_position:
            if trade_side == "buy":
                if current_bar['low'] <= stop_loss:
                    loss_pts = entry_price - stop_loss
                    net_points -= loss_pts
                    losses += 1
                    consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                    trades.append(-loss_pts)
                    in_position = False
                elif current_bar['high'] >= take_profit:
                    win_pts = take_profit - entry_price
                    net_points += win_pts
                    wins += 1
                    consecutive_losses = 0
                    trades.append(win_pts)
                    in_position = False
            elif trade_side == "sell":
                if current_bar['high'] >= stop_loss:
                    loss_pts = stop_loss - entry_price
                    net_points -= loss_pts
                    losses += 1
                    consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                    trades.append(-loss_pts)
                    in_position = False
                elif current_bar['low'] <= take_profit:
                    win_pts = entry_price - take_profit
                    net_points += win_pts
                    wins += 1
                    consecutive_losses = 0
                    trades.append(win_pts)
                    in_position = False
            continue
            
        if not valid_time_mask[i]:
            continue
            
        window = bars_list[i-lookback:i+1]
        setup = detect_ict_setup_fast(window, config_params)
        
        if setup:
            trade_side = setup['side']
            entry_price = current_bar['close']
            risk_points = setup['risk_points']
            if trade_side == "buy":
                stop_loss = entry_price - risk_points
                take_profit = entry_price + (risk_points * rr_ratio)
            else:
                stop_loss = entry_price + risk_points
                take_profit = entry_price - (risk_points * rr_ratio)
                
            in_position = True
            
    return {
        "params": config_params,
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": (wins/len(trades)*100) if trades else 0,
        "net_points": net_points,
        "net_pnl": net_points * 2, # MNQ multiplier
        "max_dd": max_consecutive_losses
    }

def main():
    print("🚀 Loading historical data...")
    df_1m = pd.read_csv("historical_mnq_30d.csv")
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_1m.set_index('timestamp', inplace=True)
    
    # Pre-resample dataframes and convert to dictionaries for ultra-fast looping
    resampled_data = {}
    print("⏳ Resampling and building memory structures...")
    for tf in PARAM_GRID['TIMEFRAME']:
        if tf == 1:
            df = df_1m
        else:
            df = df_1m.resample(f'{tf}min').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
        
        # Convert to list of dicts
        bars = []
        for index, row in df.iterrows():
            bars.append({
                'timestamp': index,
                'high': row['high'],
                'low': row['low'],
                'close': row['close']
            })
        resampled_data[tf] = bars
            
    keys, values = zip(*PARAM_GRID.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    print(f"🔬 Starting Grid Search over {len(combinations)} combinations...")
    results = []
    
    for i, config in enumerate(combinations):
        if i % 50 == 0:
            print(f"Progress: {i}/{len(combinations)}")
            
        bars_list = resampled_data[config['TIMEFRAME']]
        res = simulate_backtest_fast(bars_list, config)
        results.append(res)
        
    print("\n✅ Grid Search Complete. Filtering and Sorting...")
    
    # Filter out strategies with Max Drawdown >= 4 (Busts $400 account)
    # Require at least 5 trades
    viable = [r for r in results if r['max_dd'] < 4 and r['trades'] >= 5]
    
    viable.sort(key=lambda x: x['net_pnl'], reverse=True)
    
    print("\n🏆 TOP 5 PARAMETER CONFIGURATIONS 🏆")
    print("="*60)
    for i, r in enumerate(viable[:5]):
        p = r['params']
        print(f"Rank #{i+1}:")
        print(f"  Timeframe : {p['TIMEFRAME']} min")
        print(f"  Risk/Rwd  : {p['RR_RATIO']}x")
        print(f"  Lookback  : {p['LOOKBACK_BARS']} bars")
        print(f"  Max Risk  : {p['MAX_RISK_POINTS']} points")
        print(f"  Window    : {p['TIME_WINDOW']['name']}")
        print(f"  --> Trades: {r['trades']} | Win Rate: {r['win_rate']:.1f}% | Max DD: {r['max_dd']} | PnL: ${r['net_pnl']:.2f}")
        print("-"*60)
        
    if not viable:
        print("❌ No viable parameter combinations found that survive a 3-loss limit with >5 trades.")

if __name__ == "__main__":
    main()
