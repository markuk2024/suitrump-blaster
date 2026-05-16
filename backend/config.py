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

# Pool Configuration - testing durations: 10min, 15min, 20min
POOL_DURATIONS = {
    "daily": 600,         # 10 minutes in seconds
    "weekly": 900,       # 15 minutes in seconds
    "monthly": 1200      # 20 minutes in seconds
}

POOL_PAYOUTS = {
    "daily": [50, 30, 20],
    "weekly": [40, 25, 20, 15],
    "monthly": [45, 25, 20, 10]
}

POOL_ENTRY_FEES = {
    "daily": 2_000_000_000,  # 2 SUI
    "weekly": 2_500_000_000,  # 2.5 SUI
    "monthly": 1_000_000_000,  # 1 SUI
}

POOL_CONTRACT_IDS = {
    "daily": "0x9aca57fc06b61557f9f893d9ad25a96fa6a1ad053bd2b36bced0914e45a6af66",
    "weekly": "0x1aabc79aa06979b37b0923b18c7615dd3487a641518eb37719417b550b263d65",
    "monthly": "0xf7e04ca08481dda0eb6d9b53c058bcb15a49bb309b79168cf5914335fea9b785",
}

# Cetus Configuration for SUI to SUITRUMP swaps
CETUS_PACKAGE = "0x1eabed72c53feb3805120a081dc15963c204dc8d091542592abaf7a35689b2fb"
SUITRUMP_PACKAGE = "0xdeb831e796f16f8257681c0d5d4108fa94333060300b2459133a96631bf470b8"
SUITRUMP_TYPE = f"{SUITRUMP_PACKAGE}::suitrump::SUITRUMP"
# Cetus pool ID for SUI/SUITRUMP pair
CETUS_SUI_SUITRUMP_POOL_ID = os.getenv("CETUS_SUI_SUITRUMP_POOL_ID", "0x2c2bbe5623c66e9ddf39185d3ab5528493c904b89c415df991aeed73c2427aa9")

@dataclass
class Config:
    SUI_NETWORK: str = "https://fullnode.mainnet.sui.io"
    PACKAGE_ID: str = _get_env("PACKAGE_ID", "PackageID", default="0x175918d5654f0eaf645412ce72399bef2c2508e95f01bd81bf27c880b839e1b8")
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
    
    # Cetus Configuration
    CETUS_SUI_SUITRUMP_POOL_ID: str = os.getenv("CETUS_SUI_SUITRUMP_POOL_ID", "0x2c2bbe5623c66e9ddf39185d3ab5528493c904b89c415df991aeed73c2427aa9")
    REQUIRE_SUITRUMP_PAYOUTS: bool = os.getenv("REQUIRE_SUITRUMP_PAYOUTS", "true").lower() == "true"
    
    # Real On-chain Pool Object IDs
    DAILY_POOL_ID: str = os.getenv("DAILY_POOL_ID", "0x478672bbf8512f9403d029df4adb5e1e386bd9d23ff318e14f47136035df5597")
    WEEKLY_POOL_ID: str = os.getenv("WEEKLY_POOL_ID", "0x73704b5dcf1fba6c7cfec523bff2e8d3b6f6e4ae24a4d87a14bc75e72d21417d")
    MONTHLY_POOL_ID: str = os.getenv("MONTHLY_POOL_ID", "0xc110d1a5896b78230dfc1e6a9951f1e74dc93a1790483be33cb248209c2701e9")

config = Config()
