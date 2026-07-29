import logging
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

logger = logging.getLogger("ExecutionManager")

class ExecutionManager:
    def __init__(self, trading_client: TradingClient):
        self.client = trading_client

    def get_account_capital(self) -> dict:
        """Returns both equity and margin buying power."""
        try:
            account = self.client.get_account()
            return {
                "equity": float(account.equity),
                "buying_power": float(account.buying_power)
            }
        except Exception as e:
            logger.error(f"Failed to fetch account info: {e}")
            return {"equity": 50000.0, "buying_power": 100000.0}

    def execute_hybrid_bracket(self, action: str, current_price: float, symbol: str, max_position_pct: float = 0.10):
        """
        Executes a dynamic-sized market order with a wide bracket for catastrophic safety.
        The algorithmic Z-score engine is still expected to exit the trade earlier dynamically.
        """
        try:
            account_info = self.get_account_capital()
            equity = account_info["equity"]
            buying_power = account_info["buying_power"]

            # Dynamic Margin Sizing
            target_cost = equity * max_position_pct
            
            # Safety check: Do we have enough buying power?
            estimated_cost = min(target_cost, buying_power * 0.95)
            shares = max(1, int(estimated_cost / current_price))
            
            if estimated_cost < target_cost:
                logger.warning(f"⚠️ Margin limit reached! Reduced {symbol} allocation to fit remaining Buying Power.")

            # Define catastrophic safety bracket (10% profit limit, 5% stop loss)
            if action == "LONG":
                side = OrderSide.BUY
                tp_price = round(current_price * 1.10, 2)
                sl_price = round(current_price * 0.95, 2)
            elif action == "SHORT":
                side = OrderSide.SELL
                tp_price = round(current_price * 0.90, 2)
                sl_price = round(current_price * 1.05, 2)
            else:
                return

            req = MarketOrderRequest(
                symbol=symbol,
                qty=shares,
                side=side,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=tp_price),
                stop_loss=StopLossRequest(stop_price=sl_price)
            )
            
            self.client.submit_order(order_data=req)
            logger.info(f"🚀 EXECUTED {action} | {shares} shs of {symbol} @ ~{current_price} | BP: ${buying_power:,.2f}")
            logger.info(f"🛡️ SAFETY BRACKET ATTACHED | TP: {tp_price} | SL: {sl_price}")
            
        except Exception as e:
            logger.error(f"🚨 ORDER EXECUTION FAILED FOR {symbol}: {e}")

    def exit_position(self, symbol: str):
        """
        Dynamic exit from the Z-Score engine.
        Closing the position via Alpaca automatically cancels any resting OCO/Bracket orders.
        """
        try:
            self.client.close_position(symbol, cancel_orders=True)
            logger.info(f"💥 EXECUTED DYNAMIC EXIT | Closed all open positions and cancelled brackets for {symbol}")
        except Exception as e:
            logger.error(f"🚨 FAILED TO EXIT {symbol}: {e}")
