#!/usr/bin/env python3
"""
Production Secrets Generator for Agency Swarm

This script helps generate secure tokens and provides guidance for setting up
GitHub repository secrets for production deployment.

Usage:
    python tools/generate_production_secrets.py
    python tools/generate_production_secrets.py --environment production
    python tools/generate_production_secrets.py --help
"""

import argparse
import base64
import secrets
import string
import sys
from pathlib import Path
from typing import Dict, List


def generate_secure_token(length: int = 32, prefix: str = "") -> str:
    """Generate a cryptographically secure token."""
    token = secrets.token_urlsafe(length)
    return f"{prefix}{token}" if prefix else token


def generate_app_token(environment: str = "prod") -> str:
    """Generate a secure APP_TOKEN with environment prefix."""
    return generate_secure_token(32, f"{environment}_")


def generate_api_key_placeholder() -> str:
    """Generate a placeholder for API key format validation."""
    return f"sk-proj-{secrets.token_urlsafe(48)}"


def encode_file_to_base64(file_path: str) -> str:
    """Encode a file to base64 for SSL certificate secrets."""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        return base64.b64encode(content).decode('utf-8')
    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        return ""
    except Exception as e:
        print(f"❌ Error encoding file {file_path}: {e}")
        return ""


def validate_openai_key_format(api_key: str) -> bool:
    """Validate OpenAI API key format."""
    return api_key.startswith(('sk-', 'sk-proj-')) and len(api_key) > 20


def generate_docker_credentials_guide() -> Dict[str, str]:
    """Generate guide for Docker Hub credentials."""
    return {
        "DOCKER_USERNAME": "your_dockerhub_username",
        "DOCKER_PASSWORD": "Use Personal Access Token from https://hub.docker.com/settings/security"
    }


def print_secrets_configuration(environment: str = "production") -> None:
    """Print complete secrets configuration guide."""
    
    print(f"""
🔐 GitHub Repository Secrets Configuration
==========================================
Environment: {environment.upper()}

📋 REQUIRED SECRETS (copy these to GitHub repository settings):
""")
    
    # Generate secure tokens
    app_token = generate_app_token(environment[:4])  # prod/stag prefix
    
    required_secrets = {
        "OPENAI_API_KEY": "⚠️  GET FROM: https://platform.openai.com/api-keys",
        "APP_TOKEN": app_token,
        "DOCKER_USERNAME": "⚠️  YOUR DOCKER HUB USERNAME",
        "DOCKER_PASSWORD": "⚠️  GET FROM: https://hub.docker.com/settings/security (use PAT)"
    }
    
    for name, value in required_secrets.items():
        print(f"{name:<20} = {value}")
    
    print(f"""
📋 OPTIONAL SECRETS (add if needed):
""")
    
    optional_secrets = {
        "SSL_KEYFILE_CONTENT": "⚠️  base64 encoded SSL private key",
        "SSL_CERTFILE_CONTENT": "⚠️  base64 encoded SSL certificate", 
        "ALERT_WEBHOOK_URL": "⚠️  Slack/Discord webhook URL",
        "DATABASE_URL": "⚠️  Database connection string"
    }
    
    for name, value in optional_secrets.items():
        print(f"{name:<22} = {value}")
    
    print(f"""
🛠️  SETUP INSTRUCTIONS:
1. Go to: https://github.com/YOUR_USERNAME/YOUR_REPO/settings/secrets/actions
2. Click "New repository secret" for each secret above
3. Copy the exact name and value (secrets are case-sensitive)
4. Test with: gh workflow run test-production-secrets.yml

🔒 SECURITY NOTES:
- APP_TOKEN generated: {app_token}
- Save this token securely - you'll need it for API authentication
- Rotate all secrets every 90 days
- Use different secrets for staging vs production
- Never commit secrets to the repository

🧪 TESTING:
After adding secrets, run the test workflow:
    gh workflow run test-production-secrets.yml

Or manually test OpenAI API:
    curl -H "Authorization: Bearer YOUR_OPENAI_KEY" https://api.openai.com/v1/models
""")


