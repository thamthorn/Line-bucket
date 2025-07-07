# Deployment Guide

## Overview
This guide covers deploying the LINE to Google Drive Bot to various platforms, with specific focus on Render.com (the recommended platform).

## Platform Requirements

### Minimum System Requirements
- **RAM**: 512MB (1GB recommended)
- **Storage**: 1GB
- **Python**: 3.8+ (3.13 recommended)
- **Database**: PostgreSQL 12+
- **Network**: HTTPS support required

### Supported Platforms
- ✅ **Render.com** (Recommended)
- ✅ **Heroku**
- ✅ **Railway**
- ✅ **DigitalOcean App Platform**
- ✅ **AWS Elastic Beanstalk**
- ✅ **Google Cloud Run**

## Pre-Deployment Checklist

### 1. LINE Bot Setup
- [ ] Create LINE Developers account
- [ ] Create Messaging API channel
- [ ] Get Channel Access Token
- [ ] Get Channel Secret
- [ ] Configure webhook URL (will be your deployed URL + `/callback`)

### 2. Google Cloud Setup
- [ ] Create Google Cloud Project
- [ ] Enable Google Drive API
- [ ] Create OAuth 2.0 credentials
- [ ] Add authorized redirect URIs
- [ ] Get Client ID and Client Secret

### 3. Database Setup
- [ ] Provision PostgreSQL database
- [ ] Get database connection URL
- [ ] Test connection (optional)

### 4. Environment Variables
- [ ] Prepare all required environment variables
- [ ] Verify no sensitive data in code
- [ ] Test locally with production-like settings

## Render.com Deployment (Recommended)

### Step 1: Prepare Repository
```bash
# Ensure all required files are present
ls -la
# Should show:
# - app.py
# - requirements.txt
# - runtime.txt
# - render.yaml (optional)
```

