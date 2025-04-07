import logging
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, root_validator, validator
from typing import Optional

from bybit_client import BybitClient, OrderType, OrderSide
from config import settings

# Configure logging to output timestamps and log levels
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

app = FastAPI(
    title="Bybit Trade Bot API",
    description="API server for executing orders on Bybit exchange",
    version="2.0.0"
)

@app.on_event("startup")
async def startup_event():
    try:
        settings.validate()
        logging.info("Application startup complete. Settings validated.")
    except ValueError as e:
        logging.error(f"Configuration error during startup: {e}")
        raise RuntimeError(f"Configuration error: {str(e)}")

# Pydantic model for order requests. Extra fields from TradingView alerts are allowed.
class OrderRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    side: OrderSide = Field(..., description="Order side (Buy/Sell)")
    order_type: OrderType = Field(..., description="Order type (Market/Limit)")
    # Allow quantity to be supplied as either 'quantity' or 'qty'
    quantity: float = Field(..., gt=0, description="Quantity of the trade")
    price: Optional[float] = Field(None, gt=0, description="Limit price (required only for Limit orders)")
    leverage: int = Field(1, ge=1, le=100, description="Leverage (1-100)")
    reduce_only: bool = Field(False, description="True if only reducing position")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profit: Optional[float] = Field(None, description="Take profit price")
    stop_loss_pct: Optional[float] = Field(None, description="Stop loss percentage (e.g., 0.10 for 10%)")
    take_profit_pct: Optional[float] = Field(None, description="Take profit percentage (e.g., 0.30 for 30%)")
    is_leverage: Optional[int] = Field(0, description="Whether to borrow margin in spot trading (0: spot, 1: margin)")

    class Config:
        # Allow extra fields from TradingView alerts.
        extra = "allow"

    @root_validator(pre=True)
    def populate_quantity(cls, values):
        """
        Allow the incoming payload to have either 'quantity' or 'qty'.
        If only 'qty' is provided, assign it to 'quantity'.
        """
        if "qty" in values and "quantity" not in values:
            values["quantity"] = float(values["qty"])
        return values

    @validator("price", pre=True, always=True)
    def parse_price(cls, v, values, **kwargs):
        """
        If price is provided as a string (e.g. "{{close}}"), try to convert to float.
        If conversion fails and it matches a known placeholder, return None.
        """
        if v is None:
            return v
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                if v.strip() == "{{close}}":
                    return None
                raise ValueError("price must be a valid number")
        return v

    @validator("stop_loss_pct", "take_profit_pct", pre=True, always=True)
    def parse_pct(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                raise ValueError("Percentage fields must be valid numbers")
        return v

def compute_tp_sl_from_price(base_price: float, side: str, sl_pct: Optional[float], tp_pct: Optional[float]):
    """
    Calculate stop loss and take profit prices from the given base price.
    For Buy orders:
        SL = base_price * (1 - sl_pct)
        TP = base_price * (1 + tp_pct)
    For Sell orders:
        SL = base_price * (1 + sl_pct)
        TP = base_price * (1 - tp_pct)
    """
    stop_loss = None
    take_profit = None
    if side.lower() == "buy":
        if sl_pct is not None:
            stop_loss = base_price * (1 - sl_pct)
        if tp_pct is not None:
            take_profit = base_price * (1 + tp_pct)
    elif side.lower() == "sell":
        if sl_pct is not None:
            stop_loss = base_price * (1 + sl_pct)
        if tp_pct is not None:
            take_profit = base_price * (1 - tp_pct)
    return stop_loss, take_profit

# Endpoint for direct order placement (for frontends or manual testing)
@app.post("/order", description="Execute an order")
async def create_order(order: OrderRequest):
    logging.info(f"Received order request: {order.dict()}")
    try:
        # If a base price is provided and TP/SL percentages are given but TP/SL are not set,
        # compute them from the provided price.
        if order.price is not None and (order.stop_loss is None or order.take_profit is None):
            if order.stop_loss_pct is not None or order.take_profit_pct is not None:
                computed_sl, computed_tp = compute_tp_sl_from_price(order.price, order.side, order.stop_loss_pct, order.take_profit_pct)
                if order.stop_loss is None:
                    order.stop_loss = computed_sl
                if order.take_profit is None:
                    order.take_profit = computed_tp

        client = BybitClient()
        result = client.place_order(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            qty=order.quantity,
            price=None if order.order_type.lower() == "market" else order.price,
            leverage=order.leverage,
            reduce_only=order.reduce_only,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            stop_loss_pct=order.stop_loss_pct,
            take_profit_pct=order.take_profit_pct,
            is_leverage=order.is_leverage
        )
        logging.info(f"Order placed successfully: {result}")
        return {"status": "success", "data": result}
    except ValueError as e:
        logging.error(f"Order validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Error placing order: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Webhook endpoint to process TradingView alerts
@app.post("/webhook", description="Webhook endpoint to execute orders from TradingView")
async def webhook_order(request: Request):
    raw_body = await request.body()
    decoded_body = raw_body.decode("utf-8")
    logging.info(f"Raw webhook payload: {decoded_body}")
    try:
        order = OrderRequest.parse_raw(raw_body)
        logging.info(f"Parsed webhook order: {order.dict()}")

        # Compute TP/SL if price and percentage values are provided but absolute TP/SL are missing.
        if order.price is not None and (order.stop_loss is None or order.take_profit is None):
            if order.stop_loss_pct is not None or order.take_profit_pct is not None:
                computed_sl, computed_tp = compute_tp_sl_from_price(order.price, order.side, order.stop_loss_pct, order.take_profit_pct)
                if order.stop_loss is None:
                    order.stop_loss = computed_sl
                if order.take_profit is None:
                    order.take_profit = computed_tp

        client = BybitClient()
        result = client.place_order(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            qty=order.quantity,
            price=order.price,
            leverage=order.leverage,
            reduce_only=order.reduce_only,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            stop_loss_pct=order.stop_loss_pct,
            take_profit_pct=order.take_profit_pct,
            is_leverage=order.is_leverage
        )
        logging.info(f"Webhook order placed successfully: {result}")
        return {"status": "success", "data": result}
    except ValueError as e:
        logging.error(f"Webhook validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Validation error: {e}")
    except Exception as e:
        logging.error(f"Error processing webhook order: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Request model for canceling a specific order
class CancelOrderRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    order_id: str = Field(..., description="ID of the order to cancel")

# Request model for canceling all orders
class CancelAllOrdersRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")

# Request model for fetching position or closing a position
class PositionRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")

@app.post("/cancel-order", description="Cancel a specific order")
async def cancel_order(request: CancelOrderRequest):
    logging.info(f"Cancel order request: {request.dict()}")
    try:
        client = BybitClient()
        result = client.cancel_order(order_id=request.order_id, symbol=request.symbol)
        logging.info(f"Order cancelled: {result}")
        return {"status": "success", "data": result}
    except Exception as e:
        logging.error(f"Error cancelling order: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cancel-all-orders", description="Cancel all orders for the specified symbol")
async def cancel_all_orders(request: CancelAllOrdersRequest):
    logging.info(f"Cancel all orders request: {request.dict()}")
    try:
        client = BybitClient()
        result = client.cancel_all_orders(symbol=request.symbol)
        logging.info(f"All orders cancelled for {request.symbol}: {result}")
        return {"status": "success", "data": result}
    except Exception as e:
        logging.error(f"Error cancelling all orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/position/{symbol}", description="Get current position information")
async def get_position(symbol: str):
    logging.info(f"Get position request for symbol: {symbol}")
    try:
        client = BybitClient()
        result = client.get_position(symbol)
        logging.info(f"Position for {symbol}: {result}")
        return {"status": "success", "data": result}
    except Exception as e:
        logging.error(f"Error fetching position for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/close-position", description="Close a position")
async def close_position(request: PositionRequest):
    logging.info(f"Close position request for symbol: {request.symbol}")
    try:
        client = BybitClient()
        result = client.close_position(request.symbol)
        logging.info(f"Position closed for {request.symbol}: {result}")
        return {"status": "success", "data": result}
    except ValueError as e:
        logging.error(f"Error closing position for {request.symbol}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Error closing position for {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/balance", description="Get wallet balance")
async def get_balance():
    logging.info("Get wallet balance request received.")
    try:
        client = BybitClient()
        result = client.get_wallet_balance()
        logging.info(f"Wallet balance: {result}")
        return {"status": "success", "data": result}
    except Exception as e:
        logging.error(f"Error fetching wallet balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
