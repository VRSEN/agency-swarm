# Production Deployment Guide

This guide covers deploying Agency Swarm in production with comprehensive monitoring, security, and reliability features.

## 🚀 Quick Start

### 1. Environment Setup

Create a `.env` file with required configuration:

```bash
# Required
OPENAI_API_KEY=your_openai_api_key_here
APP_TOKEN=your_secure_app_token_here

# Optional - Production Settings
LOG_LEVEL=INFO
WORKERS=4
MAX_CONNECTIONS=1000
CORS_ORIGINS=https://yourdomain.com,https://api.yourdomain.com
ENABLE_RATE_LIMITING=true
RATE_LIMIT_PER_MINUTE=60

# SSL/TLS (recommended for production)
SSL_KEYFILE=/path/to/ssl/key.pem
SSL_CERTFILE=/path/to/ssl/cert.pem
```

### 2. Basic Production Server

```python
from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi import run_fastapi

def create_agency(load_threads_callback=None, save_threads_callback=None):
    agent = Agent(name="ProductionAgent", instructions="Your instructions here")
    return Agency(agent, load_threads_callback=load_threads_callback, 
                  save_threads_callback=save_threads_callback)

# Production configuration
run_fastapi(
    agencies={"api": create_agency},
    host="0.0.0.0",
    port=8000,
    enable_monitoring=True,      # Health checks and metrics
    enable_rate_limiting=True,   # DDoS protection
    rate_limit_per_minute=60,    # Requests per minute per IP
    cors_origins=["https://yourdomain.com"],  # Restrict CORS
    app_token_env="APP_TOKEN",   # Enable authentication
)
```

## 📊 Monitoring Endpoints

### Health Check Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `/health` | Basic health check for load balancers | `200` (healthy) or `503` (unhealthy) |
| `/ready` | Detailed readiness check for Kubernetes | Comprehensive health information |
| `/metrics` | Performance metrics and statistics | Request counts, response times, errors |

### Health Check Response Examples

**Healthy Service (`/health`):**
```json
{
  "status": "healthy",
  "timestamp": 1703123456.789,
  "version": "1.0.2"
}
```

**Detailed Readiness (`/ready`):**
```json
{
  "ready": true,
  "status": "healthy",
  "timestamp": 1703123456.789,
  "duration_ms": 45.23,
  "checks": [
    {
      "name": "basic_service",
      "status": "healthy",
      "message": "Service is responding",
      "duration_ms": 1.23
    },
    {
      "name": "openai_api",
      "status": "healthy", 
      "message": "OpenAI API is accessible",
      "duration_ms": 234.56
    },
    {
      "name": "system_resources",
      "status": "healthy",
      "message": "System resources within normal limits",
      "duration_ms": 8.90,
      "details": {
        "cpu_percent": 45.2,
        "memory_percent": 62.1,
        "disk_percent": 78.3
      }
    }
  ],
  "summary": {
    "total_checks": 3,
    "healthy": 3,
    "degraded": 0,
    "unhealthy": 0
  }
}
```

## 🔒 Security Features

### Authentication
- Bearer token authentication via `Authorization: Bearer <token>` header
- Configurable via `APP_TOKEN` environment variable
- Automatic 401 responses for invalid/missing tokens

### Security Headers
Automatically added to all responses:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy: default-src 'self'`

### Rate Limiting
- Token bucket algorithm per client IP
- Configurable requests per minute
- Automatic 429 responses when exceeded
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`

### CORS Protection
- Configurable allowed origins
- Restricted methods and headers in production
- Credential support when needed

## 📈 Performance Monitoring

### Metrics Collected
- **Request Metrics**: Count, error rate, requests per second
- **Response Times**: p50, p95, p99 percentiles and averages
- **System Resources**: CPU, memory, disk usage
- **Service Health**: Uptime, dependency status
- **Error Tracking**: 4xx/5xx error counts and rates

### Performance Headers
Added to all responses:
- `X-Response-Time: 123.45ms` - Request processing time

## 🏥 Health Monitoring

### System Resource Thresholds

| Resource | Warning | Critical |
|----------|---------|----------|
| CPU Usage | 80% | 95% |
| Memory Usage | 80% | 95% |
| Disk Usage | 85% | 95% |

