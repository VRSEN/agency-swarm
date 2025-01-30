from agency_swarm.agents.base_agent import BaseAgent
from pathlib import Path
import os
from typing import Dict, Any, List

class ContentAcquisitionAgent(BaseAgent):
    """Agent responsible for acquiring content from various sources."""
    
    def __init__(self):
        """Initialize the Content Acquisition Agent."""
        super().__init__(
            name="ContentAcquisitionAgent",
            description="Responsible for downloading and processing source content",
            tools_folder=str(Path(__file__).parent / "tools"),
            temperature=0.5
        )
        
        # Create downloads directory
        self.downloads_dir = Path("downloads")
        self.downloads_dir.mkdir(exist_ok=True)
    
    def download_video(self, video_url: str, extract_subtitles: bool = True) -> Dict[str, Any]:
        """
        Download a video from YouTube.
        
        Args:
            video_url: URL of the video to download
            extract_subtitles: Whether to extract subtitles
            
        Returns:
            Dict containing download results
        """
        youtube_downloader = self.get_tool("youtube_downloader")
        if not youtube_downloader:
            error_msg = "YouTube downloader tool not found"
            self.log_message(error_msg, level="error")
            raise Exception(error_msg)
            
        try:
            result = youtube_downloader(
                video_url=video_url,
                output_dir=str(self.downloads_dir),
                extract_subtitles=extract_subtitles
            ).run()
            
            self.log_message(f"Successfully downloaded video from {video_url}")
            return result
            
        except Exception as e:
            error_msg = f"Failed to download video: {str(e)}"
            self.log_message(error_msg, level="error")
            raise Exception(error_msg)
    
    def get_tool(self, tool_name: str):
        """Get a tool by name."""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None
    
    def list_downloads(self) -> List[Dict[str, Any]]:
        """List all downloaded videos and their metadata."""
        downloads = []
        for video_file in self.downloads_dir.glob("*.mp4"):
            # Get associated subtitle files
            subtitle_files = list(self.downloads_dir.glob(f"{video_file.stem}*.vtt"))
            
            downloads.append({
                "video_path": str(video_file),
                "subtitle_paths": [str(sub) for sub in subtitle_files],
                "size_mb": round(video_file.stat().st_size / (1024 * 1024), 2)
            })
        
        return downloads

if __name__ == "__main__":
    # Test the agent
    agent = ContentAcquisitionAgent()
    
    # Test video download
    try:
        result = agent.download_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        print(f"Download result: {result}")
        
        # List downloads
        downloads = agent.list_downloads()
        print(f"Current downloads: {downloads}")
    except Exception as e:
        print(f"Error during test: {str(e)}") 