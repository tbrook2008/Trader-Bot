from bot.optimize_v2 import detect_ict_setup_fast

def simulate_combine(bars_list, config_params, point_value=1.0, contracts=4, htf_bias_dict=None):
    lookback = config_params['LOOKBACK_BARS']
    rr_ratio = config_params['RR_RATIO']
    time_window = config_params['TIME_WINDOW']
    
    st_h, st_m = time_window['start_h'], time_window['start_m']
    en_h, en_m = time_window['end_h'], time_window['end_m']
    start_minutes = st_h * 60 + st_m
    end_minutes = en_h * 60 + en_m
    
    in_position = False
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    trade_side = ""
    
    current_balance = 50000.0
    start_of_day_balance = 50000.0
    peak_eod_balance = 50000.0
    current_position_contracts = 0
    combines_passed = 0
    combines_blown = 0
    
    current_date = None
    daily_cap_hit = False
    
    valid_time_mask = []
    for b in bars_list:
        dt = b['timestamp']
        m = dt.hour * 60 + dt.minute
        if 12 * 60 <= m < 13 * 60:
            valid_time_mask.append(False)
        else:
            valid_time_mask.append(start_minutes <= m <= end_minutes)
            
    for i in range(lookback, len(bars_list)):
        current_bar = bars_list[i]
        dt = current_bar['timestamp']
        
        if current_date != dt.date():
            if current_date is not None:
                start_of_day_balance = current_balance
                daily_cap_hit = False
                if current_balance > peak_eod_balance:
                    peak_eod_balance = current_balance
            current_date = dt.date()
            in_position = False
            
        if in_position:
            pnl_points = 0
            closed = False
            exit_price = 0
            
            if trade_side == "buy":
                if current_bar['low'] <= stop_loss:
                    exit_price = stop_loss
                    closed = True
                elif current_bar['high'] >= take_profit:
                    exit_price = take_profit
                    closed = True
            elif trade_side == "sell":
                if current_bar['high'] >= stop_loss:
                    exit_price = stop_loss
                    closed = True
                elif current_bar['low'] <= take_profit:
                    exit_price = take_profit
                    closed = True
                    
            if closed:
                if trade_side == 'buy':
                    pnl_points = exit_price - entry_price
                else:
                    pnl_points = entry_price - exit_price
                    
                trade_pnl = pnl_points * point_value * current_position_contracts
                current_balance += trade_pnl
                in_position = False
                
                daily_pnl = current_balance - start_of_day_balance
                
                floor = peak_eod_balance - 2000
                if floor > 50000: floor = 50000
                if floor < 48000: floor = 48000
                
                if current_balance <= floor or daily_pnl <= -1000:
                    combines_blown += 1
                    current_balance = 50000.0
                    start_of_day_balance = 50000.0
                    peak_eod_balance = 50000.0
                    daily_cap_hit = False
                    
                elif current_balance >= 53000:
                    combines_passed += 1
                    current_balance = 50000.0
                    start_of_day_balance = 50000.0
                    peak_eod_balance = 50000.0
                    daily_cap_hit = False
                    
                elif daily_pnl >= 1450:
                    daily_cap_hit = True
                    
            continue
            
        if not valid_time_mask[i] or daily_cap_hit:
            continue
            
        window = bars_list[i-lookback:i+1]
        bias = htf_bias_dict.get(dt) if htf_bias_dict else None
        setup = detect_ict_setup_fast(window, config_params, htf_bias=bias)
        
        if setup:
            trade_side = setup['side']
            entry_price = current_bar['close']
            
            floor = peak_eod_balance - 2000
            if floor > 50000.0:
                floor = 50000.0
                
            buffer = current_balance - floor
            if buffer > 750:
                dynamic_c = contracts
            elif buffer > 400:
                dynamic_c = max(1, contracts // 2)
            else:
                dynamic_c = 1

            risk_pts = setup['risk_points']
            if risk_pts * point_value * dynamic_c > 600:
                continue
                
            if trade_side == 'buy':
                stop_loss = entry_price - risk_pts
                take_profit = entry_price + (risk_pts * rr_ratio)
            else:
                stop_loss = entry_price + risk_pts
                take_profit = entry_price - (risk_pts * rr_ratio)
                
            in_position = True
            current_position_contracts = dynamic_c
            
    return combines_passed, combines_blown
