import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest

load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

tc = TradingClient(API_KEY, SECRET_KEY)
req = GetOptionContractsRequest(underlying_symbols=["SPY"], limit=5)
try:
    contracts = tc.get_option_contracts(req)
    print([c.symbol for c in contracts.option_contracts])
except Exception as e:
    print("Error:", e)
