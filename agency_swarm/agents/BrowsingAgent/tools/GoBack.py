import time

from agency_swarm.tools import BaseTool

from .util.selenium import get_web_driver, set_web_driver


class GoBack(BaseTool):
    """
    This tool allows you to go back 1 page in the browser history. Use it in case of a mistake or if a page shows you unexpected content.
    """

    def run(self):
        wd = get_web_driver()

        wd.back()

        time.sleep(3)

        set_web_driver(wd)

        return "Success. Went back 1 page. Current URL is: " + wd.current_url
