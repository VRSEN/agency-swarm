# Agency Swarm

A powerful AI-driven social media content creation and management system that automates the process of creating viral content from long-form videos.

## Features

- Automated YouTube video downloading with timestamp extraction
- AI-powered viral moment detection
- Dynamic video editing and enhancement
- Automated publishing and analytics
- Multi-agent system for scalable content creation

## Prerequisites

- Python 3.8 or higher
- FFmpeg installed on your system
- YouTube Data API v3 credentials
- OpenAI API key

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/agency-swarm.git
cd agency-swarm
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.template .env
```
Edit the `.env` file and add your API keys and configuration values.

## Usage

1. Start the content acquisition process:
```python
from src.agents.content_acquisition_agent import ContentAcquisitionAgent
from src.config.config import Config

# Initialize the agent
config = Config.get_agent_config('content_acquisition')
agent = ContentAcquisitionAgent('content_downloader', config)

# Download a video
video_info = await agent.run('https://youtube.com/watch?v=VIDEO_ID')
```

2. Monitor a channel for new content:
```python
new_videos = await agent.monitor_channel('CHANNEL_ID')
```

## Project Structure

```
agency-swarm/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── CURRENT_STATE.md
│   └── quick_start.md
├── src/
│   └── agents/
│       ├── content_acquisition_agent/
│       │   └── tools/
│       ├── analysis_agent/
│       │   └── tools/
│       └── creative_agent/
│           └── tools/
│               ├── Anim

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
