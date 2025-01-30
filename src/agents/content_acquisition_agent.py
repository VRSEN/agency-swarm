import os
from typing import Dict, Any, List, Optional
import yt_dlp
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from .base_agent import BaseAgent

class ContentAcquisitionAgent(BaseAgent):
    """Agent responsible for downloading and monitoring YouTube content."""
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.youtube = None
        self._setup_youtube_api()
        self.download_path = self.config.get('download_path', 'downloads')
        os.makedirs(self.download_path, exist_ok=True)
        
    def _setup_youtube_api(self):
        """Set up the YouTube API client."""
        if 'youtube_api_key' in self.config:
            self.youtube = build('youtube', 'v3', 
                               developerKey=self.config['youtube_api_key'])
            
    async def run(self, video_url: str) -> Dict[str, Any]:
        """
        Download a YouTube video and extract information.
        
        Args:
            video_url: URL of the YouTube video to process
            
        Returns:
            Dict containing video information and local file path
        """
        self.log_info(f"Processing video: {video_url}")
        
        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(self.download_path, '%(id)s.%(ext)s'),
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitlesformat': 'srt',
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                
            video_path = os.path.join(
                self.download_path, 
                f"{info['id']}.{info['ext']}"
            )
            
            result = {
                'video_id': info['id'],
                'title': info['title'],
                'duration': info['duration'],
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'local_path': video_path,
                'download_time': datetime.now().isoformat(),
                'subtitles_path': self._get_subtitles_path(info)
            }
            
            self.log_info(f"Successfully downloaded video: {info['title']}")
            return result
            
        except Exception as e:
            self.log_error(f"Error downloading video: {str(e)}")
            raise
            
    def _get_subtitles_path(self, info: Dict[str, Any]) -> Optional[str]:
        """Get the path to the downloaded subtitles file."""
        base_path = os.path.join(self.download_path, info['id'])
        potential_paths = [
            f"{base_path}.en.srt",
            f"{base_path}.auto.en.srt"
        ]
        
        for path in potential_paths:
            if os.path.exists(path):
                return path
        return None
        
    async def monitor_channel(self, channel_id: str) -> List[str]:
        """
        Monitor a YouTube channel for new uploads.
        
        Args:
            channel_id: ID of the YouTube channel to monitor
            
        Returns:
            List of new video URLs
        """
        if not self.youtube:
            self.log_warning("YouTube API not configured. Skipping channel monitoring.")
            return []
            
        try:
            request = self.youtube.search().list(
                part="id,snippet",
                channelId=channel_id,
                order="date",
                maxResults=10
            )
            response = request.execute()
            
            video_urls = []
            for item in response.get('items', []):
                if item['id']['kind'] == 'youtube#video':
                    video_urls.append(
                        f"https://www.youtube.com/watch?v={item['id']['videoId']}"
                    )
            
            return video_urls
            
        except Exception as e:
            self.log_error(f"Error monitoring channel: {str(e)}")
            return [] 