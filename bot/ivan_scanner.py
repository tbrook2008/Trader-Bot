import os
import time
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load Alpaca keys from .env
load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

if not API_KEY or not SECRET_KEY:
    print("❌ Missing Alpaca API keys in .env")
    exit(1)

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# We track QQQ (for NQ) and SPY (for ES)
SYMBOLS = ["QQQ", "SPY"]

def get_recent_bars(symbol, limit=60):
    """Fetch the most recent 1-minute bars."""
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(hours=3) # ensure we have enough data
    
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start_dt,
        end=end_dt
    )
    bars = client.get_stock_bars(req)
    if not bars or symbol not in bars.data:
        return pd.DataFrame()
        
    df = pd.DataFrame([
        {
            "timestamp": b.timestamp,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume
        } for b in bars.data[symbol]
    ])
    return df.tail(limit).reset_index(drop=True)

def detect_ict_setup(df, symbol):
    """
    Detects IvanTrades/ICT style setups: Liquidity Sweep -> MSS -> FVG
    Returns a dict with trade details if a setup is found.
    """
    if len(df) < 10:
        return None
        
    future_ticker = "NQ (Nasdaq)" if symbol == "QQQ" else "ES (S&P 500)"
    
    # We analyze the last 5-10 bars for the actual setup, using older bars for context
    recent_bars = df.tail(10).reset_index(drop=True)
    current_price = df.iloc[-1]['close']
    
    # 1. Look for Bearish Setup (Short)
    highest_idx = recent_bars['high'].idxmax()
    if highest_idx < len(recent_bars) - 2: # Sweep happened recently
        sweep_high = recent_bars.loc[highest_idx, 'high']
        
        recent_close = recent_bars.iloc[-1]['close']
        if recent_close < recent_bars.loc[highest_idx, 'low']: # Broke structure below the sweep candle
            
            # Cond 3: Fair Value Gap (FVG)
            # Look for a gap from the high down to current
            for i in range(highest_idx, len(recent_bars)-2):
                c1_low = recent_bars.loc[i, 'low']
                c3_high = recent_bars.loc[i+2, 'high']
                
                if c3_high < c1_low: # Bearish FVG exists!
                    entry_zone = (c3_high, c1_low)
                    stop_loss = sweep_high
                    risk = stop_loss - entry_zone[0]
                    target = entry_zone[0] - (risk * 2) # 1:2 Risk Reward
                    
                    if current_price <= c1_low and current_price >= c3_high:
                        return {
                            "type": "SHORT",
                            "symbol": future_ticker,
                            "proxy": symbol,
                            "entry": f"${c3_high:.2f} to ${c1_low:.2f}",
                            "stop": f"${stop_loss:.2f}",
                            "target": f"${target:.2f}",
                            "reason": "Bearish Liquidity Sweep -> Downward MSS -> Price inside Bearish FVG"
                        }

    # 2. Look for Bullish Setup (Long)
    lowest_idx = recent_bars['low'].idxmin()
    if lowest_idx < len(recent_bars) - 2: 
        sweep_low = recent_bars.loc[lowest_idx, 'low']
        
        recent_close = recent_bars.iloc[-1]['close']
        if recent_close > recent_bars.loc[lowest_idx, 'high']: # Broke structure above the sweep candle
            
            for i in range(lowest_idx, len(recent_bars)-2):
                c1_high = recent_bars.loc[i, 'high']
                c3_low = recent_bars.loc[i+2, 'low']
                
                if c3_low > c1_high: # Bullish FVG exists!
                    entry_zone = (c1_high, c3_low)
                    stop_loss = sweep_low
                    risk = entry_zone[1] - stop_loss
                    target = entry_zone[1] + (risk * 2) # 1:2 Risk Reward
                    
                    if current_price >= c1_high and current_price <= c3_low:
                        return {
                            "type": "LONG",
                            "symbol": future_ticker,
                            "proxy": symbol,
                            "entry": f"${c1_high:.2f} to ${c3_low:.2f}",
                            "stop": f"${stop_loss:.2f}",
                            "target": f"${target:.2f}",
                            "reason": "Bullish Liquidity Sweep -> Upward MSS -> Price inside Bullish FVG"
                        }
                        
    return None

def main():
    print("🦅 IvanTrades ICT Scanner Started (Tracking QQQ & SPY for Topstep)")
    print("Waiting for setups. Refreshing every 10 seconds...\n")
    
    last_signal = ""
    
    while True:
        try:
            for sym in SYMBOLS:
                df = get_recent_bars(sym, limit=40)
                setup = detect_ict_setup(df, sym)
                
                if setup:
                    # Prevent spamming the exact same signal repeatedly
                    signal_hash = f"{setup['type']}-{setup['proxy']}-{setup['entry']}"
                    if signal_hash != last_signal:
                        # Calculate futures points approximation
                        risk_dollars = abs(float(setup['stop'].replace('$','')) - float(setup['entry'].split(' ')[0].replace('$','')))
                        if setup['proxy'] == "QQQ":
                            futures_pts = risk_dollars * 40 # QQQ moves roughly 1/40th of NQ
                        else:
                            futures_pts = risk_dollars * 10 # SPY moves roughly 1/10th of ES
                            
                        print("=" * 60)
                        print(f"🚨 ICT SETUP DETECTED: {setup['type']} {setup['symbol']}")
                        print(f"📊 Based on {setup['proxy']} ETF data")
                        print(f"📝 Reason: {setup['reason']}")
                        print(f"🎯 ENTRY ZONE : {setup['entry']} (Wait for proxy price to hit this)")
                        print(f"🛑 STOP LOSS  : {setup['stop']} (Approx {futures_pts:.1f} NQ/ES points risk)")
                        print(f"💰 TAKE PROFIT: {setup['target']} (Approx {futures_pts * 2:.1f} NQ/ES points profit)")
                        print("=" * 60)
                        last_signal = signal_hash
                        
            # Sleep before pulling new 1m bars
            time.sleep(10)
            
        except Exception as e:
            print(f"Error fetching data: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
