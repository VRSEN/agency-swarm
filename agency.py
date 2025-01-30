from agency_swarm import Agency
from agency_swarm.src.agents.content_acquisition_agent import ContentAcquisitionAgent
from agency_swarm.src.agents.analysis_agent import AnalysisAgent
from agency_swarm.src.agents.creative_agent import CreativeAgent

def create_agency():
    content_acquisition = ContentAcquisitionAgent()
    analysis = AnalysisAgent()
    creative = CreativeAgent()
    
    return Agency(
        agents=[content_acquisition, analysis, creative],
        shared_instructions='./docs/agency_manifesto.md'
    )

if __name__ == '__main__':
    agency = create_agency()
    agency.demo_gradio() 