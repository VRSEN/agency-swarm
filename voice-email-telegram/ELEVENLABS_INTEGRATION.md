# ElevenLabs Integration Guide

Complete guide for integrating ElevenLabs voice synthesis with your voice-first email system.

---

## Overview

ElevenLabs provides AI-powered text-to-speech that will:
- Convert email drafts to natural voice audio
- Create voice messages for Telegram
- Support multiple languages and voices
- Generate lifelike, expressive speech

---

## Getting Your API Key

### Step 1: Create Account

1. **Visit ElevenLabs**
   - Go to https://elevenlabs.io
   - Click "Get Started" or "Sign Up"

2. **Sign Up**
   - Use email or Google/GitHub sign-in
   - No credit card required for free tier

3. **Verify Email**
   - Check your inbox for verification email
   - Click verification link

### Step 2: Get API Key

1. **Navigate to Profile Settings**
   - Click your profile icon (top right)
   - Select "Profile"

2. **Find API Keys Section**
   - Look for "API Keys" or "API" tab
   - Should see existing keys or option to create

3. **Generate API Key**
   - Click "Generate API Key" or "New Key"
   - Name it: "Voice Email System"
   - Copy the key (starts with `xi_`)

4. **Save Securely**
   ```bash
   # Add to .env file
   echo "ELEVENLABS_API_KEY=xi_your_key_here" >> .env
   ```

### Free Tier Details

**Monthly Limits**:
- 10,000 characters per month (some sources say 20,000)
- 100 requests per minute
- Access to standard voices
- Commercial use not allowed

**What 10,000 characters means**:
- ~150-200 words
- ~10-15 email drafts (typical length)
- Good for testing and prototyping

**To Get More**:
- Starter Plan: $5/month for 30,000 characters
- Creator Plan: $22/month for 100,000 characters
- Pro Plan: $99/month for 500,000 characters

---

## Connecting to Composio

### Python Setup

```python
from composio import Composio
import os
from dotenv import load_dotenv

load_dotenv()

composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
entity_id = "default_user"

# Connect ElevenLabs
connection = composio.connections.initiate(
    integration="ELEVENLABS",
    entity_id=entity_id,
    auth_config={
        "api_key": os.getenv("ELEVENLABS_API_KEY")
    }
)

print(f"Connection status: {connection.status}")
```

### Verify Connection

```python
# Check connection status
connections = composio.connections.list(entity_id="default_user")

for conn in connections:
    if conn.integration == "ELEVENLABS":
        print(f"ElevenLabs: {conn.status}")
```

---

## Available Voices

### List Available Voices

```python
result = composio.tools.execute(
    action="ELEVENLABS_LIST_VOICES",
    params={},
    entity_id="default_user"
)

for voice in result.get('voices', []):
    print(f"Name: {voice['name']}")
    print(f"Voice ID: {voice['voice_id']}")
    print(f"Category: {voice.get('category', 'N/A')}")
    print("---")
```

### Pre-made Voices

ElevenLabs provides several high-quality pre-made voices:

**Male Voices**:
- Adam - Deep and authoritative
- Antoni - Well-rounded, clear
- Arnold - Crisp, professional
- Callum - Hoarse, conversational
- Charlie - Casual, natural

**Female Voices**:
- Bella - Soft and pleasant
- Charlotte - Smooth, professional
- Dorothy - Pleasant, warm
- Emily - Calm and clear
- Rachel - Calm, news-anchor style

**Voice IDs** (as of Jan 2025):
```python
# Common voice IDs (may vary)
VOICES = {
    "rachel": "21m00Tcm4TlvDq8ikWAM",
    "adam": "pNInz6obpgDQGcFmaJgB",
    "antoni": "ErXwobaYiN019PkySvjV",
    "bella": "EXAVITQu4vr4xnSDxMaL",
    "charlotte": "XB0fDUnXU5powFXDhCwa",
}
```

---

## Text-to-Speech Actions

### 1. Basic Text-to-Speech

```python
result = composio.tools.execute(
    action="ELEVENLABS_TEXT_TO_SPEECH",
    params={
        "text": "Hello! This is your email draft assistant speaking.",
        "voice_id": "21m00Tcm4TlvDq8ikWAM",  # Rachel
        "model_id": "eleven_monolingual_v1",  # or "eleven_multilingual_v2"
    },
    entity_id="default_user"
)

# Result contains audio data
audio_data = result['audio']  # Base64 or binary data
```

