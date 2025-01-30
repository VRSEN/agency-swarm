from agency_swarm.tools.base_tool import BaseTool
from pydantic import Field
import yt_dlp
from pathlib import Path
import os
from typing import Optional, Dict, Any

class YouTubeDownloader(BaseTool):
    """Tool for downloading YouTube videos and extracting subtitles."""
    
    name: str = "youtube_downloader"
    description: str = "Downloads YouTube videos and extracts subtitles using yt-dlp"
    
    video_url: str = Field(..., description="URL of the YouTube video to download")
    output_dir: str = Field(
        default="downloads",
        description="Directory to save downloaded content"
    )
    extract_subtitles: bool = Field(
        default=True,
        description="Whether to extract subtitles"
    )
    subtitle_langs: list = Field(
        default=["en"],
        description="List of subtitle languages to download"
    )
    
    def run(self) -> Dict[str, Any]:
        """
        Download video and extract subtitles using yt-dlp.
        
        Returns:
            Dict containing paths to downloaded video and subtitle files
        """
        self.log_message(f"Starting download of {self.video_url}")
        
        # Create output directory
        output_path = Path(self.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Configure yt-dlp options
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': str(output_path / '%(title)s.%(ext)s'),
            'writesubtitles': self.extract_subtitles,
            'writeautomaticsub': True,
            'subtitleslangs': self.subtitle_langs,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4'
            }]
        }
        
        try:
            # Download video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.video_url, download=True)
                video_path = ydl.prepare_filename(info)
                
                # Get subtitle paths
                subtitle_paths = {}
                if self.extract_subtitles:
                    base_path = Path(video_path).with_suffix('')
                    for lang in self.subtitle_langs:
                        sub_path = f"{base_path}.{lang}.vtt"
                        if os.path.exists(sub_path):
                            subtitle_paths[lang] = sub_path
                
                self.log_message(f"Successfully downloaded video to {video_path}")
                
                return {
                    "video_path": video_path,
                    "subtitle_paths": subtitle_paths,
                    "video_info": {
                        "title": info.get('title'),
                        "duration": info.get('duration'),
                        "view_count": info.get('view_count'),
                        "like_count": info.get('like_count'),
                        "channel": info.get('channel'),
                        "upload_date": info.get('upload_date')
                    }
                }
                
        except Exception as e:
            error_msg = f"Failed to download video: {str(e)}"
            self.log_message(error_msg, level="error")
            raise Exception(error_msg)
            
if __name__ == "__main__":
    # Test the tool
    downloader = YouTubeDownloader(
        video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        output_dir="test_downloads",
        extract_subtitles=True
    )
    result = downloader.run()
    print(f"Download result: {result}") 