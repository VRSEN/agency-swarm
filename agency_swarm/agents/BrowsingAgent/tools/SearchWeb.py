from duckduckgo_search import DDGS
from agency_swarm.tools import BaseTool
from pydantic import Field

class SearchWeb(BaseTool):
    """
    A tool to search the web using DuckDuckGo and return the results.
    
    This tool takes a search phrase and returns a list of URLs and titles of the search results.
    """
    phrase: str = Field(
        ..., description="The search phrase you want to use. Optimize the search phrase for an internet search engine."
    )

    def run(self):
        """
        Executes the web search using DuckDuckGo and returns a list of results.

        Each result is a dictionary containing 'title' and 'href' keys.
        """
        try:
            with DDGS() as ddgs:
                results = [{'title': r['title'], 'href': r['href']} for r in ddgs.text(self.phrase, max_results=10)]
                return results
        except Exception as e:
            return {"error": str(e)}

# Example usage:
# tool = SearchWeb(phrase="OpenAI GPT-4")
# print(tool.run())
