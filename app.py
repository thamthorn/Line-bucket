from flask import Flask, request, abort, redirect, session, url_for, render_template_string
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, ImageMessage, FileMessage, TextMessage, TextSendMessage, TemplateSendMessage, ButtonsTemplate, URIAction

import os
import io
import json
import secrets
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Load environment variables from .env (for local use)
load_dotenv()

# Load from environment
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(16))

# Your app's domain (Render will provide this automatically)
DOMAIN = os.environ.get("RENDER_EXTERNAL_URL", os.environ.get("DOMAIN", "http://localhost:5000"))

# Database URL for PostgreSQL (Render provides this)
DATABASE_URL = os.environ.get("DATABASE_URL")

# Check if keys are set
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET not set")

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    raise ValueError("Google OAuth credentials not set")

# Initialize LINE SDK
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# Database functions
def init_db():
    """Initialize database tables"""
    if not DATABASE_URL:
        print("Warning: DATABASE_URL not set, using in-memory storage")
        return
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Create table for storing user tokens
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_tokens (
                user_id VARCHAR(255) PRIMARY KEY,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create table for tracking group/room memberships
        cur.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                group_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                group_type VARCHAR(20) NOT NULL,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, user_id)
            )
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("Database initialized successfully")
        
    except Exception as e:
        print(f"Error initializing database: {e}")

def store_user_token(user_id, token_data):
    """Store user token in database"""
    if not DATABASE_URL:
        # Fallback to in-memory storage
        user_tokens[user_id] = token_data
        return
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO user_tokens (user_id, access_token, refresh_token, expires_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) 
            DO UPDATE SET 
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                updated_at = EXCLUDED.updated_at
        """, (
            user_id,
            token_data['access_token'],
            token_data.get('refresh_token'),
            token_data.get('expires_at'),
            datetime.now()
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error storing user token: {e}")

def get_user_token(user_id):
    """Get user token from database"""
    if not DATABASE_URL:
        # Fallback to in-memory storage
        token = user_tokens.get(user_id)
        print(f"DEBUG: In-memory token for {user_id}: {'Found' if token else 'Not found'}")
        return token
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT * FROM user_tokens WHERE user_id = %s", (user_id,))
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if result:
            print(f"DEBUG: Database token for {user_id}: Found")
            return {
                'access_token': result['access_token'],
                'refresh_token': result['refresh_token'],
                'expires_at': result['expires_at']
            }
        else:
            print(f"DEBUG: Database token for {user_id}: Not found")
        return None
        
    except Exception as e:
        print(f"Error getting user token: {e}")
        return None

def delete_user_token(user_id):
    """Delete user token from database"""
    if not DATABASE_URL:
        # Fallback to in-memory storage
        if user_id in user_tokens:
            del user_tokens[user_id]
        return
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("DELETE FROM user_tokens WHERE user_id = %s", (user_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error deleting user token: {e}")

def track_group_member(group_id, user_id, group_type):
    """Track a user's membership in a group/room"""
    if not DATABASE_URL:
        return  # Skip tracking if no database
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO group_members (group_id, user_id, group_type, last_active)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (group_id, user_id) 
            DO UPDATE SET 
                last_active = EXCLUDED.last_active
        """, (group_id, user_id, group_type, datetime.now()))
        
        conn.commit()
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error tracking group member: {e}")

def get_authenticated_group_members(group_id):
    """Get all authenticated users in a specific group/room"""
    if not DATABASE_URL:
        return []  # Return empty if no database
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Get all users in the group who are also authenticated
        cur.execute("""
            SELECT DISTINCT gm.user_id 
            FROM group_members gm
            INNER JOIN user_tokens ut ON gm.user_id = ut.user_id
            WHERE gm.group_id = %s
            AND gm.last_active > %s
        """, (group_id, datetime.now() - timedelta(days=30)))  # Active within 30 days
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return [row[0] for row in results]
        
    except Exception as e:
        print(f"Error getting authenticated group members: {e}")
        return []

# In-memory storage fallback (for development or when database is not available)
user_tokens = {}

# Google OAuth 2.0 configuration
SCOPES = ['https://www.googleapis.com/auth/drive.file']
REDIRECT_URI = f"{DOMAIN}/oauth/callback"

def get_oauth_flow():
    """Create OAuth flow object"""
    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES
    )
    flow.redirect_uri = REDIRECT_URI
    return flow

def get_drive_service_for_user(user_id):
    """Get Google Drive service for a specific user"""
    try:
        token_info = get_user_token(user_id)
        if not token_info:
            return None
            
        # Check if token is expired
        if token_info.get('expires_at') and datetime.now() > token_info['expires_at']:
            # Try to refresh the token
            creds = Credentials(
                token=token_info['access_token'],
                refresh_token=token_info.get('refresh_token'),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=GOOGLE_CLIENT_ID,
                client_secret=GOOGLE_CLIENT_SECRET
            )
            
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Update stored token
                new_token_info = {
                    'access_token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'expires_at': datetime.now() + timedelta(seconds=3600)
                }
                store_user_token(user_id, new_token_info)
                token_info = new_token_info
            else:
                return None
        
        creds = Credentials(token=token_info['access_token'])
        service = build('drive', 'v3', credentials=creds)
        return service
        
    except Exception as e:
        print(f"Error getting Drive service for user {user_id}: {e}")
        return None

def upload_to_user_drive(user_id, file_content, filename, mime_type='application/octet-stream'):
    """Upload file to user's Google Drive"""
    try:
        service = get_drive_service_for_user(user_id)
        if not service:
            return None
        
        # Create file metadata
        file_metadata = {
            'name': filename,
            'parents': ['root']  # Save to root folder, or create a specific folder
        }
        
        # Create media upload object
        media = MediaIoBaseUpload(
            io.BytesIO(file_content),
            mimetype=mime_type,
            resumable=True
        )
        
        # Upload file
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink'
        ).execute()
        
        print(f"File uploaded successfully to user {user_id}: {file.get('name')}")
        
        return {
            'id': file.get('id'),
            'name': file.get('name'),
            'url': file.get('webViewLink')
        }
        
    except Exception as e:
        print(f"Error uploading to user {user_id} Google Drive: {e}")
        return None

