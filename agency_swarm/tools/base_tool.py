from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
import logging
from pathlib import Path

class BaseTool(BaseModel):
    """Base class for all tools in the agency-swarm system."""
    
    name: str = Field(..., description="Name of the tool")
    description: str = Field(..., description="Description of what the tool does")
    
    def __init__(self, **data):
        """Initialize the tool with logging setup."""
        super().__init__(**data)
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up logging for the tool."""
        log_dir = Path("logs/tools")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(f"tool.{self.name}")
        self.logger.setLevel(logging.INFO)
        
        # File handler
        fh = logging.FileHandler(log_dir / f"{self.name.lower()}.log")
        fh.setLevel(logging.INFO)
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)
    
    def run(self, *args, **kwargs) -> Any:
        """
        Execute the tool's functionality.
        
        This method must be implemented by all tool classes.
        """
        raise NotImplementedError("Tool must implement run method")
    
    def validate_inputs(self, **kwargs) -> bool:
        """
        Validate the inputs before running the tool.
        
        Returns:
            bool: True if inputs are valid, False otherwise
        """
        return True
    
    def get_config(self) -> Dict[str, Any]:
        """Get the tool's configuration."""
        return {
            "name": self.name,
            "description": self.description
        }
    
    def log_message(self, message: str, level: str = "info"):
        """Log a message at the specified level."""
        log_func = getattr(self.logger, level.lower())
        log_func(message) 