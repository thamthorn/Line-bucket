# Environment Variables Template

# Copy this file to .env and fill in your actual values
# Do NOT commit the .env file to version control

# =============================================================================
# LINE Bot Configuration
# =============================================================================
# Get these from LINE Developers Console: https://developers.line.biz/
# 1. Create a new channel (Messaging API)
# 2. Get the Channel Access Token and Channel Secret

LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token_here
LINE_CHANNEL_SECRET=your_line_channel_secret_here

# =============================================================================
# Google OAuth Configuration  
# =============================================================================
# Get these from Google Cloud Console: https://console.cloud.google.com/
# 1. Create a new project or select existing
# 2. Enable Google Drive API
# 3. Create OAuth 2.0 Client ID credentials
# 4. Add your redirect URI: https://your-domain.com/oauth/callback

GOOGLE_CLIENT_ID=your_google_client_id.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret_here

# =============================================================================
# Database Configuration
# =============================================================================
# For production: PostgreSQL connection string
# Format: postgresql://username:password@host:port/database
# Leave empty for development (will use in-memory storage)

DATABASE_URL=postgresql://username:password@host:port/database

# =============================================================================
# Application Configuration
# =============================================================================
# Your application's public URL (for OAuth redirects)
# For local development: http://localhost:5000
# For production: https://your-app.onrender.com

DOMAIN=http://localhost:5000

# Or for Render (this is set automatically):
# RENDER_EXTERNAL_URL=https://your-app.onrender.com

# Flask secret key for session management
# Generate a random string: python -c "import secrets; print(secrets.token_hex(16))"
FLASK_SECRET_KEY=your_random_secret_key_here

# =============================================================================
# Optional Configuration
# =============================================================================
# Server port (usually auto-detected on deployment platforms)
PORT=5000
