# Code Architecture Documentation

## Overview
This document provides a comprehensive technical overview of the LINE to Google Drive Bot architecture, design patterns, and code organization.

## System Architecture

### High-Level Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        External Services                        │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   LINE Platform │ Google Cloud    │     PostgreSQL Database     │
│                 │                 │                             │
│ • Messaging API │ • Drive API     │ • User tokens               │
│ • Webhooks      │ • OAuth 2.0     │ • Group memberships         │
│ • User profiles │ • Authentication│ • Session data              │
└─────────────────┴─────────────────┴─────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Flask Application                            │
├─────────────────────────────────────────────────────────────────┤
│  Web Routes           │  Webhook Handlers  │  Core Functions    │
│                       │                    │                    │
│ • Health check        │ • Image handler    │ • Authentication   │
│ • OAuth flow          │ • File handler     │ • File operations  │
│ • Auth callback       │ • Text commands    │ • Group management │
│ • Debug endpoints     │ • Error handling   │ • Database access  │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    In-Memory Fallback                          │
├─────────────────────────────────────────────────────────────────┤
│ • User tokens (dict)                                            │
│ • Group memberships (dict)                                      │
│ • Session storage                                               │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

#### **Flask Application Layer**
- HTTP request handling
- Route management
- Session management
- Error handling and logging

#### **LINE Integration Layer**
- Webhook event processing
- Message sending (reply/push)
- User profile management
- Group membership tracking

#### **Google Integration Layer**
- OAuth 2.0 authentication flow
- Google Drive API interactions
- Token management and refresh
- File upload operations

#### **Data Access Layer**
- PostgreSQL database operations
- In-memory storage fallback
- Data persistence and retrieval
- Migration handling

## Code Organization

### File Structure
```
app.py (1,267 lines)
├── Imports and Configuration (lines 1-45)
├── Database Functions (lines 46-245)
├── Google OAuth & Drive Functions (lines 246-385)
├── Authentication & Group Management (lines 386-465)
├── Web Routes (lines 466-790)
├── LINE Webhook Handlers (lines 791-1,235)
├── Utility Functions (lines 1,236-1,267)
└── Application Startup (lines 1,268+)
```

### Function Categories

#### **Database Operations**
```python
# Core database functions
init_db()                    # Initialize database schema
store_user_token()           # Store OAuth tokens
get_user_token()            # Retrieve OAuth tokens
delete_user_token()         # Remove OAuth tokens
track_group_member()        # Track group memberships
get_authenticated_group_members()  # Get group members
```

#### **Authentication & Authorization**
```python
# OAuth and permission functions
get_oauth_flow()            # Create OAuth flow
get_drive_service_for_user() # Get authenticated Drive service
is_user_authenticated()     # Check user auth status
send_auth_request()         # Send auth prompts
```

#### **File Operations**
```python
# File handling functions
upload_to_user_drive()      # Upload files to Drive
get_authenticated_users_in_context()  # Determine recipients
```

#### **Messaging**
```python
# Communication functions
safe_reply_message()        # Send messages with fallback
handle_image()              # Process image messages
handle_file()               # Process file messages
handle_text_message()       # Process text commands
```

## Design Patterns

### 1. **Fallback Pattern**
Used throughout the application for reliability:

```python
def get_user_token(user_id):
    if not DATABASE_URL:
        # Fallback to in-memory storage
        return user_tokens.get(user_id)
    
    try:
        # Primary: Database storage
        return fetch_from_database(user_id)
    except Exception:
        # Fallback: Return None
        return None
```

**Applied in**:
- Database vs in-memory storage
- Reply message vs push message
- PostgreSQL vs local development

### 2. **Context Manager Pattern**
For resource management:

```python
def database_operation():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Database operations
        conn.commit()
    except Exception as e:
        # Error handling
    finally:
        cur.close()
        conn.close()
```

### 3. **Factory Pattern**
For service creation:

```python
def get_drive_service_for_user(user_id):
    """Factory for creating authenticated Drive services"""
    token_info = get_user_token(user_id)
    if not token_info:
        return None
    
    # Handle token refresh
    if is_expired(token_info):
        token_info = refresh_token(token_info)
    
    return build('drive', 'v3', credentials=create_credentials(token_info))
```

### 4. **Strategy Pattern**
For different message handling contexts:

```python
def get_authenticated_users_in_context(event):
    source_type = event.source.type
    
    if source_type == 'user':
        # Private chat strategy
        return handle_private_chat(event)
    elif source_type in ['group', 'room']:
        # Group chat strategy
        return handle_group_chat(event)
    
    return []
```

