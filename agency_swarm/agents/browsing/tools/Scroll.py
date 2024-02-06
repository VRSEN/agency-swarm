from typing import Literal

from pydantic import Field

from agency_swarm.tools import BaseTool
from .util.selenium import get_web_driver, set_web_driver


class Scroll(BaseTool):
    """
    This tool allows you to scroll the current web page up or down by 1 screen height.
    """
    direction: Literal["up", "down"] = Field(
        ..., description="Direction to scroll."
    )

    def run(self):
        wd = get_web_driver()

        height = wd.get_window_size()['height']

        current_scroll_position = wd.execute_script("return window.pageYOffset;")
        total_scroll_height = wd.execute_script("return document.body.scrollHeight;")

        result = ""

        if self.direction == "up":
            if current_scroll_position == 0:
                # Reached the top of the page
                result = "Reached the top of the page. Cannot scroll up any further.\n"
            else:
                wd.execute_script(f"window.scrollBy(0, -{height});")
                result = "Scrolled up by 1 screen height. Make sure to use the AnalyzePage tool to analyze the page after scrolling."

        elif self.direction == "down":
            if current_scroll_position + wd.get_window_size()['height'] >= total_scroll_height:
                # Reached the bottom of the page
                result = "Reached the bottom of the page. Cannot scroll down any further.\n"
            else:
                wd.execute_script(f"window.scrollBy(0, {height});")
                result = "Scrolled down by 1 screen height. Make sure to use the AnalyzePage tool to analyze the page after scrolling."

        set_web_driver(wd)

        return result




