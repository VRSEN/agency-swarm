from agency_swarm import Agency
from agency_swarm.agents.browsing import BrowsingAgent
from agency_swarm.agents.genesis import GenesisCEO, AgentCreator
import os

from agency_swarm.agents.genesis import ToolCreator
from agency_swarm.agents.genesis import OpenAPICreator


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
1. Browse the web to find the most relevant API that the requested agent needs in order to perform its role. If you already have an idea of what API to use, search google directly for this API documentation.
2. After finding the right API to use, navigate to its documentation page. Prefer to do this by searching for the API documentation page in google, rather than navigating to the API's website and then finding the documentation page, if possible.
3. Ensure that the current page actually contains the necessary API endpoints descriptions with the AnalyzeContent tool. If you can't find a link to the documentation page, try to search for it in google.
4. If you have confirmed that the page contains the necessary API documentation, export the page with ExportFile tool and send the file_id back to the user along with a brief description of the API.
5. If not, continue browsing the web until you find the right API documentation page.
6. Repeat these steps for each new requested agent.
""")


            kwargs['agency_chart'] = [
                genesis_ceo,
                [genesis_ceo, agent_creator],
                [agent_creator, browsing_agent],
                [agent_creator, openapi_creator],
            ]

        if 'shared_instructions' not in kwargs:
            kwargs['shared_instructions'] = "./manifesto.md"

        super().__init__(**kwargs)
