# Suiter Deployment Guide

This guide will help you deploy Suiter so other users can play it.

## Prerequisites

- Git repository with the code
- Accounts on deployment platforms (free tiers available)
- Backend deployed package ID: `0x529e9c233a7f2f6cc5bcd8371735cba8e44d80a1d30c8bd0a29ea4b4be4d4b54`

## Deployment Options

### Option 1: Render (Recommended - Free Tier)

#### Backend Deployment (Render)

1. **Create a Render account** at https://render.com
2. **Deploy the backend:**
   - Go to Render Dashboard → New → Web Service
   - Connect your GitHub repository
   - Root directory: `backend`
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Add environment variables:
     ```
     SUI_NETWORK=https://fullnode.mainnet.sui.io
     PACKAGE_ID=0x45f3505dd139ff3f68525a9bba495ae4b9cb4309c052612f288992aff6968920
     DEV_FEE_PERCENTAGE=2.5
     DEV_WALLET_ADDRESS=0x0d32cdae7aa9a25003687dcbfe154c5d13bc51b76fd29116a54276c1f80fd140
     MAX_SCORE_PER_SECOND=100
     MAX_GAME_DURATION=300
     POOL_ENTRY_FEE=100000000
     ```
   - Click Deploy Web Service
   - Copy the deployed URL (e.g., `https://suitrump-blaster-backend.onrender.com`)

#### Frontend Deployment (Vercel)

1. **Create a Vercel account** at https://vercel.com
2. **Deploy the frontend:**
   - Go to Vercel Dashboard → Add New Project
   - Import your GitHub repository
   - Root directory: `frontend`
   - Build command: `npm run build`
   - Output directory: `dist`
   - Add environment variable:
     ```
     VITE_API_URL=https://your-backend-url.onrender.com
     VITE_SUI_PACKAGE_ID=0x45f3505dd139ff3f68525a9bba495ae4b9cb4309c052612f288992aff6968920
     ```
   - Click Deploy
   - Copy the deployed frontend URL

### Option 2: Railway (Alternative Free Tier)

#### Backend Deployment (Railway)

1. **Create a Railway account** at https://railway.app
2. **Deploy the backend:**
   - New Project → Deploy from GitHub repo
   - Select your repository
   - Set root directory to `backend`
   - Add environment variables (same as Render)
   - Deploy
   - Copy the deployed URL

#### Frontend Deployment (Netlify)

1. **Create a Netlify account** at https://netlify.com
2. **Deploy the frontend:**
   - New site from Git
   - Connect GitHub repository
   - Set build directory to `frontend`
   - Build command: `npm run build`
   - Publish directory: `frontend/dist`
   - Add environment variable `VITE_API_URL`
   - Deploy

### Option 3: Self-Hosted (VPS)

If you have a VPS (DigitalOcean, AWS, etc.):

#### Backend Deployment

```bash
# SSH into your server
ssh user@your-server

# Clone the repository
git clone <your-repo-url>
cd suitrump-blaster/backend

# Install dependencies
pip install -r requirements.txt

# Install nginx and supervisor
sudo apt install nginx supervisor

# Create a systemd service
sudo nano /etc/systemd/system/suitrump-blaster.service
```

Add this content:
```
[Unit]
Description=SuiTrump Blaster Backend
After=network.target

[Service]
User=your-user
WorkingDirectory=/path/to/suitrump-blaster/backend
ExecStart=/usr/local/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Start the service
sudo systemctl start suitrump-blaster
sudo systemctl enable suitrump-blaster

# Configure nginx
sudo nano /etc/nginx/sites-available/suitrump-blaster
```

Add this content:
```
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# Enable the site
sudo ln -s /etc/nginx/sites-available/suitrump-blaster /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### Frontend Deployment

```bash
cd ../frontend
npm run build

# Copy build files to nginx
sudo cp -r dist/* /var/www/html/
```

## Important Notes

### Data Persistence

The current implementation uses file-based storage (`data.json`). For production:

- **Option 1:** Use a cloud storage service (AWS S3, Google Cloud Storage)
- **Option 2:** Use a database (PostgreSQL, MongoDB)
- **Option 3:** Keep file storage with regular backups

### Security

- Never commit `.env` files to git
- Use HTTPS for all deployments
- Consider adding rate limiting to the backend
- Add authentication for admin endpoints

### Smart Contract

The deployed smart contract is a simplified version. For production:

1. Update the contract to handle actual SUI transfers
2. Deploy an updated version with proper escrow logic
3. Update the `PACKAGE_ID` in environment variables

## Testing After Deployment

1. **Test backend:**
   - Visit `https://your-backend-url.com/pools`
   - Should return pool data

2. **Test frontend:**
   - Visit your frontend URL
   - Connect wallet
   - Join a pool
   - Play the game

3. **Test wallet connection:**
   - Ensure Slush wallet can connect
   - Verify transactions work on mainnet

## Troubleshooting

**CORS Errors:**
- Ensure backend has CORS middleware enabled
- Check that frontend API URL is correct

**Wallet Connection Issues:**
- Verify the network is set to mainnet
- Check that Slush wallet is installed
- Ensure the smart contract is deployed on mainnet

**Data Persistence Issues:**
- If using file storage, data may be lost on redeployment
- Consider implementing a database for production

## Cost Estimates

- **Render Free Tier:** Free (limited to 750 hours/month)
- **Vercel Free Tier:** Free (unlimited bandwidth)
- **Railway Free Tier:** Free ($5 credit/month)
- **VPS:** ~$5-10/month (DigitalOcean, Linode)

## Next Steps

1. Deploy backend to Render/Railway
2. Deploy frontend to Vercel/Netlify
3. Update frontend environment variable with backend URL
4. Test the full game flow
5. Share the frontend URL with users
