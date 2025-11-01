#!/usr/bin/env python3
"""
Test Gmail via Composio Python SDK
"""
import os
from dotenv import load_dotenv

load_dotenv()

try:
    from composio import Composio

    print("=" * 80)
    print("GMAIL TEST VIA COMPOSIO PYTHON SDK")
    print("=" * 80)

    # Initialize Composio
    api_key = os.getenv("COMPOSIO_API_KEY")
    entity_id = os.getenv("GMAIL_ENTITY_ID")
    gmail_account = os.getenv("GMAIL_ACCOUNT")
    connection_id = os.getenv("GMAIL_CONNECTION_ID")

    print(f"\nEntity ID: {entity_id}")
    print(f"Connection ID: {connection_id}")
    print(f"Gmail Account: {gmail_account}")

    # Create Composio client
    client = Composio(api_key=api_key)

    print("\n" + "-" * 80)
    print("Testing Gmail Send...")
    print("-" * 80)

    # Execute send email action
    result = client.tools.execute(
        "GMAIL_SEND_EMAIL",  # slug parameter
        {  # arguments parameter
            "recipient_email": gmail_account,
            "subject": "MTL Craft Cocktails - SDK Test ✅",
            "body": """Hello from MTL Craft Cocktails!

This is a test email sent via Composio Python SDK.

System Components:
✅ Composio Python SDK v0.9.0
✅ Gmail OAuth Integration
✅ Entity-based Authentication

If you're reading this, the SDK integration works!

---
Powered by Voice Email Telegram Agency
Test Date: October 31, 2025
""",
            "is_html": False
        },
        user_id=entity_id,  # Use entity_id as user_id
        dangerously_skip_version_check=True  # Skip version check for testing
    )

    print("\n✅ SUCCESS!")
    print(f"Result: {result}")
    print("\n" + "=" * 80)
    print("📧 CHECK YOUR INBOX: info@mtlcraftcocktails.com")
    print("=" * 80)
    
except ImportError as e:
    print(f"\n❌ Import Error: {e}")
    print("\nComposio SDK might not be installed correctly.")
    print("Try: pip install composio-openai")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
