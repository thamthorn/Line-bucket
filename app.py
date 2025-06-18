from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, ImageMessage, FileMessage

import os
import requests

app = Flask(__name__)

line_bot_api = LineBotApi('6vDLrqmS0/RVFOFjl0g0d5oGFqwiSF1ncH13eF6KKg5xz5LBhpvQ9VDGTntI7i8NENqzGqABczCoK/g3LitPvQOlU7KDGNVCfOXTDcHq7dsS9nLmCVSvK76umbnNIVFaqoUuUzKx8jC50IBFW/NYyQdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('6724885bee9b7fab6107fd4fae636347')

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    
    return 'OK'

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    message_id = event.message.id
    content = line_bot_api.get_message_content(message_id)
    
    with open(f'image_{message_id}.jpg', 'wb') as f:
        for chunk in content.iter_content():
            f.write(chunk)

@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    message_id = event.message.id
    file_name = event.message.file_name
    content = line_bot_api.get_message_content(message_id)
    
    with open(file_name, 'wb') as f:
        for chunk in content.iter_content():
            f.write(chunk)

if __name__ == "__main__":
    app.run(debug=True)
