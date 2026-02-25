# Cloud Deployment Guide - AWS / Google Cloud / Azure

Your Buddi Agent is ready to deploy to the cloud. This guide shows you how to prepare for AWS, Google Cloud, and Azure when you're ready.

## Architecture-Ready Status

✅ **Backend**: Stateless API (can scale easily)
✅ **Frontend**: Static files (CDN-ready)
✅ **Separation**: Backend and frontend can be deployed independently
✅ **Container**: Docker support available (docker-compose.yml exists)

## Pre-Deployment Checklist

Before deploying, complete these locally:

- [ ] Connect your agent logic in `backend/api.py` → `process_user_input()`
- [ ] Test the web interface locally
- [ ] Update `.env` with production values
- [ ] Test all API endpoints with real data
- [ ] Ensure no hardcoded secrets or credentials

## Deployment Option Comparison

| Feature | AWS | Google Cloud | Azure |
|---------|-----|--------------|-------|
| **Backend** | EC2, Lambda, AppRunner | Cloud Run, Compute Engine | App Service, Container Instances |
| **Frontend** | S3 + CloudFront | Cloud Storage + CDN | Static Web Apps |
| **Database** | RDS, DynamoDB | Cloud Firestore, Cloud SQL | Azure SQL, Cosmos DB |
| **Difficulty** | Medium | Easy | Easy |
| **Cost** | High | Medium | Medium |
| **Serverless** | Yes (Lambda) | Yes (Cloud Run) | Yes (Functions) |

## For AWS Deployment

### Backend Setup
1. **Go to AWS Console → EC2 or Lambda**
2. **If using EC2**:
   - Launch Ubuntu instance
   - Install Python3, pip
   - Clone your repo
   - Install dependencies: `pip install -r requirements.txt`
   - Run: `python -m uvicorn backend.api:app --host 0.0.0.0 --port 8000`
   - Use systemd or supervisor to keep running
   - Set up security groups to allow port 8000

3. **If using Lambda** (better for free tier):
   - Package FastAPI app with Zappa or similar
   - Deploy: `pip install zappa && zappa init && zappa deploy prod`

### Frontend Setup
1. **Go to AWS S3**
2. **Create bucket**: `buddi-agent-frontend`
3. **Upload files from `/web` folder**
4. **Enable static website hosting**
5. **Update `API_BASE_URL` in `web/script.js`**:
```javascript
const API_BASE_URL = 'https://your-backend-url.com/api';
```
6. **Use CloudFront for CDN/HTTPS**

### Update Backend CORS
In `backend/api.py`, change:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-domain.com"],  # Limit to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## For Google Cloud Deployment

### Backend Setup (Cloud Run - Recommended)
1. **Go to Google Cloud Console → Cloud Run**
2. **Create a Dockerfile** (your existing one works):
```dockerfile
# The existing Dockerfile in your repo works as-is
```
3. **Build and push**:
```bash
gcloud builds submit --tag gcr.io/YOUR-PROJECT/buddi-backend
```
4. **Deploy**:
```bash
gcloud run deploy buddi-backend \
  --image gcr.io/YOUR-PROJECT/buddi-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```
5. **Get the URL** from Cloud Run dashboard

### Frontend Setup (Firebase Hosting)
1. **Install Firebase CLI**:
```bash
npm install -g firebase-tools
firebase login
firebase init hosting
```
2. **Deploy your web files**:
```bash
cp -r web/* public/
firebase deploy
```

### Update Backend CORS
```python
allow_origins=["https://your-firebase-project.web.app"],
```

## For Azure Deployment

### Backend Setup (App Service)
1. **Go to Azure Portal → App Service**
2. **Create new Web App**:
   - Runtime: Python 3.9+
   - Region: East US (free tier available)
3. **Deploy from GitHub** (easiest):
   - Connect your GitHub repo
   - Configure deployment settings
4. **Or deploy manually**:
```bash
az login
az webapp up --name buddi-agent-backend --resource-group my-group --runtime python:3.9
```

### Frontend Setup (Static Web Apps)
1. **Go to Azure Portal → Static Web Apps**
2. **Create new Static Web App**
3. **Connect GitHub or upload files**:
```bash
az staticwebapp upload \
  --name buddi-frontend \
  --app-location web
```

### Update Backend CORS
```python
allow_origins=["https://your-static-app.azurestaticapps.net"],
```

## Changes Required for All Cloud Deployments

