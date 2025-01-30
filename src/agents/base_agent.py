from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, Optional

class BaseAgent(ABC):
    """Base class for all agents in the system."""
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the base agent.
        
        Args:
            name: The name of the agent
            config: Optional configuration dictionary
        """
        self.name = name
        self.config = config or {}
        self._setup_logging()
        
    def _setup_logging(self):
        """Set up logging for the agent."""
        self.logger = logging.getLogger(f"{self.__class__.__name__}_{self.name}")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    @abstractmethod
    async def run(self, *args, **kwargs):
        """Main execution method for the agent."""
        pass
    
    def log_info(self, message: str):
        """Log an info message."""
        self.logger.info(message)
    
    def log_error(self, message: str):
        """Log an error message."""
        self.logger.error(message)
    
    def log_warning(self, message: str):
        """Log a warning message."""
        self.logger.warning(message)
        
    def update_config(self, new_config: Dict[str, Any]):
        """Update the agent's configuration."""
        self.config.update(new_config) 