def is_user_authenticated(user_id):
    """Check if user has valid Google Drive access"""
    return get_user_token(user_id) is not None

def get_group_members(group_id):
    """Get list of authenticated users in a group - simplified version"""
    # In a real implementation, you would track group memberships
    # For now, we'll use a simple approach where we check all users
    # This is a placeholder - LINE Bot API doesn't directly provide group member lists
    # You might need to track this separately when users join/leave groups
    return []

def get_authenticated_users_in_context(event):
    """Get all authenticated users who should receive the file"""
    source_type = event.source.type
    sender_id = event.source.user_id
    
    if source_type == 'user':
        # Private chat - only save to sender
        return [sender_id] if is_user_authenticated(sender_id) else []
    
    elif source_type in ['group', 'room']:
        # Group/room chat - save to all authenticated users in the group
        group_id = event.source.group_id if source_type == 'group' else event.source.room_id
        
        # Track the current sender in this group
        track_group_member(group_id, sender_id, source_type)
        
        # Get all authenticated members of this group
        authenticated_members = get_authenticated_group_members(group_id)
        
        # IMPORTANT: Ensure the sender is included if they're authenticated
        # This fixes the issue where a newly authenticated user isn't in the group_members table yet
        if is_user_authenticated(sender_id) and sender_id not in authenticated_members:
            authenticated_members.append(sender_id)
        
        return authenticated_members
    
    return []

# def send_auth_request(user_id, reply_token):
#     """Send authentication request to user"""
#     auth_url = f"{DOMAIN}/auth?user_id={user_id}"
    
#     buttons_template = ButtonsTemplate(
#         title="Google Drive Authentication",  # 28 characters
#         text="Please authenticate to save.",  # 30 characters
#         actions=[URIAction(label="Connect to Drive", uri=auth_url)]
#     )
    
#     template_message = TemplateSendMessage(
#         alt_text="Please authenticate with Google Drive",
#         template=buttons_template
#     )
    
#     line_bot_api.reply_message(reply_token, template_message)