### Health Status Levels
- **healthy**: All systems operational
- **degraded**: Some issues but service functional  
- **unhealthy**: Critical issues, service may not work properly

### External Dependency Checks
- **OpenAI API**: Connectivity and authentication
- **File Storage**: Access and write permissions
- **Network**: Latency and connectivity tests

## 📝 Structured Logging

### Log Format
JSON structured logs for easy parsing:

```json
{
  "timestamp": "2024-01-01T12:00:00.000Z",
  "level": "INFO",
  "logger": "agency_swarm.requests",
  "message": "Request: POST /api/response -> 200",
  "module": "metrics_middleware",
  "function": "dispatch",
  "line": 45,
  "extra": {
    "request_method": "POST",
    "request_path": "/api/response",
    "response_status": 200,
    "response_time_ms": 1234.56,
    "client_ip": "192.168.1.100",
    "user_agent": "Mozilla/5.0..."
  }
}
```

### Log Categories
- `agency_swarm.requests` - HTTP request/response logs
- `agency_swarm.agents` - Agent interaction logs
- `agency_swarm.system` - System events and errors
- `agency_swarm.alerts` - Critical alerts and notifications

### Log Files
- `logs/agency_swarm.log` - Main application log (rotated)
- `logs/errors.log` - Error-only log for quick debugging
- Automatic rotation at 100MB with 10 backup files

## 🚨 Error Handling & Alerting

### Error Tracking
- Automatic error counting and rate monitoring
- Alert threshold: 10 errors within 5 minutes
- Stack trace capture for debugging
- Structured error logging with context

### Alert Integration Points
Ready for integration with:
- Slack/Discord webhooks
- Email notifications  
- PagerDuty/Opsgenie
- SMS alerts
- Custom webhook endpoints

## 🐳 Docker Deployment

### Dockerfile Example
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose Example
```yaml
version: '3.8'

services:
  agency-swarm:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - APP_TOKEN=${APP_TOKEN}
      - LOG_LEVEL=INFO
      - WORKERS=4
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - agency-swarm
    restart: unless-stopped
```

## ☸️ Kubernetes Deployment

### Deployment YAML
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agency-swarm
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agency-swarm
  template:
    metadata:
      labels:
        app: agency-swarm
    spec:
      containers:
      - name: agency-swarm
        image: your-registry/agency-swarm:latest
        ports:
        - containerPort: 8000
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: agency-secrets
              key: openai-api-key
        - name: APP_TOKEN
          valueFrom:
            secretKeyRef:
              name: agency-secrets
              key: app-token
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
```

## 🔧 Production Checklist

### Pre-Deployment
- [ ] Environment variables configured
- [ ] SSL certificates installed
- [ ] Authentication tokens generated
- [ ] CORS origins restricted
- [ ] Rate limiting configured
- [ ] Log directory permissions set
- [ ] Health check endpoints tested

### Post-Deployment
- [ ] Health checks responding correctly
- [ ] Metrics collection working
- [ ] Logs being written properly
- [ ] Rate limiting functional
- [ ] SSL/TLS working
- [ ] Authentication working
- [ ] Performance within acceptable limits

### Monitoring Setup
- [ ] Health check monitoring configured
- [ ] Error rate alerts set up
- [ ] Performance metrics dashboard created
- [ ] Log aggregation configured
- [ ] Backup and recovery procedures tested

## 🚨 Troubleshooting

### Common Issues

**Health Check Failing**
- Check OpenAI API key validity
- Verify system resource availability
- Check network connectivity
- Review error logs in `logs/errors.log`

**High Response Times**
- Check system resource usage
- Review OpenAI API response times
- Consider scaling horizontally
- Optimize agent instructions

**Rate Limiting Issues**
- Adjust `RATE_LIMIT_PER_MINUTE` setting
- Implement client-side rate limiting
- Consider IP whitelisting for trusted clients
- Monitor rate limit metrics

**Authentication Failures**
- Verify `APP_TOKEN` environment variable
- Check token format in requests
- Review authentication logs
- Ensure HTTPS for token security

This production deployment guide ensures your Agency Swarm deployment is secure, monitored, and ready for production workloads.
