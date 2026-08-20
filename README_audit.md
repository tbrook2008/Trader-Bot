# Automated Execution Bot V2

## Features
- **Dynamic Risk Scaling**: Evaluates buffer over hard floor and trades up to 4 Micro contracts.
- **State Persistence**: Serializes state to `bot_state.json` to prevent duplicate signals across restarts (Machine Gun Re-Entry Prevention).
- **Rogue Position Detection**: Polls Topstep API out-of-band to catch missing fills or manually executed trades that could desync the state engine.
