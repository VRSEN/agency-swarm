import time

from pydantic import Field

from agency_swarm.tools import BaseTool
from .util.selenium import get_web_driver, set_web_driver


class ReadURL(BaseTool):
    """
This tool reads a single URL and opens it in your current browser window. For each new source, go to a direct URL
that you think might contain the answer to the user's question or perform a google search like
'https://google.com/search?q=search' if applicable. Otherwise, don't try to guess the direct url, use ClickElement tool
to click on the link that you think might contain the desired information on the current web page.
Remember, this tool only supports opening 1 URL at a time. Previous URL will be closed when you open a new one.
    """
    chain_of_thought: str = Field(
        ..., description="Think step-by-step about where you need to navigate next to find the necessary information.",
        exclude=True
    )
    url: str = Field(
        ..., description="URL of the webpage.", examples=["https://google.com/search?q=search"]
    )
    one_call_at_a_time: bool = True


    def run(self):
        wd = get_web_driver()

        wd.get(self.url)

        time.sleep(2)

        # remove all popups
        js_script = """
        var popUpSelectors = ['modal', 'popup', 'overlay', 'dialog']; // Add more selectors that are commonly used for pop-ups
        popUpSelectors.forEach(function(selector) {
            var elements = document.querySelectorAll(selector);
            elements.forEach(function(element) {
                // You can choose to hide or remove; here we're removing the element
                element.parentNode.removeChild(element);
            });
        });
        """

        wd.execute_script(js_script)

        set_web_driver(wd)

        return "Current URL is: " + wd.current_url + "\n"


if __name__ == "__main__":
    tool = ReadURL(url="https://google.com")
    print(tool.run())