### 1. Update Frontend API URL
File: `web/script.js`
```javascript
// Change this line:
const API_BASE_URL = 'http://localhost:8000/api';

// To your cloud backend URL:
const API_BASE_URL = 'https://your-backend-url.com/api';
```

### 2. Environment Variables
Create `.env` file with cloud-specific config:
```
OPENAI_API_KEY=your_key
GOOGLE_API_KEY=your_key
MODEL_NAME=deepseek-v3
API_PORT=8000
```

### 3. Security Update
In `backend/api.py`:
```python
# Remove wildcard CORS
# Use environment variables for secrets
import os
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 4. Database Connection
If using a database:
```python
# Use environment variables for connection strings
DB_URL = os.getenv("DATABASE_URL")
# Don't hardcode credentials!
```

## Docker Deployment (Recommended for Any Cloud)

Your existing Docker setup works:
```bash
# Build
docker build -t buddi-agent:latest .

# Run locally to test
docker-compose up

# Push to cloud registry
# AWS: docker push ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/buddi-agent:latest
# GCP: docker push gcr.io/PROJECT_ID/buddi-agent:latest
# Azure: docker push YOUR_REGISTRY.azurecr.io/buddi-agent:latest
```

## Cost Estimates (Approximate - 2024)

| Provider | Backend | Frontend | Monthly Cost |
|----------|---------|----------|--------------|
| **AWS** | EC2 t2.micro | S3 + CloudFront | $10-30 |
| **Google** | Cloud Run | Firebase | Free - $10 |
| **Azure** | App Service B1 | Static Web | $10-20 |

Free tier available on all!

## SSL/HTTPS Setup

All cloud providers offer free HTTPS:
- **AWS**: CloudFront or AWS Certificate Manager
- **Google**: Automatic with Cloud Run / Firebase
- **Azure**: Automatic with Static Web Apps

Important: Update Frontend to HTTPS:
```javascript
// Browser will block HTTP->HTTPS API calls
const API_BASE_URL = 'https://your-backend-url.com/api';
```

## Domain Setup

1. Buy domain (GoDaddy, Namecheap, etc.)
2. Point DNS to:
   - **AWS**: CloudFront distribution
   - **Google**: Cloud Run URL or Firebase
   - **Azure**: Static Web App URL
3. Set up custom domain in cloud provider console

## Monitoring & Logging

### AWS
- CloudWatch for logs and metrics
- Set up alarms for errors

### Google Cloud
- Cloud Logging and Cloud Monitoring
- Integrated with Cloud Run

### Azure
- Application Insights
- Azure Monitor

## Next Steps When Ready

1. **Pick a provider** (Google Cloud Cloud Run is easiest)
2. **Set up account** with free tier
3. **Prepare environment variables** (API keys, etc.)
4. **Update `web/script.js`** with your backend URL
5. **Deploy backend** (Docker recommended)
6. **Deploy frontend** (upload files or use GitHub)
7. **Test from the internet**
8. **Set up monitoring**
9. **Configure domain**

## Quick Commands Reference

```bash
# Test locally first
python3 web-server.py

# When ready for cloud...

# Build Docker image
docker build -t buddi-agent:latest .

# Push to AWS ECR
aws ecr get-login-password | docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.REGION.amazonaws.com
docker tag buddi-agent:latest ACCOUNT.dkr.ecr.REGION.amazonaws.com/buddi-agent:latest
docker push ACCOUNT.dkr.ecr.REGION.amazonaws.com/buddi-agent:latest

# Push to Google Container Registry
docker tag buddi-agent:latest gcr.io/PROJECT_ID/buddi-agent:latest
docker push gcr.io/PROJECT_ID/buddi-agent:latest

# Push to Azure Container Registry
docker tag buddi-agent:latest YOUR_REGISTRY.azurecr.io/buddi-agent:latest
docker push YOUR_REGISTRY.azurecr.io/buddi-agent:latest
```

## Security Reminders

- ✅ Use HTTPS in production
- ✅ Use environment variables for secrets
- ✅ Restrict CORS to your domain
- ✅ Set up rate limiting
- ✅ Enable API authentication if needed
- ✅ Use managed databases (don't run DB on same server)
- ✅ Enable logging and monitoring
- ✅ Regular backups
- ✅ Keep dependencies updated

## Getting Help

- AWS: https://docs.aws.amazon.com/
- Google Cloud: https://cloud.google.com/docs
- Azure: https://docs.microsoft.com/azure/

Good luck with your deployment! 🚀
