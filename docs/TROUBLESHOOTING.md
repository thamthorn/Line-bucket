# Troubleshooting Guide

## Common Issues and Solutions

This guide covers the most common issues you might encounter when developing, deploying, or maintaining the LINE to Google Drive Bot.

## Quick Diagnostic Commands

### Check Bot Status
```bash
# Health check
curl https://your-app.com/

# Debug user authentication
curl https://your-app.com/debug/user/USER_ID

# Check application logs
render logs --service=your-service
```

### Environment Check
```bash
# Verify environment variables
echo $LINE_CHANNEL_ACCESS_TOKEN
echo $GOOGLE_CLIENT_ID
echo $DATABASE_URL
```

## LINE Bot Issues

### Issue: "Invalid reply token" Errors
**Symptoms**: 
- Error messages in logs: `LineBotApiError: Invalid reply token`
- Bot appears to work but crashes occasionally

**Cause**: 
- Reply tokens expire quickly (seconds to minutes)
- Tokens can only be used once
- Network delays or processing time

**Solution**: 
✅ **Already implemented** in the codebase with fallback system:
```python
try:
    line_bot_api.reply_message(reply_token, message)
except Exception as e:
    print(f"Reply token failed: {e}")
    line_bot_api.push_message(user_id, message)
```

**Expected Behavior**: Bot continues working, messages delivered via push instead of reply.

### Issue: LINE Webhook Not Receiving Events
**Symptoms**:
- No webhook events in logs
- Bot doesn't respond to messages

**Diagnosis**:
```bash
# Check webhook configuration
curl -X POST "https://your-app.com/callback" \
  -H "X-Line-Signature: test" \
  -d '{"events":[]}'
```

**Solutions**:
1. **Verify webhook URL** in LINE Developers Console
   - Should be: `https://your-app.com/callback`
   - Must be HTTPS (not HTTP)

2. **Check webhook status**
   - LINE Console → Your Channel → Webhook settings
   - Should be "Enabled"

3. **Verify SSL certificate**
   - Webhook URL must have valid SSL
   - Test with: `curl -I https://your-app.com`

4. **Check LINE channel settings**
   - Auto-reply should be disabled
   - Webhooks should be enabled

### Issue: Bot Not Responding in Groups
**Symptoms**:
- Bot works in private chat
- No response in group chats

**Solutions**:
1. **Add bot to group properly**
   - Invite bot via QR code or link
   - Bot should appear in member list

2. **Check group permissions**
   - Bot needs message reading permissions
   - Some corporate LINE accounts have restrictions

3. **Verify group tracking**
   ```python
   # Check if group is being tracked
   group_id = "YOUR_GROUP_ID"
   members = get_authenticated_group_members(group_id)
   print(f"Group members: {members}")
   ```

## Google OAuth Issues

### Issue: "Browser not supported" Error
**Symptoms**:
- Users see Google OAuth error
- Authentication fails in LINE app browser

**Cause**: 
LINE in-app browser doesn't support full OAuth flow

**Solution**: 
✅ **Already implemented** - Browser detection with fallback instructions:
- Users get instructions to copy link to external browser
- Direct `/start-auth` endpoint bypasses detection

**User Instructions**:
1. Copy authentication link
2. Open in Chrome/Safari
3. Complete authentication
4. Return to LINE

### Issue: Google OAuth Redirect Mismatch
**Symptoms**:
- OAuth error: "redirect_uri_mismatch"
- Authentication fails after Google login

**Solutions**:
1. **Check Google Cloud Console**
   - Go to APIs & Services → Credentials
   - Edit your OAuth 2.0 Client ID
   - Add redirect URI: `https://your-app.com/oauth/callback`

2. **Verify environment variables**
   ```bash
   echo $RENDER_EXTERNAL_URL
   # Should match your actual domain
   ```

3. **Check multiple domains**
   - Add both production and staging URLs
   - Include both with and without trailing slash

### Issue: Google Drive API Quota Exceeded
**Symptoms**:
- File uploads fail with quota error
- Error: "User Rate Limit Exceeded"

**Solutions**:
1. **Check quotas** in Google Cloud Console
   - APIs & Services → Quotas
   - Drive API limits

2. **Implement retry logic** (not currently implemented):
   ```python
   import time
   from googleapiclient.errors import HttpError
   
   def upload_with_retry(service, file_metadata, media, max_retries=3):
       for attempt in range(max_retries):
           try:
               return service.files().create(
                   body=file_metadata,
                   media_body=media
               ).execute()
           except HttpError as e:
               if e.resp.status == 429:  # Rate limit
                   time.sleep(2 ** attempt)  # Exponential backoff
               else:
                   raise
   ```

