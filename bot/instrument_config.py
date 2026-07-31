INSTRUMENT_CONFIG = {
    # US Equity Indices (Micro)
    "MNQ": {
        "sector": "equity_index",
        "tick_size": 0.25,
        "tick_value": 0.50,
        "point_value": 2.0,
        "sniper_window": {"start_h": 13, "start_m": 0, "end_h": 15, "end_m": 30},
    },
    "MES": {
        "sector": "equity_index",
        "tick_size": 0.25,
        "tick_value": 1.25,
        "point_value": 5.0,
        "sniper_window": {"start_h": 13, "start_m": 0, "end_h": 15, "end_m": 30},
    },
    "MYM": {
        "sector": "equity_index",
        "tick_size": 1.0,
        "tick_value": 0.50,
        "point_value": 0.50, # 1 pt = $0.50 for Micro Dow
        "sniper_window": {"start_h": 13, "start_m": 0, "end_h": 15, "end_m": 30},
    },
    "M2K": {
        "sector": "equity_index",
        "tick_size": 0.10,
        "tick_value": 0.50,
        "point_value": 5.0,
        "sniper_window": {"start_h": 13, "start_m": 0, "end_h": 15, "end_m": 30},
    },
    # US Equity Indices (Mini/Standard)
    "NQ": {
        "sector": "equity_index",
        "tick_size": 0.25,
        "tick_value": 5.0,
        "point_value": 20.0,
        "sniper_window": {"start_h": 13, "start_m": 0, "end_h": 15, "end_m": 30},
    },
    "ES": {
        "sector": "equity_index",
        "tick_size": 0.25,
        "tick_value": 12.50,
        "point_value": 50.0,
        "sniper_window": {"start_h": 13, "start_m": 0, "end_h": 15, "end_m": 30},
    },
    # Metals
    "GC": {
        "sector": "metals",
        "tick_size": 0.10,
        "tick_value": 10.0,
        "point_value": 100.0,
        "sniper_window": {"start_h": 8, "start_m": 0, "end_h": 10, "end_m": 0},
    },
    # Energy
    "CL": {
        "sector": "energy",
        "tick_size": 0.01,
        "tick_value": 10.0,
        "point_value": 1000.0,
        "sniper_window": {"start_h": 9, "start_m": 0, "end_h": 11, "end_m": 30},
    }
}
