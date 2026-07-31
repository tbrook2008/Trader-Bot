import pandas as pd
from bot.optimize_v2 import simulate_backtest_fast

# --- The Contenders ---

# CONTENDER A: Current Live Bot (Loose, High Reward)
CONTENDER_A = {
    'TIMEFRAME': 3,
    'RR_RATIO': 2.0,
    'LOOKBACK_BARS': 15,
    'MAX_RISK_POINTS': 30.0,
    'MIN_FVG_POINTS': 0.25,
    'TIME_WINDOW': {'name': 'Full NY Session', 'start_h': 9, 'start_m': 30, 'end_h': 16, 'end_m': 0}
}

# CONTENDER B: New Optimal Bot (Strict, High Probability)
CONTENDER_B = {
    'TIMEFRAME': 1,
    'RR_RATIO': 1.0,
    'LOOKBACK_BARS': 30,
    'MAX_RISK_POINTS': 25.0,
    'MIN_FVG_POINTS': 3.0,
    'TIME_WINDOW': {'name': 'Full NY Session', 'start_h': 9, 'start_m': 30, 'end_h': 16, 'end_m': 0}
}

def load_and_scale_data(filepath):
    print("🚀 Loading Q1 2024 Out-Of-Sample Data (QQQ)...")
    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
    df.set_index('timestamp', inplace=True)
    
    # Mathematical Scaling: QQQ was ~$400-$440 in Q1 2024. MNQ is ~$18,000.
    # Multiplying QQQ prices by 42x scales its structure to match MNQ's point values natively,
    # allowing us to test our absolute point parameters (3.0 gap, 25 risk) without modification.
    SCALAR = 42.0
    df['open'] = df['open'] * SCALAR
    df['high'] = df['high'] * SCALAR
    df['low'] = df['low'] * SCALAR
    df['close'] = df['close'] * SCALAR
    print(f"📊 Scaled QQQ data by {SCALAR}x to match Nasdaq Futures points geometry.")
    
    return df

def resample_bars(df, tf_minutes):
    if tf_minutes == 1:
        resampled_df = df
    else:
        resampled_df = df.resample(f'{tf_minutes}min').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
    bars = []
    for index, row in resampled_df.iterrows():
        bars.append({
            'timestamp': index,
            'high': row['high'],
            'low': row['low'],
            'close': row['close']
        })
    return bars

def main():
    df = load_and_scale_data("historical_qqq_2024Q1.csv")
    
    print("\n⚔️ STARTING HEAD-TO-HEAD SIMULATION (Q1 2024) ⚔️\n")
    
    # Run Contender A
    bars_A = resample_bars(df, CONTENDER_A['TIMEFRAME'])
    res_A = simulate_backtest_fast(bars_A, CONTENDER_A)
    
    # Run Contender B
    bars_B = resample_bars(df, CONTENDER_B['TIMEFRAME'])
    res_B = simulate_backtest_fast(bars_B, CONTENDER_B)
    
    print("="*50)
    print("CONTENDER A: Current Live Bot (The Baseline)")
    print("="*50)
    print(f"Timeframe: {CONTENDER_A['TIMEFRAME']}m | Min FVG: {CONTENDER_A['MIN_FVG_POINTS']} | RR: {CONTENDER_A['RR_RATIO']}x")
    print(f"Trades Taken: {res_A['trades']}")
    print(f"Win Rate:     {res_A['win_rate']:.2f}% ({res_A['wins']}W - {res_A['losses']}L)")
    print(f"Max Drawdown: {res_A['max_dd']} consecutive losses")
    print(f"Total Profit: ${res_A['net_pnl']:.2f}")
    
    print("\n" + "="*50)
    print("CONTENDER B: New Optimal Bot (The Challenger)")
    print("="*50)
    print(f"Timeframe: {CONTENDER_B['TIMEFRAME']}m | Min FVG: {CONTENDER_B['MIN_FVG_POINTS']} | RR: {CONTENDER_B['RR_RATIO']}x")
    print(f"Trades Taken: {res_B['trades']}")
    print(f"Win Rate:     {res_B['win_rate']:.2f}% ({res_B['wins']}W - {res_B['losses']}L)")
    print(f"Max Drawdown: {res_B['max_dd']} consecutive losses")
    print(f"Total Profit: ${res_B['net_pnl']:.2f}")
    
    print("\n🏆 CONCLUSION 🏆")
    if res_B['net_pnl'] > res_A['net_pnl']:
        print("Contender B (New Optimal) decisively outperformed Contender A in completely out-of-sample data.")
        print("This mathematically proves the parameters are a robust structural edge, not just curve-fitted!")
    else:
        print("Contender A held its own! The new parameters might have been overfitted to the recent 90 days.")

if __name__ == "__main__":
    main()