### 2. Text-to-Speech with Settings

```python
result = composio.tools.execute(
    action="ELEVENLABS_TEXT_TO_SPEECH",
    params={
        "text": "Your email draft is ready for review.",
        "voice_id": "21m00Tcm4TlvDq8ikWAM",
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.75,        # 0-1, higher = more stable
            "similarity_boost": 0.75, # 0-1, higher = more similar to original
            "style": 0.0,             # 0-1, higher = more expressive
            "use_speaker_boost": True # Enhance clarity
        },
        "output_format": "mp3_44100_128"  # High quality MP3
    },
    entity_id="default_user"
)
```

**Voice Settings Explained**:
- **Stability**: Controls consistency. High = monotone but consistent, Low = more expressive but less consistent
- **Similarity Boost**: Closeness to original voice
- **Style**: Adds emotional expressiveness (experimental)
- **Speaker Boost**: Enhances clarity and presence

**Recommended Settings for Email Reading**:
```python
EMAIL_VOICE_SETTINGS = {
    "stability": 0.7,         # Fairly consistent
    "similarity_boost": 0.8,  # Stay close to voice character
    "style": 0.2,             # Slight expressiveness
    "use_speaker_boost": True
}
```

### 3. Generate Speech File

```python
import base64

def generate_voice_file(text, output_path="draft_audio.mp3"):
    """Generate and save voice file"""

    result = composio.tools.execute(
        action="ELEVENLABS_TEXT_TO_SPEECH",
        params={
            "text": text,
            "voice_id": "21m00Tcm4TlvDq8ikWAM",  # Rachel
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.7,
                "similarity_boost": 0.8,
                "use_speaker_boost": True
            },
            "output_format": "mp3_44100_128"
        },
        entity_id="default_user"
    )

    # Save audio file
    audio_data = result.get('audio')

    # If base64 encoded
    if isinstance(audio_data, str):
        audio_bytes = base64.b64decode(audio_data)
    else:
        audio_bytes = audio_data

    with open(output_path, 'wb') as f:
        f.write(audio_bytes)

    return output_path

# Usage
audio_file = generate_voice_file("This is your email draft...")
print(f"Audio saved to: {audio_file}")
```

---

## Email Draft to Voice Workflow

### Complete Implementation

```python
class EmailVoiceConverter:
    def __init__(self, composio, entity_id):
        self.composio = composio
        self.entity_id = entity_id
        self.voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel

    def format_email_for_speech(self, email_draft):
        """Format email draft for natural speech"""

        # Extract components
        to = email_draft.get('to', 'unknown recipient')
        subject = email_draft.get('subject', 'no subject')
        body = email_draft.get('body', '')

        # Create natural speech script
        script = f"""
        Email draft ready for review.

        This email will be sent to {to}.

        Subject: {subject}.

        Message content:

        {body}

        End of email draft.

        Please approve or request changes.
        """

        # Clean up formatting
        script = script.strip()
        script = script.replace('\n\n', '. ')
        script = script.replace('  ', ' ')

        return script

    def generate_draft_audio(self, email_draft, output_file=None):
        """Convert email draft to voice"""

        # Format for speech
        speech_text = self.format_email_for_speech(email_draft)

        # Check character count
        char_count = len(speech_text)
        if char_count > 5000:
            print(f"Warning: Text is {char_count} chars. May hit limits.")

        # Generate voice
        result = self.composio.tools.execute(
            action="ELEVENLABS_TEXT_TO_SPEECH",
            params={
                "text": speech_text,
                "voice_id": self.voice_id,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.7,
                    "similarity_boost": 0.8,
                    "style": 0.2,
                    "use_speaker_boost": True
                },
                "output_format": "mp3_44100_128"
            },
            entity_id=self.entity_id
        )

        # Save if output file specified
        if output_file:
            audio_data = result['audio']
            if isinstance(audio_data, str):
                audio_bytes = base64.b64decode(audio_data)
            else:
                audio_bytes = audio_data

            with open(output_file, 'wb') as f:
                f.write(audio_bytes)

            return {
                "success": True,
                "file": output_file,
                "char_count": char_count
            }

        return {
            "success": True,
            "audio_data": result['audio'],
            "char_count": char_count
        }

    def generate_confirmation_audio(self, message):
        """Generate short confirmation message"""

        result = self.composio.tools.execute(
            action="ELEVENLABS_TEXT_TO_SPEECH",
            params={
                "text": message,
                "voice_id": self.voice_id,
                "model_id": "eleven_monolingual_v1",  # Faster for short text
                "voice_settings": {
                    "stability": 0.8,
                    "similarity_boost": 0.75,
                },
                "output_format": "mp3_22050_32"  # Lower quality for short messages
            },
            entity_id=self.entity_id
        )

        return result['audio']

# Usage Example
converter = EmailVoiceConverter(composio, "default_user")

# Email draft
draft = {
    "to": "john@example.com",
    "subject": "Project Update",
    "body": "Hi John,\n\nHere's the project update...\n\nBest regards"
}

# Generate voice
result = converter.generate_draft_audio(draft, "draft_preview.mp3")

if result['success']:
    print(f"Audio generated: {result['file']}")
    print(f"Characters used: {result['char_count']}")

# Generate confirmation
confirm_audio = converter.generate_confirmation_audio(
    "Email sent successfully!"
)
```

