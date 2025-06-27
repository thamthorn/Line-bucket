from flask import Flask, request, abort, redirect, session, url_for, render_template_string
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, ImageMessage, FileMessage, TextSendMessage, TemplateSendMessage, ButtonsTemplate, URIAction, PostbackAction

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
        return user_tokens.get(user_id)
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT * FROM user_tokens WHERE user_id = %s", (user_id,))
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if result:
            return {
                'access_token': result['access_token'],
                'refresh_token': result['refresh_token'],
                'expires_at': result['expires_at']
            }
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

def send_auth_request(user_id, reply_token):
    """Send authentication request with postback button"""
    buttons_template = ButtonsTemplate(
        title="Authentication Required",
        text="Tap to get your auth link",
        actions=[
            PostbackAction(
                label="🔐 Get My Auth Link",
                data=f"action=auth&user_id={user_id}"
            )
        ]
    )
    
    template_message = TemplateSendMessage(
        alt_text="Authentication required",
        template=buttons_template
    )
    
    line_bot_api.reply_message(reply_token, template_message)



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
        token_data = {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'expires_at': datetime.now() + timedelta(seconds=3600)  # Default 1 hour
        }
        store_user_token(user_id, token_data)
        
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


# Add postback handler
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    
    if data.startswith("action=auth") and f"user_id={user_id}" in data:
        auth_url = f"{DOMAIN}/auth?user_id={user_id}"
        
        auth_message = TextSendMessage(
            text=f"🔐 Your authentication link:\n{auth_url}\n\n"
                 f"Complete authentication in your browser, then return to LINE."
        )
        line_bot_api.reply_message(event.reply_token, auth_message)

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        user_id = event.source.user_id
        message_id = event.message.id
        
        # Check if user is authenticated
        if not is_user_authenticated(user_id):
            send_auth_request(user_id, event.reply_token)
            return
        
        content = line_bot_api.get_message_content(message_id)
        
        # Read the image content
        image_data = b''
        for chunk in content.iter_content():
            image_data += chunk
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"line_image_{timestamp}_{message_id}.jpg"
        
        # Upload to user's Google Drive
        result = upload_to_user_drive(user_id, image_data, filename, 'image/jpeg')
        
        if result:
            # Send confirmation message back to user
            reply_message = TextSendMessage(
                text=f"✅ Image saved to your Google Drive!\n📁 File: {result['name']}\n🔗 View: {result['url']}"
            )
            line_bot_api.reply_message(event.reply_token, reply_message)
            print(f"Image uploaded successfully for user {user_id}: {result['name']}")
        else:
            # Send error message - might need re-authentication
            reply_message = TextSendMessage(
                text="❌ Failed to save image. You may need to re-authenticate with Google Drive."
            )
            line_bot_api.reply_message(event.reply_token, reply_message)
            # Remove invalid token
            delete_user_token(user_id)
            
    except Exception as e:
        print(f"Error handling image: {e}")
        reply_message = TextSendMessage(text="❌ Error processing image")
        line_bot_api.reply_message(event.reply_token, reply_message)

@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    try:
        user_id = event.source.user_id
        message_id = event.message.id
        file_name = event.message.file_name
        
        # Check if user is authenticated
        if not is_user_authenticated(user_id):
            send_auth_request(user_id, event.reply_token)
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
        
        # Add timestamp to filename to avoid conflicts
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name_parts = file_name.rsplit('.', 1)
        if len(name_parts) == 2:
            timestamped_filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
        else:
            timestamped_filename = f"{file_name}_{timestamp}"
        
        # Upload to user's Google Drive
        result = upload_to_user_drive(user_id, file_data, timestamped_filename, mime_type)
        
        if result:
            # Send confirmation message back to user
            reply_message = TextSendMessage(
                text=f"✅ File saved to your Google Drive!\n📁 File: {result['name']}\n🔗 View: {result['url']}"
            )
            line_bot_api.reply_message(event.reply_token, reply_message)
            print(f"File uploaded successfully for user {user_id}: {result['name']}")
        else:
            # Send error message - might need re-authentication
            reply_message = TextSendMessage(
                text="❌ Failed to save file. You may need to re-authenticate with Google Drive."
            )
            line_bot_api.reply_message(event.reply_token, reply_message)
            # Remove invalid token
            delete_user_token(user_id)
            
    except Exception as e:
        print(f"Error handling file: {e}")
        reply_message = TextSendMessage(text="❌ Error processing file")
        line_bot_api.reply_message(event.reply_token, reply_message)

if __name__ == "__main__":
    # Get port from environment variable (Render sets this automatically)
    port = int(os.environ.get("PORT", 5000))
    # Bind to 0.0.0.0 to accept external connections
    app.run(host="0.0.0.0", port=port, debug=False)