3. **Request quota increase**
   - Google Cloud Console → IAM & Admin → Quotas
   - Request increase for Drive API

## Database Issues

### Issue: Database Connection Failed
**Symptoms**:
- Error: "could not connect to server"
- App falls back to in-memory storage

**Diagnosis**:
```python
import psycopg2
try:
    conn = psycopg2.connect(DATABASE_URL)
    print("Database connection successful")
    conn.close()
except Exception as e:
    print(f"Database error: {e}")
```

**Solutions**:
1. **Check DATABASE_URL format**
   ```bash
   # Correct format:
   postgresql://username:password@host:port/database
   
   # Common mistakes:
   postgres://...  # Should be postgresql://
   Missing port number
   Incorrect username/password
   ```

2. **Verify database exists**
   - Check database provider dashboard
   - Ensure database is running
   - Verify connection limits

3. **Network connectivity**
   - Some platforms require database allowlisting
   - Check firewall rules

### Issue: In-Memory Storage Warning
**Symptoms**:
- Log message: "Warning: DATABASE_URL not set, using in-memory storage"
- User data lost on restart

**Expected**: This is normal for development/testing

**For Production**:
1. Set DATABASE_URL environment variable
2. Restart application
3. Verify database connection

### Issue: Database Schema Errors
**Symptoms**:
- Error: "relation does not exist"
- Tables not created automatically

**Solutions**:
1. **Check init_db() function execution**
   ```python
   # Add logging to init_db()
   print("Initializing database...")
   # ... rest of function
   print("Database initialized successfully")
   ```

2. **Manual table creation**:
   ```sql
   -- Connect to your database and run:
   CREATE TABLE IF NOT EXISTS user_tokens (
       user_id VARCHAR(255) PRIMARY KEY,
       access_token TEXT NOT NULL,
       refresh_token TEXT,
       expires_at TIMESTAMP,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```

## Authentication Issues

### Issue: Users Can't Authenticate
**Symptoms**:
- Authentication link doesn't work
- OAuth flow fails

**Diagnosis Steps**:
1. **Test auth URL manually**
   ```bash
   curl "https://your-app.com/auth?user_id=test"
   ```

2. **Check Google credentials**
   ```bash
   echo $GOOGLE_CLIENT_ID
   echo $GOOGLE_CLIENT_SECRET
   ```

3. **Verify redirect URI**
   - Google Cloud Console → Credentials
   - Should include: `https://your-app.com/oauth/callback`

**Common Solutions**:
1. **Environment variables missing**
   - Verify all Google OAuth variables are set
   - Check for trailing spaces or extra characters

2. **Google Project configuration**
   - Enable Google Drive API
   - Configure OAuth consent screen
   - Add test users if in testing mode

### Issue: Token Refresh Failures
**Symptoms**:
- Users need to re-authenticate frequently
- Error: "Token has been expired or revoked"

**Solutions**:
1. **Check token storage**:
   ```python
   # Debug token status
   token = get_user_token("USER_ID")
   print(f"Token expires at: {token.get('expires_at')}")
   print(f"Has refresh token: {'refresh_token' in token}")
   ```

2. **Verify refresh logic**:
   - Check `get_drive_service_for_user()` function
   - Ensure refresh tokens are stored
   - Add logging to refresh attempts

## File Upload Issues

### Issue: Files Not Saving to Drive
**Symptoms**:
- Bot says "saved" but no file in Drive
- Upload errors in logs

**Diagnosis**:
```python
# Test Drive API directly
service = get_drive_service_for_user("USER_ID")
if service:
    files = service.files().list().execute()
    print(f"User has access to {len(files.get('files', []))} files")
else:
    print("No Drive service - authentication issue")
```

**Solutions**:
1. **Check permissions**
   - Verify Drive API scopes
   - User may need to re-authenticate

2. **File size limits**
   - Google Drive: 5TB max per file
   - LINE: Check size limits for downloads

3. **MIME type issues**
   - Verify correct MIME type detection
   - Some file types may be blocked

### Issue: Large File Upload Failures
**Symptoms**:
- Small files work, large files fail
- Timeout errors