---

## Integration with Agency Swarm

### Create Voice Agent

```python
from agency_swarm import Agent
from composio import Composio

composio = Composio()
entity_id = "default_user"

# Get ElevenLabs tools
elevenlabs_tools = composio.tools.get(
    toolkits=["ELEVENLABS"],
    entity_id=entity_id
)

# Create agent
voice_agent = Agent(
    name="VoiceAgent",
    description="Voice synthesis agent using ElevenLabs",
    instructions="""
    You are the voice synthesis agent for a voice-first email system.

    Your responsibilities:
    1. Convert email drafts to natural speech
    2. Format text appropriately for voice
    3. Generate audio files for Telegram delivery
    4. Provide voice confirmations for actions
    5. Handle different voice settings for different contexts

    Text Formatting Guidelines:
    - Read numbers naturally ("10" as "ten")
    - Spell out acronyms when unclear
    - Add pauses with periods and commas
    - Break long sentences into shorter ones
    - Read email addresses slowly and clearly

    Voice Settings:
    - Email drafts: Stability 0.7, Professional
    - Confirmations: Stability 0.8, Clear and quick
    - Errors: Stability 0.8, Calm and helpful

    Character Management:
    - Track character usage (10K free tier limit)
    - Warn when approaching limit
    - Optimize text for essential information
    - Suggest text shortening if too long

    Error Handling:
    - Handle quota exceeded errors gracefully
    - Provide text fallback if voice fails
    - Suggest alternative voices if issues occur
    """,
    tools=elevenlabs_tools
)
```

### Complete Workflow Integration

```python
def voice_email_workflow(telegram_chat_id, email_draft):
    """Complete workflow with voice"""

    # 1. Create draft (EmailAgent handles this)
    print("Draft created")

    # 2. Convert to voice
    converter = EmailVoiceConverter(composio, "default_user")
    voice_result = converter.generate_draft_audio(
        email_draft,
        output_file="temp_draft.mp3"
    )

    if not voice_result['success']:
        print("Voice generation failed, sending text only")
        return

    # 3. Send via Telegram
    telegram_result = composio.tools.execute(
        action="TELEGRAM_SEND_VOICE",
        params={
            "chat_id": telegram_chat_id,
            "voice": voice_result['file'],
            "caption": "📧 Your email draft is ready. Listen to review.",
        },
        entity_id="default_user"
    )

    # 4. Send approval buttons
    composio.tools.execute(
        action="TELEGRAM_SEND_MESSAGE",
        params={
            "chat_id": telegram_chat_id,
            "text": f"Draft for: {email_draft['to']}\nSubject: {email_draft['subject']}",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✓ Approve & Send", "callback_data": "approve"},
                        {"text": "✗ Cancel", "callback_data": "cancel"}
                    ],
                    [{"text": "✎ Edit", "callback_data": "edit"}]
                ]
            }
        },
        entity_id="default_user"
    )

    print(f"Voice message sent. Used {voice_result['char_count']} characters.")
```

---

## Advanced Features

### Voice Cloning (Paid Plans)

```python
# Clone your own voice (requires paid plan)
def clone_voice(name, audio_files):
    """Clone voice from audio samples"""

    result = composio.tools.execute(
        action="ELEVENLABS_CLONE_VOICE",
        params={
            "name": name,
            "files": audio_files,  # List of audio file paths
            "description": "Custom voice for email system"
        },
        entity_id="default_user"
    )

    voice_id = result['voice_id']
    return voice_id
```

