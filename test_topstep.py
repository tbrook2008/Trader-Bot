import pandas as pd
from bot.execution.topstep_client import TopstepXClient
client = TopstepXClient()
client.authenticate()
bars = client.get_historical_bars("GC", days=10, unit_number=1)
if bars: print(f"Success! Got {len(bars)} bars for GC")
else: print("Failed to get bars for GC")
