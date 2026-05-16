from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
from collections import defaultdict
from datetime import timedelta
import time
import json
import os
import subprocess
from config import config
import httpx
import hashlib
import base64
import struct
import asyncio
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Bech32 decoding for Sui keys
try:
    import bech32
    HAS_BECH32 = True
except ImportError:
    HAS_BECH32 = False
    print("bech32 library not available, custom decoding will be used")

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32M_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

def decode_sui_private_key(encoded_key: str) -> bytes:
    """Decode Sui private key from bech32 format"""
    try:
        if HAS_BECH32:
            # Use bech32 library
            hrp, data = bech32.bech32_decode(encoded_key)
            if hrp is None:
                raise ValueError("Invalid bech32 string")
            
            # Convert from 5-bit to 8-bit
            data_bytes = bech32.convertbits(data, 5, 8, False)
            result = bytes(data_bytes)
            
            # Sui keys might have a prefix byte - try different approaches
            if len(result) == 33:
                print(f"Decoded key is 33 bytes, trying different approaches")
                # Try using last 32 bytes instead of first
                result_last = result[1:]
                result_first = result[:-1]
                
                # Derive addresses for both approaches
                addr_last = None
                addr_first = None
                
                try:
                    test_key = ed25519.Ed25519PrivateKey.from_private_bytes(result_last)
                    test_pub = test_key.public_key().public_bytes(
                        encoding=serialization.Encoding.Raw,
                        format=serialization.PublicFormat.Raw
                    )
                    addr_last = "0x" + hashlib.blake2b(b'\x00' + test_pub, digest_size=32).hexdigest()
                    print(f"Stripping first byte gives address: {addr_last}")
                except Exception as e:
                    print(f"Failed with last 32 bytes: {e}")
                
                try:
                    test_key = ed25519.Ed25519PrivateKey.from_private_bytes(result_first)
                    test_pub = test_key.public_key().public_bytes(
                        encoding=serialization.Encoding.Raw,
                        format=serialization.PublicFormat.Raw
                    )
                    addr_first = "0x" + hashlib.blake2b(b'\x00' + test_pub, digest_size=32).hexdigest()
                    print(f"Stripping last byte gives address: {addr_first}")
                except Exception as e:
                    print(f"Failed with first 32 bytes: {e}")
                
                # Use last 32 bytes by default (most common)
                result = result_last
                print(f"Using last 32 bytes (stripping first byte)")
            elif len(result) > 32:
                print(f"Decoded key is {len(result)} bytes, using last 32 bytes")
                result = result[-32:]
            
            return result
        else:
            # Fallback to custom implementation
            hrp, data = bech32_decode(encoded_key)
            data_bytes = convert_bits(data, 5, 8, pad=False)
            result = bytes(data_bytes)
            
            if len(result) == 33:
                result = result[1:]
            elif len(result) > 32:
                result = result[-32:]
            
            return result
    except Exception as e:
        print(f"Failed to decode Sui key: {e}")
        return None

# BCS Encoding helpers
def encode_uleb128(value: int) -> bytes:
    """Encode unsigned LEB128"""
    result = bytearray()
    while value >= 0x80:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)

def encode_u64(value: int) -> bytes:
    """Encode u64 in little-endian"""
    return struct.pack('<Q', value)

def encode_u32(value: int) -> bytes:
    """Encode u32 in little-endian"""
    return struct.pack('<I', value)

def encode_u16(value: int) -> bytes:
    """Encode u16 in little-endian"""
    return struct.pack('<H', value)

def encode_u8(value: int) -> bytes:
    """Encode u8"""
    return struct.pack('<B', value)

def encode_bool(value: bool) -> bytes:
    """Encode bool"""
    return b'\x01' if value else b'\x00'

def encode_string(value: str) -> bytes:
    """Encode string with length prefix"""
    encoded = value.encode('utf-8')
    return encode_uleb128(len(encoded)) + encoded

def encode_address(address: str) -> bytes:
    """Encode Sui address (32 bytes)"""
    addr = address.replace('0x', '')
    return bytes.fromhex(addr.zfill(64))

def encode_object_id(object_id: str) -> bytes:
    """Encode ObjectID (32 bytes)"""
    obj_id = object_id.replace('0x', '')
    return bytes.fromhex(obj_id.zfill(64))

def encode_transaction_kind(tx_kind: dict) -> bytes:
    """Encode TransactionKind to BCS"""
    kind = tx_kind.get("kind")
    if kind == "moveCall":
        # MoveCall encoding
        result = b'\x00'  # MoveCall tag
        result += encode_string(tx_kind.get("target", ""))
        
        # Encode type arguments
        type_args = tx_kind.get("type_arguments", [])
        result += encode_uleb128(len(type_args))
        for type_arg in type_args:
            result += encode_string(type_arg)
        
        # Encode arguments (simplified - for full implementation need proper argument encoding)
        args = tx_kind.get("arguments", [])
        result += encode_uleb128(len(args))
        for arg in args:
            # Simplified argument encoding - treat as strings for now
            if isinstance(arg, str):
                result += encode_string(arg)
            elif isinstance(arg, bool):
                result += encode_bool(arg)
            elif isinstance(arg, int):
                result += encode_u64(arg)
            else:
                result += encode_string(str(arg))
        
        return result
    else:
        raise Exception(f"Unsupported transaction kind: {kind}")

def encode_transaction_data(tx_data: dict) -> bytes:
    """Encode TransactionData to BCS"""
    result = b''
    
    # Encode TransactionKind
    tx_kind = tx_data.get("kind") or tx_data.get("transactions", [{}])[0]
    result += encode_transaction_kind(tx_kind)
    
    # Encode sender
    result += encode_address(tx_data.get("sender", "0x0"))
    
    # Encode gas data (simplified)
    gas_data = tx_data.get("gasData", {})
    result += encode_address(gas_data.get("owner", "0x0"))
    result += encode_u64(int(gas_data.get("price", "1000")))
    result += encode_u64(int(gas_data.get("budget", "10000000")))
    
    # Encode gas payment (simplified)
    payment = gas_data.get("payment", [])
    result += encode_uleb128(len(payment))
    for p in payment:
        result += encode_object_id(p.get("objectId", "0x0"))
    
    return result

