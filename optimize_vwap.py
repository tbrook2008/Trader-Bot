import os
import itertools
from datetime import datetime
from dotenv import load_dotenv

from bot.strategy.mean_reversion import VWAPMeanReversion
from bot.backtest.advanced_engine import AdvancedBacktestEngine
from bot.backtest.engine import BacktestEngine

load_dotenv()

def main():
    loader = BacktestEngine(strategy=None)
    
    # We will optimize against SPY as a broad market baseline for 2024
    symbols = ["SPY"]
    
    print("Loading historical data...")
    start_train = datetime(2024, 1, 1)
    end_train   = datetime(2024, 12, 31)
    
    data = loader.load_data(symbols, start=start_train, end=end_train)
    
    if "SPY" not in data or data["SPY"].empty:
        print("No data for SPY. Make sure Alpaca keys are valid.")
        return
        
    print(f"Loaded {len(data['SPY'])} bars for SPY.")
    
    entry_z_grid = [2.5, 3.0, 3.5, 4.0]
    exit_z_grid = [0.0, 0.5, 1.0]
    stop_z_grid = [3.5, 4.0, 4.5, 5.0, 6.0]
    
    results = []
    
    combinations = list(itertools.product(entry_z_grid, exit_z_grid, stop_z_grid))
    print(f"Testing {len(combinations)} parameter combinations...")
    
    for i, (ez, exz, sz) in enumerate(combinations):
        # Stop loss should be greater than entry
        if sz <= ez:
            continue
            
        strat = VWAPMeanReversion(entry_z=ez, exit_z=exz, stop_z=sz)
        engine = AdvancedBacktestEngine(strat)
        
        # Run test
        report = engine.run_single({"SPY": data["SPY"]})
        
        results.append({
            "entry_z": ez,
            "exit_z": exz,
            "stop_z": sz,
            "trades": report["total_trades"],
            "win_rate": report["win_rate"],
            "net_pnl": report["net_pnl"],
            "max_dd": report["max_dd"]
        })
        
        if (i+1) % 10 == 0:
            print(f"Processed {i+1}/{len(combinations)} combinations...")
            
    # Sort by Net PNL
    results.sort(key=lambda x: x["net_pnl"], reverse=True)
    
    print("\n--- TOP 5 CONFIGURATIONS FOR 2024 ---")
    for r in results[:5]:
        print(f"Entry: {r['entry_z']}, Exit: {r['exit_z']}, Stop: {r['stop_z']} | "
              f"Trades: {r['trades']}, Win Rate: {r['win_rate']:.1f}%, "
              f"Net PNL: ${r['net_pnl']:.2f}, Max DD: ${r['max_dd']:.2f}")

if __name__ == "__main__":
    main()
