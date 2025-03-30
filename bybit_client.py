from typing import Literal, Optional
from pybit.unified_trading import HTTP
from config import settings

OrderType = Literal["Market", "Limit"]
OrderSide = Literal["Buy", "Sell"]
PositionSide = Literal["Both"]  # Only 'Both' is supported in Bybit's futures trading

class BybitClient:
    def __init__(self):
        kwargs = {
            "testnet": settings.TESTNET,
            "api_key": settings.BYBIT_API_KEY,
            "api_secret": settings.BYBIT_API_SECRET
        }
        if settings.BYBIT_DOMAIN:
            kwargs["domain"] = settings.BYBIT_DOMAIN
        if settings.BYBIT_TLD:
            kwargs["tld"] = settings.BYBIT_TLD

        self.client = HTTP(**kwargs)

    def set_leverage(self, symbol: str, leverage: int = 1) -> None:
        try:
            self.client.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage)
            )
        except Exception as e:
            if "leverage not modified" not in str(e).lower():
                raise Exception(f"Failed to set leverage: {str(e)}")

    def get_symbol_info(self, symbol: str) -> dict:
        try:
            response = self.client.get_instruments_info(
                category="linear",
                symbol=symbol
            )
            if not response.get("result", {}).get("list"):
                raise ValueError(f"Symbol {symbol} not found")
            return response["result"]["list"][0]
        except Exception as e:
            raise Exception(f"Failed to get symbol info: {str(e)}")

    def place_order(
            self,
            symbol: str,
            side: OrderSide,
            order_type: OrderType,
            qty: float,
            leverage: int = 1,
            price: Optional[float] = None,
            position_side: PositionSide = "Both",
            reduce_only: bool = False,
            stop_loss: Optional[float] = None,
            take_profit: Optional[float] = None,
            is_leverage: Optional[int] = None
    ) -> dict:
        symbol_info = self.get_symbol_info(symbol)
        min_qty = float(symbol_info.get("minOrderQty", "0"))
        if qty < min_qty:
            raise ValueError(
                f"Order quantity ({qty}) is less than minimum allowed quantity ({min_qty}) for {symbol}"
            )

        try:
            self.set_leverage(symbol, leverage)
            params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "positionIdx": 0,
                "reduceOnly": reduce_only
            }
            if order_type == "Limit":
                if price is None:
                    raise ValueError("Limit order requires a price")
                params["price"] = str(price)

            # Incorporate stop loss and take profit if provided
            if stop_loss is not None:
                params["stopLoss"] = str(stop_loss)
            if take_profit is not None:
                params["takeProfit"] = str(take_profit)

            # Integrate isLeverage option if provided (for Unified Account spot trading)
            if is_leverage is not None:
                params["isLeverage"] = str(is_leverage)

            response = self.client.place_order(**params)
            return response
        except Exception as e:
            raise Exception(f"Failed to place order: {str(e)}")

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        try:
            response = self.client.cancel_order(
                category="linear",
                symbol=symbol,
                orderId=order_id
            )
            return response
        except Exception as e:
            raise Exception(f"Failed to cancel order: {str(e)}")

    def cancel_all_orders(self, symbol: str) -> dict:
        try:
            response = self.client.cancel_all_orders(
                category="linear",
                symbol=symbol
            )
            return response
        except Exception as e:
            raise Exception(f"Failed to cancel all orders: {str(e)}")

    def get_position(self, symbol: str) -> dict:
        try:
            response = self.client.get_positions(
                category="linear",
                symbol=symbol
            )
            if not response.get("result", {}).get("list"):
                return None
            return response["result"]["list"][0]
        except Exception as e:
            raise Exception(f"Failed to get position: {str(e)}")

    def close_position(self, symbol: str) -> dict:
        try:
            position = self.get_position(symbol)
            if not position or float(position.get("size", "0")) == 0:
                raise ValueError(f"No open position for {symbol}")
            side = "Sell" if position["side"] == "Buy" else "Buy"
            params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": "Market",
                "qty": str(abs(float(position["size"]))),
                "positionIdx": 0,
                "reduceOnly": True
            }
            response = self.client.place_order(**params)
            return response
        except Exception as e:
            raise Exception(f"Failed to close position: {str(e)}")

    def get_wallet_balance(self) -> dict:
        try:
            return self.client.get_wallet_balance(accountType="UNIFIED")
        except Exception as e:
            raise Exception(f"Failed to get wallet balance: {str(e)}")
