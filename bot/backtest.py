import pandas as pd
from bot.execution.topstep_client import TopstepXClient
from bot.ivan_trader import detect_ict_setup, StrategyConfig
from dotenv import load_dotenv
from datetime import datetime

def run_backtest(symbol, days=7):
    load_dotenv()
    client = TopstepXClient()
    
    print(f"\n🚀 Running Backtest for {symbol} over the last {days} days...")
    print("🎯 FILTER APPLIED: Only taking trades between 9:45 AM and 11:30 AM ET (Morning Trend)")
    print(f"🕒 TIMEFRAME: {StrategyConfig.TIMEFRAME}-minute bars")
    bars = client.get_historical_bars(symbol, days=days, unit_number=StrategyConfig.TIMEFRAME)
    
    if len(bars) < 100:
        print("Not enough data fetched to backtest.")
        return

    df = pd.DataFrame(bars)
    
    trades = []
    wins = 0
    losses = 0
    net_points = 0
    consecutive_losses = 0
    max_consecutive_losses = 0
    
    in_position = False
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    trade_side = ""
    
    print(f"Processing {len(df)} bars bar-by-bar...")
    
    # Simulate step-by-step
    for i in range(40, len(df)):
        current_bar = df.iloc[i]
        
        # Check if we are managing an open position
        if in_position:
            # Did we hit stop loss or take profit?
            if trade_side == "buy":
                if current_bar['low'] <= stop_loss:
                    loss_pts = entry_price - stop_loss
                    net_points -= loss_pts
                    losses += 1
                    consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                    trades.append({"result": "LOSS", "points": -loss_pts})
                    in_position = False
                elif current_bar['high'] >= take_profit:
                    win_pts = take_profit - entry_price
                    net_points += win_pts
                    wins += 1
                    consecutive_losses = 0
                    trades.append({"result": "WIN", "points": win_pts})
                    in_position = False
                    
            elif trade_side == "sell":
                if current_bar['high'] >= stop_loss:
                    loss_pts = stop_loss - entry_price
                    net_points -= loss_pts
                    losses += 1
                    consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                    trades.append({"result": "LOSS", "points": -loss_pts})
                    in_position = False
                elif current_bar['low'] <= take_profit:
                    win_pts = entry_price - take_profit
                    net_points += win_pts
                    wins += 1
                    consecutive_losses = 0
                    trades.append({"result": "WIN", "points": win_pts})
                    in_position = False
            continue
            
        # Extract time to filter for 9:45 AM to 11:30 AM ET (13:45 to 15:30 UTC)
        bar_time_str = current_bar['timestamp']
        dt = datetime.fromisoformat(bar_time_str.replace('Z', '+00:00'))
        
        is_valid_time = False
        if dt.hour == 13 and dt.minute >= 45:
            is_valid_time = True
        elif dt.hour == 14:
            is_valid_time = True
        elif dt.hour == 15 and dt.minute <= 30:
            is_valid_time = True
            
        if not is_valid_time:
            continue
            
        # Scan for setups on the trailing 40 bars
        window = df.iloc[i-40:i+1].reset_index(drop=True)
        setup = detect_ict_setup(window, symbol)
        
        if setup:
            trade_side = setup['side']
            # We assume entry at the current close price as an approximation of the limit trigger
            entry_price = current_bar['close']
            
            # Recalculate target and stop based on actual FVG points
            risk_points = setup['risk_points']
            if trade_side == "buy":
                stop_loss = entry_price - risk_points
                take_profit = entry_price + (risk_points * StrategyConfig.RR_RATIO)
            else:
                stop_loss = entry_price + risk_points
                take_profit = entry_price - (risk_points * StrategyConfig.RR_RATIO)
                
            in_position = True

    print("\n" + "="*50)
    print(f"📊 BACKTEST RESULTS: {symbol}")
    print("="*50)
    print(f"Total Trades Taken  : {len(trades)}")
    if len(trades) > 0:
        print(f"Wins                : {wins}")
        print(f"Losses              : {losses}")
        print(f"Win Rate            : {((wins/len(trades))*100):.1f}%")
        print(f"Net Points          : {net_points:.2f} pts")
        
        # Calculate dollar equivalent for MNQ ($2 per point)
        multiplier = 2 if symbol == "MNQ" else 5
        print(f"Net Dollar PnL (1ct): ${net_points * multiplier:.2f}")
        print(f"Max Consecutive Loss: {max_consecutive_losses}")
        print("="*50)
        
        if max_consecutive_losses >= 2:
            print("⚠️ WARNING: The strategy hit 2+ consecutive losses in this backtest.")
            print("Given your $400 trailing drawdown limit, you may fail the combine if this sequence occurs live.")
    else:
        print("No trades triggered in this time period.")

if __name__ == "__main__":
    run_backtest("MNQ", days=60)
