from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, constr
from typing import Literal, Optional
from bybit_client import BybitClient, OrderType, OrderSide
from config import settings

app = FastAPI(
    title="Bybit Trade Bot API",
    description="API server for executing orders on Bybit exchange",
    version="1.0.0"
)

class OrderRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    side: OrderSide = Field(..., description="Order side (Buy/Sell)")
    order_type: OrderType = Field(..., description="Order type (Market/Limit)")
    quantity: float = Field(..., gt=0, description="Quantity of the trade")
    price: Optional[float] = Field(None, gt=0, description="Limit price (required only for Limit orders)")
    leverage: int = Field(1, ge=1, le=100, description="Leverage (1-100)")
    reduce_only: bool = Field(False, description="True if only reducing position")

@app.on_event("startup")
async def startup_event():
    """Initialization process during application startup"""
    try:
        settings.validate()
    except ValueError as e:
        raise RuntimeError(f"Configuration error: {str(e)}")

@app.post("/order", description="Execute an order")
async def create_order(order: OrderRequest):
    try:
        client = BybitClient()
        
        # Execute the order
        result = client.place_order(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            qty=order.quantity,
            price=order.price,
            leverage=order.leverage,
            reduce_only=order.reduce_only
        )
        
        return {
            "status": "success",
            "data": result
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
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
    try:
        client = BybitClient()
        result = client.cancel_order(
            order_id=request.order_id,
            symbol=request.symbol
        )
        
        return {
            "status": "success",
            "data": result
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cancel-all-orders", description="Cancel all orders for the specified symbol")
async def cancel_all_orders(request: CancelAllOrdersRequest):
    try:
        client = BybitClient()
        result = client.cancel_all_orders(
            symbol=request.symbol
        )
        
        return {
            "status": "success",
            "data": result
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/position/{symbol}", description="Get current position information")
async def get_position(symbol: str):
    try:
        client = BybitClient()
        result = client.get_position(symbol)
        
        return {
            "status": "success",
            "data": result
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/close-position", description="Close a position")
async def close_position(request: PositionRequest):
    try:
        client = BybitClient()
        result = client.close_position(request.symbol)
        
        return {
            "status": "success",
            "data": result
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/balance", description="Get wallet balance")
async def get_balance():
    try:
        client = BybitClient()
        result = client.get_wallet_balance()
        
        return {
            "status": "success",
            "data": result
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
