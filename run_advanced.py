import argparse
from bot.strategy.stat_arb import StatArbStrategy
from bot.strategy.mean_reversion import VWAPMeanReversion
from bot.backtest.advanced_engine import AdvancedBacktestEngine
from bot.backtest.engine import BacktestEngine
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=180)
    args = parser.parse_args()
    
    print("Loading data via Standard Engine...")
    # We use the old engine just to fetch the data since it has the load_data method
    loader = BacktestEngine(strategy=None)
    data = loader.load_data(["SPY", "QQQ"], days=args.days)
    
    print("\n--- Running VWAP Mean Reversion (SPY) ---")
    mr_strat = VWAPMeanReversion(entry_z=3.0, exit_z=0.5, stop_z=4.5)
    mr_engine = AdvancedBacktestEngine(mr_strat)
    mr_report = mr_engine.run_single({"SPY": data["SPY"]})
    mr_engine.print_report(mr_report)
    
    print("\n--- Running Statistical Arbitrage (QQQ vs SPY) ---")
    sa_strat = StatArbStrategy(window_size=120, entry_z=2.0, exit_z=0.0, stop_z=4.0)
    sa_engine = AdvancedBacktestEngine(sa_strat)
    sa_report = sa_engine.run_pairs({"QQQ": data["QQQ"], "SPY": data["SPY"]})
    sa_engine.print_report(sa_report)

if __name__ == "__main__":
    main()
