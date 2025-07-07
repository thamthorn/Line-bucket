# LINE to Google Drive Bot

A LINE bot that automatically saves images and files sent in group chats to authenticated users' Google Drive accounts. The bot supports both group and private chat contexts with secure OAuth authentication.

## 🌟 Features

- **Automatic File Saving**: Images and files sent in LINE groups are automatically saved to all authenticated members' Google Drive
- **Secure Authentication**: OAuth 2.0 integration with Google Drive
- **Group Management**: Tracks group memberships and handles multiple authenticated users per group
- **Smart Browser Detection**: Handles LINE's in-app browser limitations for OAuth flows
- **Error Handling**: Robust error handling with fallback messaging when reply tokens expire
- **Database Support**: PostgreSQL for production with in-memory fallback for development
- **Private Messaging**: Authentication links and file notifications sent privately to users

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   LINE Platform │    │   Flask App     │    │  Google Drive   │
│                 │◄──►│                 │◄──►│    API          │
│  • Webhooks     │    │  • OAuth Flow   │    │  • File Upload  │
│  • Messaging    │    │  • File Handler │    │  • Auth Token   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │   PostgreSQL    │
                       │                 │
                       │  • User Tokens  │
                       │  • Group Members│
                       └─────────────────┘
```

## 📋 Prerequisites

### Required Accounts & Services
1. **LINE Developers Account**
   - Create a LINE Bot channel
   - Get Channel Access Token and Channel Secret

2. **Google Cloud Platform Account**
   - Create a project with Google Drive API enabled
   - Set up OAuth 2.0 credentials
   - Get Client ID and Client Secret

3. **PostgreSQL Database** (Production)
   - Render PostgreSQL or any PostgreSQL provider
   - Database URL with connection string

4. **Deployment Platform** (Optional)
   - Render, Heroku, or similar platform for hosting

### Required Environment Variables
```bash
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
LINE_CHANNEL_SECRET=your_line_channel_secret
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
DATABASE_URL=postgresql://user:password@host:port/database
RENDER_EXTERNAL_URL=https://your-app.onrender.com
FLASK_SECRET_KEY=your_flask_secret_key
```

## 🚀 Installation & Setup

### 1. Clone and Install Dependencies
```bash
git clone <repository-url>
cd line_bucket_image
pip install -r requirements.txt
```

### 2. Environment Configuration
Create a `.env` file:
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

### 3. Database Setup
The app automatically creates required tables on startup:
- `user_tokens`: Stores Google OAuth tokens
- `group_members`: Tracks group memberships

### 4. Google OAuth Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create/select a project
3. Enable Google Drive API
4. Create OAuth 2.0 credentials
5. Add your domain to authorized redirect URIs:
   - `https://your-domain.com/oauth/callback`

