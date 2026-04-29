import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

@dataclass
class Config:
    SUI_NETWORK: str = "https://fullnode.mainnet.sui.io"
    PACKAGE_ID: str = os.getenv("PACKAGE_ID", "")
    MAX_SCORE_PER_SECOND: int = 100
    MAX_GAME_DURATION: int = 300  # 5 minutes
    DEV_FEE_PERCENTAGE: float = 2.5  # 2.5% dev fee on prize pools
    DEV_WALLET_ADDRESS: str = os.getenv("DEV_WALLET_ADDRESS", "0x4c2891f70f1317fed1198140e0f06f49593c82558b2b467e1717c23fee9131a6")
    POOL_ENTRY_FEE: int = 100_000_000  # 0.1 SUI in MIST
    ADMIN_PRIVATE_KEY: str = os.getenv("ADMIN_PRIVATE_KEY", "")
    
    # Real On-chain Pool Object IDs
    DAILY_POOL_ID: str = os.getenv("DAILY_POOL_ID", "0x0")
    WEEKLY_POOL_ID: str = os.getenv("WEEKLY_POOL_ID", "0x0")
    MONTHLY_POOL_ID: str = os.getenv("MONTHLY_POOL_ID", "0x0")

config = Config()
