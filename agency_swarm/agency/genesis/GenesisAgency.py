from agency_swarm import Agency
from .AgentCreator import AgentCreator
from agency_swarm.agents.browsing import BrowsingAgent
from .GenesisCEO import GenesisCEO
from .OpenAPICreator import OpenAPICreator
from .ToolCreator import ToolCreator

new_agency_path = None


class GenesisAgency(Agency):
    def __init__(self, **kwargs):

        if 'agency_chart' not in kwargs:
            agent_creator = AgentCreator()
            genesis_ceo = GenesisCEO()
            tool_creator = ToolCreator()
            openapi_creator = OpenAPICreator()
            browsing_agent = BrowsingAgent()

            browsing_agent.instructions += ("""\n
# BrowsingAgent's Primary instructions
1. Browse the web to find the API documentation requested by the user. Prefer searching google directly for this API documentation page.
2. Navigate to the API documentation page and ensure that it contains the necessary API endpoints descriptions. You can use the AnalyzeContent tool to check if the page contains the necessary API descriptions. If not, try perfrom another search in google and keep browsing until you find the right page.
3. If you have confirmed that the page contains the necessary API documentation, export the page with ExportFile tool. Then, send the file_id back to the user along with a brief description of the API.
4. Repeat these steps for each new agent, as requested by the user.
""")

            kwargs['agency_chart'] = [
                genesis_ceo, tool_creator, agent_creator,
                [genesis_ceo, agent_creator],
                [agent_creator, openapi_creator],
                [openapi_creator, browsing_agent],
                [agent_creator, tool_creator],
            ]

        if 'shared_instructions' not in kwargs:
            kwargs['shared_instructions'] = "./manifesto.md"

        super().__init__(**kwargs)
