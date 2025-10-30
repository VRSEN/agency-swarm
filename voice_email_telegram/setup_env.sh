#!/bin/bash
# Setup environment variables interactively
# Run: bash setup_env.sh

echo "Voice Email Telegram Agency - Environment Setup"
echo "================================================"
echo ""

# Check if .env already exists
if [ -f .env ]; then
    echo "⚠️  Warning: .env file already exists!"
    read -p "Overwrite it? (y/n): " overwrite
    if [ "$overwrite" != "y" ]; then
        echo "Aborted."
        exit 0
    fi
fi

echo "Please enter your API keys:"
echo ""

# OpenAI API Key
read -p "OpenAI API Key (sk-...): " openai_key
echo ""

# Composio API Key
read -p "Composio API Key: " composio_key
echo ""

# Optional: Composio User ID
read -p "Composio User ID (optional, press Enter to skip): " composio_user
echo ""

# Create .env file
cat > .env << EOF
# Voice Email Telegram Agency - Environment Variables
# Generated: $(date)

# Required
OPENAI_API_KEY=$openai_key
COMPOSIO_API_KEY=$composio_key

# Optional
COMPOSIO_USER_ID=$composio_user

# Production (add later)
# TELEGRAM_BOT_TOKEN=
# ELEVENLABS_API_KEY=
# MEM0_API_KEY=
EOF

echo "✅ .env file created successfully!"
echo ""
echo "Your API keys are stored securely in .env"
echo "This file is ignored by git (.gitignore)"
echo ""
echo "To test the agency, run:"
echo "  python agency.py"
