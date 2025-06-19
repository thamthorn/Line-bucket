from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, ImageMessage, FileMessage

import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env (for local use)
load_dotenv()

# Load from environment
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")

# Check if keys are set
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET not set")

# Initialize LINE SDK
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)

# Add a root route for health checks
@app.route("/")
def health_check():
    return "LINE Bot is running!", 200

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
    message_id = event.message.id
    content = line_bot_api.get_message_content(message_id)

    # Save image file
    file_path = f"downloads/image_{message_id}.jpg"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, 'wb') as f:
        for chunk in content.iter_content():
            f.write(chunk)
    print(f"Saved image to {file_path}")

@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    message_id = event.message.id
    file_name = event.message.file_name
    content = line_bot_api.get_message_content(message_id)

    # Save file (PDF or others)
    file_path = f"downloads/{file_name}"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, 'wb') as f:
        for chunk in content.iter_content():
            f.write(chunk)
    print(f"Saved file to {file_path}")

if __name__ == "__main__":
    # Get port from environment variable (Render sets this automatically)
    port = int(os.environ.get("PORT", 5000))
    # Bind to 0.0.0.0 to accept external connections
    app.run(host="0.0.0.0", port=port, debug=False)