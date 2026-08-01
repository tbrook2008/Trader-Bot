import pandas as pd
import itertools
from datetime import datetime
import json
from multiprocessing import Pool, cpu_count
import os

PARAM_GRID = {
    'TIMEFRAME': [1, 2, 3, 5, 10, 15],           
    'RR_RATIO': [1.0, 1.5, 2.0, 2.5, 3.0, 4.0],          
    'LOOKBACK_BARS': [15, 20, 30],      
    'MIN_RISK_ATR_MULTIPLIER': [0.5],
    'MAX_RISK_ATR_MULTIPLIER': [3.0, 4.0, 5.0, 6.0],
    'MIN_FVG_ATR_MULTIPLIER': [0.1, 0.25, 0.5, 1.0],
    'TIME_WINDOW': [
        {'name': 'Morning Sniper', 'start_h': 8, 'start_m': 30, 'end_h': 11, 'end_m': 30},
        {'name': 'Afternoon Sniper', 'start_h': 13, 'start_m': 0, 'end_h': 15, 'end_m': 30},
        {'name': 'Full NY Session', 'start_h': 9, 'start_m': 30, 'end_h': 16, 'end_m': 0},
        {'name': 'London/NY Overlap', 'start_h': 8, 'start_m': 0, 'end_h': 10, 'end_m': 0},
        {'name': 'All Day', 'start_h': 0, 'start_m': 0, 'end_h': 23, 'end_m': 59}
    ]
}

def check_rejection_fast(bars_since_fvg, zone_low, zone_high, direction):
    if not bars_since_fvg:
        return False
        
    touched = False
    for b in bars_since_fvg:
        if b['high'] >= zone_low and b['low'] <= zone_high:
            touched = True
            break
            
    if not touched:
        return False
        
    last_close = bars_since_fvg[-1]['close']
    if direction == "sell":
        return last_close < zone_low
    else:
        return last_close > zone_high

