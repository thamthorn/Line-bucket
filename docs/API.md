# API Documentation

## Overview
This document provides detailed information about the LINE to Google Drive Bot's internal API structure, functions, and endpoints.

## Database Schema

### Table: `user_tokens`
Stores Google OAuth tokens for authenticated users.

```sql
CREATE TABLE user_tokens (
    user_id VARCHAR(255) PRIMARY KEY,      -- LINE user ID
    access_token TEXT NOT NULL,            -- Google OAuth access token
    refresh_token TEXT,                    -- Google OAuth refresh token
    expires_at TIMESTAMP,                  -- Token expiration time
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: `group_members`
Tracks user membership in LINE groups/rooms.

```sql
CREATE TABLE group_members (
    group_id VARCHAR(255) NOT NULL,        -- LINE group/room ID
    user_id VARCHAR(255) NOT NULL,         -- LINE user ID
    group_type VARCHAR(20) NOT NULL,       -- 'group' or 'room'
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (group_id, user_id)
);
```

## Core Functions

### Authentication Functions

#### `is_user_authenticated(user_id: str) -> bool`
**Purpose**: Check if a user has valid Google Drive access.

**Parameters**:
- `user_id`: LINE user identifier

**Returns**: 
- `True` if user has valid token
- `False` if no token or invalid token

**Example**:
```python
if is_user_authenticated("U123456789"):
    print("User is authenticated")
```

#### `get_user_token(user_id: str) -> dict | None`
**Purpose**: Retrieve stored OAuth token for a user.

**Parameters**:
- `user_id`: LINE user identifier

**Returns**: 
- Dictionary with token data or `None`
```python
{
    'access_token': 'ya29.a0...',
    'refresh_token': '1//04...',
    'expires_at': datetime(2025, 7, 8, 12, 0, 0)
}
```

#### `store_user_token(user_id: str, token_data: dict) -> None`
**Purpose**: Store or update user's OAuth token.

**Parameters**:
- `user_id`: LINE user identifier
- `token_data`: Token information dictionary

**Example**:
```python
token_data = {
    'access_token': 'ya29.a0...',
    'refresh_token': '1//04...',
    'expires_at': datetime.now() + timedelta(hours=1)
}
store_user_token("U123456789", token_data)
```

#### `delete_user_token(user_id: str) -> None`
**Purpose**: Remove user's stored token (logout).

**Parameters**:
- `user_id`: LINE user identifier

### Group Management Functions

#### `track_group_member(group_id: str, user_id: str, group_type: str) -> None`
**Purpose**: Record user membership in a group/room.

**Parameters**:
- `group_id`: LINE group/room identifier
- `user_id`: LINE user identifier  
- `group_type`: Either 'group' or 'room'

**Storage**: 
- Database: `group_members` table
- Fallback: `group_members_memory` dictionary

#### `get_authenticated_group_members(group_id: str) -> List[str]`
**Purpose**: Get all authenticated users in a specific group.

**Parameters**:
- `group_id`: LINE group/room identifier

**Returns**: List of authenticated user IDs

**Example**:
```python
members = get_authenticated_group_members("C987654321")
# Returns: ["U123456789", "U987654321"]
```

#### `get_authenticated_users_in_context(event) -> List[str]`
**Purpose**: Determine which users should receive a file based on context.

**Parameters**:
- `event`: LINE webhook event object

**Logic**:
- **Private chat**: Returns sender if authenticated
- **Group/room**: Returns all authenticated group members
- **Auto-tracking**: Adds sender to group membership

**Returns**: List of user IDs who should receive the file

### File Operations

#### `upload_to_user_drive(user_id: str, file_content: bytes, filename: str, mime_type: str) -> dict | None`
**Purpose**: Upload file to user's Google Drive.

**Parameters**:
- `user_id`: LINE user identifier
- `file_content`: Binary file data
- `filename`: Desired filename
- `mime_type`: MIME type (e.g., 'image/jpeg')

**Returns**:
```python
{
    'id': '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
    'name': 'uploaded_file.jpg',
    'url': 'https://drive.google.com/file/d/1Bxi.../view'
}
```

**Error Handling**: Returns `None` on failure

#### `get_drive_service_for_user(user_id: str) -> googleapiclient.discovery.Resource | None`
**Purpose**: Get authenticated Google Drive service for user.

**Parameters**:
- `user_id`: LINE user identifier

**Features**:
- Automatic token refresh
- Token expiration handling
- Error logging

**Returns**: Google Drive API service object or `None`

### OAuth Functions

#### `get_oauth_flow() -> Flow`
**Purpose**: Create Google OAuth flow object.

**Returns**: Configured `google_auth_oauthlib.flow.Flow` object

**Configuration**:
- Scopes: `['https://www.googleapis.com/auth/drive.file']`
- Redirect URI: `{DOMAIN}/oauth/callback`

### Messaging Functions

#### `send_auth_request(user_id: str, reply_token: str, source_type: str) -> None`
**Purpose**: Send authentication request to user.

**Parameters**:
- `user_id`: LINE user identifier
- `reply_token`: LINE reply token
- `source_type`: 'user', 'group', or 'room'

**Behavior**:
- Sends private message with auth link
- Sends group acknowledgment if in group context
- Handles reply token errors gracefully

#### `safe_reply_message(event, message, fallback_user_id: str) -> None`
**Purpose**: Safely send reply with fallback to push message.

**Parameters**:
- `event`: LINE webhook event
- `message`: `TextSendMessage` object
- `fallback_user_id`: User ID for fallback (optional)

**Error Handling**:
- Tries reply message first
- Falls back to push message on failure
- Logs errors for debugging

## Webhook Event Handlers

### `handle_image(event: MessageEvent)`
**Purpose**: Process image messages.

**Flow**:
1. Extract user and source information
2. Get authenticated users in context
3. Send auth request if sender not authenticated
4. Download image content from LINE
5. Upload to each authenticated user's Drive
6. Send private notifications with Drive links
7. Send group acknowledgment

**Error Handling**:
- Failed uploads trigger re-authentication
- Reply token errors use push message fallback

### `handle_file(event: MessageEvent)`
**Purpose**: Process file messages.

**Similar to `handle_image`** but:
- Handles various MIME types
- Preserves original filename with timestamp
- Supports larger file sizes

### `handle_text_message(event: MessageEvent)`
**Purpose**: Process text commands.

**Commands**:
- `/status`, `status`, `/auth`, `auth`: Check authentication
- `/help`, `help`, `/commands`, `commands`: Show help
- Ignores other text to avoid spam

**Features**:
- Private responses in group contexts
- Group membership tracking
- Error-tolerant messaging

## Web Endpoints

### `GET /`
**Purpose**: Health check endpoint.

**Response**: "LINE Bot with Google OAuth is running on Render!"

### `GET /auth?user_id=<user_id>`
**Purpose**: Start OAuth authentication flow.

**Parameters**:
- `user_id`: LINE user identifier (query param)

**Features**:
- Browser detection for LINE in-app browser
- Fallback instructions for unsupported browsers
- Session management

### `GET /start-auth?user_id=<user_id>`
**Purpose**: Direct OAuth start (bypasses browser detection).

**Use Case**: When user copies link to external browser

### `GET /oauth/callback`
**Purpose**: Handle OAuth callback from Google.

**Process**:
1. Validate session state
2. Exchange code for tokens
3. Store tokens in database
4. Send success message to user
5. Return success page

### `POST /callback`
**Purpose**: LINE webhook endpoint.

**Headers Required**:
- `X-Line-Signature`: LINE signature for verification

**Process**:
1. Verify LINE signature
2. Parse webhook events
3. Route to appropriate handlers

### `GET /debug/user/<user_id>`
**Purpose**: Debug endpoint for user authentication status.

**Response**: HTML page with:
- Token existence
- Authentication status
- Token details
- Current timestamp

## Error Handling Patterns

### Reply Token Errors
**Problem**: LINE reply tokens expire quickly and can only be used once.

**Solution**: 
```python
try:
    line_bot_api.reply_message(reply_token, message)