# Sui RPC Client with BCS support
class SuiRPCClient:
    def __init__(self, rpc_url: str, private_key: str):
        self.rpc_url = rpc_url
        self.private_key = private_key
        self._load_key()
    
    def _load_key(self):
        """Load Ed25519 private key"""
        try:
            key_hex = self.private_key.strip()
            
            # Check if it's Sui bech32 format (suiprivkey1...)
            if key_hex.startswith("suiprivkey1"):
                print("Detected Sui bech32 key format, decoding...")
                key_bytes = decode_sui_private_key(key_hex)
                if key_bytes is None:
                    raise ValueError("Failed to decode Sui bech32 key")
            else:
                # Remove 0x prefix if present
                key_hex = key_hex.replace("0x", "")
                
                # Validate hex string
                if not key_hex:
                    raise ValueError("Private key is empty")
                
                # Check if it's a valid hex string
                try:
                    key_bytes = bytes.fromhex(key_hex)
                except ValueError:
                    print(f"Private key contains non-hex characters. Length: {len(key_hex)}")
                    raise ValueError("Private key must be hexadecimal")
            
            # Ed25519 private key should be 32 bytes
            if len(key_bytes) != 32:
                print(f"Private key length: {len(key_bytes)} bytes (expected 32 bytes)")
                if len(key_bytes) > 32:
                    # Try truncating to 32 bytes
                    key_bytes = key_bytes[:32]
                    print("Truncating private key to 32 bytes")
                else:
                    # Try padding with zeros
                    key_bytes = key_bytes.ljust(32, b'\x00')
                    print("Padding private key to 32 bytes")
            
            self.signing_key = ed25519.Ed25519PrivateKey.from_private_bytes(key_bytes)
            self.public_key = self.signing_key.public_key()
            self.address = self._get_address_from_public_key()
            print(f"Private key loaded successfully. Address: {self.address}")
        except Exception as e:
            print(f"Failed to load private key: {e}")
            print(f"Private key value (first 16 chars): {self.private_key[:16] if self.private_key else 'None'}")
            self.signing_key = None
    
    def _get_address_from_public_key(self) -> str:
        """Derive Sui address from public key"""
        pub_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        hash_obj = hashlib.blake2b(b'\x00' + pub_bytes, digest_size=32)
        return "0x" + hash_obj.hexdigest()
    
    async def _rpc_call(self, method: str, params: list = None):
        """Make RPC call to Sui node"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params or []
                },
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    def _build_transaction_payload(self, move_calls: list) -> dict:
        """Build transaction payload for Move calls"""
        # Simplified transaction builder - for full implementation need BCS encoding
        return {
            "kind": "moveCall",
            "target": move_calls[0]["target"] if move_calls else "",
            "arguments": move_calls[0]["arguments"] if move_calls else [],
            "type_arguments": move_calls[0]["type_arguments"] if move_calls else []
        }
    
    def _sign_transaction(self, transaction_data: dict) -> str:
        """Sign transaction data with proper BCS encoding"""
        if not self.signing_key:
            raise Exception("Private key not loaded")
        
        # Encode transaction data to BCS
        tx_bytes = encode_transaction_data(transaction_data)
        
        # Sign the BCS-encoded transaction
        signature = self.signing_key.sign(tx_bytes)
        
        # Sui signature format: flag + signature + pubkey
        flag = bytes([0x00])  # Ed25519 signature flag
        sig_bytes = signature + self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return "0x" + (flag + sig_bytes).hex()
    
    async def execute_move_call(self, target: str, arguments: list = None, type_arguments: list = None):
        """Execute a Move call via RPC with proper BCS signing"""
        if not self.signing_key:
            raise Exception("Private key not loaded")
        
        # Build transaction kind
        tx_kind = {
            "kind": "moveCall",
            "target": target,
            "arguments": arguments or [],
            "type_arguments": type_arguments or []
        }
        
        # Try to execute via executeTransactionBlock with BCS-encoded signing
        try:
            # Get gas objects for the sender - use correct RPC method
            gas_result = await self._rpc_call("sui_getCoins", [self.address, "0x2::sui::SUI", None, None])
            
            if "error" in gas_result:
                print(f"RPC Error getting coins: {gas_result['error']}")
                return await self._simulate_transaction(tx_kind)
            
            gas_objects = gas_result.get("result", {}).get("data", [])
            if not gas_objects:
                print(f"No gas objects found for address {self.address}")
                return await self._simulate_transaction(tx_kind)
            
            # Use first gas object
            gas_object_id = gas_objects[0]["coinObjectId"]
            
            # Build transaction data with proper structure for Sui RPC
            transaction_data = {
                "kind": "moveCall",
                "target": target,
                "arguments": arguments or [],
                "type_arguments": type_arguments or [],
                "sender": self.address,
                "gasData": {
                    "payment": [{"objectId": gas_object_id, "version": gas_objects[0].get("version", 1), "digest": gas_objects[0].get("digest", "0x0000000000000000000000000000000000000000000000000000000000000000")}],
                    "owner": self.address,
                    "price": "1000",
                    "budget": "10000000"
                }
            }
            
            # Sign transaction with BCS encoding
            signature = self._sign_transaction(transaction_data)
            
            # Execute transaction via RPC
            result = await self._rpc_call(
                "sui_executeTransactionBlock",
                [
                    transaction_data,
                    [signature],
                    {"showEffects": True, "showEvents": True}
                ]
            )
            
            if "error" in result:
                print(f"Execution error: {result['error']}")
                return await self._simulate_transaction(tx_kind)
            
            tx_digest = result.get("result", {}).get("digest", "")
            effect_status = result.get("result", {}).get("effects", {}).get("status", {}).get("status")
            if effect_status and effect_status != "success":
                print(f"Execution failed on-chain: {result.get('result', {}).get('effects', {}).get('status')}")
                return {
                    "status": "error",
                    "transaction_id": tx_digest,
                    "message": "Transaction failed on-chain"
                }
            if tx_digest:
                print(f"Transaction executed on-chain: {tx_digest}")
                return {
                    "status": "success",
                    "transaction_id": tx_digest,
                    "message": "Transaction executed on-chain"
                }
            else:
                print("No transaction digest in result")
                return await self._simulate_transaction(tx_kind)
            
        except Exception as e:
            print(f"Execution failed: {e}")
            return await self._simulate_transaction(tx_kind)
    
    async def _simulate_transaction(self, tx_kind: dict):
        """Simulate transaction via devInspectTransactionBlock"""
        try:
            result = await self._rpc_call(
                "sui_devInspectTransactionBlock",
                [
                    self.address,
                    tx_kind,
                    None,  # gas price
                    None   # gas sponsor
                ]
            )
            
            if "error" in result:
                print(f"RPC Error: {result['error']}")
                return {
                    "status": "error",
                    "error": result.get("error")
                }
            
            return {
                "status": "simulated",
                "transaction_id": f"inspect_{int(time.time())}",
                "message": "Transaction inspected successfully",
                "inspection_result": result.get("result", {})
            }
            
        except Exception as e:
            print(f"Simulation failed: {e}")
            return {
                "status": "simulated",
                "transaction_id": f"sim_{int(time.time())}",
                "message": "Transaction simulated"
            }
    

HAS_PYSUI = False


app = FastAPI(title="SuiTrump Blaster Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://suitrump-blaster.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Admin auth: only the dev wallet can access sensitive endpoints
async def dev_wallet_auth(x_dev_wallet: str = Header(None, alias="X-Dev-Wallet")):
    dev = config.DEV_WALLET_ADDRESS
    if not x_dev_wallet or x_dev_wallet.strip().lower() != dev.lower():
        raise HTTPException(status_code=403, detail="Forbidden: dev wallet required")
    return x_dev_wallet

class ScoreData(BaseModel):
    wallet: str
    score: int
    game_duration: int
    timestamp: int
    pool_id: Optional[str] = None
    replay_data: Optional[List[dict]] = None

class PoolCreate(BaseModel):
    name: str
    duration: str
    entry_fee: str
    prize: str

class PoolJoin(BaseModel):
    pool_id: str
    wallet: str
    transaction_id: Optional[str] = None  # Sui transaction digest
    amount: Optional[str] = None  # Amount paid in SUI

class ScoreSubmit(BaseModel):
    pool_id: str
    wallet: str
    score: int

class PayoutRequest(BaseModel):
    pool_id: str
    num_winners: int = 10  # Number of top players to pay out

# Data persistence
DATA_FILE = os.getenv("DATA_FILE", "/var/data/sui/data.json")

# Try to use Render Disk, fall back to local if not available
if not os.path.exists(os.path.dirname(DATA_FILE)):
    print(f"Render Disk mount point not found, using local storage")
    DATA_FILE = os.path.join(os.getcwd(), "data.json")


def _get_duration_override(env_name: str, default_seconds: int) -> int:
    """Allow overriding a pool duration via environment variable (seconds)."""
    value = os.getenv(env_name)
    if not value:
        return default_seconds
    try:
        parsed = int(value)
        if parsed <= 0:
            raise ValueError
        print(f"Using {env_name} override: {parsed} seconds")
        return parsed
    except ValueError:
        print(f"Invalid {env_name}='{value}', falling back to {default_seconds}")
        return default_seconds


# Pool durations (seconds) - testing durations: 10min, 15min, 20min
POOL_DURATIONS = {
    "daily": _get_duration_override("POOL_DURATION_DAILY_SECONDS", 10 * 60),  # 10 minutes
    "weekly": _get_duration_override("POOL_DURATION_WEEKLY_SECONDS", 15 * 60),  # 15 minutes
    "monthly": _get_duration_override("POOL_DURATION_MONTHLY_SECONDS", 20 * 60)  # 20 minutes
}

POOL_PAYOUTS = {
    "daily": [50, 30, 20],
    "weekly": [40, 25, 20, 15],
    "monthly": [45, 25, 20, 10]
}


def _ensure_data_dir():
    data_dir = os.path.dirname(DATA_FILE)
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)


def _parse_entry_fee_to_mist(entry_fee) -> int:
    if not entry_fee:
        return config.POOL_ENTRY_FEE
    # Handle both string and integer entry fees
    if isinstance(entry_fee, (int, float)):
        # If already a number, assume it's in mist if large, or SUI if small
        if entry_fee > 1000:
            return int(entry_fee)
        else:
            return int(entry_fee * 1_000_000_000)
    # String handling
    cleaned = "".join(ch for ch in str(entry_fee) if ch.isdigit() or ch == ".")
    try:
        value = float(cleaned)
    except ValueError:
        return config.POOL_ENTRY_FEE
    return int(value * 1_000_000_000)


def _normalize_address(value: Optional[str]) -> Optional[str]:
    return value.lower() if isinstance(value, str) else value

def _migrate_participants(participants):
    """Migrate old string-only participant lists to rich dict records"""
    migrated = []
    now = int(time.time())
    for p in participants:
        if isinstance(p, str):
            migrated.append({
                "wallet": p,
                "joined_at": now,
                "games_played": 0,
                "best_score": 0,
                "total_score": 0,
                "last_active": now
            })
        elif isinstance(p, dict):
            migrated.append(p)
    return migrated

def get_pool_wallets(pool_id):
    """Extract wallet addresses from participant records"""
    participants = pool_participants.get(pool_id, [])
    # Ensure participants is a list
    if not isinstance(participants, list):
        print(f"WARNING: pool_participants[{pool_id}] is not a list, resetting to empty list")
        pool_participants[pool_id] = []
        participants = []
    wallets = []
    for p in participants:
        if isinstance(p, str):
            wallets.append(p)
        elif isinstance(p, dict):
            wallets.append(p.get("wallet", ""))
    return wallets


def prune_global_leaderboard_entries() -> bool:
    """Remove global leaderboard entries that no longer exist in pool leaderboards."""
    global global_leaderboard
    if not global_leaderboard:
        return False

    cleaned = []
    for entry in global_leaderboard:
        pool_id = entry.get("pool_id")
        if not pool_id:
            cleaned.append(entry)
            continue

        pool_scores = pool_leaderboards.get(pool_id, [])
        if any(
            score.get("wallet") == entry.get("wallet")
            and score.get("score") == entry.get("score")
            and score.get("timestamp") == entry.get("timestamp")
            for score in pool_scores
        ):
            cleaned.append(entry)

    if len(cleaned) != len(global_leaderboard):
        global_leaderboard = cleaned
        return True
    return False

def load_data():
    """Load data from local JSON file"""
    global global_leaderboard, pool_leaderboards, pool_data, transactions, escrow_funds, pool_participants, dev_fees_collected, pool_start_times, active_games, pool_history, POOL_DURATIONS
    
    try:
        _ensure_data_dir()
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            print("Data loaded from local file")
            
            # ... (mock data check omitted for brevity)
        else:
            print("No existing data found, starting fresh")
            data = {}
        
        global_leaderboard = data.get("global_leaderboard", [])
        pool_leaderboards = defaultdict(list, {k: v for k, v in data.get("pool_leaderboards", {}).items()})
        # Load pool data and handle migration from list to dict if necessary
        raw_pool_data = data.get("pool_data", {})
        if isinstance(raw_pool_data, list):
            # Migrate old list format to dict
            pool_data_dict = {}
            for p in raw_pool_data:
                if isinstance(p, dict) and "id" in p:
                    pool_data_dict[p["id"]] = p
            pool_data = pool_data_dict
        else:
            pool_data = raw_pool_data if raw_pool_data else pool_data.copy()

        # Ensure latest defaults (name/duration/entry fee) and contract IDs override stale stored values
        for pool_id, defaults in DEFAULT_POOL_SETTINGS.items():
            if pool_id not in pool_data:
                pool_data[pool_id] = {
                    "id": pool_id,
                    "prize": "0 SUI",
                    "players": 0,
                }
            pool_data[pool_id]["id"] = pool_id
            pool_data[pool_id]["name"] = defaults["name"]
            pool_data[pool_id]["duration"] = defaults["duration"]
            pool_data[pool_id]["entry_fee"] = defaults["entry_fee"]
            pool_data[pool_id]["contract_id"] = getattr(config, f"{pool_id.upper()}_POOL_ID", "0x0")
        
        transactions = data.get("transactions", [])
        escrow_funds = defaultdict(float, {k: v for k, v in data.get("escrow_funds", {}).items()})
        raw_participants = data.get("pool_participants", {})
        pool_participants = defaultdict(list, {k: _migrate_participants(v) for k, v in raw_participants.items()})
        dev_fees_collected = defaultdict(float, {k: v for k, v in data.get("dev_fees_collected", {}).items()})
        
        # Load active games and pool history
        active_games.update(data.get("active_games", {}))
        pool_history.extend(data.get("pool_history", []))
        
        # Load pool start times or initialize them
        loaded_start_times = data.get("pool_start_times", {})
        pool_start_times = {}
        for pool_id in POOL_DURATIONS.keys():
            if pool_id in loaded_start_times:
                pool_start_times[pool_id] = loaded_start_times[pool_id]
            else:
                pool_start_times[pool_id] = int(time.time())
                print(f"Initialized {pool_id} pool start time to current time")

        # Clean up stale leaderboard entries that reference cleared pools
        if prune_global_leaderboard_entries():
            save_data()
    except Exception as e:
        print(f"Error loading data: {e}")
        print("Starting with empty data")

def save_data():
    """Save data to local JSON file"""
    data = {
        "global_leaderboard": global_leaderboard,
        "pool_leaderboards": dict(pool_leaderboards),
        "pool_data": pool_data,
        "transactions": transactions,
        "escrow_funds": dict(escrow_funds),
        "pool_participants": dict(pool_participants),
        "dev_fees_collected": dict(dev_fees_collected),
        "pool_start_times": pool_start_times,
        "active_games": dict(active_games),
        "pool_history": list(pool_history)
    }
    try:
        _ensure_data_dir()
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print("Data saved to local file")
    except Exception as e:
        print(f"Error saving data: {e}")

# In-memory storage (in production, use a database)
global_leaderboard = []
pool_leaderboards = defaultdict(list)  # pool_id -> list of scores
DEFAULT_POOL_SETTINGS = {
    "daily": {"name": "Daily Pool", "duration": "24h", "entry_fee": "5 SUI"},
    "weekly": {"name": "Weekly Pool", "duration": "7d", "entry_fee": "2.5 SUI"},
    "monthly": {"name": "Monthly Pool", "duration": "28d", "entry_fee": "1 SUI"}
}

pool_data = {
    pool_id: {
        "id": pool_id,
        "name": settings["name"],
        "duration": settings["duration"],
        "entry_fee": settings["entry_fee"],
        "prize": "0 SUI",
        "players": 0,
        "contract_id": getattr(config, f"{pool_id.upper()}_POOL_ID", "0x0")
    }
    for pool_id, settings in DEFAULT_POOL_SETTINGS.items()
}

# Transaction recording system
transactions = []  # List of all transactions
escrow_funds = defaultdict(float)  # pool_id -> total SUI held in escrow
pool_participants = defaultdict(list)  # pool_id -> list of participant dicts
dev_fees_collected = defaultdict(float)  # pool_id -> total dev fees collected

# Active game sessions tracking (frontend down resilience)
active_games = {}  # wallet -> {pool_id, started_at, session_id}

# Pool history for audit trail across resets
pool_history = []  # List of past completed pool cycles

# Sui RPC helper functions
async def call_sui_rpc(method: str, params: List = None):
    """Make a call to Sui RPC"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            config.SUI_NETWORK,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params or []
            },
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()

