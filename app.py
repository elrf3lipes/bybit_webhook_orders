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
    leverage: int = Field(5, ge=1, le=100, description="Leverage (default 5)")
    reduce_only: bool = Field(False, description="True if only reducing position")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profit: Optional[float] = Field(None, description="Take profit price")
    stop_loss_pct: Optional[float] = Field(0.10, description="Stop loss percentage (default 10%)")
    take_profit_pct: Optional[float] = Field(0.30, description="Take profit percentage (default 30%)")
    is_leverage: Optional[int] = Field(0, description="Whether to borrow margin in spot trading (0: spot, 1: margin)")

    class Config:
        extra = "allow"

    @root_validator(pre=True)
    def populate_quantity(cls, values):
        # Allow incoming payload to have either 'quantity' or 'qty'
        if "qty" in values and "quantity" not in values:
            values["quantity"] = float(values["qty"])
        return values

    @validator("price", pre=True, always=True)
    def parse_price(cls, v, values, **kwargs):
        if v is None:
            return v
        if isinstance(v, str):
            try:
                # If it's the placeholder "{{close}}", ignore it for market orders.
                if v.strip() == "{{close}}":
                    return None
                return float(v)
            except ValueError:
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

@app.post("/order", description="Execute an order")
async def create_order(order: OrderRequest):
    logging.info(f"Received order request: {order.dict()}")
    try:
        # For market orders, override any provided price so it executes at market price.
        if order.order_type.lower() == "market":
            order.price = None

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
            price=order.price,
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

@app.post("/webhook", description="Webhook endpoint to execute orders from TradingView")
async def webhook_order(request: Request):
    raw_body = await request.body()
    decoded_body = raw_body.decode("utf-8")
    logging.info(f"Raw webhook payload: {decoded_body}")
    try:
        order = OrderRequest.parse_raw(raw_body)
        logging.info(f"Parsed webhook order: {order.dict()}")

        # For market orders, force price to None so it executes at current market price.
        if order.order_type.lower() == "market":
            order.price = None

        # Compute TP/SL if necessary using the provided price (if any) and percentages.
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

# Endpoints for canceling orders, getting positions, and balance checks remain unchanged...
# (Please refer to the original code for those endpoints.)

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
