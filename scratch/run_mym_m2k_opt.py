import pandas as pd
import itertools
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import sys
import os

sys.path.append("/Users/tbrook/Desktop/topstep-trader-bot-v2")
from bot.optimize_v2 import simulate_backtest_fast

def calculate_atr(df, period=14):
    df['prev_close'] = df['close'].shift(1)
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['prev_close'])
    df['tr3'] = abs(df['low'] - df['prev_close'])
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=period).mean()
    return df

def resample_and_convert(df, timeframe):
    if timeframe > 1:
        resampled = df.set_index('timestamp').resample(f'{timeframe}min', closed='left', label='left').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna().reset_index()
    else:
        resampled = df.copy()
    
    resampled = calculate_atr(resampled, 14)
    # drop nas for clean simulation
    resampled = resampled.dropna(subset=['atr']).reset_index(drop=True)
    return resampled.to_dict('records')

def worker_task(params):
    tf, rr, lookback, max_r, min_fvg, w_name, st_h, st_m, en_h, en_m, bars_list, point_value = params
    config = {
        'TIMEFRAME': tf,
        'RR_RATIO': rr,
        'LOOKBACK_BARS': lookback,
        'MIN_RISK_ATR_MULTIPLIER': 0.5,
        'MAX_RISK_ATR_MULTIPLIER': max_r,
        'MIN_FVG_ATR_MULTIPLIER': min_fvg,
        'TIME_WINDOW': {'name': w_name, 'start_h': st_h, 'start_m': st_m, 'end_h': en_h, 'end_m': en_m}
    }
    res = simulate_backtest_fast(bars_list, config, point_value=point_value)
    return res

def run_optimization(asset_name, file_path, point_value):
    print(f"\n🚀 Loading {asset_name} from {file_path}")
    if not os.path.exists(file_path):
        print("File not found!")
        return
        
    df = pd.read_csv(file_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    timeframes = [1, 3, 5, 10, 15]
    rr_ratios = [1.0, 1.5, 2.0, 3.0]
    lookbacks = [20, 30]
    max_risks = [2.0, 3.0, 5.0]
    min_fvgs = [0.25, 0.5, 1.0, 1.5]
    windows = [
        ('Morning Sniper', 8, 30, 11, 30),
        ('Afternoon Sniper', 13, 0, 15, 30),
        ('Full NY Session', 9, 30, 16, 0)
    ]
    
    print("Pre-computing timeframes...")
    bars_by_tf = {}
    for tf in timeframes:
        bars_by_tf[tf] = resample_and_convert(df, tf)
        
    tasks = []
    for tf, rr, lb, max_r, min_fvg, w in itertools.product(timeframes, rr_ratios, lookbacks, max_risks, min_fvgs, windows):
        tasks.append((tf, rr, lb, max_r, min_fvg, w[0], w[1], w[2], w[3], w[4], bars_by_tf[tf], point_value))
        
    print(f"Running {len(tasks)} combinations using {multiprocessing.cpu_count()} cores...")
    
    results = []
    with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
        for res in executor.map(worker_task, tasks, chunksize=50):
            if res['trades'] >= 20 and res['win_rate'] >= 55.0 and res['net_pnl'] > 0:
                results.append(res)
                
    results.sort(key=lambda x: (x['net_pnl'] * (x['win_rate'] / 100)), reverse=True)
    
    print(f"\n🏆 TOP 5 CONFIGS FOR {asset_name}:")
    for r in results[:5]:
        p = r['params']
        print("-" * 40)
        print(f"Timeframe: {p['TIMEFRAME']}m | Window: {p['TIME_WINDOW']['name']}")
        print(f"RR: {p['RR_RATIO']} | Min FVG ATR: {p['MIN_FVG_ATR_MULTIPLIER']} | Max Risk ATR: {p['MAX_RISK_ATR_MULTIPLIER']}")
        print(f"Trades: {r['trades']} | Win Rate: {r['win_rate']:.1f}%")
        print(f"Net Points: {r['net_points']:.2f} | PnL: ${r['net_pnl']:.2f} | Max DD: {r['max_dd']} losses")
        
def main():
    # MYM is $0.50 per point
    run_optimization("MYM (Micro Dow - 2 Years)", "data/historical/historical_mym_2yr.csv", point_value=0.50)
    
    # M2K is $5.00 per point
    run_optimization("M2K (Micro Russell - 30 Days)", "data/historical/historical_m2k_30d.csv", point_value=5.00)

if __name__ == '__main__':
    main()