def encode_ssl_files(key_file: str, cert_file: str) -> None:
    """Encode SSL certificate files to base64."""
    print("\n🔒 SSL Certificate Encoding:")
    print("=" * 40)
    
    if key_file:
        key_b64 = encode_file_to_base64(key_file)
        if key_b64:
            print(f"SSL_KEYFILE_CONTENT = {key_b64[:50]}...")
            print(f"Full key saved to: ssl_key_base64.txt")
            with open("ssl_key_base64.txt", "w") as f:
                f.write(key_b64)
    
    if cert_file:
        cert_b64 = encode_file_to_base64(cert_file)
        if cert_b64:
            print(f"SSL_CERTFILE_CONTENT = {cert_b64[:50]}...")
            print(f"Full certificate saved to: ssl_cert_base64.txt")
            with open("ssl_cert_base64.txt", "w") as f:
                f.write(cert_b64)


def validate_existing_secrets() -> None:
    """Validate format of existing secrets from environment."""
    import os
    
    print("\n🔍 Validating Existing Secrets:")
    print("=" * 35)
    
    # Check OpenAI API key
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        if validate_openai_key_format(openai_key):
            print("✅ OPENAI_API_KEY format is valid")
        else:
            print("❌ OPENAI_API_KEY format is invalid (should start with 'sk-')")
    else:
        print("⚠️  OPENAI_API_KEY not found in environment")
    
    # Check APP_TOKEN
    app_token = os.getenv("APP_TOKEN")
    if app_token:
        if len(app_token) >= 32:
            print("✅ APP_TOKEN length is sufficient")
        else:
            print("⚠️  APP_TOKEN is shorter than recommended (32+ characters)")
    else:
        print("⚠️  APP_TOKEN not found in environment")
    
    # Check Docker credentials
    docker_user = os.getenv("DOCKER_USERNAME")
    docker_pass = os.getenv("DOCKER_PASSWORD")
    
    if docker_user:
        print("✅ DOCKER_USERNAME is set")
    else:
        print("⚠️  DOCKER_USERNAME not found in environment")
    
    if docker_pass:
        print("✅ DOCKER_PASSWORD is set")
    else:
        print("⚠️  DOCKER_PASSWORD not found in environment")


def main():
    parser = argparse.ArgumentParser(
        description="Generate secure tokens and setup guide for Agency Swarm production deployment"
    )
    parser.add_argument(
        "--environment", 
        choices=["staging", "production"], 
        default="production",
        help="Environment for token generation (default: production)"
    )
    parser.add_argument(
        "--ssl-key", 
        help="Path to SSL private key file for base64 encoding"
    )
    parser.add_argument(
        "--ssl-cert", 
        help="Path to SSL certificate file for base64 encoding"
    )
    parser.add_argument(
        "--validate", 
        action="store_true",
        help="Validate existing secrets from environment variables"
    )
    parser.add_argument(
        "--token-only", 
        action="store_true",
        help="Generate only APP_TOKEN without full guide"
    )
    
    args = parser.parse_args()
    
    if args.validate:
        validate_existing_secrets()
        return
    
    if args.token_only:
        token = generate_app_token(args.environment[:4])
        print(f"APP_TOKEN = {token}")
        return
    
    # Generate full configuration guide
    print_secrets_configuration(args.environment)
    
    # Encode SSL files if provided
    if args.ssl_key or args.ssl_cert:
        encode_ssl_files(args.ssl_key or "", args.ssl_cert or "")
    
    print(f"""
🎯 NEXT STEPS:
1. Copy the APP_TOKEN to your password manager
2. Get your OpenAI API key from https://platform.openai.com/api-keys
3. Set up Docker Hub Personal Access Token
4. Add all secrets to GitHub repository settings
5. Run the test workflow to verify configuration
6. Deploy to {args.environment} environment

🚀 Ready for production deployment!
""")


if __name__ == "__main__":
    main()