## Data Flow Diagrams

### File Upload Flow
```
User sends file → LINE webhook → Bot receives event
                                        │
                                        ▼
                               Extract file content
                                        │
                                        ▼
                          Get authenticated users in context
                                        │
                                        ▼
                              Check sender authentication
                                        │
                                  ┌─────┴─────┐
                                  │           │
                                  ▼           ▼
                            Authenticated   Not Authenticated
                                  │           │
                                  │           ▼
                                  │    Send auth request
                                  │           │
                                  ▼           ▼
                            Upload to Drive  Continue with others
                                  │           │
                                  ▼           ▼
                            Send private     Check if any
                            notifications   authenticated users
                                  │           │
                                  ▼           ▼
                            Send group      Return if none
                            acknowledgment
```

### Authentication Flow
```
User clicks auth link → Browser detection → Show instructions or redirect
                                                    │
                                                    ▼
                                           Start OAuth flow
                                                    │
                                                    ▼
                                          Google authentication
                                                    │
                                                    ▼
                                           Receive auth code
                                                    │
                                                    ▼
                                          Exchange for tokens
                                                    │
                                                    ▼
                                           Store tokens in DB
                                                    │
                                                    ▼
                                          Send success message
```

## Error Handling Strategy

### Error Categories

#### 1. **External Service Errors**
```python
# LINE API errors
try:
    line_bot_api.reply_message(reply_token, message)
except LineBotApiError as e:
    if "Invalid reply token" in str(e):
        # Expected error - use fallback
        line_bot_api.push_message(user_id, message)
    else:
        # Unexpected error - log and investigate
        logger.error(f"LINE API error: {e}")
```

#### 2. **Google API Errors**
```python
# Drive API errors
try:
    service.files().create().execute()
except HttpError as e:
    if e.resp.status == 401:
        # Token expired - refresh and retry
        refresh_user_token(user_id)
    elif e.resp.status == 429:
        # Rate limit - implement backoff
        implement_backoff_retry()
    else:
        # Other error - log and fail gracefully
        logger.error(f"Drive API error: {e}")
```

#### 3. **Database Errors**
```python
# Database connectivity errors
try:
    conn = psycopg2.connect(DATABASE_URL)
except psycopg2.Error as e:
    logger.warning(f"Database unavailable: {e}")
    # Fallback to in-memory storage
    use_memory_storage()
```

### Error Recovery Mechanisms

#### **Graceful Degradation**
- Database down → Use in-memory storage
- Reply token expired → Use push message
- File upload failed → Notify user, request re-authentication

#### **Retry Logic**
- Token refresh on API failures
- Automatic reconnection for database
- Exponential backoff for rate limits (could be implemented)

#### **User Communication**
- Clear error messages sent privately
- Group notifications when appropriate
- Debug information available via special endpoints

## Security Architecture

### Authentication Security
```python
# OAuth 2.0 implementation
def get_oauth_flow():
    """Secure OAuth configuration"""
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": GOOGLE_CLIENT_ID,      # From environment
                "client_secret": GOOGLE_CLIENT_SECRET,  # From environment
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=['https://www.googleapis.com/auth/drive.file']  # Minimal scope
    )
```

### Data Protection
- **No sensitive data in logs**: Tokens masked in debug output
- **Environment variables only**: No hardcoded secrets
- **HTTPS enforcement**: All external communication encrypted
- **Database encryption**: Connection uses SSL
- **Token isolation**: Users can only access their own tokens

### Access Control
- **User isolation**: Drive access restricted to authenticated users
- **Group-based sharing**: Files only shared within group context
- **Permission validation**: Every operation checks user authentication
- **Token validation**: Automatic refresh and cleanup of invalid tokens

## Performance Considerations

### Database Optimization
```python
# Connection pooling (could be implemented)
from psycopg2 import pool

connection_pool = psycopg2.pool.SimpleConnectionPool(
    1, 20,  # min=1, max=20 connections
    DATABASE_URL
)

# Query optimization
def get_authenticated_group_members(group_id):
    # Single query with JOIN instead of multiple queries
    cur.execute("""
        SELECT DISTINCT gm.user_id 
        FROM group_members gm
        INNER JOIN user_tokens ut ON gm.user_id = ut.user_id
        WHERE gm.group_id = %s
    """, (group_id,))
```

