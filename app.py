import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional
from bybit_client import BybitClient, OrderType, OrderSide
from config import settings

# Configure logging
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

# Define the data model for order requests.
# Allow extra fields so that any additional data from TradingView (like trigger_time, max_lag, strategy_id) is ignored.
class OrderRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    side: OrderSide = Field(..., description="Order side (Buy/Sell)")
    order_type: OrderType = Field(..., description="Order type (Market/Limit)")
    quantity: float = Field(..., gt=0, description="Quantity of the trade")
    price: Optional[float] = Field(None, gt=0, description="Limit price (required only for Limit orders)")
    leverage: int = Field(1, ge=1, le=100, description="Leverage (1-100)")
    reduce_only: bool = Field(False, description="True if only reducing position")

    class Config:
        extra = "allow"  # Allow extra fields from TradingView

# Endpoint for direct order placement
@app.post("/order", description="Execute an order")
async def create_order(order: OrderRequest):
    logging.info(f"Received order request: {order.dict()}")
    try:
        client = BybitClient()
        result = client.place_order(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            qty=order.quantity,
            price=order.price,
            leverage=order.leverage,
            reduce_only=order.reduce_only
        )
        logging.info(f"Order placed successfully: {result}")
        return {"status": "success", "data": result}
    except ValueError as e:
        logging.error(f"Order validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Error placing order: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Webhook endpoint for TradingView alerts
@app.post("/webhook", description="Webhook endpoint to execute orders from TradingView")
async def webhook_order(order: OrderRequest):
    logging.info(f"Webhook alert received: {order.dict()}")
    try:
        client = BybitClient()
        result = client.place_order(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            qty=order.quantity,
            price=order.price,
            leverage=order.leverage,
            reduce_only=order.reduce_only
        )
        logging.info(f"Webhook order placed successfully: {result}")
        return {"status": "success", "data": result}
    except ValueError as e:
        logging.error(f"Webhook order validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Error processing webhook order: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class CancelOrderRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    order_id: str = Field(..., description="ID of the order to cancel")

class CancelAllOrdersRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")

class PositionRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")

@app.post("/cancel-order", description="Cancel a specific order")
async def cancel_order(request: CancelOrderRequest):
    logging.info(f"Cancel order request received: {request.dict()}")
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
    logging.info(f"Cancel all orders request received: {request.dict()}")
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
    logging.info(f"Get position request received for symbol: {symbol}")
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
    logging.info(f"Close position request received for symbol: {request.symbol}")
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
