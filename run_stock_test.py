import os
from datetime import datetime
from dotenv import load_dotenv
from bot.strategy.mean_reversion import VWAPMeanReversion
from bot.backtest.advanced_engine import AdvancedBacktestEngine
from bot.backtest.engine import BacktestEngine

load_dotenv()

def main():
    loader = BacktestEngine(strategy=None)
    
    symbols = [
        "AAPL", "TSLA", "NVDA", "AMZN", 
        "MSFT", "META", "GOOGL", "AMD", 
        "SPCX"
    ]
    
    start_train = datetime(2022, 1, 1)
    end_train   = datetime(2023, 12, 31)
    
    start_blind = datetime(2024, 1, 1)
    end_blind   = datetime(2024, 12, 31)
    
    for symbol in symbols:
        print(f"\n{'='*50}\n TESTING SYMBOL: {symbol}\n{'='*50}")
        
        # Load Train Data just for this symbol
        data_train = loader.load_data([symbol], start=start_train, end=end_train)
        has_train = symbol in data_train and not data_train[symbol].empty
        
        # Load Blind Data just for this symbol
        data_blind = loader.load_data([symbol], start=start_blind, end=end_blind)
        has_blind = symbol in data_blind and not data_blind[symbol].empty
        
        if not has_train and not has_blind:
            print(f"\nSkipping {symbol} — No data returned.")
            continue
            
        # Train
        if has_train:
            strat_train = VWAPMeanReversion(entry_z=3.0, exit_z=0.5, stop_z=4.5)
            engine_train = AdvancedBacktestEngine(strat_train)
            report_train = engine_train.run_single({symbol: data_train[symbol]})
            report_train["name"] = f"VWAP Mean Reversion - {symbol} (2022-2023)"
            engine_train.print_report(report_train)

        # Blind
        if has_blind:
            strat_blind = VWAPMeanReversion(entry_z=3.0, exit_z=0.5, stop_z=4.5)
            engine_blind = AdvancedBacktestEngine(strat_blind)
            report_blind = engine_blind.run_single({symbol: data_blind[symbol]})
            report_blind["name"] = f"VWAP Mean Reversion - {symbol} (2024 BLIND)"
            engine_blind.print_report(report_blind)
            
        # Free memory
        del data_train
        del data_blind

if __name__ == "__main__":
    main()
