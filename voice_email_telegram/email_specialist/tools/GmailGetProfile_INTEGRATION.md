# GmailGetProfile Integration Guide

**Complete integration guide for GmailGetProfile tool in production systems**

## Table of Contents

1. [Quick Start](#quick-start)
2. [Agency Swarm Integration](#agency-swarm-integration)
3. [Voice Assistant Integration](#voice-assistant-integration)
4. [Web Dashboard Integration](#web-dashboard-integration)
5. [Automation & Monitoring](#automation--monitoring)
6. [Performance Optimization](#performance-optimization)
7. [Production Deployment](#production-deployment)

---

## Quick Start

### 5-Minute Setup

```bash
# 1. Install dependencies
pip install composio-core agency-swarm python-dotenv pydantic

# 2. Connect Gmail via Composio
composio add gmail

# 3. Get entity ID
composio connections list

# 4. Configure environment
cat > .env << EOF
COMPOSIO_API_KEY=your_composio_api_key
GMAIL_ENTITY_ID=your_gmail_entity_id
EOF

# 5. Test the tool
python GmailGetProfile.py
```

### First Test

```python
from email_specialist.tools.GmailGetProfile import GmailGetProfile
import json

# Get your profile
tool = GmailGetProfile()
result = json.loads(tool.run())

if result["success"]:
    print(f"✓ Connected: {result['email_address']}")
    print(f"✓ Messages: {result['messages_total']:,}")
else:
    print(f"✗ Error: {result['error']}")
```

---

## Agency Swarm Integration

### Basic Agent Setup

```python
from agency_swarm import Agent
from email_specialist.tools.GmailGetProfile import GmailGetProfile

# Create email specialist agent
email_agent = Agent(
    name="Email Specialist",
    description="Handles Gmail profile and statistics operations",
    instructions="""
    You are an email specialist that helps users manage their Gmail account.

    CAPABILITIES:
    - Get user's Gmail address
    - Check total message and thread counts
    - Provide mailbox statistics
    - Assess mailbox health

    RESPONSE PATTERNS:
    - "What's my Gmail address?" → Use GmailGetProfile, return email_address
    - "How many emails do I have?" → Use GmailGetProfile, return messages_total
    - "Show my Gmail profile" → Use GmailGetProfile, return full summary
    - "Check my mailbox stats" → Use GmailGetProfile, calculate health metrics
    """,
    tools=[GmailGetProfile],
    temperature=0.5
)
```

### Multi-Agent System

```python
from agency_swarm import Agency
from email_specialist.tools.GmailGetProfile import GmailGetProfile
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails

# Email Specialist Agent
email_agent = Agent(
    name="Email Specialist",
    description="Manages Gmail operations",
    tools=[GmailGetProfile, GmailFetchEmails]
)

# User Interface Agent
ui_agent = Agent(
    name="User Interface",
    description="Handles user interactions"
)

# Create agency with communication flows
agency = Agency(
    [
        ui_agent,  # Entry point
        [ui_agent, email_agent],  # UI can delegate to Email
    ],
    shared_instructions="Use GmailGetProfile for profile queries"
)

# Run agency
response = agency.get_completion("What's my Gmail address?")
print(response)
```

### Voice Email Agent Integration

```python
from agency_swarm import Agent
from email_specialist.tools.GmailGetProfile import GmailGetProfile

voice_email_agent = Agent(
    name="Voice Email Assistant",
    description="Voice-activated Gmail assistant",
    instructions="""
    You are a voice assistant for Gmail operations.

    PROFILE QUERIES:
    - User asks "what's my email" → Use GmailGetProfile, speak email address
    - User asks "how many emails" → Use GmailGetProfile, speak message count
    - User asks "inbox status" → Use GmailGetProfile, assess and report health

    VOICE RESPONSE FORMAT:
    - Be concise and natural
    - Use numbers in spoken format ("fifteen thousand" not "15000")
    - Provide context ("You have 234 messages across 156 conversations")
    """,
    tools=[GmailGetProfile],
    temperature=0.7  # Slightly higher for natural speech
)

# Process voice command
command = "Hey, what's my Gmail address?"
response = voice_email_agent.get_completion(command)
```

---

## Voice Assistant Integration

### ElevenLabs Voice Integration

```python
import json
from elevenlabs import generate, set_api_key
from email_specialist.tools.GmailGetProfile import GmailGetProfile

set_api_key("your_elevenlabs_api_key")

def speak_gmail_profile():
    """Get Gmail profile and speak it using ElevenLabs"""

    tool = GmailGetProfile()
    result = json.loads(tool.run())

    if result["success"]:
        # Format for natural speech
        email = result["email_address"]
        messages = result["messages_total"]
        threads = result["threads_total"]

        # Create natural speech text
        speech_text = f"""
        Your Gmail address is {email.replace('@', ' at ').replace('.', ' dot ')}.
        You have {messages:,} messages across {threads:,} conversation threads.
        """

        # Generate speech
        audio = generate(
            text=speech_text,
            voice="Rachel",  # Choose your preferred voice
            model="eleven_monolingual_v1"
        )

        return audio
    else:
        error_speech = f"I couldn't retrieve your Gmail profile. {result['error']}"
        return generate(text=error_speech, voice="Rachel")
```

### Telegram Bot Integration

```python
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from email_specialist.tools.GmailGetProfile import GmailGetProfile
import json

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /profile command in Telegram"""

    # Get Gmail profile
    tool = GmailGetProfile()
    result = json.loads(tool.run())

    if result["success"]:
        # Format message for Telegram
        message = f"""
📧 *Gmail Profile*

*Email:* `{result['email_address']}`
*Messages:* {result['messages_total']:,}
*Threads:* {result['threads_total']:,}
*Messages/Thread:* {result['messages_per_thread']}

{get_health_emoji(result['messages_per_thread'])} {get_health_status(result['messages_per_thread'])}
        """
        await update.message.reply_text(message, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            f"❌ Error: {result['error']}",
            parse_mode='Markdown'
        )

def get_health_emoji(ratio: float) -> str:
    """Get health status emoji"""
    if ratio < 2: return "✅"
    elif ratio < 5: return "ℹ️"
    elif ratio < 10: return "⚠️"
    else: return "🔥"

def get_health_status(ratio: float) -> str:
    """Get health status text"""
    if ratio < 2: return "Healthy mailbox"
    elif ratio < 5: return "Normal activity"
    elif ratio < 10: return "Active conversations"
    else: return "Very active threads"

# Set up bot
app = Application.builder().token("YOUR_TELEGRAM_BOT_TOKEN").build()
app.add_handler(CommandHandler("profile", profile_command))
app.run_polling()
```

---

## Web Dashboard Integration

### Streamlit Dashboard

```python
import streamlit as st
import json
from email_specialist.tools.GmailGetProfile import GmailGetProfile
import plotly.graph_objects as go

st.set_page_config(page_title="Gmail Dashboard", page_icon="📧")

def main():
    st.title("📧 Gmail Profile Dashboard")

    # Get profile with caching
    @st.cache_data(ttl=300)  # Cache for 5 minutes
    def get_profile():
        tool = GmailGetProfile()
        return json.loads(tool.run())

    result = get_profile()

    if result["success"]:
        # Display metrics in columns
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                label="📧 Email Address",
                value=result["email_address"]
            )

        with col2:
            st.metric(
                label="📬 Total Messages",
                value=f"{result['messages_total']:,}"
            )

        with col3:
            st.metric(
                label="💬 Total Threads",
                value=f"{result['threads_total']:,}"
            )

        # Mailbox health indicator
        ratio = result["messages_per_thread"]
        health_color = get_health_color(ratio)

        st.markdown(f"""
        ### Mailbox Health
        <div style='padding: 20px; background-color: {health_color}20; border-radius: 10px;'>
            <h4>Messages per Thread: {ratio}</h4>
            <p>{get_health_description(ratio)}</p>
        </div>
        """, unsafe_allow_html=True)

        # Visualization
        fig = go.Figure(data=[
            go.Bar(
                x=['Messages', 'Threads'],
                y=[result['messages_total'], result['threads_total']],
                marker_color=['#1a73e8', '#34a853']
            )
        ])
        fig.update_layout(title="Mailbox Statistics", height=400)
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.error(f"❌ {result['error']}")

def get_health_color(ratio: float) -> str:
    if ratio < 2: return "#34a853"  # Green
    elif ratio < 5: return "#4285f4"  # Blue
    elif ratio < 10: return "#fbbc04"  # Yellow
    else: return "#ea4335"  # Red

def get_health_description(ratio: float) -> str:
    if ratio < 2: return "✓ Healthy - Most emails are standalone"
    elif ratio < 5: return "ℹ️ Normal - Moderate conversation activity"
    elif ratio < 10: return "⚠️ Active - High conversation engagement"
    else: return "🔥 Very Active - Extensive email threads"

if __name__ == "__main__":
    main()
```

### Flask API Endpoint

```python
from flask import Flask, jsonify
from email_specialist.tools.GmailGetProfile import GmailGetProfile
import json

app = Flask(__name__)

@app.route('/api/gmail/profile', methods=['GET'])
def get_gmail_profile():
    """API endpoint for Gmail profile"""

    tool = GmailGetProfile()
    result = json.loads(tool.run())

    if result["success"]:
        return jsonify({
            "status": "success",
            "data": {
                "email": result["email_address"],
                "messages": result["messages_total"],
                "threads": result["threads_total"],
                "ratio": result["messages_per_thread"],
                "health": assess_health(result["messages_per_thread"])
            }
        }), 200
    else:
        return jsonify({
            "status": "error",
            "message": result["error"]
        }), 500

def assess_health(ratio: float) -> dict:
    """Assess mailbox health"""
    if ratio < 2:
        return {"level": "healthy", "score": 95, "color": "green"}
    elif ratio < 5:
        return {"level": "normal", "score": 75, "color": "blue"}
    elif ratio < 10:
        return {"level": "active", "score": 50, "color": "yellow"}
    else:
        return {"level": "very_active", "score": 25, "color": "red"}

if __name__ == '__main__':
    app.run(debug=True, port=5000)
```

---

## Automation & Monitoring

### Scheduled Profile Monitoring

```python
import schedule
import time
import json
from email_specialist.tools.GmailGetProfile import GmailGetProfile
from datetime import datetime

def monitor_gmail_profile():
    """Monitor Gmail profile every hour"""

    tool = GmailGetProfile()
    result = json.loads(tool.run())

    if result["success"]:
        timestamp = datetime.now().isoformat()

        # Log metrics
        log_entry = {
            "timestamp": timestamp,
            "email": result["email_address"],
            "messages": result["messages_total"],
            "threads": result["threads_total"],
            "ratio": result["messages_per_thread"]
        }

        # Save to monitoring log
        with open('gmail_monitoring.jsonl', 'a') as f:
            f.write(json.dumps(log_entry) + '\n')

        # Alert if quota threshold reached
        if result["messages_total"] > 12000:
            send_alert(f"⚠️ Gmail quota alert: {result['messages_total']:,} messages")

        print(f"✓ {timestamp}: Profile monitored successfully")
    else:
        print(f"✗ Error monitoring profile: {result['error']}")

def send_alert(message: str):
    """Send monitoring alert (implement your notification method)"""
    print(f"ALERT: {message}")
    # Add: Slack, email, SMS, etc.

# Schedule monitoring every hour
schedule.every(1).hours.do(monitor_gmail_profile)

# Run scheduler
while True:
    schedule.run_pending()
    time.sleep(60)
```

### Health Check Integration

```python
from typing import Dict
import json
from email_specialist.tools.GmailGetProfile import GmailGetProfile

def gmail_health_check() -> Dict[str, any]:
    """
    Comprehensive Gmail health check for monitoring systems

    Returns:
        dict: Health check status with metrics
    """

    tool = GmailGetProfile()
    result = json.loads(tool.run())

    if result["success"]:
        messages = result["messages_total"]
        threads = result["threads_total"]
        ratio = result["messages_per_thread"]

        # Determine overall health
        health_status = "healthy"
        if messages > 12000:  # Approaching quota
            health_status = "warning"
        if messages > 14000:  # Critical quota
            health_status = "critical"

        return {
            "service": "gmail",
            "status": health_status,
            "timestamp": datetime.now().isoformat(),
            "metrics": {
                "messages_total": messages,
                "threads_total": threads,
                "messages_per_thread": ratio,
                "quota_usage_percent": (messages / 15000) * 100  # Assuming 15k limit
            },
            "details": {
                "email": result["email_address"],
                "history_id": result["history_id"]
            }
        }
    else:
        return {
            "service": "gmail",
            "status": "down",
            "timestamp": datetime.now().isoformat(),
            "error": result["error"]
        }

# Use in monitoring system
health = gmail_health_check()
print(json.dumps(health, indent=2))
```

---

## Performance Optimization

### Redis Caching

```python
import redis
import json
from email_specialist.tools.GmailGetProfile import GmailGetProfile

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

def get_gmail_profile_cached(ttl: int = 300):
    """
    Get Gmail profile with Redis caching

    Args:
        ttl: Time to live in seconds (default 5 minutes)

    Returns:
        dict: Gmail profile data
    """

    # Check cache
    cache_key = "gmail:profile"
    cached = redis_client.get(cache_key)

    if cached:
        print("✓ Cache hit")
        return json.loads(cached)

    # Cache miss - fetch from API
    print("✗ Cache miss - fetching from API")
    tool = GmailGetProfile()
    result = json.loads(tool.run())

    if result["success"]:
        # Store in cache
        redis_client.setex(
            cache_key,
            ttl,
            json.dumps(result)
        )

    return result

# Usage
profile = get_gmail_profile_cached(ttl=600)  # Cache for 10 minutes
```

### Async Implementation

```python
import asyncio
import json
from email_specialist.tools.GmailGetProfile import GmailGetProfile

async def get_profile_async():
    """Async wrapper for GmailGetProfile"""

    # Run in executor to avoid blocking
    loop = asyncio.get_event_loop()
    tool = GmailGetProfile()

    result = await loop.run_in_executor(None, tool.run)
    return json.loads(result)

# Use in async application
async def main():
    profile = await get_profile_async()
    print(f"Email: {profile['email_address']}")

asyncio.run(main())
```

---

## Production Deployment

### Docker Container

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy tool
COPY email_specialist/tools/GmailGetProfile.py /app/

# Copy environment
COPY .env /app/

# Run health check
HEALTHCHECK --interval=5m --timeout=3s \
  CMD python -c "from GmailGetProfile import GmailGetProfile; import json; result = json.loads(GmailGetProfile().run()); exit(0 if result['success'] else 1)"

CMD ["python", "GmailGetProfile.py"]
```

### Environment Variables

```bash
# .env.production
COMPOSIO_API_KEY=prod_api_key_here
GMAIL_ENTITY_ID=prod_entity_id_here

# Optional performance settings
REDIS_URL=redis://localhost:6379/0
CACHE_TTL=300
LOG_LEVEL=INFO
```

### Kubernetes Deployment

```yaml
# gmail-profile-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: gmail-profile-service
spec:
  selector:
    app: gmail-profile
  ports:
    - protocol: TCP
      port: 80
      targetPort: 5000

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gmail-profile-deployment
spec:
  replicas: 3
  selector:
    matchLabels:
      app: gmail-profile
  template:
    metadata:
      labels:
        app: gmail-profile
    spec:
      containers:
      - name: gmail-profile
        image: your-registry/gmail-profile:latest
        ports:
        - containerPort: 5000
        env:
        - name: COMPOSIO_API_KEY
          valueFrom:
            secretKeyRef:
              name: composio-secrets
              key: api-key
        - name: GMAIL_ENTITY_ID
          valueFrom:
            secretKeyRef:
              name: composio-secrets
              key: entity-id
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 30
          periodSeconds: 10
```

---

## Support & Resources

- **Tool Documentation**: `GmailGetProfile_README.md`
- **Test Suite**: `test_gmail_get_profile.py`
- **Pattern Reference**: `FINAL_VALIDATION_SUMMARY.md`
- **Composio Docs**: https://docs.composio.dev

## Next Steps

1. ✅ Set up environment and test basic functionality
2. ✅ Integrate with your agent system
3. ✅ Implement caching for performance
4. ✅ Add monitoring and alerts
5. ✅ Deploy to production

---

**Version**: 1.0.0
**Last Updated**: 2025-01-01
**Maintained By**: Email Specialist Team