### Multi-Language Support

```python
# Generate speech in different languages
def generate_multilingual(text, language="en"):
    """Generate speech in specified language"""

    result = composio.tools.execute(
        action="ELEVENLABS_TEXT_TO_SPEECH",
        params={
            "text": text,
            "voice_id": "21m00Tcm4TlvDq8ikWAM",
            "model_id": "eleven_multilingual_v2",  # Supports 29+ languages
            "language_code": language  # "en", "es", "fr", "de", etc.
        },
        entity_id="default_user"
    )

    return result['audio']

# Usage
spanish_audio = generate_multilingual(
    "Hola, este es tu borrador de correo electrónico",
    language="es"
)
```

### Streaming Audio (Real-time)

```python
# Stream audio for real-time playback
def stream_text_to_speech(text, voice_id):
    """Stream audio in chunks"""

    result = composio.tools.execute(
        action="ELEVENLABS_STREAM_TEXT_TO_SPEECH",
        params={
            "text": text,
            "voice_id": voice_id,
            "model_id": "eleven_monolingual_v1",
            "optimize_streaming_latency": 3  # 0-4, higher = faster but lower quality
        },
        entity_id="default_user"
    )

    # Handle streaming response
    for audio_chunk in result['stream']:
        # Play or send chunk immediately
        yield audio_chunk
```

---

## Usage Tracking

### Monitor Character Usage

```python
class UsageTracker:
    def __init__(self):
        self.monthly_usage = 0
        self.monthly_limit = 10000  # Free tier

    def track_usage(self, char_count):
        """Track character usage"""
        self.monthly_usage += char_count

        remaining = self.monthly_limit - self.monthly_usage
        percentage = (self.monthly_usage / self.monthly_limit) * 100

        print(f"Used: {self.monthly_usage}/{self.monthly_limit} ({percentage:.1f}%)")
        print(f"Remaining: {remaining} characters")

        if remaining < 1000:
            print("⚠️  Warning: Approaching monthly limit!")

        return remaining

    def can_generate(self, text):
        """Check if text can be generated"""
        char_count = len(text)
        remaining = self.monthly_limit - self.monthly_usage

        if char_count > remaining:
            return False, f"Not enough quota. Need {char_count}, have {remaining}"

        return True, "OK"

# Usage
tracker = UsageTracker()

text = "Your email draft..."
can_generate, message = tracker.can_generate(text)

if can_generate:
    # Generate voice
    tracker.track_usage(len(text))
else:
    print(message)
```

### Get Usage from API

```python
# Get actual usage from ElevenLabs API
def get_usage_stats():
    """Get current month usage"""

    result = composio.tools.execute(
        action="ELEVENLABS_GET_USAGE",
        params={},
        entity_id="default_user"
    )

    usage = result.get('character_count', 0)
    limit = result.get('character_limit', 10000)

    return {
        "used": usage,
        "limit": limit,
        "remaining": limit - usage,
        "percentage": (usage / limit) * 100
    }

stats = get_usage_stats()
print(f"Current usage: {stats['used']}/{stats['limit']} ({stats['percentage']:.1f}%)")
```

---

## Best Practices

### 1. Optimize Text for Voice

```python
def optimize_for_voice(text):
    """Optimize text for natural speech"""

    # Replace common abbreviations
    replacements = {
        "e.g.": "for example",
        "i.e.": "that is",
        "etc.": "and so on",
        "Mr.": "Mister",
        "Mrs.": "Misses",
        "Dr.": "Doctor",
        "@": " at ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Add pauses for readability
    text = text.replace(". ", ". ... ")  # Longer pause after sentences

    # Handle email addresses
    import re
    emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    for email in emails:
        # Spell out email clearly
        readable = email.replace("@", " at ").replace(".", " dot ")
        text = text.replace(email, readable)

    return text

# Usage
original = "Contact john.doe@example.com for more info, e.g., product details."
optimized = optimize_for_voice(original)
print(optimized)
# "Contact john dot doe at example dot com for more info, for example, product details. ... "
```

### 2. Handle Errors Gracefully

