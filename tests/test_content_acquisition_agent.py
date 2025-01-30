import pytest
from pathlib import Path
from agency_swarm.agents.content_acquisition.content_acquisition_agent import ContentAcquisitionAgent

@pytest.fixture
def agent():
    """Create a Content Acquisition Agent instance for testing."""
    return ContentAcquisitionAgent()

@pytest.fixture
def test_video_url():
    """Return a test video URL."""
    return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

def test_agent_initialization(agent):
    """Test that the agent initializes correctly."""
    assert agent.name == "ContentAcquisitionAgent"
    assert agent.description is not None
    assert len(agent.tools) > 0
    assert Path(agent.downloads_dir).exists()

def test_get_tool(agent):
    """Test that the agent can retrieve tools by name."""
    youtube_downloader = agent.get_tool("youtube_downloader")
    assert youtube_downloader is not None
    assert youtube_downloader.name == "youtube_downloader"

def test_download_video(agent, test_video_url):
    """Test video downloading functionality."""
    result = agent.download_video(test_video_url)
    
    assert result is not None
    assert "video_path" in result
    assert "subtitle_paths" in result
    assert "video_info" in result
    
    video_path = Path(result["video_path"])
    assert video_path.exists()
    assert video_path.suffix == ".mp4"

def test_list_downloads(agent, test_video_url):
    """Test listing downloaded videos."""
    # First download a video
    agent.download_video(test_video_url)
    
    # List downloads
    downloads = agent.list_downloads()
    
    assert len(downloads) > 0
    assert all(isinstance(d, dict) for d in downloads)
    assert all("video_path" in d for d in downloads)
    assert all("subtitle_paths" in d for d in downloads)
    assert all("size_mb" in d for d in downloads)

def test_invalid_video_url(agent):
    """Test handling of invalid video URLs."""
    with pytest.raises(Exception):
        agent.download_video("https://youtube.com/invalid_url") 