def send_auth_request(user_id, reply_token, source_type=None):
    """Send authentication request to user with browser-friendly link"""
    auth_url = f"{DOMAIN}/auth?user_id={user_id}"
    
    # Send instructions with the link privately to the user
    instruction_message = TextSendMessage(
        text=f"🔐 To save files to Google Drive, please authenticate:\n\n"
             f"👆 Tap this link and follow the instructions:\n"
             f"{auth_url}\n\n"
             f"📱 If Google shows 'browser not supported':\n"
             f"• Copy the link above\n"
             f"• Open it in Chrome/Safari instead\n"
             f"• Complete authentication\n"
             f"• Return to LINE when done"
    )
    
    # Send private message to user (not visible in group chat)
    line_bot_api.push_message(user_id, instruction_message)
    
    # Send a brief acknowledgment in the group chat (if it's a group)
    if source_type == 'group' or source_type == 'room':
        group_reply = TextSendMessage(
            text="📨 Authentication link sent to you privately. Please check your personal messages."
        )
        line_bot_api.reply_message(reply_token, group_reply)



# Initialize database on startup
init_db()

# Web routes for OAuth flow
@app.route("/")
def health_check():
    return "LINE Bot with Google OAuth is running on Render!", 200

@app.route("/auth")
def auth():
    """Start OAuth flow with smart browser detection"""
    user_id = request.args.get('user_id')
    if not user_id:
        return "Missing user ID", 400
    
    # Check if this is coming from LINE browser or similar webview
    user_agent = request.headers.get('User-Agent', '')
    is_webview_browser = any(indicator in user_agent for indicator in [
        'Line', 'NAVER', 'WebView', 'wv)', 'Instagram', 'FBAV', 'FB_IAB'
    ])
    
    if is_webview_browser:
        # Show instructions to open in external browser
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Open in External Browser</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <meta charset="UTF-8">
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .container { 
                    background: white;
                    padding: 30px;
                    border-radius: 15px;
                    max-width: 420px;
                    width: 100%;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                    text-align: center;
                }
                .icon {
                    font-size: 48px;
                    margin-bottom: 20px;
                }
                .title {
                    color: #333;
                    font-size: 24px;
                    font-weight: 600;
                    margin-bottom: 15px;
                }
                .warning { 
                    color: #e74c3c; 
                    font-size: 16px; 
                    margin-bottom: 25px;
                    background: #fff5f5;
                    padding: 15px;
                    border-radius: 8px;
                    border-left: 4px solid #e74c3c;
                }
                .instructions { 
                    color: #555; 
                    margin-bottom: 25px;
                    text-align: left;
                    line-height: 1.6;
                }
                .step {
                    display: flex;
                    align-items: center;
                    margin: 12px 0;
                    padding: 12px;
                    background: #f8f9ff;
                    border-radius: 8px;
                    border-left: 3px solid #667eea;
                }
                .step-number {
                    background: #667eea;
                    color: white;
                    width: 24px;
                    height: 24px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    font-size: 12px;
                    margin-right: 12px;
                    flex-shrink: 0;
                }
                .url-box {
                    background: #f8f9fa;
                    padding: 15px;
                    border-radius: 8px;
                    border: 2px dashed #667eea;
                    margin: 20px 0;
                    word-break: break-all;
                    font-family: 'Courier New', monospace;
                    font-size: 14px;
                    color: #333;
                    position: relative;
                }
                .copy-btn {
                    background: linear-gradient(135deg, #667eea, #764ba2);
                    color: white;
                    padding: 12px 24px;
                    border: none;
                    border-radius: 25px;
                    cursor: pointer;
                    font-size: 16px;
                    font-weight: 600;
                    margin: 15px 0;
                    transition: all 0.3s ease;
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
                }
                .copy-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
                }
                .copy-btn:active {
                    transform: translateY(0);
                }
                .footer {
                    margin-top: 25px;
                    padding-top: 20px;
                    border-top: 1px solid #eee;
                    color: #888;
                    font-size: 14px;
                }
                .success-message {
                    display: none;
                    background: #d4edda;
                    color: #155724;
                    padding: 10px;
                    border-radius: 5px;
                    margin: 10px 0;
                    border: 1px solid #c3e6cb;
                }
                @media (max-width: 480px) {
                    .container {
                        padding: 20px;
                        margin: 10px;
                    }
                    .title {
                        font-size: 20px;
                    }
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">🔐</div>
                <div class="title">Google Drive Authentication</div>
                
                <div class="warning">
                    ⚠️ In-app browser detected! Google OAuth requires a regular browser.
                </div>
                
                <div class="instructions">
                    <div class="step">
                        <div class="step-number">1</div>
                        <div>Copy the authentication link below</div>
                    </div>
                    
                    <div class="url-box" id="auth-url">{{ request.url_root }}start-auth?user_id={{ user_id }}</div>
                    
                    <button class="copy-btn" onclick="copyToClipboard()">
                        📋 Copy Authentication Link
                    </button>
                    
                    <div class="success-message" id="success-msg">
                        ✅ Link copied! Now open your browser and paste it.
                    </div>
                    
                    <div class="step">
                        <div class="step-number">2</div>
                        <div>Open Chrome, Safari, or your default browser</div>
                    </div>
                    
                    <div class="step">
                        <div class="step-number">3</div>
                        <div>Paste and visit the copied link</div>
                    </div>
                    
                    <div class="step">
                        <div class="step-number">4</div>
                        <div>Complete Google authentication</div>
                    </div>
                    
                    <div class="step">
                        <div class="step-number">5</div>
                        <div>Return to LINE when authentication is complete</div>
                    </div>
                </div>
                
                <div class="footer">
                    💡 This ensures secure authentication with Google Drive
                </div>
            </div>
            
            <script>
                async function copyToClipboard() {
                    const url = document.getElementById('auth-url').textContent;
                    const button = document.querySelector('.copy-btn');
                    const successMsg = document.getElementById('success-msg');
                    
                    try {
                        // Try modern clipboard API first
                        if (navigator.clipboard && window.isSecureContext) {
                            await navigator.clipboard.writeText(url);
                            showSuccess();
                        } else {
                            // Fallback for older browsers or non-HTTPS
                            const textArea = document.createElement('textarea');
                            textArea.value = url;
                            textArea.style.position = 'fixed';
                            textArea.style.left = '-999999px';
                            textArea.style.top = '-999999px';
                            document.body.appendChild(textArea);
                            textArea.focus();
                            textArea.select();
                            
                            const successful = document.execCommand('copy');
                            document.body.removeChild(textArea);
                            
                            if (successful) {
                                showSuccess();
                            } else {
                                throw new Error('Copy command failed');
                            }
                        }
                    } catch (err) {
                        // If all else fails, select the text
                        const range = document.createRange();
                        range.selectNode(document.getElementById('auth-url'));
                        window.getSelection().removeAllRanges();
                        window.getSelection().addRange(range);
                        
                        button.innerHTML = '👆 Text selected - Copy manually';
                        button.style.background = '#f39c12';
                        
                        setTimeout(() => {
                            button.innerHTML = '📋 Copy Authentication Link';
                            button.style.background = 'linear-gradient(135deg, #667eea, #764ba2)';
                        }, 3000);
                    }
                    
                    function showSuccess() {
                        successMsg.style.display = 'block';
                        button.innerHTML = '✅ Copied! Open your browser';
                        button.style.background = '#27ae60';
                        
                        setTimeout(() => {
                            button.innerHTML = '📋 Copy Authentication Link';
                            button.style.background = 'linear-gradient(135deg, #667eea, #764ba2)';
                            successMsg.style.display = 'none';
                        }, 4000);
                    }
                }
                
                // Auto-select text on mobile for easier copying
                document.getElementById('auth-url').addEventListener('click', function() {
                    if (window.getSelection) {
                        const range = document.createRange();
                        range.selectNode(this);
                        window.getSelection().removeAllRanges();
                        window.getSelection().addRange(range);
                    }
                });
            </script>
        </body>
        </html>
        """, user_id=user_id)
    
    # If not a webview browser, proceed with normal OAuth flow
    # Store user_id in session
    session['user_id'] = user_id
    
    # Create OAuth flow
    flow = get_oauth_flow()
    
    # Generate authorization URL
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    # Store state in session
    session['state'] = state
    
    return redirect(authorization_url)


# Add this new route for direct OAuth start (for external browsers)
@app.route("/start-auth")
def start_auth():
    """Direct OAuth start - bypasses browser detection"""
    user_id = request.args.get('user_id')
    if not user_id:
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Error</title></head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h2>❌ Error</h2>
            <p>Missing user ID parameter</p>
        </body>
        </html>
        """, 400
    
    # Store user_id in session
    session['user_id'] = user_id
    
    try:
        # Create OAuth flow
        flow = get_oauth_flow()
        
        # Generate authorization URL
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        
        # Store state in session
        session['state'] = state
        
        return redirect(authorization_url)
        
    except Exception as e:
        print(f"Error in start_auth: {e}")
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Authentication Error</title></head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h2>❌ Authentication Error</h2>
            <p>Failed to start authentication process</p>
            <p>Please try again or contact support</p>
            <p><small>Error: {str(e)}</small></p>
        </body>
        </html>
        """, 500


@app.route("/oauth/callback")
def oauth_callback():
    """Handle OAuth callback"""
    user_id = session.get('user_id')
    state = session.get('state')
    
    if not user_id or not state:
        return "Invalid session", 400
    
    try:
        # Create OAuth flow
        flow = get_oauth_flow()
        flow.fetch_token(authorization_response=request.url)
        
        # Get credentials
        credentials = flow.credentials
        
        # Store user tokens in database
        # Google access tokens typically expire in 1 hour from issue time
        # If the credentials object has expiry info, use it, otherwise default to 1 hour
        expiry_time = credentials.expiry if hasattr(credentials, 'expiry') and credentials.expiry else (datetime.now() + timedelta(seconds=3600))
        
        token_data = {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'expires_at': expiry_time
        }
        print(f"DEBUG: Storing token for user {user_id}")
        store_user_token(user_id, token_data)
        print(f"DEBUG: Token stored, verification: {get_user_token(user_id) is not None}")
        
        # Clear session
        session.clear()
        
        # Send success message to user via LINE
        success_message = TextSendMessage(
            text="✅ Google Drive connected successfully! You can now send files and images, and they'll be saved to your Google Drive."
        )
        
        line_bot_api.push_message(user_id, success_message)
        
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Success</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                .success { color: #4CAF50; font-size: 24px; margin: 20px 0; }
                .info { color: #666; margin: 20px 0; }
            </style>
        </head>
        <body>
            <div class="success">✅ Authentication Successful!</div>
            <div class="info">Your Google Drive has been connected successfully.</div>
            <div class="info">You can now close this window and return to LINE.</div>
        </body>
        </html>
        """)
        
    except Exception as e:
        print(f"OAuth callback error: {e}")
        return f"Authentication failed: {str(e)}", 400

