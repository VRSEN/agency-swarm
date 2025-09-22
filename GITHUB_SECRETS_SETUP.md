# 🔐 Quick GitHub Secrets Setup for Agency Swarm

## 🚀 1-Minute Setup Guide

### Step 1: Generate Secure Tokens
```bash
# Generate production secrets with setup guide
python3 tools/generate_production_secrets.py --environment production
```

### Step 2: Configure GitHub Repository Secrets

1. **Go to your repository:** `https://github.com/YOUR_USERNAME/YOUR_REPO/settings/secrets/actions`
2. **Click "New repository secret"** for each required secret:

#### Required Secrets:
- `OPENAI_API_KEY` - Get from: https://platform.openai.com/api-keys
- `APP_TOKEN` - Use the generated token from Step 1
- `DOCKER_USERNAME` - Your Docker Hub username
- `DOCKER_PASSWORD` - Get Personal Access Token from: https://hub.docker.com/settings/security

#### Optional Secrets (if using HTTPS/alerts):
- `SSL_KEYFILE_CONTENT` - Base64 encoded SSL private key
- `SSL_CERTFILE_CONTENT` - Base64 encoded SSL certificate  
- `ALERT_WEBHOOK_URL` - Slack/Discord webhook for error alerts
- `DATABASE_URL` - Database connection string

### Step 3: Test Configuration
```bash
# Test all secrets automatically
gh workflow run test-production-secrets.yml

# Or manually test OpenAI API
curl -H "Authorization: Bearer YOUR_OPENAI_KEY" https://api.openai.com/v1/models
```

---

## 🔒 Security Best Practices

- ✅ **Use strong tokens:** Generated tokens are 32+ characters
- ✅ **Rotate regularly:** Every 90 days recommended
- ✅ **Environment separation:** Different secrets for staging/production
- ✅ **Never commit secrets:** Always use GitHub repository secrets
- ✅ **Monitor usage:** Check GitHub audit logs regularly

---

## 🧪 Testing Your Setup

After configuring secrets, the automated workflow will test:
- ✅ OpenAI API connectivity and authentication
- ✅ Docker Hub access and authentication
- ✅ SSL certificate format validation (if provided)
- ✅ Alert webhook functionality (if provided)
- ✅ Secret format validation and security checks

---

## 📚 Complete Documentation

For detailed setup instructions, troubleshooting, and advanced configuration:
- **[Complete Setup Guide](docs/github_secrets_setup.md)** - Detailed instructions
- **[Production Deployment](docs/production_deployment.md)** - Full deployment guide
- **[Monitoring Setup](docs/production_deployment.md#monitoring-and-health-checks)** - Health checks and metrics

---

## 🎯 Ready for Production!

Once all secrets are configured and tests pass, your Agency Swarm deployment will have:
- 🔐 Secure API authentication
- 📊 Production monitoring and health checks
- 🚨 Error alerting and logging
- 🔒 SSL/TLS support (if configured)
- 🐳 Automated Docker deployment
- 📈 Performance metrics and observability

**Your Agency Swarm project is now production-ready!** 🚀
