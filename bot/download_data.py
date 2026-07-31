import pandas as pd
import os
from dotenv import load_dotenv
from bot.execution.topstep_client import TopstepXClient
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    load_dotenv()
    
    symbol = "MNQ"
    days = 90
    output_file = f"historical_{symbol.lower()}_{days}d.csv"
    
    print(f"📥 Starting data download for {symbol} ({days} days)...")
    
    client = TopstepXClient()
    bars = client.get_historical_bars(symbol, days=days, unit_number=1)
    
    if not bars:
        print("❌ Failed to fetch bars or no data returned.")
        return
        
    df = pd.DataFrame(bars)
    
    # Save to CSV
    df.to_csv(output_file, index=False)
    print(f"✅ Successfully downloaded and saved {len(df)} bars to {output_file}")

if __name__ == "__main__":
    main()