# LINE webhook handler
@app.route("/callback", methods=["POST"])
def callback():
    # Get X-Line-Signature header
    signature = request.headers["X-Line-Signature"]

    # Get request body as text
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        user_id = event.source.user_id
        message_id = event.message.id
        source_type = event.source.type  # 'user', 'group', or 'room'
        
        # Debug logging
        print(f"Image received from user {user_id} in {source_type}")
        print(f"User authenticated: {is_user_authenticated(user_id)}")
        
        # Get all authenticated users who should receive this file
        target_users = get_authenticated_users_in_context(event)
        print(f"Target users: {target_users}")
        
        # If no one is authenticated, send auth request to sender
        if not target_users:
            print(f"No target users found, sending auth request to {user_id}")
            send_auth_request(user_id, event.reply_token, source_type)
            return
        
        content = line_bot_api.get_message_content(message_id)
        
        # Read the image content
        image_data = b''
        for chunk in content.iter_content():
            image_data += chunk
        
        # Generate filename with timestamp and sender info
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Get sender's display name if possible (for better file naming)
        try:
            sender_profile = line_bot_api.get_profile(user_id)
            sender_name = sender_profile.display_name.replace(' ', '_')[:20]  # Limit length and remove spaces
        except:
            sender_name = "user"
        
        filename = f"line_image_{timestamp}_{sender_name}_{message_id}.jpg"
        
        # Upload to each authenticated user's Google Drive
        successful_uploads = []
        failed_uploads = []
        
        for target_user_id in target_users:
            result = upload_to_user_drive(target_user_id, image_data, filename, 'image/jpeg')
            if result:
                successful_uploads.append((target_user_id, result))
                print(f"Image uploaded successfully for user {target_user_id}: {result['name']}")
            else:
                failed_uploads.append(target_user_id)
                print(f"Failed to upload image for user {target_user_id}")
        
        # Send notifications
        if successful_uploads:
            # Notify each user privately about their copy
            for target_user_id, result in successful_uploads:
                if target_user_id == user_id:
                    # Sender gets detailed info
                    private_message = TextSendMessage(
                        text=f"✅ Your image saved to your Google Drive!\n📁 File: {result['name']}\n🔗 View: {result['url']}"
                    )
                else:
                    # Other group members get notification
                    private_message = TextSendMessage(
                        text=f"📸 Image from {sender_name} saved to your Google Drive!\n📁 File: {result['name']}\n🔗 View: {result['url']}"
                    )
                line_bot_api.push_message(target_user_id, private_message)
            
            # Send group acknowledgment
            if source_type == 'group' or source_type == 'room':
                group_reply = TextSendMessage(
                    text=f"✅ Image saved to {len(successful_uploads)} Google Drive(s)!"
                )
                line_bot_api.reply_message(event.reply_token, group_reply)
            else:
                # In private chat, just reply normally
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ Image saved to your Google Drive!"))
        
        # Handle failed uploads
        if failed_uploads:
            for failed_user_id in failed_uploads:
                error_message = TextSendMessage(
                    text="❌ Failed to save image to your Google Drive. You may need to re-authenticate."
                )
                line_bot_api.push_message(failed_user_id, error_message)
                # Remove invalid token
                delete_user_token(failed_user_id)
            
    except Exception as e:
        print(f"Error handling image: {e}")
        # Send error to sender
        error_message = TextSendMessage(text="❌ Error processing image")
        line_bot_api.push_message(user_id, error_message)
        
        # Send brief error in group/room (if applicable)
        if source_type == 'group' or source_type == 'room':
            group_reply = TextSendMessage(text="❌ Error processing image")
            line_bot_api.reply_message(event.reply_token, group_reply)
        else:
            line_bot_api.reply_message(event.reply_token, error_message)

