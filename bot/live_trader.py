"""
bot/live_trader.py — Autonomous Alpaca Live Execution Engine
Streams live 1-minute bars via WebSocket and executes VWAP Mean Reversion mathematically.
Supports multi-symbol portfolio routing.
"""

import os
import time
import asyncio
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
import logging

from alpaca.data.live import StockDataStream
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, PositionSide

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
historical_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Strategy & State (Multi-Symbol)
SYMBOLS = ["SPY", "QQQ", "IWM", "MSFT", "NVDA", "AAPL", "GOOGL", "AMD", "AMZN", "META"]
RISK_PCT = 0.005  # 0.5% risk per trade per symbol. Max simultaneous risk = 1.5%

# Dictionaries to maintain independent state per symbol
strategies = {sym: VWAPMeanReversion(entry_z=3.5, exit_z=0.5, stop_z=5.0) for sym in SYMBOLS}
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
    
    # ── STATE RECOVERY ──────────────────────────────────────────────────────────
    logger.info("🔄 Checking Alpaca for active positions to recover state...")
    try:
        positions = trading_client.get_all_positions()
        recovered_count = 0
        for pos in positions:
            if pos.symbol in SYMBOLS:
                direction = 1 if pos.side == PositionSide.LONG else -1
                current_positions[pos.symbol] = direction
                strategies[pos.symbol].position = direction
                strategies[pos.symbol].entry_price = float(pos.avg_entry_price)
                recovered_count += 1
                logger.info(f"✅ Recovered {pos.symbol} | Side: {pos.side.name} | Entry: ${pos.avg_entry_price}")
        logger.info(f"🔄 State Recovery Complete. Restored {recovered_count} active positions.")
    except Exception as e:
        logger.error(f"🚨 Failed to recover state: {e}")
    # ── HISTORICAL DATA WARM UP ─────────────────────────────────────────────────
    logger.info("🔥 Initiating Historical Data Warm Up...")
    try:
        tz = pytz.timezone('US/Eastern')
        now = datetime.now(tz)
        start_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
        
        # If we start the bot before 9:30 AM, fetch yesterday's data instead so we don't crash
        if now < start_time:
            start_time = start_time - timedelta(days=1)
            
        req = StockBarsRequest(
            symbol_or_symbols=SYMBOLS,
            timeframe=TimeFrame.Minute,
            start=start_time
        )
        
        bars = historical_client.get_stock_bars(req)
        
        # Loop through each symbol's returned historical bars and feed them sequentially
        for symbol in SYMBOLS:
            if symbol in bars.data:
                symbol_bars = bars.data[symbol]
                for bar in symbol_bars:
                    bar_dict = {
                        "timestamp": bar.timestamp,
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": float(bar.volume)
                    }
                    signal = strategies[symbol].evaluate(bar_dict, symbol)
                    bar_counts[symbol] += 1
                    
                    if signal and signal["action"] == "EXIT" and current_positions[symbol] != 0:
                        logger.warning(f"🚨 {symbol} triggered EXIT during warm up! Exiting stranded position immediately.")
                        exec_manager.exit_position(symbol)
                        current_positions[symbol] = 0
                        
                logger.info(f"🔥 Warmed up {len(symbol_bars)} bars for {symbol}. Current Z-Score: {strategies[symbol].latest_z_score:.2f}")
            else:
                logger.warning(f"⚠️ No historical data found for {symbol} to warm up.")
        
        logger.info("🔥 Engine Warm Up Complete.")
    except Exception as e:
        logger.error(f"🚨 Failed to warm up historical data: {e}")
    # ────────────────────────────────────────────────────────────────────────────

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
