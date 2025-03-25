import os
from typing import Optional

class Settings:
    BYBIT_API_KEY: Optional[str] = os.getenv("BYBIT_API_KEY")
    BYBIT_API_SECRET: Optional[str] = os.getenv("BYBIT_API_SECRET")
    TESTNET: bool = False  # Use "True" or "False" string from environment

    @classmethod
    def validate(cls):
        if not cls.BYBIT_API_KEY or not cls.BYBIT_API_SECRET:
            raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET must be set in environment variables")

settings = Settings()
