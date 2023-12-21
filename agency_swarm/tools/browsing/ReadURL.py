from agency_swarm.tools import BaseTool
from pydantic import Field
import tempfile
import base64

from agency_swarm.tools.browsing.util.selenium import get_web_driver, set_web_driver
from agency_swarm.util import get_openai_client


class ReadURL(BaseTool):
    """
    This tool reads a URL and saves it to selenium web driver instance. In the beginning, go to a direct URL that you think might contain the answer to the user's question. Prefer to go directly to sub-urls like 'https://google.com/search?q=search' if applicable. Prefer to use Google for simple queries. If the user provides a direct URL, go to that one.
    """
    url: str = Field(
        ..., description="URL of the webpage."
    )

    def run(self):
        wd = get_web_driver()

        wd.get(self.url)

        wd.implicitly_wait(3)

        set_web_driver(wd)

        return "Success. Current URL is: " + wd.current_url + "\n"
