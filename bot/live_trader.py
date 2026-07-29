"""
bot/live_trader.py — Autonomous Alpaca Live Execution Engine
Streams live 1-minute bars via WebSocket and executes VWAP Mean Reversion mathematically.
Supports multi-symbol portfolio routing.
"""

import os
import time
import asyncio
from dotenv import load_dotenv
import logging

from alpaca.data.live import StockDataStream
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from bot.strategy.mean_reversion import VWAPMeanReversion
from bot.execution.execution_manager import ExecutionManager

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LiveTrader")

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

if not API_KEY or not SECRET_KEY:
    raise ValueError("Missing Alpaca API keys in .env")

# Initialize Alpaca Clients
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_stream = StockDataStream(API_KEY, SECRET_KEY)

# Strategy & State (Multi-Symbol)
SYMBOLS = ["SPY", "QQQ", "IWM", "MSFT", "NVDA", "AAPL", "GOOGL", "AMD", "AMZN", "META"]
RISK_PCT = 0.005  # 0.5% risk per trade per symbol. Max simultaneous risk = 1.5%

# Dictionaries to maintain independent state per symbol
strategies = {sym: VWAPMeanReversion(entry_z=3.0, exit_z=0.5, stop_z=4.5) for sym in SYMBOLS}
current_positions = {sym: 0 for sym in SYMBOLS}  # 1 = LONG, -1 = SHORT, 0 = FLAT
bar_counts = {sym: 0 for sym in SYMBOLS}

# Initialize Execution Manager
exec_manager = ExecutionManager(trading_client)



async def handle_bar(bar_message):
    """Callback fired by Alpaca every time a 1-minute bar closes."""
    global current_positions
    
    symbol = bar_message.symbol
    if symbol not in SYMBOLS:
        return
        
    # Format bar to match our backtester structure
    bar_dict = {
        "timestamp": bar_message.timestamp,
        "open": float(bar_message.open),
        "high": float(bar_message.high),
        "low": float(bar_message.low),
        "close": float(bar_message.close),
        "volume": float(bar_message.volume)
    }
    
    # Pass to specific symbol's strategy engine
    signal = strategies[symbol].evaluate(bar_dict, symbol)
    
    if signal:
        action = signal["action"]
        price = signal["price"]
        z = signal["z_score"]
        
        logger.info(f"⚡ {symbol} SIGNAL: {action} at Z-Score: {z:.2f}")
        
        # Guard against executing entries if we are already in a position for THIS symbol
        pos = current_positions[symbol]
        if action in ["LONG", "SHORT"] and pos == 0:
            exec_manager.execute_hybrid_bracket(action, price, symbol)
            current_positions[symbol] = 1 if action == "LONG" else -1
        elif action == "EXIT" and pos != 0:
            exec_manager.exit_position(symbol)
            current_positions[symbol] = 0
    
    # Heartbeat logging every 30 bars (30 minutes) per symbol
    bar_counts[symbol] += 1
    if bar_counts[symbol] % 30 == 0:
        z = strategies[symbol].latest_z_score
        logger.info(f"💓 HEARTBEAT: {symbol} is active. Processed {bar_counts[symbol]} bars. Current Z-Score: {z:.2f}")

def main():
    logger.info("🤖 Starting Multi-Symbol Live Trader Execution Engine")
    
    # Just grab equity once for starting log
    start_bp = exec_manager.get_account_capital()["buying_power"]
    logger.info(f"Account Margin Buying Power: ${start_bp:,.2f}")
    logger.info(f"Listening to live 1m bars for: {', '.join(SYMBOLS)}")
    
    try:
        # Unpack the SYMBOLS list as positional arguments to subscribe_bars
        data_stream.subscribe_bars(handle_bar, *SYMBOLS)
        data_stream.run()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down Live Trader gracefully.")
    except Exception as e:
        logger.error(f"Fatal error in stream: {e}")

if __name__ == "__main__":
    main()