@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    try:
        user_id = event.source.user_id
        message_id = event.message.id
        file_name = event.message.file_name
        source_type = event.source.type  # 'user', 'group', or 'room'
        
        # Get all authenticated users who should receive this file
        target_users = get_authenticated_users_in_context(event)
        
        # If no one is authenticated, send auth request to sender
        if not target_users:
            send_auth_request(user_id, event.reply_token, source_type)
            return
        
        content = line_bot_api.get_message_content(message_id)
        
        # Read the file content
        file_data = b''
        for chunk in content.iter_content():
            file_data += chunk
        
        # Determine MIME type based on file extension
        mime_type = 'application/octet-stream'
        if file_name.lower().endswith('.pdf'):
            mime_type = 'application/pdf'
        elif file_name.lower().endswith(('.doc', '.docx')):
            mime_type = 'application/msword'
        elif file_name.lower().endswith('.txt'):
            mime_type = 'text/plain'
        elif file_name.lower().endswith(('.xlsx', '.xls')):
            mime_type = 'application/vnd.ms-excel'
        elif file_name.lower().endswith(('.pptx', '.ppt')):
            mime_type = 'application/vnd.ms-powerpoint'
        
        # Get sender's display name if possible (for better file naming)
        try:
            sender_profile = line_bot_api.get_profile(user_id)
            sender_name = sender_profile.display_name.replace(' ', '_')[:20]  # Limit length and remove spaces
        except:
            sender_name = "user"
        
        # Add timestamp and sender to filename to avoid conflicts
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name_parts = file_name.rsplit('.', 1)
        if len(name_parts) == 2:
            timestamped_filename = f"{name_parts[0]}_{timestamp}_{sender_name}.{name_parts[1]}"
        else:
            timestamped_filename = f"{file_name}_{timestamp}_{sender_name}"
        
        # Upload to each authenticated user's Google Drive
        successful_uploads = []
        failed_uploads = []
        
        for target_user_id in target_users:
            result = upload_to_user_drive(target_user_id, file_data, timestamped_filename, mime_type)
            if result:
                successful_uploads.append((target_user_id, result))
                print(f"File uploaded successfully for user {target_user_id}: {result['name']}")
            else:
                failed_uploads.append(target_user_id)
                print(f"Failed to upload file for user {target_user_id}")
        
        # Send notifications
        if successful_uploads:
            # Notify each user privately about their copy
            for target_user_id, result in successful_uploads:
                if target_user_id == user_id:
                    # Sender gets detailed info
                    private_message = TextSendMessage(
                        text=f"✅ Your file saved to your Google Drive!\n📁 File: {result['name']}\n🔗 View: {result['url']}"
                    )
                else:
                    # Other group members get notification
                    private_message = TextSendMessage(
                        text=f"📄 File from {sender_name} saved to your Google Drive!\n📁 File: {result['name']}\n🔗 View: {result['url']}"
                    )
                line_bot_api.push_message(target_user_id, private_message)
            
            # Send group acknowledgment
            if source_type == 'group' or source_type == 'room':
                group_reply = TextSendMessage(
                    text=f"✅ File saved to {len(successful_uploads)} Google Drive(s)!"
                )
                line_bot_api.reply_message(event.reply_token, group_reply)
            else:
                # In private chat, just reply normally
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ File saved to your Google Drive!"))
        
        # Handle failed uploads
        if failed_uploads:
            for failed_user_id in failed_uploads:
                error_message = TextSendMessage(
                    text="❌ Failed to save file to your Google Drive. You may need to re-authenticate."
                )
                line_bot_api.push_message(failed_user_id, error_message)
                # Remove invalid token
                delete_user_token(failed_user_id)
            
    except Exception as e:
        print(f"Error handling file: {e}")
        # Send error to sender
        error_message = TextSendMessage(text="❌ Error processing file")
        line_bot_api.push_message(user_id, error_message)
        
        # Send brief error in group/room (if applicable)
        if source_type == 'group' or source_type == 'room':
            group_reply = TextSendMessage(text="❌ Error processing file")
            line_bot_api.reply_message(event.reply_token, group_reply)
        else:
            line_bot_api.reply_message(event.reply_token, error_message)

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    """Handle text messages for commands"""
    try:
        user_id = event.source.user_id
        text = event.message.text.lower().strip()
        source_type = event.source.type
        
        # Track group membership when user interacts
        if source_type in ['group', 'room']:
            group_id = event.source.group_id if source_type == 'group' else event.source.room_id
            track_group_member(group_id, user_id, source_type)
        
        if text in ['/status', 'status', '/auth', 'auth']:
            # Check authentication status
            if is_user_authenticated(user_id):
                status_message = TextSendMessage(
                    text="✅ You are authenticated with Google Drive!\nYou can send images and files to save them to your Google Drive."
                )
            else:
                status_message = TextSendMessage(
                    text="❌ You are not authenticated with Google Drive.\nSend an image or file to start the authentication process."
                )
            
            # Send status privately if in group/room
            if source_type == 'group' or source_type == 'room':
                line_bot_api.push_message(user_id, status_message)
                group_reply = TextSendMessage(text="📊 Status sent to you privately.")
                line_bot_api.reply_message(event.reply_token, group_reply)
            else:
                line_bot_api.reply_message(event.reply_token, status_message)
                
        elif text in ['/help', 'help', '/commands', 'commands']:
            help_message = TextSendMessage(
                text="🤖 LINE to Google Drive Bot Help\n\n"
                     "📸 Send images → Saved to ALL authenticated members' Google Drive\n"
                     "📄 Send files → Saved to ALL authenticated members' Google Drive\n"
                     "/status → Check authentication status\n"
                     "/help → Show this help message\n\n"
                     "🔒 First time users need to authenticate with Google Drive.\n"
                     "👥 In groups: Files are shared with all authenticated members!"
            )
            
            # Send help privately if in group/room
            if source_type == 'group' or source_type == 'room':
                line_bot_api.push_message(user_id, help_message)
                group_reply = TextSendMessage(text="📖 Help sent to you privately.")
                line_bot_api.reply_message(event.reply_token, group_reply)
            else:
                line_bot_api.reply_message(event.reply_token, help_message)
                
        # Don't respond to other text messages to avoid spam
        
    except Exception as e:
        print(f"Error handling text message: {e}")

@app.route("/debug/user/<user_id>")
def debug_user_auth(user_id):
    """Debug route to check user authentication status"""
    token = get_user_token(user_id)
    is_auth = is_user_authenticated(user_id)
    
    return f"""
    <h2>Debug Info for User: {user_id}</h2>
    <p><strong>Has Token:</strong> {token is not None}</p>
    <p><strong>Is Authenticated:</strong> {is_auth}</p>
    <p><strong>Token Details:</strong> {token if token else 'None'}</p>
    <p><strong>Current Time:</strong> {datetime.now()}</p>
    """

if __name__ == "__main__":
    # Get port from environment variable (Render sets this automatically)
    port = int(os.environ.get("PORT", 5000))
    # Bind to 0.0.0.0 to accept external connections
    app.run(host="0.0.0.0", port=port, debug=False)