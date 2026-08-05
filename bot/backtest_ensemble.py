import pandas as pd
import json
import os
import sys
from collections import defaultdict
from bot.optimize_cross_val import build_resampled_dict, build_htf_bias_series
from bot.optimize_v2 import detect_ict_setup_fast

def get_all_signals_fast(bars_list, config_params, htf_bias_dict=None):
    lookback = config_params['LOOKBACK_BARS']
    rr_ratio = config_params['RR_RATIO']
    time_window = config_params['TIME_WINDOW']
    
    st_h, st_m = time_window['start_h'], time_window['start_m']
    en_h, en_m = time_window['end_h'], time_window['end_m']
    start_minutes = st_h * 60 + st_m
    end_minutes = en_h * 60 + en_m
    
    signals = []
    
    valid_time_mask = []
    for b in bars_list:
        dt = b['timestamp']
        m = dt.hour * 60 + dt.minute
        if 12 * 60 <= m < 13 * 60:
            valid_time_mask.append(False)
        else:
            valid_time_mask.append(start_minutes <= m <= end_minutes)
    
    for i in range(lookback, len(bars_list)):
        if not valid_time_mask[i]:
            continue
            
        current_bar = bars_list[i]
        window = bars_list[i-lookback:i+1]
        dt = current_bar['timestamp']
        bias = htf_bias_dict.get(dt) if htf_bias_dict else None
        
        setup = detect_ict_setup_fast(window, config_params, htf_bias=bias)
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
                
            signals.append({
                "timestamp": dt,
                "side": trade_side,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit
            })
            
    return signals

def run_ensemble_backtest(asset, point_value, scale_factor, min_votes):
    filepath = f"data/historical/historical_{asset.lower()}_2yr.csv"
    if not os.path.exists(filepath):
        print(f"❌ Cannot find {filepath}")
        return
        
    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
    df.set_index('timestamp', inplace=True)
    
    if scale_factor != 1.0:
        for c in ['open', 'high', 'low', 'close']:
            df[c] *= scale_factor
            
    # Use Out-of-Sample data (last 40%)
    split_idx = int(len(df) * 0.6)
    df_oos = df.iloc[split_idx:]
    
    # Check if there are holy grails
    hg_file = f"data/optimization/best_params_{asset.lower()}.json"
    if not os.path.exists(hg_file):
        print(f"❌ Cannot find {hg_file}")
        return
        
    with open(hg_file, 'r') as f:
        holy_grails = json.load(f)
        
    print(f"⏳ Building HTF bias and resampling...")
    bias_30m_oos = build_htf_bias_series(df_oos, 30)
    bias_240m_oos = build_htf_bias_series(df_oos, 240)
    
    timeframes = list(set([c['TIMEFRAME'] for c in holy_grails]))
    data_dict_oos = build_resampled_dict(df_oos, timeframes)
    
    print(f"🔬 Collecting signals from {len(holy_grails)} Holy Grails...")
    all_signals = []
    for i, config in enumerate(holy_grails):
        b_oos = bias_240m_oos if config['TIMEFRAME'] >= 30 else bias_30m_oos
        bars = data_dict_oos[config['TIMEFRAME']]
        sigs = get_all_signals_fast(bars, config, htf_bias_dict=b_oos)
        all_signals.extend(sigs)
        
    # Sort signals by time
    all_signals.sort(key=lambda x: x['timestamp'])
    
    # We will build a minute-by-minute vote count array.
    # Signal vote expires after 15 minutes.
    vote_map = {}
    for sig in all_signals:
        ts = sig['timestamp']
        side = sig['side']
        for offset in range(16): # 0 to 15 mins
            minute_ts = ts + pd.Timedelta(minutes=offset)
            if minute_ts not in vote_map:
                vote_map[minute_ts] = {"buy": [], "sell": []}
            vote_map[minute_ts][side].append(sig)
            
    print(f"▶️ Simulating ensemble votes with Threshold = {min_votes}...")
    trades = []
    net_points = 0
    wins = 0
    losses = 0
    
    in_position = False
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    trade_side = ""
    
    for index, row in df_oos.iterrows():
        dt = index
        
        if in_position:
            if trade_side == "buy":
                if row['low'] <= stop_loss:
                    loss_pts = entry_price - stop_loss
                    net_points -= loss_pts
                    if loss_pts > 0: losses += 1
                    trades.append(-loss_pts)
                    in_position = False
                elif row['high'] >= take_profit:
                    win_pts = take_profit - entry_price
                    net_points += win_pts
                    wins += 1
                    trades.append(win_pts)
                    in_position = False
            elif trade_side == "sell":
                if row['high'] >= stop_loss:
                    loss_pts = stop_loss - entry_price
                    net_points -= loss_pts
                    if loss_pts > 0: losses += 1
                    trades.append(-loss_pts)
                    in_position = False
                elif row['low'] <= take_profit:
                    win_pts = entry_price - take_profit
                    net_points += win_pts
                    wins += 1
                    trades.append(win_pts)
                    in_position = False
            continue
            
        # Not in position, check votes
        votes = vote_map.get(dt)
        if votes:
            buy_sigs = votes['buy']
            sell_sigs = votes['sell']
            
            # Simple assumption: We only take if exclusively >= min_votes in one direction
            if len(buy_sigs) >= min_votes and len(sell_sigs) < min_votes:
                trade_side = "buy"
                entry_price = row['close']
                stop_loss = sum([s['stop_loss'] for s in buy_sigs]) / len(buy_sigs)
                take_profit = sum([s['take_profit'] for s in buy_sigs]) / len(buy_sigs)
                in_position = True
            elif len(sell_sigs) >= min_votes and len(buy_sigs) < min_votes:
                trade_side = "sell"
                entry_price = row['close']
                stop_loss = sum([s['stop_loss'] for s in sell_sigs]) / len(sell_sigs)
                take_profit = sum([s['take_profit'] for s in sell_sigs]) / len(sell_sigs)
                in_position = True

    win_rate = (wins/len(trades)*100) if trades else 0
    print(f"✅ RESULTS FOR {asset} (Votes >= {min_votes}):")
    print(f"Total Trades: {len(trades)}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Net Points: {net_points:.2f}")
    print(f"Net PnL: ${net_points * point_value:.2f}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 backtest_ensemble.py <MNQ|MES>")
        sys.exit(1)
        
    asset = sys.argv[1].upper()
    configs = {
        "MNQ": {"point_value": 2.0, "scale_factor": 40.0},
        "MES": {"point_value": 5.0, "scale_factor": 10.0}
    }
    
    if asset not in configs:
        sys.exit(1)
        
    c = configs[asset]
    for min_votes in [3, 5, 10]:
        run_ensemble_backtest(asset, c["point_value"], c["scale_factor"], min_votes)
