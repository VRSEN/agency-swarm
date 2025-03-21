from langchain.callbacks.base import BaseCallbackHandler
import logging

logger = logging.getLogger(__name__)

class AgentOpsCallbackHandler(BaseCallbackHandler):
    """Callback handler that integrates with AgentOps."""
    
    def __init__(self, **kwargs):
        super().__init__()
        import agentops
        self.agentops = agentops
        if "api_key" in kwargs:
            agentops.init(kwargs.get("api_key"))
        else:
            agentops.init()
        
        self.tags = kwargs.get("tags", [])
        
    def on_llm_start(self, serialized, prompts, **kwargs):
        """Record when LLM starts generating"""
        try:
            self.agentops.track_agent(
                prompts=prompts,
                tags=self.tags
            )
        except Exception as e:
            logger.warning(f"Failed to track LLM start in AgentOps: {e}")
        
    def on_tool_start(self, serialized, input_str, **kwargs):
        """Record when a tool starts execution"""
        try:
            self.agentops.track_tool(
                tool_name=serialized.get("name", "unknown_tool"),
                input=input_str,
                tags=self.tags
            )
        except Exception as e:
            logger.warning(f"Failed to track tool start in AgentOps: {e}")