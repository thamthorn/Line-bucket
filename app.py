from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, ImageMessage, FileMessage, TextSendMessage

import os
import io
import json
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.service_account import Credentials

# Load environment variables from .env (for local use)
load_dotenv()

# Load from environment
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

# Check if keys are set
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET not set")

if not GOOGLE_DRIVE_FOLDER_ID or not GOOGLE_SERVICE_ACCOUNT_JSON:
    raise ValueError("Google Drive credentials not set")

# Initialize LINE SDK
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Initialize Google Drive API
def get_drive_service():
    try:
        # Parse the JSON string from environment variable
        service_account_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        
        # Create credentials from service account info
        credentials = Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        
        # Build the Drive API service
        service = build('drive', 'v3', credentials=credentials)
        return service
    except Exception as e:
        print(f"Error initializing Google Drive service: {e}")
        return None

def upload_to_drive(file_content, filename, mime_type='application/octet-stream'):
    """Upload file to Google Drive and return the file URL"""
    try:
        service = get_drive_service()
        if not service:
            return None
        
        # Create file metadata
        file_metadata = {
            'name': filename,
            'parents': [GOOGLE_DRIVE_FOLDER_ID]
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
        
        print(f"File uploaded successfully: {file.get('name')}")
        print(f"File ID: {file.get('id')}")
        print(f"File URL: {file.get('webViewLink')}")
        
        return {
            'id': file.get('id'),
            'name': file.get('name'),
            'url': file.get('webViewLink')
        }
        
    except Exception as e:
        print(f"Error uploading to Google Drive: {e}")
        return None

app = Flask(__name__)

# Add a root route for health checks
@app.route("/")
def health_check():
    return "LINE Bot with Google Drive is running!", 200

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
        message_id = event.message.id
        content = line_bot_api.get_message_content(message_id)
        
        # Read the image content
        image_data = b''
        for chunk in content.iter_content():
            image_data += chunk
        
        # Generate filename
        filename = f"image_{message_id}.jpg"
        
        # Upload to Google Drive
        result = upload_to_drive(image_data, filename, 'image/jpeg')
        
        if result:
            # Send confirmation message back to user
            reply_message = TextSendMessage(
                text=f"✅ Image saved successfully!\n📁 File: {result['name']}\n🔗 URL: {result['url']}"
            )
            line_bot_api.reply_message(event.reply_token, reply_message)
            print(f"Image uploaded successfully: {result['name']}")
        else:
            # Send error message
            reply_message = TextSendMessage(text="❌ Failed to save image to Google Drive")
            line_bot_api.reply_message(event.reply_token, reply_message)
            print("Failed to upload image to Google Drive")
            
    except Exception as e:
        print(f"Error handling image: {e}")
        reply_message = TextSendMessage(text="❌ Error processing image")
        line_bot_api.reply_message(event.reply_token, reply_message)

@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    try:
        message_id = event.message.id
        file_name = event.message.file_name
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
        
        # Upload to Google Drive
        result = upload_to_drive(file_data, file_name, mime_type)
        
        if result:
            # Send confirmation message back to user
            reply_message = TextSendMessage(
                text=f"✅ File saved successfully!\n📁 File: {result['name']}\n🔗 URL: {result['url']}"
            )
            line_bot_api.reply_message(event.reply_token, reply_message)
            print(f"File uploaded successfully: {result['name']}")
        else:
            # Send error message
            reply_message = TextSendMessage(text="❌ Failed to save file to Google Drive")
            line_bot_api.reply_message(event.reply_token, reply_message)
            print("Failed to upload file to Google Drive")
            
    except Exception as e:
        print(f"Error handling file: {e}")
        reply_message = TextSendMessage(text="❌ Error processing file")
        line_bot_api.reply_message(event.reply_token, reply_message)

if __name__ == "__main__":
    # Get port from environment variable (Render sets this automatically)
    port = int(os.environ.get("PORT", 5000))
    # Bind to 0.0.0.0 to accept external connections
    app.run(host="0.0.0.0", port=port, debug=False)