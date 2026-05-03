import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def _get_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default

@dataclass
class Config:
    SUI_NETWORK: str = "https://fullnode.mainnet.sui.io"
    PACKAGE_ID: str = _get_env("PACKAGE_ID", "PackageID", default="")
    MAX_SCORE_PER_SECOND: int = 100
    MAX_GAME_DURATION: int = 300  # 5 minutes
    DEV_FEE_PERCENTAGE: float = 2.5  # 2.5% dev fee on prize pools
    DEV_WALLET_ADDRESS: str = os.getenv("DEV_WALLET_ADDRESS", "0x4c2891f70f1317fed1198140e0f06f49593c82558b2b467e1717c23fee9131a6")
    POOL_ENTRY_FEE: int = 100_000_000  # 0.1 SUI in MIST
    ADMIN_PRIVATE_KEY: str = _get_env("ADMIN_PRIVATE_KEY", "PRIVATE_KEY", "SUI_PRIVATE_KEY", default="")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "")
    S3_DATA_KEY: str = os.getenv("S3_DATA_KEY", "sui-blaster/data.json")
    
    # Real On-chain Pool Object IDs
    DAILY_POOL_ID: str = os.getenv("DAILY_POOL_ID", "0x0")
    WEEKLY_POOL_ID: str = os.getenv("WEEKLY_POOL_ID", "0x0")
    MONTHLY_POOL_ID: str = os.getenv("MONTHLY_POOL_ID", "0x0")

config = Config()