```python
def safe_text_to_speech(text):
    """Generate speech with error handling"""

    try:
        result = composio.tools.execute(
            action="ELEVENLABS_TEXT_TO_SPEECH",
            params={
                "text": text,
                "voice_id": "21m00Tcm4TlvDq8ikWAM",
            },
            entity_id="default_user"
        )

        return {"success": True, "audio": result['audio']}

    except Exception as e:
        error_msg = str(e)

        if "quota_exceeded" in error_msg:
            return {
                "success": False,
                "error": "Monthly character limit reached",
                "suggestion": "Upgrade plan or wait for next month"
            }
        elif "invalid_api_key" in error_msg:
            return {
                "success": False,
                "error": "Invalid API key",
                "suggestion": "Check ELEVENLABS_API_KEY in .env"
            }
        elif "voice_not_found" in error_msg:
            return {
                "success": False,
                "error": "Voice not available",
                "suggestion": "Use different voice_id"
            }
        else:
            return {
                "success": False,
                "error": str(e)
            }
```

### 3. Cache Voice Files

```python
import hashlib
import os

class VoiceCache:
    def __init__(self, cache_dir="voice_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def get_cache_key(self, text, voice_id):
        """Generate cache key from text and voice"""
        content = f"{text}:{voice_id}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, text, voice_id):
        """Get cached audio if exists"""
        key = self.get_cache_key(text, voice_id)
        cache_file = os.path.join(self.cache_dir, f"{key}.mp3")

        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                return f.read()

        return None

    def set(self, text, voice_id, audio_data):
        """Cache audio data"""
        key = self.get_cache_key(text, voice_id)
        cache_file = os.path.join(self.cache_dir, f"{key}.mp3")

        with open(cache_file, 'wb') as f:
            f.write(audio_data)

# Usage
cache = VoiceCache()

def generate_with_cache(text, voice_id):
    # Check cache first
    cached_audio = cache.get(text, voice_id)
    if cached_audio:
        print("Using cached audio")
        return cached_audio

    # Generate if not cached
    result = composio.tools.execute(
        action="ELEVENLABS_TEXT_TO_SPEECH",
        params={"text": text, "voice_id": voice_id},
        entity_id="default_user"
    )

    audio = result['audio']
    cache.set(text, voice_id, audio)

    return audio
```

---

## Troubleshooting

### API Key Issues

**Problem**: "Invalid API key"
**Solution**:
```bash
# Verify key is correct
echo $ELEVENLABS_API_KEY

# Check key format (should start with xi_)
# Re-generate key from ElevenLabs dashboard if needed
```

### Quota Exceeded

**Problem**: "Quota exceeded" error
**Solution**:
1. Check current usage in ElevenLabs dashboard
2. Wait for monthly reset
3. Upgrade to paid plan
4. Optimize text to use fewer characters

### Audio Quality Issues

**Problem**: Voice sounds robotic
**Solution**:
- Lower stability setting (try 0.5-0.6)
- Increase style setting (try 0.3-0.5)
- Use multilingual model
- Try different voice

**Problem**: Audio cuts off
**Solution**:
- Check text length
- Remove special characters
- Verify output format setting

### Connection Issues

**Problem**: Timeout errors
**Solution**:
```python
# Add timeout and retry
import time

def generate_with_retry(text, max_retries=3):
    for attempt in range(max_retries):
        try:
            result = composio.tools.execute(...)
            return result
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Retry {attempt + 1}/{max_retries}")
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise
```

---

## MCP Server Alternative

Official ElevenLabs MCP server:

```bash
# Install
npm install @elevenlabs/elevenlabs-mcp

# Configure
{
  "mcpServers": {
    "elevenlabs": {
      "command": "npx",
      "args": ["-y", "@elevenlabs/elevenlabs-mcp"],
      "env": {
        "ELEVENLABS_API_KEY": "your_key_here"
      }
    }
  }
}
```

Features same capabilities as Composio integration.

---

## Resources

- ElevenLabs Docs: https://elevenlabs.io/docs
- API Reference: https://elevenlabs.io/docs/api-reference
- Voice Lab: https://elevenlabs.io/voice-lab
- Pricing: https://elevenlabs.io/pricing
- Community: https://discord.gg/elevenlabs

---

## Next Steps

1. Get free API key
2. Test basic text-to-speech
3. Experiment with different voices
4. Implement email draft conversion
5. Integrate with Telegram for delivery
6. Monitor usage and optimize
