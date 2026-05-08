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
    DEV_WALLET_ADDRESS: str = os.getenv("DEV_WALLET_ADDRESS", "0x0d32cdae7aa9a25003687dcbfe154c5d13bc51b76fd29116a54276c1f80fd140")
    POOL_ENTRY_FEE: int = 100_000_000  # 0.1 SUI in MIST
    ADMIN_PRIVATE_KEY: str = _get_env("ADMIN_PRIVATE_KEY", "PRIVATE_KEY", "SUI_PRIVATE_KEY", default="")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "")
    S3_DATA_KEY: str = os.getenv("S3_DATA_KEY", "suitrump-blaster/data.json")
    
    # SUITRUMP Token Configuration
    SUITRUMP_TOKEN_PACKAGE: str = os.getenv("SUITRUMP_TOKEN_PACKAGE", "0x0")
    SUITRUMP_TOKEN_MODULE: str = os.getenv("SUITRUMP_TOKEN_MODULE", "suitrump")
    SUITRUMP_TOKEN_NAME: str = os.getenv("SUITRUMP_TOKEN_NAME", "SUITRUMP")
    
    # Real On-chain Pool Object IDs
    DAILY_POOL_ID: str = os.getenv("DAILY_POOL_ID", "0x478672bbf8512f9403d029df4adb5e1e386bd9d23ff318e14f47136035df5597")
    WEEKLY_POOL_ID: str = os.getenv("WEEKLY_POOL_ID", "0x73704b5dcf1fba6c7cfec523bff2e8d3b6f6e4ae24a4d87a14bc75e72d21417d")
    MONTHLY_POOL_ID: str = os.getenv("MONTHLY_POOL_ID", "0xc110d1a5896b78230dfc1e6a9951f1e74dc93a1790483be33cb248209c2701e9")

config = Config()
