import os
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration management for the agency swarm."""
    
    @staticmethod
    def get_agent_config(agent_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific agent.
        
        Args:
            agent_name: Name of the agent to get config for
            
        Returns:
            Dictionary containing agent configuration
        """
        base_config = {
            'download_path': os.getenv('DOWNLOAD_PATH', 'downloads'),
            'youtube_api_key': os.getenv('YOUTUBE_API_KEY'),
            'openai_api_key': os.getenv('OPENAI_API_KEY'),
        }
        
        # Agent-specific configurations
        agent_configs = {
            'content_acquisition': {
                'max_video_length': int(os.getenv('MAX_VIDEO_LENGTH', '3600')),
                'supported_formats': ['mp4', 'mkv'],
                'download_subtitles': True,
            },
            'analysis': {
                'whisper_model': os.getenv('WHISPER_MODEL', 'base'),
                'min_segment_length': int(os.getenv('MIN_SEGMENT_LENGTH', '10')),
                'max_segment_length': int(os.getenv('MAX_SEGMENT_LENGTH', '60')),
            },
            'creative': {
                'output_format': os.getenv('OUTPUT_FORMAT', 'mp4'),
                'target_resolution': os.getenv('TARGET_RESOLUTION', '1080x1920'),
                'fps': int(os.getenv('FPS', '30')),
            }
        }
        
        # Merge base config with agent-specific config
        if agent_name in agent_configs:
            base_config.update(agent_configs[agent_name])
            
        return base_config
        
    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        """
        Validate that all required configuration values are present.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            True if config is valid, False otherwise
        """
        required_keys = [
            'youtube_api_key',
            'openai_api_key',
            'download_path'
        ]
        
        return all(key in config and config[key] is not None 
                  for key in required_keys) 