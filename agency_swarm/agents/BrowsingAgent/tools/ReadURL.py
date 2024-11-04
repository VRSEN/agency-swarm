import time

from pydantic import Field

from agency_swarm.tools import BaseTool
from .util.selenium import get_web_driver, set_web_driver


class ReadURL(BaseTool):
    """
This tool reads a single URL and opens it in your current browser window. For each new source, either navigate directly to a URL that you believe contains the answer to the user's question or perform a Google search (e.g., 'https://google.com/search?q=search') if necessary. 

If you are unsure of the direct URL, do not guess. Instead, use the ClickElement tool to click on links that might contain the desired information on the current web page.

Note: This tool only supports opening one URL at a time. The previous URL will be closed when you open a new one.
    """
    chain_of_thought: str = Field(
        ..., description="Think step-by-step about where you need to navigate next to find the necessary information.",
        exclude=True
    )
    url: str = Field(
        ..., description="URL of the webpage.", examples=["https://google.com/search?q=search"]
    )

    class ToolConfig:
        one_call_at_a_time: bool = True

    def run(self):
        wd = get_web_driver()

        wd.get(self.url)

        time.sleep(2)

        set_web_driver(wd)

        self._shared_state.set("elements_highlighted", "")

        return "Current URL is: " + wd.current_url + "\n" + "Please output '[send screenshot]' next to analyze the current web page or '[highlight clickable elements]' for further navigation."


if __name__ == "__main__":
    tool = ReadURL(url="https://google.com")
    print(tool.run())