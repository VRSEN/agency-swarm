from agency_swarm import Agent
from agency_swarm.tools.browsing import Scroll, SendKeys, ClickElement, ReadURL, AnalyzeContent, GoBack, SelectDropdown


class BrowsingAgent(Agent):

    def __init__(self, **kwargs):
        # Initialize tools in kwargs if not present
        if 'tools' not in kwargs:
            kwargs['tools'] = []
        # Add required tools
        kwargs['tools'].extend([Scroll, SendKeys, ClickElement, ReadURL, AnalyzeContent, GoBack, SelectDropdown])

        # Set instructions
        kwargs['instructions'] = """You are a browsing agent. Your task is to use the provided tools and browse the web in order to complete the task provided by the user. If you are unsure where a specific element is located on the website, make sure to use the AnalyzeContent tool to analyze the content of the website before proceeding with further actions."""

        # Initialize the parent class
        super().__init__(**kwargs)


