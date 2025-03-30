from typing import Optional
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env file


class Settings:
    BYBIT_API_KEY: Optional[str] = os.getenv("BYBIT_API_KEY")
    BYBIT_API_SECRET: Optional[str] = os.getenv("BYBIT_API_SECRET")

    # Parse flags as booleans
    TESTNET: bool = os.getenv("TESTNET", "True").lower() in ["true", "1", "t", "y", "yes"]
    DEMO: bool = os.getenv("DEMO", "True").lower() in ["true", "1", "t", "y", "yes"]

    # For testnet, BYBIT_DOMAIN must be provided; for mainnet, default to "api.bybit.com"
    BYBIT_DOMAIN: Optional[str] = os.getenv("BYBIT_DOMAIN") if TESTNET else os.getenv("BYBIT_DOMAIN", "api.bybit.com")
    BYBIT_TLD: Optional[str] = os.getenv("BYBIT_TLD", "")

    @classmethod
    def validate(cls):
        if not cls.BYBIT_API_KEY or not cls.BYBIT_API_SECRET:
            raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET must be set in environment variables")
        if cls.TESTNET and not cls.BYBIT_DOMAIN:
            raise ValueError("For testnet, BYBIT_DOMAIN must be set in environment variables")


settings = Settings()
