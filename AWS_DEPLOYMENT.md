# AWS Deployment Guide for SuiTrump Blaster

This guide will help you deploy SuiTrump Blaster to AWS using App Runner (backend) and Amplify (frontend).

## Prerequisites

- AWS account (already created)
- GitHub repository with the code
- AWS CLI installed (optional but recommended)

## Step 1: Deploy Backend to AWS App Runner

### 1.1 Create App Runner Service

1. Go to AWS Console → App Runner
2. Click "Create service"
3. **Source settings:**
   - Source repository account: "My account"
   - Source repository: Select your GitHub repository
   - Repository type: "Repository image" or "Source code" (we'll use Source code)
   - Connect GitHub if not already connected
   - Select your repository and branch (main)

4. **Build settings:**
   - Build configuration: "Automatic"
   - Runtime: "Python 3.11"
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port 8080`
   - Port: `8080`

5. **Environment variables:**
   Click "Add variable" and add:
   ```
   SUI_NETWORK=https://fullnode.mainnet.sui.io
   PACKAGE_ID=0x529e9c233a7f2f6cc5bcd8371735cba8e44d80a1d30c8bd0a29ea4b4be4d4b54
   DEV_FEE_PERCENTAGE=2.5
   DEV_WALLET_ADDRESS=0x0d32cdae7aa9a25003687dcbfe154c5d13bc51b76fd29116a54276c1f80fd140
   MAX_SCORE_PER_SECOND=100
   MAX_GAME_DURATION=300
   POOL_ENTRY_FEE=100000000
   ```

6. **Service settings:**
   - Service name: `suitrump-blaster-backend`
   - CPU: 1 vCPU
   - Memory: 2 GB (or 1 GB for free tier if available)
   - Auto scaling: Enable (minimum 1, maximum 2)

7. Click "Create and deploy"

8. Wait for deployment (5-10 minutes)
9. Copy the service URL (e.g., `https://xxxxx.us-east-1.awsapprunner.com`)

### 1.2 Alternative: Using Docker Image

If you prefer using the Dockerfile:

1. Push your code to GitHub
2. Go to AWS Console → Elastic Container Registry (ECR)
3. Create a repository named `suitrump-blaster-backend`
4. Follow the push commands shown in ECR:
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
   docker build -t suitrump-blaster-backend .
   docker tag suitrump-blaster-backend:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/suitrump-blaster-backend:latest
   docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/suitrump-blaster-backend:latest
   ```

5. Then create App Runner service using the ECR image

## Step 2: Deploy Frontend to AWS Amplify

### 2.1 Create Amplify App

1. Go to AWS Console → Amplify
2. Click "New app" → "Host web app"
3. **Repository:**
   - Select GitHub
   - Connect your GitHub account
   - Select your repository and branch (main)

4. **Build settings:**
   - App name: `suitrump-blaster-frontend`
   - Build and test settings:
     - Build command: `npm run build`
     - Output directory: `dist`
     - Base directory: `frontend`

5. **Environment variables:**
   Click "Add variable" and add:
   ```
   VITE_API_URL=https://your-backend-url.us-east-1.awsapprunner.com
   VITE_SUI_PACKAGE_ID=0x529e9c233a7f2f6cc5bcd8371735cba8e44d80a1d30c8bd0a29ea4b4be4d4b54
   ```

6. Click "Next" → "Save and deploy"

7. Wait for deployment (2-3 minutes)
8. Copy the Amplify URL (e.g., `https://main.xxxxx.amplifyapp.com`)

### 2.2 Add Custom Domain (Optional)

1. In Amplify console, go to "Domain management"
2. Click "Add domain"
3. Enter your domain name (e.g., `suitrumpblaster.yourdomain.com`)
4. Follow the DNS setup instructions

## Step 3: Test the Deployment

### 3.1 Test Backend

```bash
curl https://your-backend-url.us-east-1.awsapprunner.com/pools
```

Should return pool data.

### 3.2 Test Frontend

1. Open the Amplify URL in your browser
2. Connect wallet
3. Try joining a pool
4. Play the game

## Step 4: Data Persistence (Important)

The current implementation uses file-based storage (`data.json`). This is **not suitable for production** because:
- Data will be lost when the service restarts
- App Runner uses ephemeral storage

### Solutions:

#### Option 1: AWS S3 (Recommended)

1. Create an S3 bucket named `suitrump-blaster-data`
2. Update the backend to use S3 instead of local file

Install boto3:
```bash
pip install boto3
```

Update `main.py`:
```python
import boto3
from botocore.exceptions import NoCredentialsError

s3 = boto3.client('s3')
BUCKET_NAME = 'suitrump-blaster-data'

def save_data():
    try:
        data = {
            'leaderboard': global_leaderboard,
            'pools': pool_data,
            'escrow': escrow_funds,
            'transactions': transactions,
            'dev_fees': dev_fees_collected,
            'pool_leaderboards': pool_leaderboards
        }
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key='data.json',
            Body=json.dumps(data),
            ContentType='application/json'
        )
    except NoCredentialsError:
        print("AWS credentials not found")

def load_data():
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key='data.json')
        data = json.loads(response['Body'].read())
        # Load data into global variables
    except s3.exceptions.NoSuchKey:
        print("No existing data found")
```

Add IAM permissions to App Runner service to access S3.

#### Option 2: AWS DynamoDB (Better for structured data)

1. Create a DynamoDB table named `SuiTrumpBlasterData`
2. Use AWS SDK to store/retrieve data

#### Option 3: AWS RDS (PostgreSQL)

1. Create RDS PostgreSQL instance
2. Use SQLAlchemy for database operations

## Step 5: Security Considerations

### 5.1 API Gateway (Optional)

Add API Gateway in front of App Runner for:
- Rate limiting
- Authentication
- WAF (Web Application Firewall)

### 5.2 Environment Variables

- Never commit `.env` files to git
- Use AWS Secrets Manager for sensitive data
- Enable HTTPS only (Amplify does this by default)

### 5.3 CORS

The backend already has CORS enabled, but you may want to restrict origins in production:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-amplify-url.amplifyapp.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Step 6: Cost Estimates

### AWS Free Tier (12 months)

- App Runner: 1,000 GB-hours/month of compute (free for first 12 months)
- Amplify: 1,000 build minutes/month (free)
- S3: 5 GB storage + 20,000 requests/month (free)
- Total: **Free for first 12 months**

### After Free Tier

- App Runner: ~$20-30/month (1 vCPU, 2 GB RAM)
- Amplify: ~$10-20/month
- S3: ~$0.023/GB/month
- Total: **~$30-50/month**

## Step 7: Monitoring

### 7.1 CloudWatch

App Runner automatically sends metrics to CloudWatch:
- CPU utilization
- Memory utilization
- Request count
- Response time

### 7.2 CloudWatch Logs

View logs in:
- App Runner → Logs
- Amplify → Logs

### 7.3 Alarms

Set up CloudWatch alarms for:
- High error rate
- High latency
- Low health status

## Troubleshooting

### Backend Won't Start

1. Check App Runner logs
2. Verify environment variables are set correctly
3. Ensure port 8080 is used in start command

### Frontend Build Fails

1. Check Amplify logs
2. Verify build command is `npm run build`
3. Ensure `package.json` is in the root of frontend directory

### CORS Errors

1. Check backend CORS middleware
2. Verify `VITE_API_URL` is correct
3. Ensure backend URL is HTTPS

### Data Not Persisting

1. Implement S3 or DynamoDB for data storage
2. File storage will not work in production with App Runner

## Next Steps

1. Deploy backend to App Runner
2. Deploy frontend to Amplify
3. Test the full application
4. Implement S3 or DynamoDB for data persistence
5. Set up CloudWatch alarms
6. Add custom domain (optional)
7. Share the Amplify URL with users
