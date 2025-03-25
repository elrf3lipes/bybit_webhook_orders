from typing import Literal, Optional
from pybit.unified_trading import HTTP
from config import settings

OrderType = Literal["Market", "Limit"]
OrderSide = Literal["Buy", "Sell"]
PositionSide = Literal["Both"]  #Only 'Both' is supported in Bybit's futures trading

class BybitClient:
    def __init__(self):
        self.client = HTTP(
            testnet=settings.TESTNET,
            api_key=settings.BYBIT_API_KEY,
            api_secret=settings.BYBIT_API_SECRET
        )

    def set_leverage(self, symbol: str, leverage: int = 1) -> None:
        """
        Set leverage
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            leverage: Leverage (1-100)
        """
        try:
            self.client.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage)
            )
        except Exception as e:
            # Ignore if leverage is already set
            if "leverage not modified" not in str(e).lower():
                raise Exception(f"Failed to set leverage: {str(e)}")

    def get_symbol_info(self, symbol: str) -> dict:
        """
        Get trading information for a symbol
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            
        Returns:
            Symbol information
        """
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
        reduce_only: bool = False
    ) -> dict:
        # Get symbol information and check the minimum order quantity
        symbol_info = self.get_symbol_info(symbol)
        min_qty = float(symbol_info.get("minOrderQty", "0"))
        
        if qty < min_qty:
            raise ValueError(
                f"Order quantity ({qty}) is less than minimum allowed quantity ({min_qty}) for {symbol}"
            )
        """
        Place an order
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            side: Order side (Buy/Sell)
            order_type: Order type (Market/Limit)
            qty: Quantity to trade
            price: Price for limit orders (required only for Limit orders)
        
        Returns:
            Order response
        """
        try:
            # Set leverage
            self.set_leverage(symbol, leverage)

            # Order parameters
            params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "positionIdx": 0,  # Both: 0
                "reduceOnly": reduce_only
            }

            # Set price for limit orders
            if order_type == "Limit":
                if price is None:
                    raise ValueError("Limit order requires a price")
                params["price"] = str(price)

            # Execute the order
            response = self.client.place_order(**params)
            return response

        except Exception as e:
            raise Exception(f"Failed to place order: {str(e)}")

        def place_order(
        self,
        symbol: str,
        int_side: int,
        qty: float,
        leverage: int = 1,
        position_side: PositionSide = "Both",
        reduce_only: bool = False
    ) -> dict:
        # Get symbol information and check the minimum order quantity
        symbol_info = self.get_symbol_info(symbol)
        min_qty = float(symbol_info.get("minOrderQty", "0"))
        
        if qty < min_qty:
            raise ValueError(
                f"Order quantity ({qty}) is less than minimum allowed quantity ({min_qty}) for {symbol}"
            )
        """
        Place an order
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            side: Order side (Buy/Sell)
            order_type: Order type (Market/Limit)
            qty: Quantity to trade
            price: Price for limit orders (required only for Limit orders)
        
        Returns:
            Order response
        """
        try:
            # Set leverage
            self.set_leverage(symbol, leverage)

            if int_side == 1:
                side = OrderSide.Buy
            elif int_side == -1:
                side = OrderSide.Sell
            elif int_side == 0:
                return self.close_position(symbol)
            else:
                raise ValueError("Invalid side value")


            # Order parameters
            params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": OrderType.Market,
                "qty": str(qty),
                "positionIdx": 0,  # Both: 0
                "reduceOnly": reduce_only
            }

            # Set price for limit orders
            if order_type == "Limit":
                if price is None:
                    raise ValueError("Limit order requires a price")
                params["price"] = str(price)

            # Execute the order
            response = self.client.place_order(**params)
            return response

        except Exception as e:
            raise Exception(f"Failed to place order: {str(e)}")

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        """
        Cancel an order
        
        Args:
            order_id: The ID of the order to cancel
            symbol: Trading pair (e.g., BTCUSDT)
            
        Returns:
            Cancel result response
        """
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
        """
        Cancel all orders for a given symbol
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            
        Returns:
            Cancel all orders result response
        """
        try:
            response = self.client.cancel_all_orders(
                category="linear",
                symbol=symbol
            )
            return response
        except Exception as e:
            raise Exception(f"Failed to cancel all orders: {str(e)}")

    def get_position(self, symbol: str) -> dict:
        """
        Get current position information
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            
        Returns:
            Position information
        """
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
        """
        Close a position
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            
        Returns:
            Close position result response
        """
        try:
            # Get current position information
            position = self.get_position(symbol)
            if not position or float(position.get("size", "0")) == 0:
                raise ValueError(f"No open position for {symbol}")

            # Create an order for the opposite side of the position
            side = "Sell" if position["side"] == "Buy" else "Buy"
            
            # Close with a market order (use current leverage)
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
        """
        Get wallet balance
        
        Returns:
            Balance information
        """
        try:
            return self.client.get_wallet_balance(accountType="UNIFIED")
        except Exception as e:
            raise Exception(f"Failed to get wallet balance: {str(e)}")
