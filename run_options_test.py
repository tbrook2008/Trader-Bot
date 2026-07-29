import os
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

from alpaca.data.historical import OptionHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest

from bot.backtest.engine import BacktestEngine
from bot.strategy.mean_reversion import VWAPMeanReversion

load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

def get_atm_call_option(underlying_symbol="SPY"):
    """Fetches an active at-the-money call option expiring in ~1-7 days."""
    tc = TradingClient(API_KEY, SECRET_KEY)
    
    # We just fetch some active SPY contracts to test against
    req = GetOptionContractsRequest(underlying_symbols=[underlying_symbol], limit=50)
    contracts = tc.get_option_contracts(req)
    
    # Filter for CALLS expiring in the future
    calls = [c for c in contracts.option_contracts if c.type == "call"]
    if not calls:
        raise ValueError(f"No active calls found for {underlying_symbol}")
    
    # Pick the first one for demonstration
    return calls[0].symbol

def run_options_backtest():
    print("🤖 Options Backtesting Engine Starting...")
    
    symbol = "SPY"
    opt_symbol = get_atm_call_option(symbol)
    print(f"✅ Selected Option Contract: {opt_symbol}")
    
    # We will test over a 5 day window strictly in the past to avoid SIP limits
    end_dt = datetime.now() - timedelta(days=2)
    start_dt = end_dt - timedelta(days=5)
    
    # 1. Load Underlying Data
    loader = BacktestEngine(strategy=None)
    print(f"📊 Loading underlying data for {symbol}...")
    underlying_data = loader.load_data([symbol], start=start_dt, end=end_dt)
    if symbol not in underlying_data or underlying_data[symbol].empty:
        print("❌ No underlying data found.")
        return
    df_under = underlying_data[symbol]
    
    # 2. Load Options Data
    print(f"📊 Loading options data for {opt_symbol}...")
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
    req = OptionBarsRequest(
        symbol_or_symbols=[opt_symbol],
        timeframe=TimeFrame.Minute,
        start=start_dt,
        end=end_dt
    )
    opt_bars = opt_client.get_option_bars(req)
    if opt_bars.df.empty:
        print("❌ No options data found.")
        return
        
    df_opt = opt_bars.df.reset_index()
    # Handle Alpaca multi-index format if necessary
    if 'symbol' in df_opt.columns:
        df_opt = df_opt[df_opt['symbol'] == opt_symbol]
    df_opt = df_opt.set_index('timestamp')
    df_opt.index = df_opt.index.tz_convert('UTC')
    
    # 3. Align Data
    print("⚙️ Aligning timestamps and running simulation...")
    # Join on index (timestamp)
    df_joined = df_under.join(df_opt[['close']], rsuffix='_opt', how='inner')
    
    if df_joined.empty:
        print("❌ No overlapping timestamps between underlying and option.")
        return
        
    print(f"✅ Aligned {len(df_joined)} overlapping 1-minute bars.")
    
    # 4. Run Strategy
    strat = VWAPMeanReversion(entry_z=3.0, exit_z=0.5, stop_z=4.5)
    
    trades = []
    pos = 0
    entry_price = 0.0
    
    for ts, row in df_joined.iterrows():
        bar = {
            "timestamp": ts,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"])
        }
        opt_price = float(row["close_opt"])
        
        sig = strat.evaluate(bar, symbol)
        if sig:
            act = sig["action"]
            if act == "LONG" and pos == 0:
                pos = 1
                entry_price = opt_price
                print(f"[{ts}] 🟢 BOUGHT OPTION @ ${opt_price:.2f} (Underlying Z: {sig['z_score']:.2f})")
            elif act == "EXIT" and pos == 1:
                pnl = opt_price - entry_price
                trades.append(pnl)
                pos = 0
                print(f"[{ts}] 🔴 SOLD OPTION  @ ${opt_price:.2f} | PnL: ${pnl:.2f}")
                
    # 5. Report
    print("\n" + "="*40)
    print("🎯 OPTIONS BACKTEST RESULTS")
    print("="*40)
    print(f"Total Trades: {len(trades)}")
    if trades:
        wins = [t for t in trades if t > 0]
        win_rate = len(wins) / len(trades) * 100
        total_pnl = sum(trades)
        # Options are 100 multiplier
        total_pnl_dollars = total_pnl * 100 
        print(f"Win Rate:     {win_rate:.1f}%")
        print(f"Net P&L:      ${total_pnl_dollars:.2f} (assuming 1 contract)")
    print("="*40)

if __name__ == "__main__":
    run_options_backtest()