def detect_ict_setup_fast(bars_slice, config_params, htf_bias=None):
    current_atr = bars_slice[-1]['atr']
    if pd.isna(current_atr) or current_atr == 0:
        return None
        
    min_fvg = config_params['MIN_FVG_ATR_MULTIPLIER'] * current_atr
    min_risk = config_params['MIN_RISK_ATR_MULTIPLIER'] * current_atr
    max_risk = config_params['MAX_RISK_ATR_MULTIPLIER'] * current_atr
    current_price = bars_slice[-1]['close']
    
    # Bearish - Only allow if htf_bias is not "buy" (i.e. "sell" or None)
    highest_idx = 0
    highest_val = -float('inf')
    if htf_bias != "buy":
        for i, b in enumerate(bars_slice):
            if b['high'] > highest_val:
                highest_val = b['high']
                highest_idx = i
                
        if highest_idx < len(bars_slice) - 2:
            sweep_high = highest_val
            sweep_low_threshold = bars_slice[highest_idx]['low']
            
            # MSS check
            mss_idx = None
            for j in range(highest_idx + 1, len(bars_slice)):
                if bars_slice[j]['close'] < sweep_low_threshold:
                    c = bars_slice[j]
                    body = abs(c['close'] - c['open'])
                    crange = c['high'] - c['low']
                    if crange > 0 and (body / crange) >= 0.60:
                        mss_idx = j
                        break
                        
            if mss_idx is not None:
                for i in range(highest_idx, len(bars_slice)-2):
                    c1_low = bars_slice[i]['low']
                    c3_high = bars_slice[i+2]['high']
                    fvg_gap = c1_low - c3_high
                    if fvg_gap >= min_fvg:
                        zone_low, zone_high = c3_high, c1_low
                        risk_points = sweep_high - zone_low
                        if min_risk <= risk_points <= max_risk:
                            # OTE Filter
                            swing_low = min([b['low'] for b in bars_slice[highest_idx:i+3]])
                            move_range = sweep_high - swing_low
                            fib_618 = sweep_high - (move_range * 0.618)
                            fib_790 = sweep_high - (move_range * 0.790)
                            
                            if fib_790 <= current_price <= fib_618:
                                bars_since_fvg = bars_slice[i+2:]
                                if check_rejection_fast(bars_since_fvg, zone_low, zone_high, "sell"):
                                    return {"side": "sell", "risk_points": risk_points}
                                
    # Bullish - Only allow if htf_bias is not "sell" (i.e. "buy" or None)
    lowest_idx = 0
    lowest_val = float('inf')
    if htf_bias != "sell":
        for i, b in enumerate(bars_slice):
            if b['low'] < lowest_val:
                lowest_val = b['low']
                lowest_idx = i
                
        if lowest_idx < len(bars_slice) - 2:
            sweep_low = lowest_val
            sweep_high_threshold = bars_slice[lowest_idx]['high']
            
            # MSS check
            mss_idx = None
            for j in range(lowest_idx + 1, len(bars_slice)):
                if bars_slice[j]['close'] > sweep_high_threshold:
                    c = bars_slice[j]
                    body = abs(c['close'] - c['open'])
                    crange = c['high'] - c['low']
                    if crange > 0 and (body / crange) >= 0.60:
                        mss_idx = j
                        break
                        
            if mss_idx is not None:
                for i in range(lowest_idx, len(bars_slice)-2):
                    c1_high = bars_slice[i]['high']
                    c3_low = bars_slice[i+2]['low']
                    fvg_gap = c3_low - c1_high
                    if fvg_gap >= min_fvg:
                        zone_low, zone_high = c1_high, c3_low
                        risk_points = zone_high - sweep_low
                        if min_risk <= risk_points <= max_risk:
                            # OTE Filter
                            swing_high = max([b['high'] for b in bars_slice[lowest_idx:i+3]])
                            move_range = swing_high - sweep_low
                            fib_618 = sweep_low + (move_range * 0.618)
                            fib_790 = sweep_low + (move_range * 0.790)
                            
                            if fib_618 <= current_price <= fib_790:
                                bars_since_fvg = bars_slice[i+2:]
                                if check_rejection_fast(bars_since_fvg, zone_low, zone_high, "buy"):
                                    return {"side": "buy", "risk_points": risk_points}
                                
    return None

def simulate_backtest_fast(bars_list, config_params, point_value=1.0, htf_bias_dict=None):
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
    be_activated = False
    risk_points = 0
    
    valid_time_mask = []
    for b in bars_list:
        dt = b['timestamp']
        m = dt.hour * 60 + dt.minute
        # Lunch hour exclusion 12-1pm
        if 12 * 60 <= m < 13 * 60:
            valid_time_mask.append(False)
        else:
            valid_time_mask.append(start_minutes <= m <= end_minutes)
    
    for i in range(lookback, len(bars_list)):
        current_bar = bars_list[i]
        
        if in_position:
            if trade_side == "buy":
                pnl = current_bar['high'] - entry_price
                if not be_activated and pnl >= risk_points:
                    be_activated = True
                    stop_loss = entry_price
                    
                if current_bar['low'] <= stop_loss:
                    loss_pts = entry_price - stop_loss
                    net_points -= loss_pts
                    if loss_pts > 0:
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
                pnl = entry_price - current_bar['low']
                if not be_activated and pnl >= risk_points:
                    be_activated = True
                    stop_loss = entry_price
                    
                if current_bar['high'] >= stop_loss:
                    loss_pts = stop_loss - entry_price
                    net_points -= loss_pts
                    if loss_pts > 0:
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
            
        if consecutive_losses >= 3:
            # Simple assumption: resets daily
            pass 
            
        window = bars_list[i-lookback:i+1]
        bias = htf_bias_dict.get(dt) if htf_bias_dict else None
        setup = detect_ict_setup_fast(window, config_params, htf_bias=bias)
        
        if setup:
            trade_side = setup['side']
            entry_price = current_bar['close']
            risk_points = setup['risk_points']
            be_activated = False
            
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
        "net_pnl": net_points * point_value,
        "max_dd": max_consecutive_losses
    }
