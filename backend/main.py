from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
from collections import defaultdict
import time
import json
import os
import subprocess
from config import config
import httpx

# Sui Imports
try:
    from pysui import SuiConfig, SyncClient, handle_result, ObjectID
    try:
        from pysui.sui.sui_types.address import SuiAddress
        from pysui.sui.sui_types.scalars import SuiString, SuiU64
        from pysui.sui.sui_types.collections import SuiArray
    except ImportError:
        # Fall back to legacy module path (pysui < 0.95)
        from pysui.sui_types.address import SuiAddress
        from pysui.sui_types.scalars import SuiString, SuiU64
        from pysui.sui_types.collections import SuiArray
    HAS_PYSUI = True
except ImportError as e:
    print(f"pysui import failed ({e}) - using simulation mode")
    HAS_PYSUI = False


app = FastAPI(title="Sui Blaster Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
DATA_FILE = os.getenv("DATA_FILE", os.path.join(os.getcwd(), "data.json"))


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


# Pool durations (seconds)
POOL_DURATIONS = {
    "daily": _get_duration_override("POOL_DURATION_DAILY_SECONDS", 24 * 60),
    "weekly": _get_duration_override("POOL_DURATION_WEEKLY_SECONDS", 7 * 24 * 3600),
    "monthly": _get_duration_override("POOL_DURATION_MONTHLY_SECONDS", 28 * 24 * 3600)
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


def _parse_entry_fee_to_mist(entry_fee: str) -> int:
    if not entry_fee:
        return config.POOL_ENTRY_FEE
    cleaned = "".join(ch for ch in entry_fee if ch.isdigit() or ch == ".")
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
    wallets = []
    for p in participants:
        if isinstance(p, str):
            wallets.append(p)
        elif isinstance(p, dict):
            wallets.append(p.get("wallet", ""))
    return wallets

def load_data():
    """Load data from local JSON file"""
    global global_leaderboard, pool_leaderboards, pool_data, transactions, escrow_funds, pool_participants, dev_fees_collected, pool_start_times, active_games, pool_history
    
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
        pool_data = data.get("pool_data", {
            "daily": {"id": "daily", "name": "Daily Pool", "duration": "24h", "entry_fee": "0.1 SUI", "prize": "0 SUI", "players": 0, "contract_id": config.DAILY_POOL_ID},
            "weekly": {"id": "weekly", "name": "Weekly Pool", "duration": "7d", "entry_fee": "0.5 SUI", "prize": "0 SUI", "players": 0, "contract_id": config.WEEKLY_POOL_ID},
            "monthly": {"id": "monthly", "name": "Monthly Pool", "duration": "28d", "entry_fee": "1 SUI", "prize": "0 SUI", "players": 0, "contract_id": config.MONTHLY_POOL_ID}
        })
        # Always ensure latest contract IDs from config are applied to pools
        if "daily" in pool_data: pool_data["daily"]["contract_id"] = config.DAILY_POOL_ID
        if "weekly" in pool_data: pool_data["weekly"]["contract_id"] = config.WEEKLY_POOL_ID
        if "monthly" in pool_data: pool_data["monthly"]["contract_id"] = config.MONTHLY_POOL_ID
        
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
        now = int(time.time())
        pool_start_times = {
            "daily": loaded_start_times.get("daily", now),
            "weekly": loaded_start_times.get("weekly", now),
            "monthly": loaded_start_times.get("monthly", now)
        }
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
pool_data = {
    "daily": {"id": "daily", "name": "Daily Pool", "duration": "24h", "entry_fee": "0.1 SUI", "prize": "0 SUI", "players": 0, "contract_id": config.DAILY_POOL_ID},
    "weekly": {"id": "weekly", "name": "Weekly Pool", "duration": "7d", "entry_fee": "0.5 SUI", "prize": "0 SUI", "players": 0, "contract_id": config.WEEKLY_POOL_ID},
    "monthly": {"id": "monthly", "name": "Monthly Pool", "duration": "28d", "entry_fee": "1 SUI", "prize": "0 SUI", "players": 0, "contract_id": config.MONTHLY_POOL_ID}
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

    # First try to read the Balance<SUI> dynamic field that actually holds escrow funds.
    if config.PACKAGE_ID:
        try:
            params = [
                pool_object_id,
                {
                    "type": f"{config.PACKAGE_ID}::pool::EscrowKey",
                    "value": {}
                }
            ]
            dyn_result = await call_sui_rpc("suix_getDynamicFieldObject", params)
            dyn_data = dyn_result.get("result", {}).get("data", {})
            dyn_content = dyn_data.get("content", {})
            dyn_fields = dyn_content.get("fields", {})
            balance_struct = dyn_fields.get("value")  # Balance<SUI>
            if isinstance(balance_struct, dict):
                balance_value = balance_struct.get("fields", {}).get("value")
            else:
                balance_value = balance_struct
            if balance_value is not None:
                return int(balance_value)
        except Exception as e:
            print(f"Error fetching dynamic escrow balance for {pool_object_id}: {e}")

    # Fall back to legacy `pool.balance` field if dynamic fetch fails.
    try:
        params = [
            pool_object_id,
            {
                "showContent": True,
                "showType": True,
                "showOwner": False,
                "showPreviousTransaction": False,
                "showStorageRebate": False,
                "showDisplay": False
            }
        ]
        result = await call_sui_rpc("sui_getObject", params)
        data = result.get("result", {}).get("data", {})
        content = data.get("content", {})
        fields = content.get("fields", {})
        balance_value = fields.get("balance")
        if balance_value is None:
            return None
        if isinstance(balance_value, str):
            return int(balance_value)
        if isinstance(balance_value, (int, float)):
            return int(balance_value)
    except Exception as e:
        print(f"Error fetching on-chain pool balance for {pool_object_id}: {e}")
    return None

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
    """Call a smart contract function on Sui - attempts real transaction if pysui + admin key available"""
    try:
        admin_key = config.ADMIN_PRIVATE_KEY.strip() if config.ADMIN_PRIVATE_KEY else ""
        
        if HAS_PYSUI and admin_key and config.PACKAGE_ID and config.PACKAGE_ID != "0x0":
            print(f"Attempting REAL on-chain transaction: {function}")
            try:
                # Initialize Sui client with admin key
                cfg = SuiConfig.user_config(
                    rpc_url=config.SUI_NETWORK,
                    prv_keys=[admin_key]
                )
                client = SyncClient(cfg)
                
                # Build and execute transaction
                txer = client.transaction()
                
                if function == "distribute_rewards":
                    # args: [pool_object_id, [(winner_addr, amount_mist), ...]]
                    pool_id = args[0] if len(args) > 0 else "0x0"
                    winners = args[1] if len(args) > 1 else []
                    
                    # Separate into parallel vectors for new Move contract signature
                    winner_addrs_list = [SuiAddress(w[0]) for w in winners]
                    winner_amounts_list = [SuiU64(int(w[1])) for w in winners]
                    
                    winner_addrs = SuiArray(winner_addrs_list)
                    winner_amounts = SuiArray(winner_amounts_list)
                    
                    txer.move_call(
                        target=f"{config.PACKAGE_ID}::pool::distribute_rewards",
                        arguments=[ObjectID(pool_id), winner_addrs, winner_amounts]
                    )
                else:
                    # Generic fallback - just simulate for unsupported functions
                    print(f"Function {function} not implemented for real signing, using simulation")
                    return {
                        "status": "simulated",
                        "function": function,
                        "transaction_id": f"sim_{int(time.time())}"
                    }
                
                result = txer.execute()
                result = handle_result(result)
                tx_digest = result.transaction_digest if hasattr(result, 'transaction_digest') else str(result)
                
                print(f"Transaction succeeded: {tx_digest}")
                return {
                    "status": "success",
                    "function": function,
                    "transaction_id": tx_digest,
                    "message": "Transaction executed on-chain"
                }
            except Exception as e:
                print(f"Real transaction failed: {e}")
                # Fall through to simulation
        
        # Fallback to simulation
        if not admin_key:
            print(f"ADMIN_PRIVATE_KEY not found - simulating {function}")
        elif not HAS_PYSUI:
            print(f"pysui not installed - simulating {function}")
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
    return {"status": "Sui Blaster Backend Running"}

import asyncio

# Add pool start times to track expiration
pool_start_times = {
    "daily": int(time.time()),
    "weekly": int(time.time()),
    "monthly": int(time.time())
}

async def auto_distribute_task():
    """Background task to automatically distribute rewards when pools expire"""
    while True:
        try:
            now = int(time.time())
            
            for pool_id, duration in POOL_DURATIONS.items():
                start_time = pool_start_times.get(pool_id, now)
                elapsed = now - start_time
                if elapsed >= duration:
                    participants = pool_participants.get(pool_id, [])
                    escrow_balance = escrow_funds.get(pool_id, 0)
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
                    
                    # Call the distribution logic (reuse existing endpoint)
                    try:
                        result = await distribute_rewards(PayoutRequest(pool_id=pool_id, num_winners=10))
                    except Exception as dist_err:
                        print(f"AUTOMATION: Distribution failed for {pool_id}: {dist_err}")
                        continue

                    status = result.get("status") if isinstance(result, dict) else None
                    if status != "success":
                        print(f"AUTOMATION: Distribution did not complete for {pool_id} (status={status}). Pool will remain open for manual retry.")
                        continue

                    # Reset pool for the next period only when payout succeeded
                    pool_start_times[pool_id] = now
                    pool_leaderboards[pool_id] = []
                    pool_participants[pool_id] = []

                    # Clear completed/abandoned game sessions for this pool
                    for wallet in list(active_games.keys()):
                        if active_games[wallet].get("pool_id") == pool_id:
                            del active_games[wallet]

                    save_data()
                    print(f"AUTOMATION: Pool {pool_id} reset for new period.")
            
            # Check every hour
            await asyncio.sleep(3600)
            
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
        pool_copy["prize"] = f"{current_prize:.2f} SUI (Dynamic)"
        pool_copy["payout_structure"] = POOL_PAYOUTS.get(pool["id"], [])

        # Add countdown metadata
        duration_seconds = POOL_DURATIONS.get(pool["id"])
        start_time = pool_start_times.get(pool["id"], int(time.time()))
        if duration_seconds:
            now_ts = int(time.time())
            elapsed = max(0, now_ts - start_time)
            remaining = max(duration_seconds - elapsed, 0)
            pool_copy["seconds_remaining"] = remaining
            pool_copy["duration_seconds"] = duration_seconds
            pool_copy["started_at"] = start_time
            pool_copy["ends_at"] = start_time + duration_seconds
        else:
            pool_copy["seconds_remaining"] = None
            pool_copy["duration_seconds"] = None
            pool_copy["started_at"] = start_time
            pool_copy["ends_at"] = None

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
    if data.pool_id not in pool_data:
        raise HTTPException(status_code=404, detail="Pool not found")

    
    # Check if wallet is already in this pool
    if data.wallet in get_pool_wallets(data.pool_id):
        raise HTTPException(status_code=400, detail="Already joined this pool")
    
    # Determine expected entry fee in MIST
    pool_entry_fee = pool_data[data.pool_id].get("entry_fee", str(config.POOL_ENTRY_FEE / 1_000_000_000))
    expected_entry_fee = _parse_entry_fee_to_mist(pool_entry_fee)

    # Verify transaction if provided
    transaction_verified = False
    payment_amount_mist = 0
    
    if data.transaction_id:
        # Verify the Sui transaction
        tx_verification = await verify_sui_transaction(data.transaction_id, data.pool_id, expected_entry_fee)
        if tx_verification:
            transaction_verified = True
            payment_amount_mist = tx_verification.get("amount_mist", 0)
        else:
            raise HTTPException(status_code=400, detail="Invalid transaction")
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
    save_data()
    
    return {
        "status": "success",
        "message": "Joined pool successfully",
        "pool": pool_data[data.pool_id],
        "transaction_verified": transaction_verified,
        "escrow_balance": escrow_funds[data.pool_id]
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
async def distribute_rewards(data: PayoutRequest):
    """Distribute rewards to winners of a pool"""
    try:
        if data.pool_id not in pool_leaderboards:
            raise HTTPException(status_code=404, detail="Pool not found")
        
        if data.pool_id not in pool_data:
            raise HTTPException(status_code=404, detail="Pool not found")
        
        leaderboard = pool_leaderboards[data.pool_id][:data.num_winners]
        
        if not leaderboard:
            print(f"PAYOUT: {data.pool_id} distribution skipped - no leaderboard entries during payout")
            return {"status": "no_scores", "message": "No scores to distribute rewards for"}
        
        # Use actual escrow balance as prize pool (dynamic based on entry fees)
        prize_amount = escrow_funds[data.pool_id]
        
        if prize_amount <= 0:
            print(f"PAYOUT: {data.pool_id} distribution skipped - escrow balance is {prize_amount}")
            return {"status": "no_funds", "message": "No funds in prize pool"}
        
        # Calculate and deduct dev fee
        dev_fee = prize_amount * (config.DEV_FEE_PERCENTAGE / 100)
        prize_after_fee = prize_amount - dev_fee
        
        # Record dev fee
        dev_fees_collected[data.pool_id] += dev_fee
        
        reward_percentages = POOL_PAYOUTS.get(data.pool_id, [100])
            
        payouts = []
        winners = [] # List of (address, amount_mist)
        
        # Add Dev Fee to the winners list so it gets paid at the same time
        if dev_fee > 0:
            dev_wallet = config.DEV_WALLET_ADDRESS
            winners.append((dev_wallet, int(dev_fee * 1_000_000_000)))
        
        # We pay out to the number of winners specified in reward_percentages, 
        # but only if there are enough people on the leaderboard.
        num_to_pay = len(reward_percentages)
        actual_winners_count = min(len(leaderboard), num_to_pay)
        
        # Adjust percentages if fewer winners than slots
        if actual_winners_count > 0 and actual_winners_count < num_to_pay:
            adjusted_pct = 100 / actual_winners_count
            reward_percentages = [adjusted_pct] * actual_winners_count
        
        for i in range(actual_winners_count):
            entry = leaderboard[i]
            reward = prize_after_fee * (reward_percentages[i] / 100)
            payouts.append({
                "rank": i + 1,
                "wallet": entry["wallet"],
                "score": entry["score"],
                "reward": f"{reward:.2f} SUI"
            })
            winners.append((entry["wallet"], int(reward * 1_000_000_000)))  # Convert to MIST
        
        # Call smart contract to distribute rewards
        contract_result = await call_smart_contract("distribute_rewards", [
            pool_data[data.pool_id].get("contract_id", "0x0"),  # Pool object ID
            winners
        ])
        
        if contract_result["status"] == "success":
            # Archive this pool cycle to history before clearing
            pool_history.append({
                "pool_id": data.pool_id,
                "distributed_at": int(time.time()),
                "total_prize": prize_amount,
                "dev_fee": dev_fee,
                "prize_after_fee": prize_after_fee,
                "num_winners": len(payouts),
                "payouts": payouts,
                "participants": [p.get("wallet") if isinstance(p, dict) else p for p in pool_participants.get(data.pool_id, [])],
                "leaderboard_at_distribution": leaderboard[:actual_winners_count] if actual_winners_count > 0 else [],
                "contract_transaction": contract_result.get("transaction_id")
            })
            
            # Clear escrow after distribution (contract handles actual transfer)
            escrow_funds[data.pool_id] = 0
            dev_fees_collected[data.pool_id] = 0  # Contract handles dev fee transfer
            pool_leaderboards[data.pool_id] = []
            pool_participants[data.pool_id] = []
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
                "total_prize": f"{prize_amount:.2f} SUI (from escrow)",
                "dev_fee": f"{dev_fee:.2f} SUI ({config.DEV_FEE_PERCENTAGE}%)",
                "prize_after_fee": f"{prize_after_fee:.2f} SUI",
                "num_winners": len(payouts),
                "payouts": payouts,
                "contract_transaction": contract_result["transaction_id"],
                "message": "Rewards distributed via smart contract"
            }
        else:
            return {
                "status": "error",
                "error": contract_result.get("error"),
                "message": "Failed to call smart contract"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@app.post("/admin/force-payout", dependencies=[Depends(dev_wallet_auth)])
async def admin_force_payout(pool_id: str):
    """Force payout - queries real chain balance, adds dev wallet as winner, distributes"""
    if pool_id not in pool_data:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    dev_wallet = config.DEV_WALLET_ADDRESS
    
    # If leaderboard is empty (data was lost), add dev wallet as sole winner
    if not pool_leaderboards.get(pool_id):
        print(f"FORCE PAYOUT: No scores found for {pool_id}, adding dev wallet as winner")
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
        print(f"FORCE PAYOUT: Restoring escrow to real on-chain balance: {real_balance} SUI")
        escrow_funds[pool_id] = real_balance
        save_data()
    else:
        print(f"FORCE PAYOUT: On-chain balance query returned 0 or failed for {pool_object_id}")
    
    # Trigger distribution
    result = await distribute_rewards(PayoutRequest(pool_id=pool_id, num_winners=10))
    
    return {
        "status": "force_payout_triggered",
        "pool_id": pool_id,
        "pool_object_id": pool_object_id,
        "real_balance_queried": real_balance,
        "result": result,
        "message": "If on-chain transaction succeeded, funds have been distributed. Check Sui Explorer for the transaction digest."
    }

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
