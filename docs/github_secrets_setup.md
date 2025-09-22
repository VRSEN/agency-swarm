# 🔐 GitHub Repository Secrets Configuration

Complete guide for setting up GitHub repository secrets for Agency Swarm production deployment and CI/CD workflows.

## 📋 Required Secrets Overview

### Critical Production Secrets
| Secret Name | Purpose | Example Value | Required |
|-------------|---------|---------------|----------|
| `OPENAI_API_KEY` | OpenAI API access for agents | `sk-proj-...` | ✅ Yes |
| `APP_TOKEN` | API authentication token | `prod_abc123...` | ✅ Yes |
| `DOCKER_USERNAME` | Docker Hub registry access | `your_username` | ✅ Yes |
| `DOCKER_PASSWORD` | Docker Hub authentication | `dckr_pat_...` | ✅ Yes |

### Optional Production Secrets
| Secret Name | Purpose | Example Value | Required |
|-------------|---------|---------------|----------|
| `SSL_KEYFILE_CONTENT` | SSL private key (base64) | `LS0tLS1CRUdJTi...` | 🔶 Optional |
| `SSL_CERTFILE_CONTENT` | SSL certificate (base64) | `LS0tLS1CRUdJTi...` | 🔶 Optional |
| `ALERT_WEBHOOK_URL` | Error alerts webhook | `https://hooks.slack.com/...` | 🔶 Optional |
| `DATABASE_URL` | Database connection | `postgresql://user:pass@host/db` | 🔶 Optional |

---

## 🛠️ Step-by-Step Setup Guide

### Step 1: Access Repository Settings

1. Navigate to your GitHub repository
2. Click **Settings** tab (requires admin access)
3. In the left sidebar, click **Secrets and variables**
4. Select **Actions**

### Step 2: Add Required Secrets

#### 🔑 OPENAI_API_KEY
```bash
# Get your API key from: https://platform.openai.com/api-keys
# Format: sk-proj-... (starts with sk-proj- for project keys)
```
- Click **New repository secret**
- Name: `OPENAI_API_KEY`
- Value: Your OpenAI API key
- Click **Add secret**

#### 🛡️ APP_TOKEN
```bash
# Generate a secure token (32+ characters recommended)
# Use: openssl rand -hex 32
# Or: python -c "import secrets; print(secrets.token_urlsafe(32))"
```
- Name: `APP_TOKEN`
- Value: Your generated secure token
- **Important:** Save this token securely - you'll need it for API calls

#### 🐳 DOCKER_USERNAME
```bash
# Your Docker Hub username
```
- Name: `DOCKER_USERNAME`
- Value: Your Docker Hub username

#### 🐳 DOCKER_PASSWORD
```bash
# Docker Hub password or Personal Access Token (recommended)
# Create PAT at: https://hub.docker.com/settings/security
```
- Name: `DOCKER_PASSWORD`
- Value: Your Docker Hub password or access token

### Step 3: Add Optional Secrets (if needed)

#### 🔒 SSL Certificate Secrets
```bash
# Convert SSL files to base64
base64 -w 0 /path/to/ssl/private.key > keyfile_base64.txt
base64 -w 0 /path/to/ssl/certificate.crt > certfile_base64.txt
```
- Name: `SSL_KEYFILE_CONTENT`
- Value: Base64 encoded private key content
- Name: `SSL_CERTFILE_CONTENT`
- Value: Base64 encoded certificate content

#### 📢 Alert Webhook (Slack/Discord)
```bash
# Slack webhook: https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX
# Discord webhook: https://discord.com/api/webhooks/123456789/abcdefghijklmnop
```
- Name: `ALERT_WEBHOOK_URL`
- Value: Your webhook URL

#### 🗄️ Database Connection
```bash
# PostgreSQL: postgresql://username:password@hostname:port/database
# MySQL: mysql://username:password@hostname:port/database
# SQLite: sqlite:///path/to/database.db
```
- Name: `DATABASE_URL`
- Value: Your database connection string

---

## 🔍 Verification and Testing

### Step 1: Verify Secrets Are Set
```bash
# Check in repository Settings → Secrets and variables → Actions
# You should see all required secrets listed (values are hidden)
```

