"""
run_backtest.py — Entry point to run the ORB backtest.

Usage:
    python run_backtest.py                   # 365 days, SPY + QQQ
    python run_backtest.py --days 180        # 180 days
    python run_backtest.py --symbols SPY     # SPY only
    python run_backtest.py --tp 2.0          # TP at 2x range width
"""

import argparse
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from bot.strategy.orb import ORBStrategy
from bot.backtest.engine import BacktestEngine
import bot.config as cfg


def main():
    parser = argparse.ArgumentParser(description="ORB Strategy Backtest")
    parser.add_argument("--days",    type=int,   default=cfg.BACKTEST_DAYS,    help="Days of history")
    parser.add_argument("--capital", type=float, default=cfg.BACKTEST_CAPITAL, help="Starting capital")
    parser.add_argument("--symbols", type=str,   default=",".join(cfg.SYMBOLS), help="Comma-separated symbols")
    parser.add_argument("--tp",      type=float, default=cfg.ORB_TP_MULTIPLIER, help="TP multiplier")
    parser.add_argument("--risk",    type=float, default=cfg.RISK_PER_TRADE_PCT, help="Risk per trade (fraction)")
    parser.add_argument("--save",    action="store_true", help="Save trades CSV to docs/")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]

    print(f"\n🤖  Trader Bot — ORB Backtest")
    print(f"    Symbols: {symbols}")
    print(f"    Period:  {args.days} days")
    print(f"    Capital: ${args.capital:,.0f}")
    print(f"    TP mult: {args.tp}×")
    print(f"    Risk:    {args.risk*100:.1f}% per trade\n")

    strategy = ORBStrategy(
        tp_multiplier=args.tp,
        max_range_pct=cfg.ORB_MAX_RANGE_PCT,
    )

    engine = BacktestEngine(
        strategy=strategy,
        capital=args.capital,
        risk_pct=args.risk,
    )

    data   = engine.load_data(symbols, days=args.days)
    report = engine.run(data)
    engine.print_report(report)

    if args.save and "trades_df" in report:
        os.makedirs("docs", exist_ok=True)
        path = "docs/backtest_results.csv"
        report["trades_df"].to_csv(path, index=False)
        print(f"💾  Trades saved to {path}\n")

    return 0 if report.get("_win_rate", 0) >= cfg.PASS_MIN_WIN_RATE else 1


if __name__ == "__main__":
    sys.exit(main())
