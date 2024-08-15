import time
from typing import Dict

from pydantic import Field
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By

from agency_swarm.tools import BaseTool
from .util import get_web_driver, set_web_driver
from .util.highlights import remove_highlight_and_labels


from pydantic import model_validator

class SendKeys(BaseTool):
    """
    This tool sends keys into input fields on the current webpage based on the description of that element and what needs to be typed. It then clicks "Enter" on the last element to submit the form. You do not need to tell it to press "Enter"; it will do that automatically.

    Before using this tool make sure to highlight the input elements on the page by outputting '[highlight text fields]' message.
    """
    elements_and_texts: Dict[int, str] = Field(...,
        description="A dictionary where the key is the element number and the value is the text to be typed.",
        examples=[
            {52: "johndoe@gmail.com", 53: "password123"},
            {3: "John Doe", 4: "123 Main St"},
        ]
    )

    @model_validator(mode='before')  
    @classmethod
    def check_elements_and_texts(cls, data):
        if not data.get('elements_and_texts'):
            raise ValueError(
                "elements_and_texts is required. Example format: "
                "elements_and_texts={1: 'John Doe', 2: '123 Main St'}"
            )
        return data

    def run(self):
        wd = get_web_driver()
        if 'input' not in self._shared_state.get("elements_highlighted", ""):
            raise ValueError("Please highlight input elements on the page first by outputting '[highlight text fields]' message. You must output just the message without calling the tool first, so the user can respond with the screenshot.")

        all_elements = wd.find_elements(By.CSS_SELECTOR, '.highlighted-element')

        i = 0
        try:
            for key, value in self.elements_and_texts.items():
                key = int(key)
                element = all_elements[key - 1]

                try:
                    element.click()
                    element.send_keys(Keys.CONTROL + "a")  # Select all text in input
                    element.send_keys(Keys.DELETE)
                    element.clear()
                except Exception as e:
                    pass
                element.send_keys(value)
                # send enter key to the last element
                if i == len(self.elements_and_texts) - 1:
                    element.send_keys(Keys.RETURN)
                    time.sleep(3)
                i += 1
            result = f"Sent input to element and pressed Enter. Current URL is {wd.current_url} To further analyze the page, output '[send screenshot]' command."
        except Exception as e:
            result = str(e)

        remove_highlight_and_labels(wd)

        set_web_driver(wd)

        return result
