import pandas as pd
import json
from itertools import product
import sys
sys.path.append("/Users/tbrook/Desktop/topstep-trader-bot-v2")

from bot.optimize_cross_val import build_resampled_dict, build_htf_bias_series
# Use my local version of simulate_combine
from scratch.combine_sim_engine import simulate_combine

def run_asset(asset, file_path, point_value, scale_factor=10.0, contracts=4):
    print(f"\n🚀 Running Combine Simulator for {asset} from {file_path}")
    import os
    if not os.path.exists(file_path):
        print("File not found!")
        return

    PARAM_GRID = {
        'TIMEFRAME': [3, 5, 10, 15],
        'LOOKBACK_BARS': [20, 30],
        'RR_RATIO': [1.0, 1.5, 2.0],
        'MIN_RISK_ATR_MULTIPLIER': [0.5],
        'MAX_RISK_ATR_MULTIPLIER': [2.0, 3.0, 5.0],
        'MIN_FVG_ATR_MULTIPLIER': [0.25, 0.5, 1.0, 1.5],
        'TIME_WINDOW': [
            {"name": "Morning Sniper", "start_h": 8, "start_m": 30, "end_h": 11, "end_m": 30},
            {"name": "Full NY Session", "start_h": 9, "start_m": 30, "end_h": 15, "end_m": 30}
        ]
    }

    keys, values = zip(*PARAM_GRID.items())
    configurations = [dict(zip(keys, v)) for v in product(*values)]
    
    df = pd.read_csv(file_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
    df.set_index('timestamp', inplace=True)
    
    if scale_factor != 1.0:
        for c in ['open', 'high', 'low', 'close']:
            df[c] *= scale_factor
            
    print(f"Building HTF biases...")
    bias_30m = build_htf_bias_series(df, 30)
    bias_240m = build_htf_bias_series(df, 240)
    
    timeframes = list(set([c['TIMEFRAME'] for c in configurations]))
    data_dict = build_resampled_dict(df, timeframes)
    
    results = []
    print(f"Testing {len(configurations)} setups across the Topstep rules engine...")
    for i, config in enumerate(configurations):
        tf = config['TIMEFRAME']
        bars = data_dict[tf]
        b_bias = bias_240m if tf >= 30 else bias_30m
        
        passed, blown = simulate_combine(bars, config, point_value, contracts, htf_bias_dict=b_bias)
        net_score = passed - blown
        
        results.append({
            "config": config,
            "passed": passed,
            "blown": blown,
            "net_score": net_score
        })
        
    results.sort(key=lambda x: x['net_score'], reverse=True)
    
    print(f"\n✅ TOP 3 COMBINE CONFIGS FOR {asset}:")
    for r in results[:3]:
        print("-" * 40)
        print(f"Passed: {r['passed']} | Blown: {r['blown']} | Net: {r['net_score']}")
        p = r['config']
        print(f"TF: {p['TIMEFRAME']}m | Window: {p['TIME_WINDOW']['name']} | RR: {p['RR_RATIO']}")
        print(f"FVG ATR: {p['MIN_FVG_ATR_MULTIPLIER']} | Max Risk: {p['MAX_RISK_ATR_MULTIPLIER']}")
        print("-" * 40)

if __name__ == "__main__":
    run_asset("MYM (2 Years)", "data/historical/historical_mym_2yr.csv", point_value=0.5, scale_factor=100.0, contracts=10)
    run_asset("M2K (30 Days)", "data/historical/historical_m2k_30d.csv", point_value=5.0, scale_factor=1.0, contracts=4)
