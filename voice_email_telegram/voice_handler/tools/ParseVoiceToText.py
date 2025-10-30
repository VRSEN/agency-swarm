import os

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class ParseVoiceToText(BaseTool):
    """
    Converts voice audio files to text using OpenAI's Whisper API.
    Handles various audio formats and provides high-accuracy transcription.
    """

    audio_file_path: str = Field(
        ..., description="Path to the audio file to transcribe (supports mp3, mp4, mpeg, mpga, m4a, wav, webm)"
    )

    language: str = Field(
        default="en",
        description="Language code for transcription (e.g., 'en' for English, 'es' for Spanish). "
        "Use 'auto' for automatic detection.",
    )

    def run(self):
        """
        Transcribes the audio file using OpenAI Whisper API.
        Returns the transcribed text or an error message.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "Error: OPENAI_API_KEY not found in environment variables"

        # Check if file exists
        if not os.path.exists(self.audio_file_path):
            return f"Error: Audio file not found at path: {self.audio_file_path}"

        # Check file size (Whisper has a 25MB limit)
        file_size = os.path.getsize(self.audio_file_path)
        max_size = 25 * 1024 * 1024  # 25MB in bytes
        if file_size > max_size:
            return f"Error: File size ({file_size / 1024 / 1024:.2f}MB) exceeds the 25MB limit"

        try:
            client = OpenAI(api_key=api_key)

            # Open and transcribe the audio file
            with open(self.audio_file_path, "rb") as audio_file:
                # Use whisper-1 model for transcription
                if self.language and self.language != "auto":
                    transcription = client.audio.transcriptions.create(
                        model="whisper-1", file=audio_file, language=self.language
                    )
                else:
                    transcription = client.audio.transcriptions.create(model="whisper-1", file=audio_file)

            # Return the transcribed text
            return transcription.text

        except Exception as e:
            return f"Error during transcription: {str(e)}"


if __name__ == "__main__":
    # Test with a mock file (in production, this would be a real audio file)
    print("Testing ParseVoiceToText...")

    # Note: For testing, you would need an actual audio file
    # This is a demonstration of how to use the tool

    # Create a test audio file path (this would be replaced with actual file)
    test_file = "/tmp/test_voice.mp3"

    # Test 1: File not found
    print("\n1. Test with non-existent file:")
    tool = ParseVoiceToText(audio_file_path="/tmp/nonexistent.mp3")
    print(tool.run())

    # Test 2: Check API key
    print("\n2. Test API key presence:")
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print("API key found (starts with):", api_key[:10] + "...")
    else:
        print("Warning: OPENAI_API_KEY not found")

    # Test 3: Documentation example
    print("\n3. Usage example:")
    print("""
    To use this tool in production:

    1. Download a voice file from Telegram
    2. Save it to a temporary location
    3. Call ParseVoiceToText with the file path:

    tool = ParseVoiceToText(audio_file_path="/path/to/voice.ogg")
    transcript = tool.run()

    Example output: "Send an email to John about the meeting tomorrow at 2 PM"
    """)

    print("\nTest completed! To run with real audio, provide a valid audio file path.")
