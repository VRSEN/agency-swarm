from typing import List, Optional, Dict, Any
import logging
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

class BaseAgent:
    """Base class providing common functionality for all agents in the agency-swarm system."""
    
    def __init__(
        self,
        name: str,
        description: str,
        tools_folder: Optional[str] = None,
        temperature: float = 0.5,
        max_tokens: int = 25000
    ):
        """
        Initialize a base agent with common attributes and setup.
        
        Args:
            name: The name of the agent
            description: A brief description of the agent's role
            tools_folder: Path to the folder containing agent-specific tools
            temperature: Temperature setting for LLM responses
            max_tokens: Maximum tokens for LLM context
        """
        self.name = name
        self.description = description
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.tools_folder = tools_folder
        self.tools = []
        
        # Set up logging
        self._setup_logging()
        
        # Load tools if folder specified
        if tools_folder:
            self._load_tools()
    
    def _setup_logging(self):
        """Configure logging for the agent."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger(f"agent.{self.name}")
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
    
    def _load_tools(self):
        """Load tools from the tools directory."""
        if not self.tools_folder:
            return
            
        tools_path = Path(self.tools_folder)
        if not tools_path.exists():
            self.logger.warning(f"Tools folder not found: {tools_path}")
            return
            
        for tool_file in tools_path.glob("*.py"):
            if tool_file.name.startswith("__"):
                continue
            try:
                # Import tool class from file
                module_name = tool_file.stem
                module_path = f"{self.tools_folder}.{module_name}"
                module = __import__(module_path, fromlist=["*"])
                
                # Get the tool class (assumed to be named same as file)
                tool_class = getattr(module, module_name)
                self.tools.append(tool_class)
                self.logger.info(f"Loaded tool: {module_name}")
            except Exception as e:
                self.logger.error(f"Failed to load tool {tool_file}: {str(e)}")
    
    def get_config(self) -> Dict[str, Any]:
        """Get the agent's configuration."""
        return {
            "name": self.name,
            "description": self.description,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "tools": [t.__name__ for t in self.tools]
        }
    
    def log_message(self, message: str, level: str = "info"):
        """Log a message at the specified level."""
        log_func = getattr(self.logger, level.lower())
        log_func(message) 