### 5. LINE Bot Setup
1. Go to [LINE Developers Console](https://developers.line.biz/)
2. Create a new channel (Messaging API)
3. Set webhook URL: `https://your-domain.com/callback`
4. Enable webhooks and disable auto-reply

### 6. Deploy
```bash
# For local development
python app.py

# For production (using gunicorn)
gunicorn app:app
```

## 🔧 Configuration

### Environment Variables Details

| Variable | Description | Example |
|----------|-------------|---------|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Bot access token | `abc123...` |
| `LINE_CHANNEL_SECRET` | LINE Bot channel secret | `def456...` |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | `123-abc.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | `ghi789...` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:5432/db` |
| `RENDER_EXTERNAL_URL` | Your app's public URL | `https://myapp.onrender.com` |
| `FLASK_SECRET_KEY` | Flask session secret | `random-secret-key` |

### Database Configuration
- **Production**: Uses PostgreSQL via `DATABASE_URL`
- **Development**: Falls back to in-memory storage if `DATABASE_URL` not set

## 📖 Usage Guide

### For End Users

#### First Time Setup
1. **Join a LINE group** with the bot
2. **Send any image or file**
3. **Receive authentication link** privately
4. **Complete Google OAuth** in external browser
5. **Return to LINE** - files will now auto-save

#### Daily Usage
- **Send images/files** in group → Automatically saved to all authenticated users' Google Drive
- **Check status**: Send `/status` command
- **Get help**: Send `/help` command

### Bot Commands
- `/status` or `status` - Check authentication status
- `/help` or `help` - Show help message
- `/auth` or `auth` - Alias for status check

### Group Behavior
- **File shared with ALL authenticated group members**
- **Private notifications** sent to each user with Google Drive links
- **Group acknowledgment** shows how many drives received the file
- **Non-authenticated users** receive private authentication prompts

## 🔧 API Reference

### Core Functions

#### Authentication Functions
```python
def is_user_authenticated(user_id: str) -> bool
def get_user_token(user_id: str) -> dict
def store_user_token(user_id: str, token_data: dict) -> None
def delete_user_token(user_id: str) -> None
```

#### Group Management
```python
def track_group_member(group_id: str, user_id: str, group_type: str) -> None
def get_authenticated_group_members(group_id: str) -> List[str]
def get_authenticated_users_in_context(event) -> List[str]
```

#### File Operations
```python
def upload_to_user_drive(user_id: str, file_content: bytes, filename: str, mime_type: str) -> dict
def get_drive_service_for_user(user_id: str) -> googleapiclient.discovery.Resource
```

#### Messaging
```python
def send_auth_request(user_id: str, reply_token: str, source_type: str) -> None
def safe_reply_message(event, message, fallback_user_id: str) -> None
```

### Webhook Handlers
- `handle_image(event)` - Processes image messages
- `handle_file(event)` - Processes file messages  
- `handle_text_message(event)` - Processes text commands

### Web Routes
- `GET /` - Health check
- `GET /auth?user_id=<id>` - Start OAuth flow
- `GET /start-auth?user_id=<id>` - Direct OAuth (bypasses browser detection)
- `GET /oauth/callback` - OAuth callback handler
- `POST /callback` - LINE webhook endpoint
- `GET /debug/user/<user_id>` - Debug user authentication status

## 🛠️ Development Guide

### Project Structure
```
line_bucket_image/
├── app.py              # Main application file
├── requirements.txt    # Python dependencies
├── runtime.txt        # Python version (for Render)
├── render.yaml        # Render deployment config
├── .env.example       # Environment variables template
├── README.md          # This documentation
├── docs/              # Additional documentation
│   ├── API.md         # API documentation
│   ├── DEPLOYMENT.md  # Deployment guide
│   └── TROUBLESHOOTING.md # Common issues
└── tests/             # Test files (if any)
```

### Adding New Features

#### Adding New Commands
1. Add command handler in `handle_text_message()`
2. Update help text in `/help` command
3. Test in both group and private contexts

#### Adding New File Types
1. Update MIME type detection in `handle_file()`
2. Test upload and download functionality
3. Update user documentation

#### Database Schema Changes
1. Update `init_db()` function
2. Add migration logic if needed
3. Test with both PostgreSQL and in-memory storage

### Testing
```bash
# Test authentication flow
curl -X GET "https://your-app.com/debug/user/test_user_id"

# Test webhook (requires valid LINE signature)
curl -X POST "https://your-app.com/callback" \
  -H "X-Line-Signature: valid_signature" \
  -d '{"events": [...]}'
```

## 🔒 Security Considerations

### Data Protection
- **OAuth tokens** stored securely in database
- **No plaintext passwords** stored
- **Google tokens** automatically refreshed
- **Database connections** use environment variables

### Access Control
- **Private authentication** links sent only to requesting user
- **Group isolation** - users only see their own files
- **Token validation** before each Google API call

### Error Handling
- **Reply token expiration** handled gracefully
- **Failed uploads** don't crash the bot
- **Invalid tokens** automatically cleaned up

## 📊 Monitoring & Logging

### Log Levels
- **INFO**: Successful operations, user actions
- **DEBUG**: Detailed flow information, token status
- **ERROR**: Failed operations, exceptions

### Key Metrics to Monitor
- Authentication success rate
- File upload success rate
- Reply token failure rate
- Database connection health
- Memory usage (for in-memory fallback)

## 🚨 Troubleshooting

See [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common issues and solutions.

### Common Issues
1. **"Invalid reply token" errors** - Normal, handled by fallback system
2. **Authentication failures** - Check Google OAuth setup
3. **Files not saving** - Verify Google Drive API permissions
4. **Database connection issues** - Check DATABASE_URL format

## 📄 License

[Add your license information here]

## 🤝 Contributing

[Add contribution guidelines here]

## 📞 Support

For issues and questions:
1. Check [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
2. Review server logs
3. Test with `/debug/user/<user_id>` endpoint
4. Contact development team

---

**Last Updated**: July 2025
**Version**: 1.0.0
