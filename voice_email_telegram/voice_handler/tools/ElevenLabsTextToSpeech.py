import json
import os

import requests
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class ElevenLabsTextToSpeech(BaseTool):
    """
    Generates high-quality voice audio from text using ElevenLabs API.
    Used to create voice confirmations for email operations.
    """

    text: str = Field(..., description="Text to convert to speech (max 5000 characters for standard voices)")

    voice_id: str = Field(
        default="21m00Tcm4TlvDq8ikWAM",
        description="ElevenLabs voice ID (default is 'Rachel' - professional female voice)",
    )

    model_id: str = Field(
        default="eleven_monolingual_v1",
        description="Model ID: eleven_monolingual_v1 (English) or eleven_multilingual_v2",
    )

    output_path: str = Field(default="/tmp", description="Directory to save the generated audio file")

    def run(self):
        """
        Generates speech audio and saves it to a file.
        Returns JSON string with file path and audio details.
        """
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            return json.dumps({"error": "ELEVENLABS_API_KEY not found in environment variables"})

        if len(self.text) > 5000:
            return json.dumps({"error": f"Text is too long ({len(self.text)} chars). Maximum is 5000 characters."})

        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"

            headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": api_key}

            payload = {
                "text": self.text,
                "model_id": self.model_id,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            }

            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()

            # Create output directory if it doesn't exist
            os.makedirs(self.output_path, exist_ok=True)

            # Generate filename
            import hashlib

            text_hash = hashlib.md5(self.text.encode()).hexdigest()[:8]
            filename = f"elevenlabs_{text_hash}.mp3"
            file_path = os.path.join(self.output_path, filename)

            # Save audio file
            with open(file_path, "wb") as f:
                f.write(response.content)

            file_size = os.path.getsize(file_path)

            result = {
                "success": True,
                "file_path": file_path,
                "file_size": file_size,
                "text_length": len(self.text),
                "voice_id": self.voice_id,
                "model_id": self.model_id,
            }

            return json.dumps(result, indent=2)

        except requests.exceptions.HTTPError as e:
            error_detail = "Unknown error"
            try:
                error_data = e.response.json()
                error_detail = error_data.get("detail", {}).get("message", str(e))
            except json.JSONDecodeError:
                error_detail = str(e)

            return json.dumps({"error": f"ElevenLabs API error: {error_detail}"})
        except requests.exceptions.RequestException as e:
            return json.dumps({"error": f"Failed to connect to ElevenLabs: {str(e)}"})
        except Exception as e:
            return json.dumps({"error": f"Error generating speech: {str(e)}"})


if __name__ == "__main__":
    print("Testing ElevenLabsTextToSpeech...")

    # Test 1: Check for API key
    print("\n1. Check ELEVENLABS_API_KEY:")
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if api_key:
        print(f"API key found (starts with): {api_key[:10]}...")
    else:
        print("Warning: ELEVENLABS_API_KEY not set")

    # Test 2: Generate speech
    print("\n2. Test text-to-speech generation:")
    tool = ElevenLabsTextToSpeech(text="Your email has been sent successfully!", output_path="/tmp/voice_confirmations")
    result = tool.run()
    print(result)

    # Test 3: Longer text
    print("\n3. Test with longer text:")
    tool = ElevenLabsTextToSpeech(
        text="Hello! I wanted to let you know that your email draft is ready for review. "
        "Please check your Telegram messages to approve or reject the draft. Thank you!",
        output_path="/tmp/voice_confirmations",
    )
    result = tool.run()
    print(result)

    # Test 4: Different voice
    print("\n4. Test with different voice ID:")
    tool = ElevenLabsTextToSpeech(
        text="Testing different voice.",
        voice_id="pNInz6obpgDQGcFmaJgB",  # Adam - professional male voice
        output_path="/tmp/voice_confirmations",
    )
    result = tool.run()
    print(result)

    # Test 5: Text too long
    print("\n5. Test with text that's too long:")
    long_text = "This is a test. " * 500  # Make it over 5000 chars
    tool = ElevenLabsTextToSpeech(text=long_text, output_path="/tmp/voice_confirmations")
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nPopular voice IDs:")
    print("- 21m00Tcm4TlvDq8ikWAM: Rachel (professional female)")
    print("- pNInz6obpgDQGcFmaJgB: Adam (professional male)")
    print("- EXAVITQu4vr4xnSDxMaL: Bella (young female)")
    print("\nUsage notes:")
    print("- Generated MP3 file can be sent via TelegramSendVoice")
    print("- Keep text under 5000 characters")
    print("- Voice ID can be found at elevenlabs.io/voice-library")