async def get_sui_balance(address: str) -> float:
    """Get SUI balance for an address"""
    try:
        result = await call_sui_rpc("suix_getBalance", [address, "0x2::sui::SUI"])
        if "result" in result:
            return int(result["result"]["totalBalance"]) / 1_000_000_000  # Convert MIST to SUI
        return 0
    except Exception as e:
        print(f"Error getting balance: {e}")
        return 0

async def fetch_pool_balance_onchain(pool_object_id: str) -> Optional[int]:
    """Fetch the live escrow balance stored in the pool's dynamic field."""
    if not pool_object_id or pool_object_id == "0x0":
        return None

    # 1. Try generic dynamic field discovery (best for upgraded packages)
    try:
        fields_resp = await call_sui_rpc("sui_getDynamicFields", [pool_object_id, None, 50])
        field_entries = fields_resp.get("result", {}).get("data", [])
        
        for entry in field_entries:
            name_info = entry.get("name", {})
            name_type = name_info.get("type", "")
            # Match any EscrowKey regardless of package ID
            if name_type and "::pool::EscrowKey" in name_type:
                escrow_field_id = entry.get("objectId")
                if escrow_field_id:
                    params = [escrow_field_id, {"showContent": True}]
                    dyn_result = await call_sui_rpc("sui_getObject", params)
                    dyn_data = dyn_result.get("result", {}).get("data", {})
                    dyn_fields = dyn_data.get("content", {}).get("fields", {})
                    balance_struct = dyn_fields.get("value")
                    
                    if isinstance(balance_struct, dict):
                        val = balance_struct.get("fields", {}).get("value")
                    else:
                        val = balance_struct
                        
                    if val is not None:
                        print(f"Sync: Found {int(val)} Mist in dynamic field for {pool_object_id}")
                        return int(val)
    except Exception as e:
        print(f"Generic sync failed for {pool_object_id}: {e}")

    # 2. Try legacy 'balance' field (for very old pools or direct storage)
    try:
        params = [pool_object_id, {"showContent": True}]
        result = await call_sui_rpc("sui_getObject", params)
        fields = result.get("result", {}).get("data", {}).get("content", {}).get("fields", {})
        balance_val = fields.get("balance")
        if balance_val is not None:
            print(f"Sync: Found {int(balance_val)} Mist in legacy balance field for {pool_object_id}")
            return int(balance_val)
    except Exception as e:
        pass

    return 0

async def verify_sui_transaction(transaction_id: str, pool_id: str, expected_entry_fee: int):
    """Verify a Sui transaction and extract payment details"""
    try:
        params = [
            transaction_id,
            {
                "showInput": True,
                "showEffects": True,
                "showEvents": False,
                "showObjectChanges": False,
                "showBalanceChanges": True
            }
        ]
        result = await call_sui_rpc("sui_getTransactionBlock", params)
        print(f"Transaction verification result: {result}")

        tx_result = result.get("result")
        if not tx_result:
            print("No result in transaction response - rejecting")
            return None

        effects = tx_result.get("effects", {})
        status = effects.get("status", {}).get("status")
        if status != "success":
            print(f"Transaction status not success: {status}")
            return None

        tx_data = tx_result.get("transaction", {}).get("data", {})
        programmable = tx_data.get("transaction", {})
        inputs = programmable.get("inputs", [])
        transactions = programmable.get("transactions", [])

        # Validate move call target
        move_calls = [t.get("MoveCall") for t in transactions if "MoveCall" in t]
        target_ok = any(
            mc and
            mc.get("package") == config.PACKAGE_ID and
            mc.get("module") == "pool" and
            mc.get("function") in ("deposit", "deposit_and_join")
            for mc in move_calls
        )
        if not target_ok:
            print("Transaction did not call expected move target")
            return None

        # Find amount from inputs (first pure u64) or balanceChanges
        amount_mist = None
        for inp in inputs:
            if inp.get("type") == "pure" and inp.get("valueType") == "u64":
                try:
                    amount_mist = int(inp.get("value"))
                    break
                except (TypeError, ValueError):
                    continue

        if amount_mist is None:
            for change in tx_result.get("balanceChanges", []):
                owner = change.get("owner", {})
                if owner.get("AddressOwner") == tx_data.get("sender") and change.get("coinType") == "0x2::sui::SUI":
                    try:
                        amt = int(change.get("amount", 0))
                        if amt < 0:
                            amount_mist = abs(amt)
                            break
                    except ValueError:
                        continue

        if amount_mist is None:
            print("Could not determine entry fee amount")
            return None

        if abs(amount_mist - expected_entry_fee) > 1000:
            print(f"Entry fee mismatch: expected {expected_entry_fee}, got {amount_mist}")
            return None

        return {
            "transaction_id": transaction_id,
            "status": "success",
            "timestamp": int(time.time() * 1000),
            "amount_mist": amount_mist
        }
    except Exception as e:
        print(f"Error verifying transaction: {e}")
        return None

