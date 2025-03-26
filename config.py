from typing import Optional
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env file


class Settings:
    BYBIT_API_KEY: Optional[str] = os.getenv("BYBIT_API_KEY")
    BYBIT_API_SECRET: Optional[str] = os.getenv("BYBIT_API_SECRET")
    DEMO: bool = os.getenv("DEMO", "True").lower() in ["true", "1", "t", "y", "yes"]
    TESTNET: bool = os.getenv("TESTNET", "True").lower() in ["true", "1", "t", "y", "yes"]

    @classmethod
    def validate(cls):
        if not cls.BYBIT_API_KEY or not cls.BYBIT_API_SECRET:
            raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET must be set in environment variables")


settings = Settings()