### Memory Management
```python
# Streaming file uploads (current implementation)
def handle_image(event):
    content = line_bot_api.get_message_content(message_id)
    
    # Stream processing instead of loading entire file
    file_data = b''
    for chunk in content.iter_content():
        file_data += chunk
```

### Caching Strategy
- **In-memory fallback**: Reduces database load during outages
- **Token caching**: Avoids repeated database queries
- **Group membership tracking**: Cached in memory for performance

## Scalability Architecture

### Horizontal Scaling Considerations
```python
# Stateless design enables horizontal scaling
# - No server-side state except database
# - Each request independent
# - Database handles concurrent access

# Session management
app.secret_key = FLASK_SECRET_KEY  # Shared across instances
```

### Database Scaling
```sql
-- Indexes for performance
CREATE INDEX idx_user_tokens_user_id ON user_tokens(user_id);
CREATE INDEX idx_group_members_group_id ON group_members(group_id);
CREATE INDEX idx_group_members_user_id ON group_members(user_id);
```

### Load Balancing
- **Stateless application**: Can run multiple instances
- **Database connection pooling**: Manages concurrent connections
- **Rate limiting**: Google API quotas per user, not per instance

## Testing Strategy

### Unit Testing (not implemented but recommended)
```python
def test_user_authentication():
    # Mock database
    with patch('app.get_user_token') as mock_get_token:
        mock_get_token.return_value = {'access_token': 'test'}
        assert is_user_authenticated('test_user') == True

def test_group_member_tracking():
    # Test in-memory storage
    track_group_member('group1', 'user1', 'group')
    members = get_authenticated_group_members('group1')
    assert 'user1' in members
```

### Integration Testing
```python
def test_oauth_flow():
    # Test complete OAuth flow
    response = client.get('/auth?user_id=test')
    assert response.status_code == 302  # Redirect to Google

def test_webhook_handling():
    # Test LINE webhook processing
    webhook_data = {
        'events': [{
            'type': 'message',
            'message': {'type': 'image'},
            'source': {'type': 'user', 'userId': 'test'}
        }]
    }
    response = client.post('/callback', json=webhook_data)
    assert response.status_code == 200
```

## Monitoring and Observability

### Logging Strategy
```python
import logging

# Configure logging levels
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Key events to log
logger.info(f"User {user_id} authenticated successfully")
logger.warning(f"Reply token expired for user {user_id}")
logger.error(f"Database connection failed: {error}")
```

### Metrics to Track
- **Authentication success rate**: `successful_auths / total_auth_attempts`
- **File upload success rate**: `successful_uploads / total_upload_attempts`
- **Database availability**: `successful_db_connections / total_db_attempts`
- **API response times**: Average time for key operations
- **Memory usage**: Track in-memory storage growth

### Health Checks
```python
@app.route('/health')
def health_check():
    """Comprehensive health check"""
    status = {
        'database': check_database_connection(),
        'google_api': check_google_api_connectivity(),
        'line_api': check_line_api_connectivity(),
        'memory_usage': get_memory_usage()
    }
    return jsonify(status)
```

## Future Architecture Improvements

### 1. **Microservices Architecture**
```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  LINE Handler   │  │  Auth Service   │  │  File Service   │
│   Service       │  │                 │  │                 │
│ • Webhooks      │  │ • OAuth flow    │  │ • Drive uploads │
│ • Messaging     │  │ • Token mgmt    │  │ • File processing│
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

### 2. **Event-Driven Architecture**
```python
# Message queue for async processing
from celery import Celery

@celery.task
def upload_file_async(user_id, file_content, filename):
    """Async file upload to reduce webhook response time"""
    return upload_to_user_drive(user_id, file_content, filename)
```

### 3. **Database Optimization**
```sql
-- Partitioning for large tables
CREATE TABLE user_tokens_partitioned (
    user_id VARCHAR(255),
    -- ... other fields
) PARTITION BY HASH (user_id);

-- Read replicas for scaling
-- Connection routing based on operation type
```

### 4. **Caching Layer**
```python
# Redis for distributed caching
import redis

cache = redis.Redis(host='localhost', port=6379, db=0)

def get_cached_user_token(user_id):
    cached = cache.get(f"token:{user_id}")
    if cached:
        return json.loads(cached)
    
    token = get_user_token_from_db(user_id)
    if token:
        cache.setex(f"token:{user_id}", 3600, json.dumps(token))
    return token
```

---

**Last Updated**: July 2025
**Code Version**: 1.0.0
