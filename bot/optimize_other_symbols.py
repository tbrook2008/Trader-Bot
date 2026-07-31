import pandas as pd
import itertools
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

def load_data(file_path):
    try:
        df = pd.read_csv(file_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
        df = df.sort_values('timestamp').reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Failed to load {file_path}: {e}")
        return pd.DataFrame()

def run_simulation(df, timeframe, rr_ratio, lookback, max_risk, min_fvg, start_h, start_m, end_h, end_m):
    # Resample if timeframe > 1
    if timeframe > 1:
        df_resampled = df.set_index('timestamp').resample(f'{timeframe}min', closed='left', label='left').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna().reset_index()
    else:
        df_resampled = df.copy()

    trades = 0
    wins = 0
    losses = 0
    in_position = False
    
    for i in range(lookback, len(df_resampled)):
        bar = df_resampled.iloc[i]
        ts = bar['timestamp']
        
        start_time = ts.replace(hour=start_h, minute=start_m, second=0)
        end_time = ts.replace(hour=end_h, minute=end_m, second=0)
        
        # Check window
        if not (start_time <= ts <= end_time):
            continue
            
        window = df_resampled.iloc[i - lookback:i].reset_index(drop=True)
        current_price = bar['close']
        
        # Bearish setup
        highest_idx = window['high'].idxmax()
        if highest_idx < len(window) - 2:
            sweep_high = window.loc[highest_idx, 'high']
            recent_close = window.iloc[-1]['close']
            if recent_close < window.loc[highest_idx, 'low']:
                for j in range(highest_idx, len(window)-2):
                    c1_low = window.loc[j, 'low']
                    c3_high = window.loc[j+2, 'high']
                    fvg_gap = c1_low - c3_high
                    if fvg_gap >= min_fvg:
                        entry_zone = (c3_high, c1_low)
                        sl = sweep_high
                        risk = sl - entry_zone[0]
                        if 2.0 <= risk <= max_risk:
                            if current_price <= c1_low and current_price >= c3_high:
                                trades += 1
                                # Simulate hit
                                if (i + 1) < len(df_resampled):
                                    next_bar = df_resampled.iloc[i+1]
                                    target = current_price - (risk * rr_ratio)
                                    if next_bar['low'] <= target: wins += 1
                                    else: losses += 1
                                in_position = True
                                break
                                
        if in_position:
            in_position = False
            continue
            
        # Bullish setup
        lowest_idx = window['low'].idxmin()
        if lowest_idx < len(window) - 2:
            sweep_low = window.loc[lowest_idx, 'low']
            recent_close = window.iloc[-1]['close']
            if recent_close > window.loc[lowest_idx, 'high']:
                for j in range(lowest_idx, len(window)-2):
                    c1_high = window.loc[j, 'high']
                    c3_low = window.loc[j+2, 'low']
                    fvg_gap = c3_low - c1_high
                    if fvg_gap >= min_fvg:
                        entry_zone = (c1_high, c3_low)
                        sl = sweep_low
                        risk = entry_zone[1] - sl
                        if 2.0 <= risk <= max_risk:
                            if current_price >= c1_high and current_price <= c3_low:
                                trades += 1
                                if (i + 1) < len(df_resampled):
                                    next_bar = df_resampled.iloc[i+1]
                                    target = current_price + (risk * rr_ratio)
                                    if next_bar['high'] >= target: wins += 1
                                    else: losses += 1
                                in_position = True
                                break
        if in_position:
            in_position = False
            continue
            
    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / trades * 100) if trades > 0 else 0
    }

def worker(params, df):
    res = run_simulation(df, *params)
    return {
        "params": params,
        "results": res
    }

def optimize_asset(name, df, fvg_range, risk_range):
    if df.empty:
        print(f"Skipping {name}, no data.")
        return
        
    print(f"\n🚀 Starting Optimization for {name} ({len(df)} bars)")
    
    timeframes = [1, 3]
    rr_ratios = [1.0, 1.5, 2.0]
    lookbacks = [20, 30]
    windows = [
        (9, 30, 11, 30), # Morning
        (13, 0, 15, 30), # Afternoon
    ]
    
    grid = list(itertools.product(
        timeframes, rr_ratios, lookbacks, risk_range, fvg_range,
        [w[0] for w in windows], [w[1] for w in windows], [w[2] for w in windows], [w[3] for w in windows]
    ))
    
    best_wr = 0
    best_res = None
    best_params = None
    
    # Filter valid windows
    valid_grid = []
    for g in grid:
        # Match start/end pairs
        if (g[5], g[6], g[7], g[8]) in windows:
            valid_grid.append(g)
            
    print(f"Testing {len(valid_grid)} parameter combinations...")
    
    with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
        futures = [executor.submit(worker, p, df) for p in valid_grid]
        for f in futures:
            res = f.result()
            r = res['results']
            if r['trades'] >= 10:
                if r['win_rate'] > best_wr:
                    best_wr = r['win_rate']
                    best_res = r
                    best_params = res['params']
                    
    print(f"\n🏆 Best Result for {name}:")
    if best_params:
        print(f"Timeframe: {best_params[0]}m")
        print(f"RR: {best_params[1]}")
        print(f"FVG Gap: >={best_params[4]} pts")
        print(f"Max Risk: <={best_params[3]} pts")
        print(f"Window: {best_params[5]}:{best_params[6]} to {best_params[7]}:{best_params[8]}")
        print(f"Win Rate: {best_res['win_rate']:.1f}% ({best_res['wins']}W / {best_res['losses']}L)")
    else:
        print("No profitable combinations found with >10 trades.")

def main():
    mym_df = load_data('historical_mym_30d.csv')
    optimize_asset('MYM (Dow Jones)', mym_df, fvg_range=[3.0, 5.0, 10.0, 15.0], risk_range=[30.0, 50.0, 80.0])
    
    m2k_df = load_data('historical_m2k_30d.csv')
    optimize_asset('M2K (Russell 2000)', m2k_df, fvg_range=[0.5, 1.0, 2.0], risk_range=[3.0, 5.0, 10.0])

if __name__ == "__main__":
    main()