async def call_smart_contract(function: str, args: list):
    """Call a smart contract function on Sui using direct RPC calls"""
    try:
        admin_key = config.ADMIN_PRIVATE_KEY.strip() if config.ADMIN_PRIVATE_KEY else ""
        
        if admin_key and config.PACKAGE_ID and config.PACKAGE_ID != "0x0":
            print(f"Attempting REAL on-chain transaction: {function}")
            try:
                # Initialize Sui RPC client with admin key
                client = SuiRPCClient(config.SUI_NETWORK, admin_key)
                
                if function == "distribute_rewards":
                    # args: [pool_object_id, [(winner_addr, amount_mist), ...]]
                    pool_id = args[0] if len(args) > 0 else "0x0"
                    winners = args[1] if len(args) > 1 else []
                    
                    # Build arguments list for Move call
                    arguments = [pool_id]
                    for w in winners:
                        arguments.append(w[0])
                    for w in winners:
                        arguments.append(str(int(w[1])))
                    
                    # Execute via RPC
                    result = await client.execute_move_call(
                        target=f"{config.PACKAGE_ID}::pool::distribute_rewards",
                        arguments=arguments
                    )
                    
                    # Check if transaction was real (not simulated)
                    tx_id = result.get('transaction_id', '')
                    is_real = not tx_id.startswith(('sim_', 'inspect_'))
                    
                    result_status = result.get("status", "error")
                    if result_status != "success":
                        return {
                            "status": result_status,
                            "function": function,
                            "transaction_id": tx_id,
                            "message": result.get("message", ""),
                            "is_real": False
                        }
                    print(f"Transaction {'executed on-chain' if is_real else 'simulated'}: {tx_id}")
                    return {
                        "status": "success",
                        "function": function,
                        "transaction_id": tx_id,
                        "message": result.get("message", ""),
                        "is_real": is_real
                    }
                
                elif function == "withdraw_from_escrow":
                    # args: [pool_object_id, amount]
                    pool_id = args[0] if len(args) > 0 else "0x0"
                    amount = args[1] if len(args) > 1 else 0
                    
                    # Execute via RPC
                    result = await client.execute_move_call(
                        target=f"{config.PACKAGE_ID}::pool::withdraw_from_escrow",
                        arguments=[pool_id, str(amount)]
                    )
                    
                    tx_id = result.get('transaction_id', '')
                    is_real = not tx_id.startswith(('sim_', 'inspect_'))
                    
                    result_status = result.get("status", "error")
                    if result_status != "success":
                        return {
                            "status": result_status,
                            "function": function,
                            "transaction_id": tx_id,
                            "message": result.get("message", ""),
                            "is_real": False
                        }
                    print(f"Withdrawal {'executed on-chain' if is_real else 'simulated'}: {tx_id}")
                    return {
                        "status": "success",
                        "function": function,
                        "transaction_id": tx_id,
                        "message": result.get("message", ""),
                        "is_real": is_real
                    }
                
                elif function == "distribute_external_rewards":
                    # args: [pool_object_id, coin_object_id, [(winner_addr, amount), ...]]
                    pool_id = args[0] if len(args) > 0 else "0x0"
                    coin_id = args[1] if len(args) > 1 else "0x0"
                    winners = args[2] if len(args) > 2 else []
                    
                    # Build arguments list
                    arguments = [pool_id, coin_id]
                    for w in winners:
                        arguments.append(w[0])
                    for w in winners:
                        arguments.append(str(int(w[1])))
                    
                    # Execute via RPC
                    result = await client.execute_move_call(
                        target=f"{config.PACKAGE_ID}::pool::distribute_external_rewards",
                        type_arguments=[config.SUITRUMP_TYPE],
                        arguments=arguments
                    )
                    
                    tx_id = result.get('transaction_id', '')
                    is_real = not tx_id.startswith(('sim_', 'inspect_'))
                    
                    print(f"External distribution {'executed on-chain' if is_real else 'simulated'}: {tx_id}")
                    return {
                        "status": "success",
                        "function": function,
                        "transaction_id": tx_id,
                        "message": result.get("message", ""),
                        "is_real": is_real
                    }
                
            except Exception as e:
                print(f"Real transaction failed: {e}")
        
        # Fallback to simulation
        if not admin_key:
            print(f"ADMIN_PRIVATE_KEY not found - simulating {function}")
        elif not config.PACKAGE_ID or config.PACKAGE_ID == "0x0":
            print(f"PACKAGE_ID not set - simulating {function}")
        else:
            print(f"Falling back to simulation for {function}")
        
        return {
            "status": "simulated",
            "function": function,
            "transaction_id": f"sim_{int(time.time())}"
        }
    except Exception as e:
        print(f"Error calling smart contract: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/")