### Step 2: Create Render Account
1. Go to [render.com](https://render.com)
2. Sign up/login with GitHub/GitLab
3. Connect your repository

### Step 3: Create PostgreSQL Database
1. Click "New +" → "PostgreSQL"
2. Configure:
   - **Name**: `line-bot-database`
   - **Database**: `line_bot_db`
   - **User**: `line_bot_user`
   - **Region**: Choose closest to your users
   - **Plan**: Free tier for testing, paid for production
3. Wait for deployment
4. Copy the **External Database URL**

### Step 4: Create Web Service
1. Click "New +" → "Web Service"
2. Connect your repository
3. Configure:
   - **Name**: `line-bucket-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Plan**: Free tier for testing

### Step 5: Set Environment Variables
In the Render dashboard, add these environment variables:

```bash
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
LINE_CHANNEL_SECRET=your_line_channel_secret
GOOGLE_CLIENT_ID=your_google_client_id.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret
DATABASE_URL=postgresql://user:pass@host:port/database
FLASK_SECRET_KEY=your_random_secret_key_here
```

**Note**: `RENDER_EXTERNAL_URL` is automatically set by Render.

### Step 6: Deploy
1. Click "Create Web Service"
2. Wait for initial build (5-10 minutes)
3. Check logs for successful startup
4. Note your app URL: `https://your-app-name.onrender.com`

### Step 7: Configure LINE Webhook
1. Go to LINE Developers Console
2. Select your channel
3. Set webhook URL: `https://your-app-name.onrender.com/callback`
4. Enable webhooks
5. Test webhook with "Verify" button

## Alternative Platform Deployments

### Heroku

#### Procfile
```
web: gunicorn app:app
```

#### Environment Variables
Same as Render, plus:
```bash
PORT=5000  # Usually auto-set by Heroku
```

#### Deploy Commands
```bash
heroku create your-app-name
heroku addons:create heroku-postgresql:hobby-dev
heroku config:set LINE_CHANNEL_ACCESS_TOKEN=your_token
# ... set other environment variables
git push heroku main
```

### Railway

#### Railway.toml
```toml
[build]
command = "pip install -r requirements.txt"

[deploy]
startCommand = "gunicorn app:app"

[env]
PORT = "5000"
```

#### Deploy
1. Connect GitHub repository
2. Add environment variables in dashboard
3. Deploy automatically triggers

### Google Cloud Run

#### Dockerfile
```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
```

#### Deploy Commands
```bash
gcloud builds submit --tag gcr.io/PROJECT-ID/line-bot
gcloud run deploy --image gcr.io/PROJECT-ID/line-bot --platform managed
```

## Configuration Files

### requirements.txt
```txt
Flask==3.0.3
line-bot-sdk==3.12.0
google-auth==2.29.0
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0
google-api-python-client==2.130.0
psycopg2-binary==2.9.9
python-dotenv==1.0.1
gunicorn==21.2.0
```

### runtime.txt
```txt
python-3.13.0
```

### render.yaml (Optional)
```yaml
services:
  - type: web
    name: line-bucket-bot
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app
    envVars:
      - key: LINE_CHANNEL_ACCESS_TOKEN
        sync: false
      - key: LINE_CHANNEL_SECRET
        sync: false
      - key: GOOGLE_CLIENT_ID
        sync: false
      - key: GOOGLE_CLIENT_SECRET
        sync: false
      - key: DATABASE_URL
        fromDatabase:
          name: line-bot-database
          property: connectionString
      - key: FLASK_SECRET_KEY
        generateValue: true

databases:
  - name: line-bot-database
    databaseName: line_bot_db
    user: line_bot_user
```

## Post-Deployment Configuration

### 1. Test Webhook
```bash
curl -X POST "https://your-app.com/callback" \
  -H "Content-Type: application/json" \
  -H "X-Line-Signature: test" \
  -d '{"events":[]}'
```

### 2. Test OAuth Flow
1. Visit: `https://your-app.com/auth?user_id=test`
2. Should show authentication page or redirect

### 3. Test Database Connection
1. Visit: `https://your-app.com/debug/user/test`
2. Should show debug information

### 4. Configure Google OAuth
1. Go to Google Cloud Console
2. OAuth 2.0 Client IDs
3. Add redirect URI: `https://your-app.com/oauth/callback`

### 5. Test LINE Integration
1. Add bot as friend on LINE
2. Send test message
3. Check application logs

## Environment Variables Reference

### Required
| Variable | Example | Description |
|----------|---------|-------------|
| `LINE_CHANNEL_ACCESS_TOKEN` | `abcd1234...` | LINE Bot access token |
| `LINE_CHANNEL_SECRET` | `efgh5678...` | LINE Bot channel secret |
| `GOOGLE_CLIENT_ID` | `123.googleusercontent.com` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | `ijkl9012...` | Google OAuth client secret |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db` | PostgreSQL connection string |

### Optional
| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_SECRET_KEY` | Auto-generated | Flask session secret |
| `PORT` | `5000` | Server port (auto-set on most platforms) |
| `RENDER_EXTERNAL_URL` | Platform URL | Your app's public URL |

## SSL/HTTPS Configuration

### Automatic (Recommended Platforms)
- **Render**: Automatic SSL with custom domains
- **Heroku**: Automatic SSL
- **Railway**: Automatic SSL

### Manual Setup
If using custom domain:
1. Configure DNS to point to your platform
2. Add domain in platform dashboard
3. Enable SSL certificate
4. Update LINE webhook URL

## Database Migration

### From Development to Production
```python
# The app automatically creates tables on startup
# No manual migration needed for initial deployment

# For schema changes, add to init_db() function:
def init_db():
    # existing table creation...
    
    # Add new columns/tables here
    cur.execute("""
        ALTER TABLE user_tokens 
        ADD COLUMN IF NOT EXISTS new_field TEXT;
    """)
```

## Scaling Considerations

### Free Tier Limitations
- **Render Free**: Sleeps after 15 minutes inactivity
- **Heroku Free**: Discontinued
- **Railway Free**: 500 hours/month

### Production Scaling
- Use paid plans for 24/7 availability
- Consider database connection pooling
- Monitor memory usage
- Set up health checks

### Performance Optimization
```python
# Add to app.py for production
import os

# Enable production optimizations
if os.environ.get('RENDER'):
    app.config['JSON_SORT_KEYS'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
```

## Monitoring & Logging

### Application Logs
```bash
# Render
render logs --service=your-service-id

# Heroku
heroku logs --tail --app=your-app-name

# Railway
railway logs
```

### Health Monitoring
Set up monitoring for:
- Application uptime
- Database connectivity
- Google API quota usage
- LINE API response times

### Error Tracking
Consider integrating:
- Sentry for error tracking
- Application performance monitoring
- Database query monitoring

## Backup & Recovery

### Database Backups
- **Render**: Automatic backups on paid plans
- **Heroku**: `heroku pg:backups`
- **Manual**: Regular `pg_dump` exports

### Application Backup
- Source code in Git repository
- Environment variables documented
- Database schema in version control

## Security Checklist

### Pre-Production
- [ ] All secrets in environment variables
- [ ] No hardcoded tokens in code
- [ ] HTTPS enforced
- [ ] Database connections encrypted
- [ ] Error messages don't leak sensitive data

### Production
- [ ] Regular security updates
- [ ] Monitor for suspicious activity
- [ ] Rotate secrets periodically
- [ ] Audit database access

## Troubleshooting Deployment Issues

### Common Build Errors
```bash
# Python version mismatch
# Fix: Update runtime.txt to match requirements.txt

# Missing dependencies
# Fix: Update requirements.txt with exact versions

# Environment variable missing
# Fix: Check all required variables are set
```

### Common Runtime Errors
```bash
# Database connection failed
# Fix: Verify DATABASE_URL format and accessibility

# LINE webhook verification failed
# Fix: Check X-Line-Signature header handling

# Google OAuth redirect mismatch
# Fix: Update Google Cloud Console redirect URIs
```

### Debug Commands
```bash
# Check environment variables
env | grep LINE

# Test database connection
python -c "import psycopg2; print('DB OK')"

# Check application logs
tail -f /var/log/app.log
```

---

**Last Updated**: July 2025
