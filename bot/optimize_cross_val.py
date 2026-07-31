import pandas as pd
import itertools
from datetime import datetime
import json
import multiprocessing
try:
    multiprocessing.set_start_method('fork', force=True)
except Exception:
    pass
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
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'atr': row['atr']
            })
        resampled_data[tf] = bars
    return resampled_data

def process_config(args):
    global data_dict_is, data_dict_oos
    config, point_value = args
    
    # 1. Run In-Sample
    is_bars = data_dict_is[config['TIMEFRAME']]
    is_res = simulate_backtest_fast(is_bars, config, point_value)
    
    # In-Sample Filters
    if is_res['win_rate'] < 45.0 or is_res['net_pnl'] <= 1000 or is_res['max_dd'] >= 6 or is_res['trades'] < 20:
        return None
        
    # 2. Run Out-of-Sample
    oos_bars = data_dict_oos[config['TIMEFRAME']]
    oos_res = simulate_backtest_fast(oos_bars, config, point_value)
    
    # Out-of-Sample Filters
    if oos_res['win_rate'] < 40.0 or oos_res['net_pnl'] <= 0 or oos_res['max_dd'] >= 8:
        return None
        
    # Combine results for Holy Grail scoring
    total_pnl = is_res['net_pnl'] + oos_res['net_pnl']
    avg_win_rate = (is_res['win_rate'] + oos_res['win_rate']) / 2
    total_trades = is_res['trades'] + oos_res['trades']
    max_dd = max(is_res['max_dd'], oos_res['max_dd'])
    
    return {
        "config": config,
        "is_pnl": is_res['net_pnl'],
        "oos_pnl": oos_res['net_pnl'],
        "total_pnl": total_pnl,
        "avg_win_rate": avg_win_rate,
        "total_trades": total_trades,
        "max_dd": max_dd
    }

def main(asset, point_value, scale_factor=1.0):
    global data_dict_is, data_dict_oos
    filepath = f"historical_{asset.lower()}_2yr.csv"
    if not os.path.exists(filepath):
        print(f"❌ Cannot find data file {filepath}")
        return
        
    print(f"🚀 Loading 2-Year Dataset for {asset}...")
    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
        
    df.set_index('timestamp', inplace=True)
    
    if scale_factor != 1.0:
        df['open'] *= scale_factor
        df['high'] *= scale_factor
        df['low'] *= scale_factor
        df['close'] *= scale_factor
        
    print(f"⏳ Splitting Data into In-Sample (IS) and Out-of-Sample (OOS)...")
    split_idx = int(len(df) * 0.6) # 60% IS, 40% OOS
    df_is = df.iloc[:split_idx]
    df_oos = df.iloc[split_idx:]
    
    print(f"⏳ Resampling Data and Calculating ATR for {asset} IS and OOS...")
    data_dict_is = build_resampled_dict(df_is, PARAM_GRID['TIMEFRAME'])
    data_dict_oos = build_resampled_dict(df_oos, PARAM_GRID['TIMEFRAME'])
    
    keys, values = zip(*PARAM_GRID.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    print(f"🔬 Starting Holy Grail Grid Search over {len(combinations)} configurations...")
    
    tasks = [(config, point_value) for config in combinations]
    results = []
    
    cores = cpu_count()
    with Pool(processes=cores) as pool:
        for i, res in enumerate(pool.imap_unordered(process_config, tasks)):
            if res is not None:
                results.append(res)
            if (i + 1) % 1000 == 0:
                print(f"Progress: {i + 1}/{len(combinations)} configs evaluated. Holy Grails found: {len(results)}")
                
    print("\n✅ Simulation Complete.")
    
    results.sort(key=lambda x: x['total_pnl'], reverse=True)
    
    output_file = f'best_params_{asset.lower()}.json'
    with open(output_file, 'w') as f:
        # Convert it back to the format the bot expects for best_params (just the config dicts)
        final_configs = [r['config'] for r in results[:20]]
        json.dump(final_configs, f, indent=4)
        
    print(f"\n💾 Saved Top {len(results[:20])} Holy Grail configurations to {output_file}")
    if not results:
        print("❌ CRITICAL: No configurations survived both In-Sample and Out-of-Sample testing.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 optimize_cross_val.py <GC|CL|YM|MNQ|MES|MYM>")
        sys.exit(1)
        
    asset = sys.argv[1].upper()
    configs = {
        "GC": {"point_value": 100.0, "scale_factor": 10.0},
        "CL": {"point_value": 1000.0, "scale_factor": 1.0},
        "YM": {"point_value": 5.0, "scale_factor": 100.0},
        "MNQ": {"point_value": 2.0, "scale_factor": 40.0},
        "MES": {"point_value": 5.0, "scale_factor": 10.0},
        "MYM": {"point_value": 0.5, "scale_factor": 100.0}
    }
    
    if asset not in configs:
        print(f"Asset {asset} not configured.")
        sys.exit(1)
        
    c = configs[asset]
    main(asset, c["point_value"], c["scale_factor"])
