import os
from datetime import datetime
from dotenv import load_dotenv
from bot.strategy.mean_reversion import VWAPMeanReversion
from bot.backtest.advanced_engine import AdvancedBacktestEngine
from bot.backtest.engine import BacktestEngine

load_dotenv()

def main():
    loader = BacktestEngine(strategy=None)
    
    symbols = ["SPY", "QQQ", "DIA", "IWM"]
    
    # ── PERIOD 1: 2022 to 2023 (Training Data) ──
    start_train = datetime(2022, 1, 1)
    end_train   = datetime(2023, 12, 31)
    
    print(f"\n--- Loading Training Data ({start_train.date()} to {end_train.date()}) ---")
    data_train = loader.load_data(symbols, start=start_train, end=end_train)
    
    # ── PERIOD 2: 2024 (Blind Out-Of-Sample Data) ──
    start_blind = datetime(2024, 1, 1)
    end_blind   = datetime(2024, 12, 31)
    
    print(f"\n--- Loading Blind Data ({start_blind.date()} to {end_blind.date()}) ---")
    data_blind = loader.load_data(symbols, start=start_blind, end=end_blind)
    
    for symbol in symbols:
        print(f"\n{'='*50}\n TESTING SYMBOL: {symbol}\n{'='*50}")
        
        # Train
        strat_train = VWAPMeanReversion(entry_z=3.0, exit_z=0.5, stop_z=4.5)
        engine_train = AdvancedBacktestEngine(strat_train)
        report_train = engine_train.run_single({symbol: data_train[symbol]})
        report_train["name"] = f"VWAP Mean Reversion - {symbol} (2022-2023)"
        engine_train.print_report(report_train)

        # Blind
        strat_blind = VWAPMeanReversion(entry_z=3.0, exit_z=0.5, stop_z=4.5)
        engine_blind = AdvancedBacktestEngine(strat_blind)
        report_blind = engine_blind.run_single({symbol: data_blind[symbol]})
        report_blind["name"] = f"VWAP Mean Reversion - {symbol} (2024 BLIND)"
        engine_blind.print_report(report_blind)

if __name__ == "__main__":
    main()
