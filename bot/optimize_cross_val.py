import pandas as pd
import itertools
from datetime import datetime
import json
from multiprocessing import Pool, cpu_count
import sys
import os
from bot.optimize_v2 import simulate_backtest_fast, PARAM_GRID

def build_resampled_dict(df, timeframes):
    resampled_data = {}
    for tf in timeframes:
        if tf == 1:
            res_df = df.copy()
        else:
            res_df = df.resample(f'{tf}min').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
        res_df['prev_close'] = res_df['close'].shift(1)
        res_df['tr'] = res_df[['high', 'low', 'prev_close']].apply(
            lambda row: max(row['high'] - row['low'], 
                            abs(row['high'] - row['prev_close']) if pd.notna(row['prev_close']) else 0,
                            abs(row['low'] - row['prev_close']) if pd.notna(row['prev_close']) else 0), axis=1)
        res_df['atr'] = res_df['tr'].rolling(window=14).mean()
        
        bars = []
        for index, row in res_df.iterrows():
            bars.append({
                'timestamp': index,
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'atr': row['atr']
            })
        resampled_data[tf] = bars
    return resampled_data

def process_config(args):
    config, bars_list, point_value = args
    return simulate_backtest_fast(bars_list, config, point_value)

def main(asset, point_value, scale_factor=1.0):
    filepath = f"historical_{asset.lower()}_90d.csv"
    if not os.path.exists(filepath):
        print(f"❌ Cannot find data file {filepath}")
        return
        
    print(f"🚀 Loading 90-day dataset for {asset}...")
    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
        
    df.set_index('timestamp', inplace=True)
    
    if scale_factor != 1.0:
        df['open'] *= scale_factor
        df['high'] *= scale_factor
        df['low'] *= scale_factor
        df['close'] *= scale_factor
        
    print(f"⏳ Resampling Data and Calculating ATR for {asset}...")
    data_dict = build_resampled_dict(df, PARAM_GRID['TIMEFRAME'])
    
    keys, values = zip(*PARAM_GRID.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    print(f"🔬 Starting Grid Search over {len(combinations)} configurations...")
    
    tasks = [(config, data_dict[config['TIMEFRAME']], point_value) for config in combinations]
    results = []
    
    cores = cpu_count()
    with Pool(processes=cores) as pool:
        for i, res in enumerate(pool.imap_unordered(process_config, tasks)):
            results.append(res)
            if (i + 1) % 1000 == 0:
                print(f"Progress: {i + 1}/{len(combinations)} configs evaluated.")
                
    print("\n✅ Simulation Complete. Applying holy grail filters...")
    
    viable = []
    for r in results:
        # RULES FOR SURVIVAL:
        if r['win_rate'] < 40.0: continue
        if r['net_pnl'] <= 500: continue
        if r['max_dd'] >= 6: continue
        if r['trades'] < 15: continue
        viable.append(r)
        
    viable.sort(key=lambda x: x['net_pnl'], reverse=True)
    
    output_file = f'best_params_{asset.lower()}.json'
    with open(output_file, 'w') as f:
        json.dump(viable[:20], f, indent=4)
        
    print(f"\n💾 Saved Top {len(viable[:20])} configurations to {output_file}")
    if not viable:
        print("❌ CRITICAL: No configurations survived.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 optimize_cross_val.py <GC|CL|YM>")
        sys.exit(1)
        
    asset = sys.argv[1].upper()
    configs = {
        "GC": {"point_value": 100.0, "scale_factor": 10.0},
        "CL": {"point_value": 1000.0, "scale_factor": 1.0},
        "YM": {"point_value": 5.0, "scale_factor": 100.0},
        "MNQ": {"point_value": 2.0, "scale_factor": 40.0},
        "MES": {"point_value": 5.0, "scale_factor": 10.0}
    }
    
    if asset not in configs:
        print(f"Asset {asset} not configured.")
        sys.exit(1)
        
    c = configs[asset]
    main(asset, c["point_value"], c["scale_factor"])
