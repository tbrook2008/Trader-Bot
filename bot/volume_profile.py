import pandas as pd

def calculate_daily_volume_profile(df, session_start="09:30", session_end="16:00"):
    """
    Given a dataframe of 1m bars with an Eastern Time DatetimeIndex,
    calculates the Previous Day VAH, VAL, and POC for each date.
    Returns a dictionary mapping date to {'vah': float, 'val': float, 'poc': float}.
    """
    # Filter only NY session
    ny_mask = (df.index.time >= pd.to_datetime(session_start).time()) & \
              (df.index.time <= pd.to_datetime(session_end).time())
    df_ny = df[ny_mask].copy()
    
    # Calculate typical price, round to nearest integer to bin correctly
    df_ny['tp'] = ((df_ny['high'] + df_ny['low'] + df_ny['close']) / 3.0).round(0)
    
    daily_vp = {}
    grouped = df_ny.groupby(df_ny.index.date)
    
    for date, group in grouped:
        if len(group) < 10:
            continue
            
        vol_dist = group.groupby('tp')['volume'].sum().sort_index()
        if vol_dist.empty or vol_dist.sum() == 0:
            continue
            
        total_vol = vol_dist.sum()
        poc_price = vol_dist.idxmax()
        
        # Calculate Value Area (70%)
        target_vol = total_vol * 0.70
        val_area_vol = vol_dist[poc_price]
        
        vah = poc_price
        val = poc_price
        
        idx_up = vol_dist.index.get_loc(poc_price) + 1 if poc_price in vol_dist.index else -1
        idx_dn = vol_dist.index.get_loc(poc_price) - 1 if poc_price in vol_dist.index else -1
        
        while val_area_vol < target_vol:
            vol_up = vol_dist.iloc[idx_up] if (idx_up < len(vol_dist) and idx_up != -1) else 0
            vol_dn = vol_dist.iloc[idx_dn] if idx_dn >= 0 else 0
            
            if vol_up == 0 and vol_dn == 0:
                break
                
            if vol_up > vol_dn:
                val_area_vol += vol_up
                vah = vol_dist.index[idx_up]
                idx_up += 1
            elif vol_dn > vol_up:
                val_area_vol += vol_dn
                val = vol_dist.index[idx_dn]
                idx_dn -= 1
            else:
                # equal
                val_area_vol += (vol_up + vol_dn)
                if vol_up > 0:
                    vah = vol_dist.index[idx_up]
                    idx_up += 1
                if vol_dn > 0:
                    val = vol_dist.index[idx_dn]
                    idx_dn -= 1
                    
        # Ensure VAH > VAL mathematically
        if val > vah:
            vah, val = val, vah
            
        daily_vp[date] = {
            'vah': float(vah),
            'val': float(val),
            'poc': float(poc_price)
        }
        
    # Map *today* to *yesterday's* VP so the bot doesn't look ahead
    sorted_dates = sorted(list(daily_vp.keys()))
    vp_mapped = {}
    for i in range(1, len(sorted_dates)):
        curr_date = sorted_dates[i]
        prev_date = sorted_dates[i-1]
        vp_mapped[curr_date] = daily_vp[prev_date]
        
    return vp_mapped
