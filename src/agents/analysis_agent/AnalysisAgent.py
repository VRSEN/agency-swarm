from agency_swarm import Agent
from agency_swarm.src.agents.analysis_agent.tools import TranscriptionTool, MomentDetectionTool, EmotionAnalysisTool

class AnalysisAgent(Agent):
    def __init__(self):
        super().__init__(
            name="AnalysisAgent",
            description="AI agent responsible for analyzing video content and identifying viral moments",
            instructions="instructions.md",
            tools=[TranscriptionTool, MomentDetectionTool, EmotionAnalysisTool]
        ) 