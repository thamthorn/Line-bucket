# Developer Guide

## Setting Up Development Environment

### Prerequisites
- Python 3.8+ (3.13 recommended)
- Git
- Text editor/IDE (VS Code recommended)
- LINE account for testing
- Google account for testing

### Initial Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd line_bucket_image
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your actual credentials
   ```

5. **Run the application**
   ```bash
   python app.py
   ```

### Development vs Production

| Feature | Development | Production |
|---------|-------------|------------|
| Database | In-memory | PostgreSQL |
| HTTPS | Not required | Required |
| Debug mode | Enabled | Disabled |
| Logging | Console | File/Service |
| Secrets | .env file | Environment vars |

## Code Style Guide

### Python Style
Follow PEP 8 with these specifics:

```python
# Function naming: snake_case
def get_user_token(user_id):
    pass

# Class naming: PascalCase (if you add classes)
class DriveService:
    pass

# Constants: UPPER_CASE
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

# Private functions: leading underscore
def _internal_helper():
    pass
```

### Documentation
```python
def upload_to_user_drive(user_id, file_content, filename, mime_type='application/octet-stream'):
    """Upload file to user's Google Drive.
    
    Args:
        user_id (str): LINE user identifier
        file_content (bytes): Binary file data
        filename (str): Desired filename
        mime_type (str, optional): File MIME type. Defaults to 'application/octet-stream'.
    
    Returns:
        dict: File information with id, name, url or None if failed
    
    Raises:
        Exception: If Google Drive API fails
    """
```

### Error Handling
```python
# Always use specific exception types when possible
try:
    conn = psycopg2.connect(DATABASE_URL)
except psycopg2.Error as e:
    logger.error(f"Database connection failed: {e}")
    return None
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise
```

## Adding New Features

### Adding a New Command

1. **Update text handler**
   ```python
   @handler.add(MessageEvent, message=TextMessage)
   def handle_text_message(event):
       text = event.message.text.lower().strip()
       
       # Add your new command
       if text in ['/newcommand', 'newcommand']:
           # Handle the new command
           response = handle_new_command(event)
           safe_reply_message(event, response)
   ```

2. **Create command handler**
   ```python
   def handle_new_command(event):
       """Handle the new command logic"""
       user_id = event.source.user_id
       
       # Your command logic here
       result = do_something()
       
       return TextSendMessage(text=f"Command result: {result}")
   ```

3. **Update help text**
   ```python
   # In handle_text_message, update the help command
   help_message = TextSendMessage(
       text="🤖 LINE to Google Drive Bot Help\n\n"
            "📸 Send images → Saved to Google Drive\n"
            "📄 Send files → Saved to Google Drive\n"
            "/status → Check authentication status\n"
            "/help → Show this help message\n"
            "/newcommand → Description of new command\n"  # Add this
   )
   ```

### Adding New File Type Support

1. **Update MIME type detection**
   ```python
   def handle_file(event):
       file_name = event.message.file_name
       
       # Add new MIME type
       if file_name.lower().endswith('.your_extension'):
           mime_type = 'application/your-mime-type'
   ```

2. **Test with actual files**
3. **Update documentation**

### Adding Database Fields

1. **Update schema in `init_db()`**
   ```python
   def init_db():
       # Add new column
       cur.execute("""
           ALTER TABLE user_tokens 
           ADD COLUMN IF NOT EXISTS new_field TEXT;
       """)
   ```

2. **Update related functions**
   ```python
   def store_user_token(user_id, token_data):
       cur.execute("""
           INSERT INTO user_tokens (user_id, access_token, new_field)
           VALUES (%s, %s, %s)
       """, (user_id, token_data['access_token'], token_data.get('new_field')))
   ```

## Testing

### Manual Testing Checklist

#### Authentication Flow
- [ ] Visit `/auth?user_id=test` shows proper page
- [ ] OAuth redirect works in external browser
- [ ] Tokens are stored correctly
- [ ] Success message sent to user

#### File Upload Flow
- [ ] Image upload works in private chat
- [ ] Image upload works in group chat
- [ ] File upload works with various types
- [ ] Multiple users in group receive files
- [ ] Error handling works for failed uploads

#### Command Testing
- [ ] `/status` shows correct authentication status
- [ ] `/help` shows complete help text
- [ ] Commands work in both private and group chats
- [ ] Error messages are sent privately

#### Edge Cases
- [ ] Unauthenticated user gets auth prompt
- [ ] Invalid reply tokens handled gracefully
- [ ] Database connection failure handled
- [ ] Large file uploads work
- [ ] Special characters in filenames work

### Automated Testing (recommended to add)

```python
import unittest
from unittest.mock import patch, MagicMock

