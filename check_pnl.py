import os
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

client = TradingClient(API_KEY, SECRET_KEY, paper=True)
acct = client.get_account()

tz = pytz.timezone('US/Eastern')
today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=50, after=today)
orders = client.get_orders(req)

print(f"Account Equity: ${float(acct.equity):.2f}")
print(f"Orders today: {len(orders)}")
for o in orders:
    print(f" - {o.side.name} {o.qty} {o.symbol} @ {o.filled_avg_price} (status: {o.status.name})")
