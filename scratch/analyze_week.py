import pandas as pd
from datetime import datetime, timedelta

def analyze_trades():
    print("📊 Analyzing Trade Log...")
    try:
        df = pd.read_csv("data/trade_log.csv")
    except Exception as e:
        print(f"Could not load trade_log.csv: {e}")
        return
        
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Filter for the last 7 days
    now = datetime.now()
    seven_days_ago = now - timedelta(days=7)
    recent_df = df[df['timestamp'] >= seven_days_ago]
    
    if recent_df.empty:
        print("No trades taken in the last 7 days.")
        return
        
    print(f"\nTotal trades this week: {len(recent_df)}")
    
    wins = len(recent_df[recent_df['result'] == 'WIN'])
    losses = len(recent_df[recent_df['result'] == 'LOSS'])
    win_rate = (wins / len(recent_df)) * 100
    
    print(f"Wins: {wins} | Losses: {losses} | Win Rate: {win_rate:.1f}%")
    
    total_pnl = recent_df['pnl'].sum()
    print(f"Net PnL this week: ${total_pnl:.2f}")
    
    print("\n--- Breakdowns ---")
    by_symbol = recent_df.groupby('symbol')['pnl'].sum()
    print(by_symbol)
    
    print("\n--- Daily PnL ---")
    recent_df['date'] = recent_df['timestamp'].dt.date
    daily_pnl = recent_df.groupby('date')['pnl'].sum()
    print(daily_pnl)
    
    print("\n--- Trade Log (Last 10) ---")
    print(recent_df[['timestamp', 'symbol', 'side', 'result', 'pnl']].tail(10))

if __name__ == "__main__":
    analyze_trades()
