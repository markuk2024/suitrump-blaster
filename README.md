# SuiTrump Blaster - Web3 Space Shooter Game

A mobile-only Web3 space shooter game on the Sui blockchain with competitive leaderboards and prize pools.

## Features

- **Mobile-Only Design**: Optimized for mobile devices to prevent cheating
- **Time-Based Competitions**: 24h, 7d, and 28d prize pools
- **Escrow System**: Secure fund locking and automatic reward distribution
- **Anti-Cheat**: Backend score validation before blockchain submission
- **Sui Integration**: Pay-to-play with SUI tokens, on-chain leaderboards
- **SUITRUMP Rewards**: Player payouts in SUITRUMP token, dev fees in SUI

## Architecture

```
suitrump-blaster/
├── contracts/          # Move smart contracts
├── backend/            # Python FastAPI server
├── frontend/           # React + Phaser game
└── README.md
```

## Setup Instructions

### 1. Install Dependencies

**Backend:**
```bash
cd backend
pip install -r requirements.txt
```

**Frontend:**
```bash
cd frontend
npm install
```

### 2. Deploy Smart Contract

```bash
cd contracts
sui client publish
```

### 3. Configure Backend

Edit `backend/config.py` with your:
- Sui network RPC URL
- Admin wallet private key
- Contract package ID
- (Optional) Persistent storage path via `DATA_FILE`. On Render, attach a disk and set `DATA_FILE=/var/data/suitrump-blaster/data.json` (or similar) so leaderboards and escrow mirrors survive redeploys.

### 4. Run Backend

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Run Frontend

```bash
cd frontend
npm run dev
```

### 6. Access Game

Open http://localhost:3000 on your mobile device

## Game Flow

1. **Connect Wallet**: Connect your Sui wallet
2. **Enter Pool**: Pay entry fee (Daily: 5 SUI, Weekly: 2.5 SUI, 28-day: 1 SUI) to join a competition
3. **Play Game**: Control your ship, shoot enemies, score points
4. **Score Validation**: Backend validates gameplay data
5. **Leaderboard**: Score submitted to on-chain leaderboard
6. **Claim Rewards**: After competition ends, top players claim SUITRUMP rewards (dev fees paid in SUI)

## Reward Distribution

- Before rewards go out, **2.5%** (configurable) is skimmed off the prize pool as a dev fee and sent to the dev wallet in SUI.
- Player rewards are distributed in SUITRUMP token.
- Daily Pool: Top 3 players (50%, 30%, 20%)
- Weekly Pool: Top 4 players (40%, 25%, 20%, 15%)
- 28-Day Pool: Top 4 players (45%, 25%, 20%, 10%)

## Anti-Cheat Measures

- Mobile-only restriction
- Backend score validation
- Maximum score per second limits
- Timestamp verification
- Replay data validation (future)

## Smart Contract Functions

- `create_pool`: Create a new competition pool
- `enter_pool`: Pay entry fee to join
- `submit_score`: Submit validated score (admin only)
- `finalize_pool`: End competition and calculate rewards
- `claim_reward`: Claim winnings

## Development

**Contract:**
```bash
cd contracts
sui move build
```

**Backend:**
```bash
cd backend
python -m pytest
```

**Frontend:**
```bash
cd frontend
npm test
```

## License

MIT