except Exception as e:
    print(f"Reply token failed: {e}")
    line_bot_api.push_message(user_id, message)
```

### Google API Errors
**Common Issues**:
- Expired tokens → Auto-refresh
- Invalid tokens → Request re-authentication
- Rate limits → Exponential backoff (not implemented)

### Database Connection Errors
**Fallback Strategy**:
- PostgreSQL primary storage
- In-memory storage fallback
- Graceful degradation

## Environment Configuration

### Required Variables
```bash
LINE_CHANNEL_ACCESS_TOKEN=your_token
LINE_CHANNEL_SECRET=your_secret
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
DATABASE_URL=postgresql://...
RENDER_EXTERNAL_URL=https://your-app.com
FLASK_SECRET_KEY=your_secret_key
```

### Optional Variables
```bash
PORT=5000  # Server port (auto-detected on Render)
```

## Rate Limits & Quotas

### LINE API Limits
- **Push messages**: 500/month for free tier
- **Reply messages**: Unlimited within event context
- **Webhook timeout**: 30 seconds

### Google Drive API Limits
- **Requests**: 1,000/100 seconds per user
- **File uploads**: 5TB per file
- **Storage**: User's Drive quota

## Security Considerations

### Token Security
- Tokens stored in database, not in code
- Automatic token refresh
- Token deletion on logout

### Access Control
- User isolation (no cross-user access)
- Group-based file sharing
- Private authentication flows

### Data Privacy
- No file content stored permanently
- Only metadata logged
- User consent required for Drive access

## Monitoring & Debugging

### Log Messages
- **Authentication**: Token status, OAuth flows
- **File uploads**: Success/failure with details
- **Group tracking**: Membership changes
- **Errors**: Full exception traces

### Debug Endpoints
- `/debug/user/<user_id>`: User authentication status
- Health check logs in application startup

### Performance Metrics
- File upload duration
- Database query performance
- Memory usage (in-memory fallback)

---

**Last Updated**: July 2025