**Solutions**:
1. **Increase timeout limits**:
   ```python
   # In upload function
   media = MediaIoBaseUpload(
       io.BytesIO(file_content),
       mimetype=mime_type,
       resumable=True,
       chunksize=1024*1024  # 1MB chunks
   )
   ```

2. **Implement chunked uploads**
3. **Add progress monitoring**

## Deployment Issues

### Issue: Application Won't Start
**Symptoms**:
- Build succeeds but app crashes on startup
- "Application error" in browser

**Common Causes & Solutions**:

1. **Missing environment variables**
   ```bash
   # Check all required variables are set
   render env list
   ```

2. **Port binding issues**
   ```python
   # Ensure correct port binding
   port = int(os.environ.get("PORT", 5000))
   app.run(host="0.0.0.0", port=port)
   ```

3. **Dependencies issues**
   ```bash
   # Check requirements.txt
   pip install -r requirements.txt
   ```

### Issue: Render Service Sleeping
**Symptoms**:
- Bot works initially then stops responding
- "Service unavailable" errors

**Cause**: Free tier services sleep after 15 minutes of inactivity

**Solutions**:
1. **Upgrade to paid plan** (recommended for production)
2. **Implement keep-alive ping** (not recommended):
   ```python
   # External service to ping every 10 minutes
   # Not recommended as it wastes resources
   ```

### Issue: Build Failures
**Common Build Errors**:

1. **Python version mismatch**
   ```bash
   # Error: "Could not find a version that satisfies the requirement"
   # Fix: Check runtime.txt matches your dependencies
   ```

2. **Missing system dependencies**
   ```bash
   # For psycopg2 issues, use:
   psycopg2-binary==2.9.9
   # Instead of:
   psycopg2==2.9.9
   ```

## Performance Issues

### Issue: Slow Response Times
**Symptoms**:
- Bot takes long to respond
- Timeout errors

**Diagnosis**:
```python
import time

def timed_function(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        print(f"{func.__name__} took {end - start:.2f} seconds")
        return result
    return wrapper

# Apply to key functions
@timed_function
def upload_to_user_drive(user_id, file_content, filename, mime_type):
    # ... existing code
```

**Solutions**:
1. **Database query optimization**
2. **Async file uploads** (advanced)
3. **Caching frequently accessed data**

### Issue: Memory Usage High
**Symptoms**:
- Application crashes with memory errors
- Slow performance over time

**Solutions**:
1. **Stream file uploads instead of loading into memory**:
   ```python
   # Instead of loading full file into memory
   content = line_bot_api.get_message_content(message_id)
   file_data = b''
   for chunk in content.iter_content():
       file_data += chunk
   
   # Use streaming upload (advanced implementation needed)
   ```

2. **Clear variables after use**
3. **Monitor memory usage**

## Security Issues

### Issue: Exposed Sensitive Data
**Symptoms**:
- API keys in logs
- Database credentials visible

**Prevention**:
1. **Never log sensitive data**:
   ```python
   # Bad
   print(f"Token: {access_token}")
   
   # Good
   print(f"Token: {'*' * len(access_token)}")
   ```

2. **Use environment variables only**
3. **Regular security audits**

## Getting Help

### Debug Information to Collect
When reporting issues, include:

1. **Error messages** (full stack trace)
2. **Environment details**:
   ```bash
   # Platform (Render, Heroku, etc.)
   # Python version
   # App URL
   # Timestamp of issue
   ```

3. **Steps to reproduce**
4. **Expected vs actual behavior**

### Log Analysis
```bash
# Look for these key log patterns:
grep "ERROR" app.log
grep "Invalid reply token" app.log
grep "Database" app.log
grep "OAuth" app.log
```

### Testing Commands
```bash
# Test webhook
curl -X POST "https://your-app.com/callback" \
  -H "Content-Type: application/json" \
  -d '{"events":[]}'

# Test authentication
curl "https://your-app.com/auth?user_id=test"

# Test health
curl "https://your-app.com/"
```

## Emergency Procedures

### Service Down
1. **Check platform status** (Render, Heroku status pages)
2. **Review recent deployments**
3. **Check application logs**
4. **Rollback if necessary**

### Data Loss
1. **Check database backups**
2. **Verify in-memory storage warnings**
3. **Contact users about re-authentication if needed**

### Security Breach
1. **Rotate all secrets immediately**
2. **Check access logs**
3. **Invalidate all user tokens**
4. **Review code for vulnerabilities**

---

**Last Updated**: July 2025

Need help? Check the logs first, then try the diagnostic commands in this guide.
