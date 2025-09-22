# Dockerfile for Erni-Foto system
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy application code
COPY src/ ./src/
COPY examples/ ./examples/
COPY .env.example ./.env.example

# Create directories for data and logs
RUN mkdir -p /app/data/downloads /app/data/temp /app/data/processed /app/logs

# Set environment variables
ENV PYTHONPATH=/app/src
ENV ERNI_FOTO_DATA_DIR=/app/data
ENV ERNI_FOTO_LOG_DIR=/app/logs

# Expose port for potential web interface
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from erni_foto import create_agency; agency = create_agency(); print('OK')" || exit 1

# Default command
CMD ["python", "-m", "erni_foto.main", "--help"]