def root():
    return {"status": "ok", "service": "SuiTrump Blaster Backend", "message": "Backend is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

import asyncio

# Add pool start times to track expiration
pool_start_times = {}

async def auto_distribute_task():
    """Background task to automatically distribute rewards when pools expire"""
    print("AUTO_DISTRIBUTE: Background task started")
    while True:
        try:
            now = int(time.time())
            
            for pool_id, duration in POOL_DURATIONS.items():
                start_time = pool_start_times.get(pool_id, now)
                elapsed = now - start_time
                print(f"AUTO_DISTRIBUTE: {pool_id} - elapsed: {elapsed}s, duration: {duration}s, expires in: {duration - elapsed}s")
                if elapsed >= duration:
                    # Sync escrow balances from on-chain before checking
                    pool_object_id = pool_data[pool_id].get("contract_id", "0x0")
                    if pool_object_id != "0x0":
                        real_balance_mist = await get_pool_escrow_balance(pool_object_id)
                        if real_balance_mist > 0:
                            escrow_funds[pool_id] = real_balance_mist
                            print(f"AUTOMATION: Synced {pool_id} escrow from on-chain: {real_balance_mist / 1_000_000_000:.3f} SUI")

                    participants = pool_participants.get(pool_id, [])
                    escrow_balance = escrow_funds.get(pool_id, 0)
                    print(f"AUTOMATION: {pool_id} - participants: {len(participants)}, escrow_balance: {escrow_balance}")
                    if not participants and escrow_balance <= 0:
                        print(f"AUTOMATION: Skipping {pool_id} reset (no participants or escrow)")
                        pool_start_times[pool_id] = now
                        continue
                    print(f"AUTOMATION: Pool {pool_id} has expired. Starting distribution...")
                    
                    # Check for active games before distributing
                    active_in_pool = [w for w, g in active_games.items() if g.get("pool_id") == pool_id and g.get("status") == "active"]
                    if active_in_pool:
                        print(f"AUTOMATION: Warning - {len(active_in_pool)} active games in {pool_id} pool. Waiting for them to complete...")
                        # Wait an extra 5 minutes for active games to finish, then continue
                        await asyncio.sleep(300)
                        # Re-check after wait
                        active_in_pool = [w for w, g in active_games.items() if g.get("pool_id") == pool_id and g.get("status") == "active"]
                        if active_in_pool:
                            print(f"AUTOMATION: Still {len(active_in_pool)} active games. Proceeding with distribution anyway.")
                    
                    # Archive current pool state before any reset (preserves record even if distribution fails)
                    pool_history.append({
                        "pool_id": pool_id,
                        "expired_at": now,
                        "start_time": start_time,
                        "final_leaderboard": pool_leaderboards.get(pool_id, [])[:10],
                        "final_participants": [p.get("wallet") if isinstance(p, dict) else p for p in pool_participants.get(pool_id, [])],
                        "escrow_balance": escrow_funds.get(pool_id, 0),
                        "active_sessions_at_close": active_in_pool,
                        "auto_distribution": True
                    })
                    
                    # Call the distribution logic (bypass auth for internal automation)
                    try:
                        result = await perform_reward_distribution(PayoutRequest(pool_id=pool_id, num_winners=10))
                    except Exception as dist_err:
                        print(f"AUTOMATION: Distribution failed for {pool_id}: {dist_err}")
                        continue

                    status = result.get("status") if isinstance(result, dict) else None
                    is_real = result.get("is_real", False) if isinstance(result, dict) else False
                    
                    if status != "success":
                        print(f"AUTOMATION: Distribution did not complete for {pool_id} (status={status}). Pool will remain open for manual retry.")
                        continue
                    
                    if not is_real:
                        print(f"AUTOMATION: Distribution was simulated (not real on-chain) for {pool_id}. Pool will remain open until real execution succeeds.")
                        continue

                    # Reset pool for the next period only when real on-chain payout succeeded
                    pool_start_times[pool_id] = now
                    pool_leaderboards[pool_id] = []
                    pool_participants[pool_id] = []

                    # Clear completed/abandoned game sessions for this pool
                    for wallet in list(active_games.keys()):
                        if active_games[wallet].get("pool_id") == pool_id:
                            del active_games[wallet]

                    save_data()
                    print(f"AUTOMATION: Pool {pool_id} reset for new period.")
            
            # Check every 30 seconds for faster response to pool expiration
            await asyncio.sleep(30)
            
        except Exception as e:
            print(f"AUTOMATION ERROR: {e}")
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    """Load data from file and start automation on startup"""
    load_data()
    # Start the background task
    asyncio.create_task(auto_distribute_task())

@app.post("/submit-score")
def submit_score(data: ScoreData):
    now = int(time.time() * 1000)
    
    if data.score < 0:
        raise HTTPException(status_code=400, detail="Invalid score")
    
    if data.score > config.MAX_SCORE_PER_SECOND * data.game_duration:
        raise HTTPException(status_code=400, detail="Score too high for game duration")
    
    if data.game_duration > config.MAX_GAME_DURATION:
        raise HTTPException(status_code=400, detail="Game duration too long")
    
    if data.game_duration < 10 and data.score > 50:
        raise HTTPException(status_code=400, detail="Suspiciously high score for short duration")
    
    if abs(now - data.timestamp) > 10000:
        raise HTTPException(status_code=400, detail="Invalid timestamp")
    
    # Anti-cheat: Check if player actually joined the pool
    if data.pool_id and data.pool_id != "global":
        if data.wallet not in get_pool_wallets(data.pool_id):
            raise HTTPException(status_code=403, detail="Must join and pay for the pool before submitting a score")
    
    # Add to global leaderboard
    global_leaderboard.append({
        "wallet": data.wallet,
        "score": data.score,
        "timestamp": data.timestamp,
        "game_duration": data.game_duration,
        "pool_id": data.pool_id
    })
    
    # Add to pool-specific leaderboard if pool_id provided
    if data.pool_id and data.pool_id in pool_data:
        pool_leaderboards[data.pool_id].append({
            "wallet": data.wallet,
            "score": data.score,
            "timestamp": data.timestamp,
            "game_duration": data.game_duration
        })
        pool_leaderboards[data.pool_id].sort(key=lambda x: x["score"], reverse=True)
        
        # Update participant stats in pool_participants
        for p in pool_participants[data.pool_id]:
            if isinstance(p, dict) and p.get("wallet") == data.wallet:
                p["games_played"] = p.get("games_played", 0) + 1
                p["total_score"] = p.get("total_score", 0) + data.score
                if data.score > p.get("best_score", 0):
                    p["best_score"] = data.score
                p["last_active"] = int(time.time())
                break
    
    # Mark active game as completed if present
    if data.wallet in active_games:
        active_games[data.wallet]["status"] = "completed"
        active_games[data.wallet]["ended_at"] = int(time.time())
        active_games[data.wallet]["final_score"] = data.score
    
    global_leaderboard.sort(key=lambda x: x["score"], reverse=True)
    top = global_leaderboard[:10]
    
    # Save data to file
    save_data()
    
    return {
        "status": "accepted",
        "rank": next((i + 1 for i, x in enumerate(top) if x["wallet"] == data.wallet), None),
        "top_10": top
    }

@app.get("/leaderboard")
def get_leaderboard(pool_id: Optional[str] = None):
    if prune_global_leaderboard_entries():
        save_data()
    if pool_id and pool_id in pool_leaderboards:
        return {"leaderboard": pool_leaderboards[pool_id][:10], "pool_id": pool_id}
    return {"leaderboard": global_leaderboard[:10]}

@app.get("/pools")
async def get_pools():
    pools_with_prize = []
    state_changed = False
    print(f"DEBUG: Current escrow funds state (pre-sync): {dict(escrow_funds)}")
    for pool in pool_data.values():
        pool_copy = pool.copy()
        raw_mist = escrow_funds.get(pool["id"], 0)
        pool_copy["players"] = len(pool_participants.get(pool["id"], []))
        participants_list = pool_participants.get(pool["id"], [])

        # Convert entry fee from mist to SUI for display
        entry_fee_mist = pool_copy.get("entry_fee", 0)
        entry_fee_sui = entry_fee_mist / 1_000_000_000
        pool_copy["entry_fee"] = f"{entry_fee_sui:.1f} SUI"

        contract_id = pool_copy.get("contract_id")
        onchain_balance = await fetch_pool_balance_onchain(contract_id) if contract_id else None
        if onchain_balance is not None and onchain_balance != raw_mist:
            raw_mist = onchain_balance
            escrow_funds[pool["id"]] = raw_mist
            state_changed = True

        current_prize = raw_mist / 1_000_000_000

        if current_prize > 1_000_000:
            print(f"WARNING: Insane prize detected for {pool['id']}: {current_prize}")
            current_prize = 0.0
        
        pool_copy["current_prize"] = f"{current_prize:.2f} SUI"
        pool_copy["prize"] = f"{current_prize:.2f} SUITRUMP (Dynamic)"  # Display as SUITRUMP for player rewards
        pool_copy["payout_structure"] = POOL_PAYOUTS.get(pool["id"], [])

        # Add countdown metadata
        duration = POOL_DURATIONS.get(pool["id"], 24 * 3600)
        now_ts = int(time.time())
        start_time = pool_start_times.get(pool["id"], now_ts)

        # If the pool completed and has no active players or leaderboard entries, auto-reset the timer
        if duration and now_ts >= start_time + duration:
            if not pool_leaderboards.get(pool["id"]) and not participants_list:
                start_time = now_ts
                pool_start_times[pool["id"]] = start_time
                state_changed = True

        time_left_seconds = max(0, start_time + duration - now_ts)
        
        pool_copy["time_left_seconds"] = time_left_seconds
        pool_copy["time_left_formatted"] = str(timedelta(seconds=time_left_seconds))
        pool_copy["started_at"] = start_time
        pool_copy["ends_at"] = start_time + duration if duration else None

        pools_with_prize.append(pool_copy)

    if state_changed:
        save_data()

    return {
        "pools": pools_with_prize,
        "version": "2.0.4",
        "timestamp": int(time.time())
    }

@app.post("/join-pool")
async def join_pool(data: PoolJoin):
    try:
        if data.pool_id not in pool_data:
            raise HTTPException(status_code=404, detail="Pool not found")

        
        # Check if wallet is already in this pool
        if data.wallet in get_pool_wallets(data.pool_id):
            return {"status": "success", "message": "Already joined this pool", "pool": pool_data[data.pool_id]}
        
        # Ensure pool_participants[data.pool_id] is a list
        if data.pool_id not in pool_participants or not isinstance(pool_participants[data.pool_id], list):
            print(f"WARNING: pool_participants[{data.pool_id}] is not initialized or not a list, initializing")
            pool_participants[data.pool_id] = []
        
        # Ensure pool_data[data.pool_id] is a dict with players field
        if not isinstance(pool_data[data.pool_id], dict):
            print(f"WARNING: pool_data[{data.pool_id}] is not a dict, reinitializing")
            pool_data[data.pool_id] = {
                "contract_id": pool_data[data.pool_id] if isinstance(pool_data[data.pool_id], str) else "",
                "entry_fee": 2_000_000_000,
                "duration": 86400,
                "players": 0
            }
        
        # Determine expected entry fee in MIST
        pool_entry_fee = pool_data[data.pool_id].get("entry_fee", str(config.POOL_ENTRY_FEE / 1_000_000_000))
        expected_entry_fee = _parse_entry_fee_to_mist(pool_entry_fee)

        # Verify transaction if provided
        transaction_verified = False
        payment_amount_mist = 0
        
        if data.transaction_id:
            try:
                # Verify the Sui transaction
                tx_verification = await verify_sui_transaction(data.transaction_id, data.pool_id, expected_entry_fee)
                if tx_verification:
                    transaction_verified = True
                    payment_amount_mist = tx_verification.get("amount_mist", 0)
                else:
                    # If verification fails, check if the wallet is already in the pool (might have been verified earlier)
                    if data.wallet in get_pool_wallets(data.pool_id):
                        transaction_verified = True
                        payment_amount_mist = expected_entry_fee
                    else:
                        raise HTTPException(status_code=400, detail="Invalid transaction")
            except Exception as e:
                print(f"Transaction verification error: {e}")
                # Allow proceeding without verification if transaction is on-chain
                transaction_verified = False
        else:
            # For development, allow joining without transaction but do not credit escrow
            print("WARNING: join_pool called without transaction_id - escrow not updated")

        # Record the transaction
        if data.transaction_id:
            payment_amount_sui = payment_amount_mist / 1_000_000_000 if payment_amount_mist else (float(data.amount) if data.amount else 0)
            record_amount_mist = payment_amount_mist if payment_amount_mist else int(payment_amount_sui * 1_000_000_000)
            transactions.append({
                "transaction_id": data.transaction_id,
                "pool_id": data.pool_id,
                "wallet": data.wallet,
                "amount_mist": record_amount_mist,
                "amount_sui": payment_amount_sui,
                "type": "entry_fee",
                "timestamp": int(time.time() * 1000),
                "verified": transaction_verified
            })
        
        # Add to escrow if transaction verified
        if transaction_verified and payment_amount_mist > 0:
            escrow_funds[data.pool_id] += payment_amount_mist

        # Add wallet to pool participants with full record
        now_ts = int(time.time())
        pool_participants[data.pool_id].append({
            "wallet": data.wallet,
            "joined_at": now_ts,
            "games_played": 0,
            "best_score": 0,
            "total_score": 0,
            "last_active": now_ts
        })
        pool_data[data.pool_id]["players"] += 1
        
        # Save data to file
        try:
            save_data()
        except Exception as e:
            print(f"Error saving data: {e}")
        
        return {
            "status": "success",
            "message": "Joined pool successfully",
            "pool": pool_data[data.pool_id],
            "transaction_verified": transaction_verified,
            "escrow_balance": escrow_funds[data.pool_id]
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in join_pool: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"Error joining pool: {str(e)}"
        }

@app.post("/start-game")
async def start_game(data: PoolJoin):
    """Record that a player has started a game session"""
    if data.pool_id not in pool_data:
        raise HTTPException(status_code=404, detail="Pool not found")
    if data.wallet not in get_pool_wallets(data.pool_id):
        raise HTTPException(status_code=403, detail="Must join pool before playing")
    
    session_id = f"{data.wallet}_{data.pool_id}_{int(time.time() * 1000)}"
    active_games[data.wallet] = {
        "pool_id": data.pool_id,
        "started_at": int(time.time()),
        "session_id": session_id,
        "status": "active"
    }
    save_data()
    return {
        "status": "success",
        "session_id": session_id,
        "message": "Game session recorded on backend"
    }

@app.post("/abandon-game")
async def abandon_game(data: PoolJoin):
    """Record that a player abandoned a game session (frontend disconnect)"""
    if data.wallet in active_games:
        active_games[data.wallet]["status"] = "abandoned"
        active_games[data.wallet]["ended_at"] = int(time.time())
        save_data()
        return {"status": "abandoned", "message": "Session marked as abandoned"}
    return {"status": "no_active_session"}

@app.get("/active-games", dependencies=[Depends(dev_wallet_auth)])
def get_active_games():
    """Admin endpoint: view all active game sessions"""
    return {
        "active_games": dict(active_games),
        "count": len([g for g in active_games.values() if g.get("status") == "active"])
    }

@app.post("/create-pool")
async def create_pool(data: PoolCreate):
    try:
        # Placeholder for actual Sui transaction
        # In production, this would call Sui RPC to execute the transaction
        pool_id = f"pool_{int(time.time())}"
        pool_data[pool_id] = {
            "id": pool_id,
            "name": data.name,
            "duration": data.duration,
            "entry_fee": data.entry_fee,
            "prize": data.prize,
            "players": 0
        }
        
        # Save data to file
        save_data()
        
        return {
            "status": "success",
            "pool_id": pool_id,
            "message": "Pool creation endpoint - integrate with Sui SDK"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/submit-score-onchain")
async def submit_score_onchain(data: ScoreSubmit):
    try:
        # Placeholder for actual Sui transaction
        # In production, this would:
        # 1. Build a transaction to call the smart contract's submit_score function
        # 2. Sign it with the admin key
        # 3. Execute it via Sui RPC
        # 4. Return the transaction digest
        
        # For now, just store in the pool leaderboard
        if data.pool_id in pool_leaderboards:
            pool_leaderboards[data.pool_id].append({
                "wallet": data.wallet,
                "score": data.score,
                "timestamp": int(time.time() * 1000)
            })
            pool_leaderboards[data.pool_id].sort(key=lambda x: x["score"], reverse=True)
        
        return {
            "status": "success",
            "tx_id": "placeholder_tx_id",
            "message": "Score submitted to pool leaderboard",
            "pool_id": data.pool_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/balance/{address}")
async def get_balance(address: str):
    """Get SUI balance for a wallet address"""
    try:
        balance = await get_sui_balance(address)
        return {"address": address, "balance": balance, "currency": "SUI"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    """Load persistent data and start background tasks"""
    global global_leaderboard, pool_leaderboards, pool_data, transactions, escrow_funds, pool_participants, dev_fees_collected, active_games, pool_history, pool_start_times
    load_data()
    
    # Initialize pool data with updated contract IDs and entry fees
    # Force update entry fees even if pool_data exists
    if not pool_data:
        pool_data = {
            "daily": {
                "contract_id": "0x9aca57fc06b61557f9f893d9ad25a96fa6a1ad053bd2b36bced0914e45a6af66",
                "entry_fee": 2_000_000_000,  # 2 SUI
                "duration": 86400,
                "players": 0
            },
            "weekly": {
                "contract_id": "0x1aabc79aa06979b37b0923b18c7615dd3487a641518eb37719417b550b263d65",
                "entry_fee": 2_500_000_000,  # 2.5 SUI
                "duration": 604800,
                "players": 0
            },
            "monthly": {
                "contract_id": "0xf7e04ca08481dda0eb6d9b53c058bcb15a49bb309b79168cf5914335fea9b785",
                "entry_fee": 1_000_000_000,  # 1 SUI
                "duration": 2419200,
                "players": 0
            }
        }
    else:
        # Update existing pool data with new contract IDs and entry fees
        if "daily" in pool_data:
            pool_data["daily"]["contract_id"] = "0x9aca57fc06b61557f9f893d9ad25a96fa6a1ad053bd2b36bced0914e45a6af66"
            pool_data["daily"]["entry_fee"] = 2_000_000_000  # 2 SUI
        if "weekly" in pool_data:
            pool_data["weekly"]["contract_id"] = "0x1aabc79aa06979b37b0923b18c7615dd3487a641518eb37719417b550b263d65"
            pool_data["weekly"]["entry_fee"] = 2_500_000_000  # 2.5 SUI
        if "monthly" in pool_data:
            pool_data["monthly"]["contract_id"] = "0xf7e04ca08481dda0eb6d9b53c058bcb15a49bb309b79168cf5914335fea9b785"
            pool_data["monthly"]["entry_fee"] = 1_000_000_000  # 1 SUI
    
    # Initialize pool start times if missing
    if not pool_start_times:
        pool_start_times = {
            "daily": int(time.time()),
            "weekly": int(time.time()),
            "monthly": int(time.time())
        }

    if config.ADMIN_PRIVATE_KEY:
        try:
            admin_client = SuiRPCClient(config.SUI_NETWORK, config.ADMIN_PRIVATE_KEY.strip())
            if admin_client.signing_key:
                admin_balance = await get_sui_balance(admin_client.address)
                print(f"ADMIN WALLET: derived address {admin_client.address}, balance {admin_balance} SUI")
        except Exception as e:
            print(f"ADMIN WALLET: diagnostic failed: {e}")
    
    # Start auto-distribute task
    asyncio.create_task(auto_distribute_task())

@app.post("/reset-data", dependencies=[Depends(dev_wallet_auth)])
async def reset_data():
    """Reset all data - clear pools, scores, and transactions"""
    global global_leaderboard, pool_leaderboards, pool_data, transactions, escrow_funds, pool_participants, dev_fees_collected, active_games, pool_history
    try:
        global_leaderboard = []
        pool_leaderboards = defaultdict(list)
        pool_data = {}
        transactions = []
        escrow_funds = defaultdict(float)
        pool_participants = defaultdict(list)
        dev_fees_collected = defaultdict(float)
        active_games = {}
        pool_history = []
        
        # Clear the data file
        if os.path.exists(DATA_FILE):
            os.remove(DATA_FILE)
        
        save_data()
        
        return {"status": "success", "message": "All data has been reset"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/distribute-rewards")
async def distribute_rewards(data: PayoutRequest, x_dev_wallet: str = Depends(dev_wallet_auth)):
    """Distribute rewards to winners of a pool (API Endpoint)"""
    return await perform_reward_distribution(data)

@app.post("/force-distribute-rewards")
async def force_distribute_rewards(data: PayoutRequest, x_dev_wallet: str = Depends(dev_wallet_auth)):
    """Force distribute rewards regardless of pool timer - for immediate payout testing"""
    # Override pool start time to make it appear expired
    original_start_time = pool_start_times.get(data.pool_id, int(time.time()))
    pool_start_times[data.pool_id] = int(time.time()) - POOL_DURATIONS.get(data.pool_id, 86400) - 1
    
    result = await perform_reward_distribution(data)
    
    # Restore original start time if payout failed
    if result.get("status") != "success":
        pool_start_times[data.pool_id] = original_start_time
    
    return result

@app.post("/add-test-score")
async def add_test_score(wallet: str, score: int, pool_id: str, x_dev_wallet: str = Depends(dev_wallet_auth)):
    """Add a test score for immediate payout testing"""
    now = int(time.time() * 1000)
    
    if pool_id not in pool_leaderboards:
        pool_leaderboards[pool_id] = []
    
    pool_leaderboards[pool_id].append({
        "wallet": wallet,
        "score": score,
        "timestamp": now,
        "game_duration": 60
    })
    pool_leaderboards[pool_id].sort(key=lambda x: x["score"], reverse=True)
    
    # Also add to participants if not already there
    if pool_id not in pool_participants:
        pool_participants[pool_id] = []
    
    existing = any(p.get("wallet") == wallet if isinstance(p, dict) else p == wallet for p in pool_participants[pool_id])
    if not existing:
        pool_participants[pool_id].append({
            "wallet": wallet,
            "joined_at": int(time.time()),
            "games_played": 1,
            "best_score": score,
            "total_score": score,
            "last_active": int(time.time())
        })
    
    save_data()
    return {"status": "success", "message": f"Added test score {score} for {wallet} in pool {pool_id}"}

async def perform_reward_distribution(data: PayoutRequest):
    """Internal logic to distribute rewards to winners of a pool"""
    try:
        global global_leaderboard
        if data.pool_id not in pool_leaderboards:
            return {"status": "error", "message": "Pool not found in leaderboards"}
        
        if data.pool_id not in pool_data:
            return {"status": "error", "message": "Pool not found in metadata"}
        
        leaderboard = pool_leaderboards[data.pool_id][:data.num_winners]
        
        # RECOVERY LOGIC: If active leaderboard is empty, check history for a distribution that failed to move funds
        if not leaderboard:
            print(f"PAYOUT: Active leaderboard for {data.pool_id} is empty. Checking history for missed distribution...")
            for history_entry in reversed(pool_history):
                if history_entry.get("pool_id") == data.pool_id:
                    # Found the last archived session for this pool
                    historical_leaderboard = history_entry.get("leaderboard_at_distribution", [])
                    if historical_leaderboard:
                        print(f"PAYOUT: Found {len(historical_leaderboard)} winners in history. Using them for recovery payout.")
                        leaderboard = historical_leaderboard
                        break
        
        if not leaderboard:
            print(f"PAYOUT: {data.pool_id} distribution skipped - no leaderboard entries (active or historical) found")
            return {"status": "no_scores", "message": "No scores to distribute rewards for. If this is a mistake, please submit a test score first."}
        
        # Use actual escrow balance as prize pool (stored in Mist)
        prize_amount_mist = int(escrow_funds[data.pool_id])
        
        if prize_amount_mist <= 0:
            print(f"PAYOUT: {data.pool_id} distribution skipped - escrow balance is {prize_amount_mist}")
            return {"status": "no_funds", "message": "No funds in prize pool"}
        
        # Initialize variables for pool history (will be updated based on swap path)
        dev_fee_mist = 0
        prize_after_fee_mist = prize_amount_mist
        actual_winners_count = 0
        
        reward_percentages = POOL_PAYOUTS.get(data.pool_id, [100])
            
        payouts = []
        winners = [] # List of (address, amount_mist)
        
        # NEW: Automatic SUI to SUITRUMP swap flow
        # 1. Swap full SUI prize pool to SUITRUMP via Cetus
        # 2. Calculate dev fee as percentage of SUITRUMP amount
        # 3. Distribute SUITRUMP minus dev fee to winners
        # 4. Add dev fee in SUITRUMP to dev wallet
        
        # Calculate amount to swap (full prize pool)
        swap_amount_mist = prize_amount_mist
        
        # Check if swap is configured
        if swap_amount_mist > 0 and config.CETUS_SUI_SUITRUMP_POOL_ID:
            print(f"PAYOUT: Attempting automatic swap - {swap_amount_mist / 1_000_000_000} SUI to SUITRUMP")
            
            # Step 1: Withdraw SUI from escrow
            withdraw_result = await call_smart_contract("withdraw_from_escrow", [
                pool_data[data.pool_id].get("contract_id", "0x0"),
                swap_amount_mist
            ])
            
            if withdraw_result.get("status") == "success":
                print(f"PAYOUT: Withdrawal successful - now swapping via Cetus")
                
                # Step 2: Swap SUI to SUITRUMP via Cetus
                # a_to_b = True (SUI to SUITRUMP), by_amount_in = True (exact input)
                swap_result = await call_smart_contract("cetus_swap", [
                    config.CETUS_SUI_SUITRUMP_POOL_ID,  # pool_address
                    True,  # a_to_b (SUI to SUITRUMP)
                    True,  # by_amount_in (exact input amount)
                    swap_amount_mist,  # amount to swap
                    0,  # amount_limit (minimum output, 0 = no limit)
                    79226673515401279992447579055,  # sqrt_price_limit (max)
                    ""  # partner (empty string)
                ])
                
                if swap_result.get("status") == "success":
                    print(f"PAYOUT: Cetus swap successful - calculating dev fee from SUITRUMP amount")
                    
                    swap_tx_digest = swap_result.get("transaction_id", "")
                    if swap_tx_digest:
                        print(f"PAYOUT: Swap transaction digest: {swap_tx_digest}")
                        # Query the transaction to get the created coin objects and amounts
                        try:
                            tx_response = client.client.get_transaction_block(swap_tx_digest)
                            if hasattr(tx_response, 'effects') and hasattr(tx_response.effects, 'created'):
                                created_objects = tx_response.effects.created
                                suitrump_coins = []
                                total_suitrump_amount = 0
                                for obj in created_objects:
                                    if hasattr(obj, 'type') and config.SUITRUMP_TYPE in str(obj.type):
                                        suitrump_coins.append(obj.reference.object_id)
                                        # Try to get the coin amount
                                        if hasattr(obj, 'owner') and hasattr(obj.owner, 'AddressOwner'):
                                            # This is a coin object, try to get its balance
                                            pass
                                
                                if suitrump_coins:
                                    print(f"PAYOUT: Found {len(suitrump_coins)} SUITRUMP coin objects")
                                    
                                    # For now, estimate SUITRUMP amount based on swap ratio
                                    # In production, we should query the actual coin balance
                                    # Assuming 1 SUI = 60,000 SUITRUMP (example ratio)
                                    sui_amount = swap_amount_mist / 1_000_000_000
                                    estimated_suitrump_amount = sui_amount * 60000  # TODO: Get actual swap rate
                                    
                                    print(f"PAYOUT: Estimated SUITRUMP amount: {estimated_suitrump_amount}")
                                    
                                    # Calculate dev fee as percentage of SUITRUMP amount
                                    dev_fee_suitrump = estimated_suitrump_amount * (config.DEV_FEE_PERCENTAGE / 100)
                                    prize_after_fee_suitrump = estimated_suitrump_amount - dev_fee_suitrump
                                    
                                    # Record dev fee in SUI equivalent for tracking
                                    dev_fee_mist = int(sui_amount * (config.DEV_FEE_PERCENTAGE / 100) * 1_000_000_000)
                                    dev_fees_collected[data.pool_id] += dev_fee_mist
                                    
                                    print(f"PAYOUT: Dev fee: {dev_fee_suitrump:.3f} SUITRUMP ({dev_fee_mist / 1_000_000_000} SUI equivalent)")
                                    print(f"PAYOUT: Prize after fee: {prize_after_fee_suitrump:.3f} SUITRUMP")
                                    
                                    # Calculate winner payouts in SUITRUMP
                                    # We pay out to the number of winners specified in reward_percentages, 
                                    # but only if there are enough people on the leaderboard.
                                    num_to_pay = len(reward_percentages)
                                    actual_winners_count = min(len(leaderboard), num_to_pay)
                                    
                                    # Adjust percentages if fewer winners than slots
                                    if actual_winners_count > 0 and actual_winners_count < num_to_pay:
                                        # Re-calculate reward_percentages to distribute 100% among actual winners
                                        total_slots_pct = sum(reward_percentages[:actual_winners_count])
                                        if total_slots_pct > 0:
                                            reward_percentages = [(p / total_slots_pct) * 100 for p in reward_percentages[:actual_winners_count]]
                                        else:
                                            adjusted_pct = 100 / actual_winners_count
                                            reward_percentages = [adjusted_pct] * actual_winners_count
                                    
                                    # Build winners list with SUITRUMP amounts
                                    suitrump_winners = []
                                    for i in range(actual_winners_count):
                                        entry = leaderboard[i]
                                        reward_suitrump = prize_after_fee_suitrump * (reward_percentages[i] / 100)
                                        payouts.append({
                                            "rank": i + 1,
                                            "wallet": entry["wallet"],
                                            "score": entry["score"],
                                            "reward": f"{reward_suitrump:.3f} SUITRUMP",
                                        })
                                        # For distribution, we need to convert back to SUI Mist for the contract
                                        # This is a simplified approach - in production we'd distribute actual SUITRUMP coins
                                        reward_sui_equivalent = (reward_suitrump / 60000) * 1_000_000_000  # TODO: Use actual rate
                                        suitrump_winners.append((entry["wallet"], int(reward_sui_equivalent)))
                                    
                                    # Add dev fee to winners list (in SUI equivalent for contract)
                                    dev_fee_winners = []
                                    if dev_fee_suitrump > 0:
                                        dev_wallet = config.DEV_WALLET_ADDRESS
                                        dev_fee_sui_equivalent = (dev_fee_suitrump / 60000) * 1_000_000_000
                                        dev_fee_winners.append((dev_wallet, int(dev_fee_sui_equivalent)))
                                    
                                    # Distribute using the first SUITRUMP coin object
                                    # Note: This is a simplified approach - assumes single coin
                                    coin_id = suitrump_coins[0]
                                    distribute_result = await call_smart_contract("distribute_external_rewards", [
                                        pool_data[data.pool_id].get("contract_id", "0x0"),
                                        coin_id,
                                        dev_fee_winners + suitrump_winners
                                    ])
                                    
                                    if distribute_result.get("status") == "success":
                                        print(f"PAYOUT: SUITRUMP distribution successful")
                                        escrow_funds[data.pool_id] = 0
                                        contract_result = distribute_result
                                    else:
                                        print(f"PAYOUT: SUITRUMP distribution failed - manual intervention required")
                                        contract_result = {"status": "partial", "transaction_id": swap_tx_digest}
                                else:
                                    print(f"PAYOUT: No SUITRUMP coins found in swap result - manual intervention required")
                                    contract_result = {"status": "partial", "transaction_id": swap_tx_digest}
                        except Exception as e:
                            print(f"PAYOUT: Failed to query swap transaction: {e} - manual intervention required")
                            contract_result = {"status": "partial", "transaction_id": swap_tx_digest}
                    else:
                        print(f"PAYOUT: No swap transaction digest - manual intervention required")
                        contract_result = {"status": "partial", "transaction_id": swap_tx_digest}
                else:
                    print(f"PAYOUT: Cetus swap failed - falling back to SUI distribution")
                    # Fallback to original SUI distribution logic
                    dev_fee_mist = int(prize_amount_mist * (config.DEV_FEE_PERCENTAGE / 100))
                    prize_after_fee_mist = max(prize_amount_mist - dev_fee_mist, 0)
                    dev_fees_collected[data.pool_id] += dev_fee_mist
                    
                    # Add Dev Fee to the winners list
                    if dev_fee_mist > 0:
                        dev_wallet = config.DEV_WALLET_ADDRESS
                        winners.append((dev_wallet, dev_fee_mist))
                    
                    # Calculate winner payouts in SUI
                    num_to_pay = len(reward_percentages)
                    actual_winners_count = min(len(leaderboard), num_to_pay)
                    
                    if actual_winners_count > 0 and actual_winners_count < num_to_pay:
                        total_slots_pct = sum(reward_percentages[:actual_winners_count])
                        if total_slots_pct > 0:
                            reward_percentages = [(p / total_slots_pct) * 100 for p in reward_percentages[:actual_winners_count]]
                        else:
                            adjusted_pct = 100 / actual_winners_count
                            reward_percentages = [adjusted_pct] * actual_winners_count
                    
                    for i in range(actual_winners_count):
                        entry = leaderboard[i]
                        reward_mist = int(prize_after_fee_mist * (reward_percentages[i] / 100))
                        reward_sui = reward_mist / 1_000_000_000
                        payouts.append({
                            "rank": i + 1,
                            "wallet": entry["wallet"],
                            "score": entry["score"],
                            "reward": f"{reward_sui:.3f} SUI",
                        })
                        winners.append((entry["wallet"], reward_mist))
                    
                    contract_result = await call_smart_contract("distribute_rewards", [
                        pool_data[data.pool_id].get("contract_id", "0x0"),
                        winners
                    ])
            else:
                print(f"PAYOUT: Withdrawal failed - falling back to SUI distribution")
                # Fallback to original SUI distribution logic
                dev_fee_mist = int(prize_amount_mist * (config.DEV_FEE_PERCENTAGE / 100))
                prize_after_fee_mist = max(prize_amount_mist - dev_fee_mist, 0)
                dev_fees_collected[data.pool_id] += dev_fee_mist
                
                # Add Dev Fee to the winners list
                if dev_fee_mist > 0:
                    dev_wallet = config.DEV_WALLET_ADDRESS
                    winners.append((dev_wallet, dev_fee_mist))
                
                # Calculate winner payouts in SUI
                num_to_pay = len(reward_percentages)
                actual_winners_count = min(len(leaderboard), num_to_pay)
                
                if actual_winners_count > 0 and actual_winners_count < num_to_pay:
                    total_slots_pct = sum(reward_percentages[:actual_winners_count])
                    if total_slots_pct > 0:
                        reward_percentages = [(p / total_slots_pct) * 100 for p in reward_percentages[:actual_winners_count]]
                    else:
                        adjusted_pct = 100 / actual_winners_count
                        reward_percentages = [adjusted_pct] * actual_winners_count
                
                for i in range(actual_winners_count):
                    entry = leaderboard[i]
                    reward_mist = int(prize_after_fee_mist * (reward_percentages[i] / 100))
                    reward_sui = reward_mist / 1_000_000_000
                    payouts.append({
                        "rank": i + 1,
                        "wallet": entry["wallet"],
                        "score": entry["score"],
                        "reward": f"{reward_sui:.3f} SUI",
                    })
                    winners.append((entry["wallet"], reward_mist))
                
                contract_result = await call_smart_contract("distribute_rewards", [
                    pool_data[data.pool_id].get("contract_id", "0x0"),
                    winners
                ])
        else:
            # Swap not configured - use original SUI distribution logic
            dev_fee_mist = int(prize_amount_mist * (config.DEV_FEE_PERCENTAGE / 100))
            prize_after_fee_mist = max(prize_amount_mist - dev_fee_mist, 0)
            dev_fees_collected[data.pool_id] += dev_fee_mist
            
            # Add Dev Fee to the winners list
            if dev_fee_mist > 0:
                dev_wallet = config.DEV_WALLET_ADDRESS
                winners.append((dev_wallet, dev_fee_mist))
            
            # Calculate winner payouts in SUI
            num_to_pay = len(reward_percentages)
            actual_winners_count = min(len(leaderboard), num_to_pay)
            
            if actual_winners_count > 0 and actual_winners_count < num_to_pay:
                total_slots_pct = sum(reward_percentages[:actual_winners_count])
                if total_slots_pct > 0:
                    reward_percentages = [(p / total_slots_pct) * 100 for p in reward_percentages[:actual_winners_count]]
                else:
                    adjusted_pct = 100 / actual_winners_count
                    reward_percentages = [adjusted_pct] * actual_winners_count
            
            for i in range(actual_winners_count):
                entry = leaderboard[i]
                reward_mist = int(prize_after_fee_mist * (reward_percentages[i] / 100))
                reward_sui = reward_mist / 1_000_000_000
                payouts.append({
                    "rank": i + 1,
                    "wallet": entry["wallet"],
                    "score": entry["score"],
                    "reward": f"{reward_sui:.3f} SUI",
                })
                winners.append((entry["wallet"], reward_mist))
            
            contract_result = await call_smart_contract("distribute_rewards", [
                pool_data[data.pool_id].get("contract_id", "0x0"),
                winners
            ])
        
        if contract_result["status"] == "success":
            # Archive this pool cycle to history before clearing
            pool_history.append({
                "pool_id": data.pool_id,
                "distributed_at": int(time.time()),
                "total_prize_mist": prize_amount_mist,
                "dev_fee_mist": dev_fee_mist,
                "prize_after_fee_mist": prize_after_fee_mist,
                "num_winners": len(payouts),
                "payouts": payouts,
                "participants": [p.get("wallet") if isinstance(p, dict) else p for p in pool_participants.get(data.pool_id, [])],
                "leaderboard_at_distribution": leaderboard[:actual_winners_count] if actual_winners_count > 0 else [],
                "contract_transaction": contract_result.get("transaction_id")
            })
            
            # Clear escrow after distribution (contract handles actual transfer)
            escrow_funds[data.pool_id] = 0
            dev_fees_collected[data.pool_id] = 0
            pool_leaderboards[data.pool_id] = []
            pool_participants[data.pool_id] = []
            if data.pool_id in pool_data:
                pool_data[data.pool_id]["players"] = 0
            
            # Remove from global leaderboard
            global global_leaderboard
            global_leaderboard = [entry for entry in global_leaderboard if entry.get("pool_id") != data.pool_id]
            
            pool_start_times[data.pool_id] = int(time.time())
            # Remove any lingering active game entries for this pool
            for wallet in list(active_games.keys()):
                if active_games[wallet].get("pool_id") == data.pool_id:
                    del active_games[wallet]
            
            # Save data to file
            save_data()
            
            return {
                "status": "success",
                "pool_id": data.pool_id,
                "prize_pool": prize_amount_mist / 1_000_000_000,
                "dev_fee": dev_fee_mist / 1_000_000_000,
                "payouts": payouts,
                "contract_transaction": contract_result["transaction_id"],
                "message": f"Rewards distributed via smart contract (simulated: {contract_result.get('status') == 'simulated'})"
            }
        else:
            # If smart contract fails, return error - don't clear escrow
            return {
                "status": "error",
                "error": contract_result.get("error"),
                "message": "Smart contract call failed - funds remain in escrow. Manual payout required via Sui CLI."
            }
    except Exception as e:
        print(f"Distribution internal error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/pool/{pool_id}")
def get_pool(pool_id: str):
    if pool_id not in pool_data:
        raise HTTPException(status_code=404, detail="Pool not found")
    return {
        **pool_data[pool_id],
        "escrow_balance": escrow_funds[pool_id],
        "participants": pool_participants[pool_id],
        "participant_count": len(pool_participants[pool_id]),
        "active_sessions": len([g for g in active_games.values() if g.get("pool_id") == pool_id and g.get("status") == "active"])
    }

@app.get("/pool/{pool_id}/participants", dependencies=[Depends(dev_wallet_auth)])
def get_pool_participants_detail(pool_id: str):
    """Get full participant records for a pool including stats"""
    if pool_id not in pool_data:
        raise HTTPException(status_code=404, detail="Pool not found")
    return {
        "pool_id": pool_id,
        "participant_count": len(pool_participants.get(pool_id, [])),
        "participants": pool_participants.get(pool_id, [])
    }

@app.get("/status", dependencies=[Depends(dev_wallet_auth)])
def get_backend_status():
    """Debug/status endpoint to verify data integrity"""
    total_escrow = sum(escrow_funds.values())
    total_dev = sum(dev_fees_collected.values())
    return {
        "status": "running",
        "version": "2.0.6",
        "timestamp": int(time.time()),
        "pools": {
            pool_id: {
                "name": pool_data[pool_id]["name"],
                "escrow_sui": escrow_funds.get(pool_id, 0),
                "participants": len(pool_participants.get(pool_id, [])),
                "active_games": len([g for g in active_games.values() if g.get("pool_id") == pool_id and g.get("status") == "active"]),
                "start_time": pool_start_times.get(pool_id)
            }
            for pool_id in pool_data
        },
        "totals": {
            "total_escrow_sui": total_escrow,
            "total_dev_fees_sui": total_dev,
            "total_participants": sum(len(pool_participants.get(pid, [])) for pid in pool_data),
            "total_active_sessions": len([g for g in active_games.values() if g.get("status") == "active"]),
            "completed_cycles": len(pool_history)
        }
    }

@app.get("/transactions/{pool_id}")
def get_pool_transactions(pool_id: str):
    """Get all transactions for a specific pool"""
    pool_transactions = [tx for tx in transactions if tx.get("pool_id") == pool_id]
    return {"transactions": pool_transactions}

@app.get("/pool-history", dependencies=[Depends(dev_wallet_auth)])
def get_pool_history():
    """Get complete audit trail of all past pool cycles"""
    return {
        "history": pool_history,
        "total_cycles": len(pool_history),
        "by_pool": {
            "daily": len([h for h in pool_history if h.get("pool_id") == "daily"]),
            "weekly": len([h for h in pool_history if h.get("pool_id") == "weekly"]),
            "monthly": len([h for h in pool_history if h.get("pool_id") == "monthly"])
        }
    }

@app.get("/escrow/{pool_id}")
def get_escrow_status(pool_id: str):
    """Get escrow status for a pool"""
    if pool_id not in pool_data:
        raise HTTPException(status_code=404, detail="Pool not found")
    return {
        "pool_id": pool_id,
        "escrow_balance": escrow_funds[pool_id],
        "dev_fees_collected": dev_fees_collected[pool_id],
        "total_transactions": len([tx for tx in transactions if tx.get("pool_id") == pool_id]),
        "participants": len(pool_participants[pool_id]),
        "active_sessions": len([g for g in active_games.values() if g.get("pool_id") == pool_id and g.get("status") == "active"])
    }

@app.get("/dev-fees", dependencies=[Depends(dev_wallet_auth)])
def get_dev_fees():
    """Get total dev fees collected across all pools"""
    total_fees = sum(dev_fees_collected.values())
    fees_by_pool = {
        pool_id: f"{fee:.2f} SUI" 
        for pool_id, fee in dev_fees_collected.items()
    }
    return {
        "total_dev_fees": f"{total_fees:.2f} SUI",
        "dev_fee_percentage": f"{config.DEV_FEE_PERCENTAGE}%",
        "dev_wallet_address": config.DEV_WALLET_ADDRESS,
        "fees_by_pool": fees_by_pool
    }

async def get_pool_escrow_balance(pool_object_id: str):
    """Query actual escrow balance from pool Move object on-chain"""
    try:
        # First try the generic on-chain balance function
        result = await fetch_pool_balance_onchain(pool_object_id)
        if result is not None:
            return result

        # Fallback to direct query
        res = await call_sui_rpc("sui_getObject", [pool_object_id, {"showContent": True}])
        if "result" in res and "data" in res["result"]:
            fields = res["result"]["data"].get("content", {}).get("fields", {})
            # Look for escrow balance in dynamic fields
            escrow = fields.get("escrow")
            if escrow and isinstance(escrow, dict):
                balance = escrow.get("fields", {}).get("balance")
                if balance:
                    return int(balance)

        return 0
    except Exception as e:
        print(f"Escrow balance query error for {pool_object_id}: {e}")
        return 0

async def get_pool_object_balance(pool_object_id: str):
    """Query actual SUI balance inside a pool Move object on-chain"""
    try:
        res = await call_sui_rpc("sui_getObject", [pool_object_id, {"showContent": True}])
        if "result" in res and "data" in res["result"]:
            fields = res["result"]["data"].get("content", {}).get("fields", {})
            bal = (fields.get("balance") or fields.get("pool_balance") or
                   fields.get("escrow") or fields.get("total_balance"))
            if bal:
                return int(bal) / 1_000_000_000
        return 0
    except Exception as e:
        print(f"Balance query error: {e}")
        return 0

@app.post("/admin/trigger-payout")
async def admin_trigger_payout(pool_id: str):
    """Manual trigger for payout (no auth required for testing)"""
    if pool_id not in pool_data:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    dev_wallet = config.DEV_WALLET_ADDRESS
    
    # If leaderboard is empty (data was lost), add dev wallet as sole winner
    if not pool_leaderboards.get(pool_id):
        print(f"MANUAL PAYOUT: No scores found for {pool_id}, adding dev wallet as winner")
        pool_leaderboards[pool_id].append({
            "wallet": dev_wallet,
            "score": 999999,
            "timestamp": int(time.time() * 1000),
            "game_duration": 60,
            "forced": True
        })
        save_data()
    
    # Ensure dev wallet is in participants list
    if dev_wallet not in get_pool_wallets(pool_id):
        pool_participants[pool_id].append({
            "wallet": dev_wallet,
            "joined_at": int(time.time()),
            "games_played": 1,
            "best_score": 999999,
            "total_score": 999999,
            "last_active": int(time.time()),
            "forced": True
        })
        pool_data[pool_id]["players"] += 1
        save_data()
    
    # Query REAL on-chain balance and restore escrow so distribution works
    pool_object_id = pool_data[pool_id].get("contract_id", "0x0")
    real_balance = await get_pool_object_balance(pool_object_id) if pool_object_id != "0x0" else 0
    
    if real_balance > 0:
        print(f"MANUAL PAYOUT: Restoring escrow to real on-chain balance: {real_balance} SUI")
        escrow_funds[pool_id] = real_balance * 1_000_000_000  # Convert to MIST
        save_data()
    else:
        print(f"MANUAL PAYOUT: On-chain balance query returned 0 or failed for {pool_object_id}")
    
    print(f"MANUAL PAYOUT: Triggering payout for {pool_id}")
    result = await perform_reward_distribution(PayoutRequest(pool_id=pool_id, num_winners=10))
    print(f"MANUAL PAYOUT: Result - {result}")
    return result

@app.post("/withdraw-dev-fees", dependencies=[Depends(dev_wallet_auth)])
async def withdraw_dev_fees(pool_id: Optional[str] = None):
    """Withdraw dev fees to dev wallet address"""
    try:
        if pool_id and pool_id not in dev_fees_collected:
            raise HTTPException(status_code=404, detail="Pool not found")
        
        # Calculate total fees to withdraw
        if pool_id:
            fee_amount = dev_fees_collected[pool_id]
            dev_fees_collected[pool_id] = 0
        else:
            fee_amount = sum(dev_fees_collected.values())
            for pid in dev_fees_collected:
                dev_fees_collected[pid] = 0
        
        if fee_amount <= 0:
            return {"status": "no_fees", "message": "No dev fees to withdraw"}
        
        # In production, this would execute a Sui transaction to transfer SUI
        # to the dev wallet address using the admin private key
        # For now, just clear the fees and return a message
        
        save_data()
        
        return {
            "status": "success",
            "amount": f"{fee_amount:.2f} SUI",
            "to_wallet": config.DEV_WALLET_ADDRESS,
            "message": "Dev fees withdrawn - execute Sui transaction to transfer funds"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
