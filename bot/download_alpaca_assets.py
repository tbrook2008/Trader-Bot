import os
import pandas as pd
import alpaca_trade_api as tradeapi
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def fetch_data(api, symbol, start_date, end_date):
    logging.info(f"📥 Downloading 1-minute data for {symbol} from {start_date} to {end_date}...")
    try:
        bars = api.get_bars(symbol, tradeapi.TimeFrame.Minute, start_date, end_date, adjustment='raw').df
    except Exception as e:
        logging.error(f"Failed to fetch data for {symbol}: {e}")
        return pd.DataFrame()
        
    if bars.empty:
        logging.error(f"No data returned for {symbol}.")
        return pd.DataFrame()
        
    bars = bars.reset_index()
    bars = bars.rename(columns={'timestamp': 'timestamp'})
    bars['timestamp'] = bars['timestamp'].dt.tz_convert('US/Eastern')
    return bars

def main():
    load_dotenv()
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    
    if not api_key or not secret_key:
        logging.error("Missing Alpaca API credentials in .env")
        return
        
    api = tradeapi.REST(api_key, secret_key, base_url="https://paper-api.alpaca.markets")
    
    start_date = "2024-03-01"
    end_date = "2024-05-31"
    
    # Map future to ETF proxy
    assets = {
        "MNQ": "QQQ",
        "MES": "SPY",
        "GC": "GLD",
        "CL": "USO",
        "YM": "DIA"
    }
    
    for future, etf in assets.items():
        bars = fetch_data(api, etf, start_date, end_date)
        if not bars.empty:
            output_file = f"historical_{future.lower()}_90d.csv"
            bars.to_csv(output_file, index=False)
            logging.info(f"✅ Saved {future} proxy ({etf}) to {output_file}")

if __name__ == "__main__":
    main()
