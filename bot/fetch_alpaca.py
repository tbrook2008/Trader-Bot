import os
import pandas as pd
import alpaca_trade_api as tradeapi
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    load_dotenv()
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    
    if not api_key or not secret_key:
        logging.error("Missing Alpaca API credentials in .env")
        return
        
    api = tradeapi.REST(api_key, secret_key, base_url="https://paper-api.alpaca.markets")
    
    symbol = "QQQ"
    start_date = "2024-01-01"
    end_date = "2024-03-31"
    
    logging.info(f"📥 Downloading 1-minute data for {symbol} from {start_date} to {end_date}...")
    
    # Alpaca limits to 10,000 bars per request, but get_bars handles pagination automatically
    try:
        bars = api.get_bars(symbol, tradeapi.TimeFrame.Minute, start_date, end_date, adjustment='raw').df
    except Exception as e:
        logging.error(f"Failed to fetch data: {e}")
        return
        
    if bars.empty:
        logging.error("No data returned from Alpaca.")
        return
        
    # Reset index to make timestamp a column
    bars = bars.reset_index()
    bars = bars.rename(columns={'timestamp': 'timestamp'})
    
    # Convert timezone to US/Eastern
    bars['timestamp'] = bars['timestamp'].dt.tz_convert('US/Eastern')
    
    output_file = f"historical_{symbol.lower()}_2024Q1.csv"
    bars.to_csv(output_file, index=False)
    
    logging.info(f"✅ Successfully downloaded and saved {len(bars)} 1-minute bars to {output_file}")

if __name__ == "__main__":
    main()
