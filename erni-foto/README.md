# Erni-Foto: AI-Powered Photo Processing System

A comprehensive multi-agent system built with Agency Swarm for automated photo processing and SharePoint integration with AI analysis.

## 🎯 Overview

Erni-Foto is an intelligent photo processing pipeline that:
- Downloads photos from SharePoint source libraries
- Analyzes images using GPT-4.1 Vision AI
- Generates German-language metadata
- Uploads processed photos to target SharePoint libraries
- Provides comprehensive reporting and monitoring

## 🏗️ System Architecture

### Multi-Agent System (6 Specialized Agents)

1. **SharePointMetadataAgent** - SharePoint schema management
2. **PhotoDownloadAgent** - Source photo retrieval  
3. **AIAnalysisAgent** - AI-powered photo analysis
4. **MetadataGeneratorAgent** - Metadata mapping and generation
5. **PhotoUploadAgent** - SharePoint upload management
6. **ReportGeneratorAgent** - Process monitoring and reporting

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- OpenAI API key with GPT-4.1 Vision access
- Microsoft Graph API credentials
- SharePoint Online access

### Installation

```bash
# Clone and setup
git clone <repository-url>
cd erni-foto

# Install dependencies
uv sync --all-extras

# Copy configuration template
cp .env.example .env
# Edit .env with your credentials
```

### Configuration

Edit `.env` file with your credentials:

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# Microsoft Graph API
AZURE_CLIENT_ID=your_client_id
AZURE_CLIENT_SECRET=your_client_secret
AZURE_TENANT_ID=your_tenant_id

# SharePoint Configuration
SHAREPOINT_SITE_URL=https://yourtenant.sharepoint.com/sites/yoursite
SOURCE_LIBRARY_NAME=SourcePhotos
TARGET_LIBRARY_NAME=ProcessedPhotos

# Processing Configuration
BATCH_SIZE=25
MAX_RETRIES=3
IMAGE_MAX_SIZE=2048
```

### Usage

```bash
# Run the complete processing pipeline
uv run python main.py

# Run with custom configuration
uv run python main.py --config custom_config.env

# Process specific date range
uv run python main.py --start-date 2024-01-01 --end-date 2024-01-31
```

## 📁 Project Structure

```
erni-foto/
├── agents/                     # Agent implementations
│   ├── sharepoint_metadata/    # SharePoint schema management
│   ├── photo_download/         # Photo retrieval
│   ├── ai_analysis/           # AI photo analysis
│   ├── metadata_generator/    # Metadata mapping
│   ├── photo_upload/          # SharePoint upload
│   └── report_generator/      # Monitoring & reporting
├── tools/                     # Shared tools and utilities
├── config/                    # Configuration management
├── tests/                     # Test suite
├── docs/                      # Documentation
├── examples/                  # Usage examples
└── main.py                    # Main application entry point
```

## 🔧 Features

- **Batch Processing**: Configurable batch sizes (10-50 photos)
- **AI Analysis**: GPT-4.1 Vision for intelligent photo analysis
- **German Language**: Native German metadata generation
- **Error Recovery**: Comprehensive retry mechanisms
- **Real-time Monitoring**: Progress tracking and reporting
- **Audit Trail**: Complete operation logging
- **Deduplication**: Hash-based duplicate prevention

## 📊 Processing Workflow

1. **Initialization**: Load SharePoint schema and validate connections
2. **Download**: Retrieve photos from source library
3. **Analysis**: AI-powered content analysis and EXIF extraction
4. **Metadata Generation**: Map analysis to SharePoint schema
5. **Upload**: Upload with standardized naming and metadata
6. **Reporting**: Generate comprehensive processing reports

## 🧪 Testing

```bash
# Run all tests
uv run pytest

# Run specific test suite
uv run pytest tests/agents/
uv run pytest tests/integration/

# Run with coverage
uv run pytest --cov=erni_foto
```

## 📈 Performance

- **Throughput**: 100+ photos per batch
- **Success Rate**: >95% upload success
- **Processing Time**: Configurable based on batch size
- **Memory Efficient**: Optimized image handling

## 🔒 Security

- Secure credential management via environment variables
- Microsoft Graph API authentication
- Audit logging for compliance
- Permission management for uploaded files

## 📚 Documentation

- [Agent Architecture](docs/agents.md)
- [API Reference](docs/api.md)
- [Configuration Guide](docs/configuration.md)
- [Troubleshooting](docs/troubleshooting.md)

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.
