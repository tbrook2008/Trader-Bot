import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

load_dotenv('/root/trader_bot/.env')
api = TradingClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'), paper=True)
positions = api.get_all_positions()

if not positions:
    print('No active positions.')
else:
    for pos in positions:
        print(f'Symbol: {pos.symbol}, Side: {pos.side}, Qty: {pos.qty}, Entry: ${float(pos.avg_entry_price):.2f}, Current: ${float(pos.current_price):.2f}, Unrealized PNL: ${float(pos.unrealized_pl):.2f}')