class TestBotFunctions(unittest.TestCase):
    
    def test_user_authentication(self):
        with patch('app.get_user_token') as mock_get_token:
            mock_get_token.return_value = {'access_token': 'test'}
            self.assertTrue(is_user_authenticated('test_user'))
    
    def test_group_member_tracking(self):
        # Clear memory
        group_members_memory.clear()
        
        # Track member
        track_group_member('group1', 'user1', 'group')
        
        # Verify tracking
        self.assertIn('user1', group_members_memory['group1'])

if __name__ == '__main__':
    unittest.main()
```

## Debugging

### Local Development

1. **Enable debug mode**
   ```python
   if __name__ == "__main__":
       app.run(host="0.0.0.0", port=5000, debug=True)
   ```

2. **Use debug endpoints**
   ```bash
   curl http://localhost:5000/debug/user/YOUR_USER_ID
   ```

3. **Check logs**
   ```python
   # Add debug logging
   import logging
   logging.basicConfig(level=logging.DEBUG)
   
   # In functions
   print(f"DEBUG: Processing user {user_id}")
   ```

### Production Debugging

1. **Check application logs**
   ```bash
   # Render
   render logs --service=your-service
   
   # Heroku  
   heroku logs --tail
   ```

2. **Monitor key metrics**
   - Authentication success rate
   - File upload success rate
   - Database connection health
   - Memory usage

3. **Use debug routes carefully**
   ```python
   # Only enable in development
   if os.environ.get('DEBUG'):
       @app.route("/debug/user/<user_id>")
       def debug_user_auth(user_id):
           # Debug logic
   ```

## Security Best Practices

### Code Security
```python
# Never log sensitive data
# Bad
print(f"User token: {token}")

# Good
print(f"User token: {'*' * 20}")

# Use environment variables
# Bad
GOOGLE_CLIENT_ID = "123456789.googleusercontent.com"

# Good
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
```

### Input Validation
```python
def safe_filename(filename):
    """Sanitize filename for security"""
    # Remove dangerous characters
    import re
    safe_name = re.sub(r'[^\w\-_\.]', '_', filename)
    # Limit length
    return safe_name[:100]
```

### Error Handling
```python
# Don't expose internal errors to users
try:
    result = risky_operation()
except Exception as e:
    logger.error(f"Internal error: {e}")
    # Send generic message to user
    return TextSendMessage(text="❌ An error occurred. Please try again.")
```

## Performance Optimization

### Database Optimization
```python
# Use connection pooling (future improvement)
from psycopg2 import pool

# Optimize queries
def get_user_batch_tokens(user_ids):
    """Get multiple user tokens in one query"""
    cur.execute("""
        SELECT user_id, access_token FROM user_tokens 
        WHERE user_id = ANY(%s)
    """, (user_ids,))
```

### Memory Management
```python
# Clear large variables
def process_large_file(file_content):
    result = upload_to_drive(file_content)
    del file_content  # Free memory
    return result
```

### Async Operations (future improvement)
```python
import asyncio

async def upload_to_multiple_drives(users, file_content):
    """Upload to multiple drives concurrently"""
    tasks = [upload_to_user_drive(user, file_content) for user in users]
    return await asyncio.gather(*tasks)
```

## Common Development Tasks

### Adding Environment Variable
1. Add to `.env.example`
2. Document in README.md
3. Update deployment guide
4. Add validation in code:
   ```python
   NEW_VAR = os.environ.get("NEW_VAR")
   if not NEW_VAR:
       raise ValueError("NEW_VAR environment variable not set")
   ```

### Updating Dependencies
1. Update `requirements.txt`
2. Test locally
3. Update `runtime.txt` if needed
4. Test deployment
5. Update documentation

### Database Schema Changes
1. Update `init_db()` function
2. Add migration logic if needed
3. Test with both PostgreSQL and in-memory
4. Update related functions
5. Test thoroughly

## Git Workflow

### Branching Strategy
```bash
# Feature development
git checkout -b feature/new-command
# Make changes
git commit -m "Add new command feature"
git push origin feature/new-command
# Create pull request

# Bug fixes
git checkout -b bugfix/reply-token-issue
# Make changes
git commit -m "Fix reply token error handling"
```

### Commit Messages
```bash
# Good commit messages
git commit -m "Add support for PDF file uploads"
git commit -m "Fix database connection retry logic"
git commit -m "Update OAuth flow for mobile browsers"

# Bad commit messages
git commit -m "Fix stuff"
git commit -m "Update"
git commit -m "WIP"
```

## Release Process

### Pre-Release Checklist
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Environment variables documented
- [ ] Deployment guide updated
- [ ] Security review completed

### Deployment Steps
1. **Test in staging environment**
2. **Update version numbers**
3. **Deploy to production**
4. **Monitor logs for issues**
5. **Test key functionality**
6. **Document any issues**

### Rollback Plan
1. **Keep previous version tagged**
2. **Database migration rollback script**
3. **Quick rollback procedure documented**

---

**Last Updated**: July 2025

For questions about development, check the troubleshooting guide or review the architecture documentation.
