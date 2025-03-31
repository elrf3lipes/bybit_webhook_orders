import logging
import ast
import operator as op
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, validator
from typing import Literal, Optional

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


# --- Helper function for safe evaluation of simple arithmetic expressions ---
def safe_eval(expr: str) -> float:
    """
    Safely evaluate arithmetic expressions containing only numbers and
    operators +, -, *, /, and **.
    """
    # Allowed operators mapping
    allowed_operators = {
        ast.Add: op.add,
        ast.Sub: op.sub,
        ast.Mult: op.mul,
        ast.Div: op.truediv,
        ast.Pow: op.pow,
        ast.USub: op.neg
    }

    def eval_node(node):
        if isinstance(node, ast.Num):  # <number>
            return node.n
        elif isinstance(node, ast.BinOp):  # <left> <operator> <right>
            if type(node.op) not in allowed_operators:
                raise ValueError("Unsupported operator")
            return allowed_operators[type(node.op)](eval_node(node.left), eval_node(node.right))
        elif isinstance(node, ast.UnaryOp):  # - <operand>
            if type(node.op) not in allowed_operators:
                raise ValueError("Unsupported unary operator")
            return allowed_operators[type(node.op)](eval_node(node.operand))
        else:
            raise ValueError("Unsupported expression")

    node = ast.parse(expr, mode='eval').body
    return eval_node(node)


# --- Updated Pydantic Model ---
class OrderRequest(BaseModel):
    # Use alias so that either "quantity" or "qty" in the payload works
    quantity: float = Field(..., gt=0, description="Quantity of the trade", alias="qty")
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    side: OrderSide = Field(..., description="Order side (Buy/Sell)")
    order_type: OrderType = Field(..., description="Order type (Market/Limit)")
    price: Optional[float] = Field(None, gt=0, description="Limit price (required only for Limit orders)")
    leverage: int = Field(1, ge=1, le=100, description="Leverage (1-100)")
    reduce_only: bool = Field(False, description="True if only reducing position")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profit: Optional[float] = Field(None, description="Take profit price")
    stop_loss_pct: Optional[float] = Field(None, description="Stop loss percentage (e.g., 0.10 for 10%)")
    take_profit_pct: Optional[float] = Field(None, description="Take profit percentage (e.g., 0.30 for 30%)")
    # Field from TradingView alerts; not used for linear orders.
    is_leverage: Optional[int] = Field(0, description="Whether to borrow margin in spot trading (0: spot, 1: margin)")

    class Config:
        extra = "allow"
        allow_population_by_field_name = True  # Allow using alias names

    @validator("symbol", pre=True)
    def fix_symbol(cls, v):
        # Remove trailing ".P" if present (commonly used in auto sell alerts)
        if isinstance(v, str) and v.endswith(".P"):
            return v.replace(".P", "")
        return v

    @validator("stop_loss", "take_profit", pre=True)
    def parse_numeric(cls, v):
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                try:
                    return safe_eval(v)
                except Exception:
                    raise ValueError(f"Invalid expression for value: {v}")
        return v


# --- Endpoints ---
@app.post("/order", description="Execute an order")
async def create_order(order: OrderRequest):
    logging.info(f"Received order request: {order.dict()}")
    try:
        client_obj = BybitClient()
        result = client_obj.place_order(
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
        client_obj = BybitClient()
        result = client_obj.place_order(
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


@app.post("/cancel-order", description="Cancel a specific order")
async def cancel_order(request: OrderRequest):
    logging.info(f"Cancel order request: {request.dict()}")
    try:
        client_obj = BybitClient()
        result = client_obj.cancel_order(order_id=request.symbol, symbol=request.symbol)
        logging.info(f"Order cancelled: {result}")
        return {"status": "success", "data": result}
    except Exception as e:
        logging.error(f"Error cancelling order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cancel-all-orders", description="Cancel all orders for the specified symbol")
async def cancel_all_orders(request: OrderRequest):
    logging.info(f"Cancel all orders request: {request.dict()}")
    try:
        client_obj = BybitClient()
        result = client_obj.cancel_all_orders(symbol=request.symbol)
        logging.info(f"All orders cancelled for {request.symbol}: {result}")
        return {"status": "success", "data": result}
    except Exception as e:
        logging.error(f"Error cancelling all orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/position/{symbol}", description="Get current position information")
async def get_position(symbol: str):
    logging.info(f"Get position request for symbol: {symbol}")
    try:
        client_obj = BybitClient()
        result = client_obj.get_position(symbol)
        logging.info(f"Position for {symbol}: {result}")
        return {"status": "success", "data": result}
    except Exception as e:
        logging.error(f"Error fetching position for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/close-position", description="Close a position")
async def close_position(request: OrderRequest):
    logging.info(f"Close position request for symbol: {request.symbol}")
    try:
        client_obj = BybitClient()
        result = client_obj.close_position(request.symbol)
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
        client_obj = BybitClient()
        result = client_obj.get_wallet_balance()
        logging.info(f"Wallet balance: {result}")
        return {"status": "success", "data": result}
    except Exception as e:
        logging.error(f"Error fetching wallet balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
