import os
from datetime import datetime
from dotenv import load_dotenv
from bot.execution.topstep_client import TopstepXClient
import logging

logging.basicConfig(level=logging.INFO)

def main():
    load_dotenv()
    client = TopstepXClient()
    if not client.authenticate():
        print("Auth failed")
        return
        
    contract_id = client.get_contract_id("MNQ")
    print(f"Contract ID: {contract_id}")
    
    payload = {
        "contractId": contract_id,
        "live": False,
        "startTime": "2024-02-01T00:00:00Z",
        "endTime": "2024-02-05T00:00:00Z",
        "unit": 2, # Minute
        "unitNumber": 1,
        "limit": 1000
    }
    
    resp = client.session.post(f"{client.base_url}/History/retrieveBars", json=payload, headers=client._get_auth_headers())
    print(f"Status: {resp.status_code}")
    data = resp.json()
    if data.get("bars"):
        print(f"Received {len(data['bars'])} bars.")
    else:
        print(f"No bars or error: {data}")

if __name__ == "__main__":
    main()
