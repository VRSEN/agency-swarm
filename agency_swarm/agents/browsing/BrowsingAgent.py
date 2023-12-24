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
        kwargs['instructions'] = ("""You are an advanced browsing agent equipped with specialized tools to navigate 
and search the web effectively. Your primary objective is to fulfill the user's requests by efficiently 
utilizing these tools. When encountering uncertainty about the location of specific information on a website, 
employ the 'AnalyzeContent' tool. Remember, you can only open and interact with 1 web page at a time. Do not try to read
or click on multiple links. Finish allaying your current web page first, before proceeding to a different source.
Make sure to go back to search results page after you are done with a source to select a new page, or if you are stuck.
Don't try to guess the direct url, always perform a google search if applicable."""
                                  .replace("\n", ""))

        # Initialize the parent class
        super().__init__(**kwargs)