### Step 2: Test with GitHub Actions
Create `.github/workflows/test-secrets.yml`:
```yaml
name: Test Secrets Configuration
on:
  workflow_dispatch:  # Manual trigger for testing

jobs:
  test-secrets:
    runs-on: ubuntu-latest
    steps:
      - name: Check Required Secrets
        run: |
          echo "Testing secret availability..."
          [ -n "${{ secrets.OPENAI_API_KEY }}" ] && echo "✅ OPENAI_API_KEY is set"
          [ -n "${{ secrets.APP_TOKEN }}" ] && echo "✅ APP_TOKEN is set"
          [ -n "${{ secrets.DOCKER_USERNAME }}" ] && echo "✅ DOCKER_USERNAME is set"
          [ -n "${{ secrets.DOCKER_PASSWORD }}" ] && echo "✅ DOCKER_PASSWORD is set"
```

### Step 3: Test Production Deployment
```bash
# After deployment, test monitoring endpoints
curl -H "Authorization: Bearer $APP_TOKEN" https://your-domain.com/health
curl -H "Authorization: Bearer $APP_TOKEN" https://your-domain.com/ready
curl -H "Authorization: Bearer $APP_TOKEN" https://your-domain.com/metrics
```

---

## 🔐 Security Best Practices

### Token Generation
```bash
# Generate secure APP_TOKEN
openssl rand -hex 32

# Or using Python
python3 -c "import secrets; print('prod_' + secrets.token_urlsafe(32))"
```

### Secret Rotation Schedule
- **API Keys:** Every 90 days
- **APP_TOKEN:** Every 60 days
- **Docker Credentials:** Every 180 days
- **SSL Certificates:** Before expiration

### Environment Separation
```bash
# Use different secrets for different environments
OPENAI_API_KEY_STAGING    # For staging environment
OPENAI_API_KEY_PROD       # For production environment
APP_TOKEN_STAGING         # For staging API access
APP_TOKEN_PROD           # For production API access
```

### Access Control
- ✅ Only repository admins can view/edit secrets
- ✅ Secrets are encrypted at rest
- ✅ Secrets are masked in workflow logs
- ✅ Use least-privilege principle for API keys

---

## 🚨 Troubleshooting

### Common Issues

#### Secret Not Found Error
```bash
# Error: Secret OPENAI_API_KEY not found
# Solution: Check secret name spelling (case-sensitive)
```

#### Invalid API Key Format
```bash
# Error: Invalid OpenAI API key format
# Solution: Ensure key starts with 'sk-proj-' or 'sk-'
```

#### Docker Authentication Failed
```bash
# Error: Docker login failed
# Solution: Use Personal Access Token instead of password
```

#### SSL Certificate Issues
```bash
# Error: SSL certificate validation failed
# Solution: Verify base64 encoding and certificate chain
```

### Debug Commands
```bash
# Test OpenAI API key locally
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models

# Test Docker Hub access
docker login -u $DOCKER_USERNAME -p $DOCKER_PASSWORD

# Validate SSL certificate
openssl x509 -in certificate.crt -text -noout
```

---

## 📚 Related Documentation

- [Production Deployment Guide](./production_deployment.md)
- [Monitoring Setup](./production_deployment.md#monitoring-and-health-checks)
- [Security Configuration](./production_deployment.md#security-configuration)
- [Docker Deployment](./production_deployment.md#docker-deployment)
- [Kubernetes Deployment](./production_deployment.md#kubernetes-deployment)

---

## ✅ Checklist

Before going to production, ensure:

- [ ] All required secrets are configured in GitHub repository
- [ ] APP_TOKEN is strong and securely generated (32+ characters)
- [ ] OPENAI_API_KEY has sufficient credits and proper permissions
- [ ] Docker credentials allow pushing to your registry
- [ ] SSL certificates are valid and properly encoded (if using HTTPS)
- [ ] Alert webhook is configured and tested (if using alerts)
- [ ] Database connection string is valid (if using database)
- [ ] Secrets are documented in your team's secure password manager
- [ ] Secret rotation schedule is established
- [ ] Production deployment pipeline is tested with secrets

**🎯 Ready for Production!** Once all secrets are configured and tested, your Agency Swarm deployment will have secure access to all required services.
