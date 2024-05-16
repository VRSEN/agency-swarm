import json
import re

from selenium.webdriver.common.by import By

from agency_swarm.agents import Agent
from .tools.util import get_b64_screenshot, highlight_elements_with_labels, remove_highlight_and_labels
from .tools.util.selenium import get_web_driver, set_selenium_config, set_web_driver
from agency_swarm.tools.oai import FileSearch
from typing_extensions import override
from selenium.webdriver.support.select import Select
from agency_swarm.util.exceptions import AgencySwarmValueError
import base64


class BrowsingAgent(Agent):
    SCREENSHOT_FILE_NAME = "screenshot.jpg"

    def __init__(self, selenium_config=None, **kwargs):
        super().__init__(
            name="BrowsingAgent",
            description="This agent is designed to navigate and search web effectively.",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[FileSearch],
            tools_folder="./tools",
            temperature=0,
            max_prompt_tokens=25000,
            model="gpt-4-turbo",
            validation_attempts=20,
            **kwargs
        )
        if selenium_config is not None:
            set_selenium_config(selenium_config)

    @override
    def response_validator(self, message):
        if "[send screenshot]" in message.lower():
            wd = get_web_driver()
            remove_highlight_and_labels(wd)
            self.take_screenshot()
            response_text = "Here is the screenshot of the page you requested."

        elif '[highlight clickable elements]' in message.lower():
            wd = get_web_driver()
            highlight_elements_with_labels(wd, 'a, button, div[onclick], div[role="button"], div[tabindex], '
                                               'span[onclick], span[role="button"], span[tabindex]')

            self.take_screenshot()

            all_elements = wd.find_elements(By.CSS_SELECTOR, '.highlighted-element')

            all_element_texts = [element.text[:30] for element in all_elements]

            element_texts_json = {}
            for i, element_text in enumerate(all_element_texts):
                element_texts_json[str(i + 1)] = self.remove_unicode(element_text)

            element_texts_json = json.dumps(element_texts_json)

            response_text = "Here is the screenshot with highlighted clickable elements. "
                             # "Texts of the elements are: ") + element_texts_json

        elif '[highlight text fields]' in message.lower():
            wd = get_web_driver()
            highlight_elements_with_labels(wd, 'input, textarea')

            self.take_screenshot()

            all_elements = wd.find_elements(By.CSS_SELECTOR, '.highlighted-element')

            all_element_texts = [element.text[:30] for element in all_elements]

            element_texts_json = {}
            for i, element_text in enumerate(all_element_texts):
                element_texts_json[str(i + 1)] = self.remove_unicode(element_text)

            element_texts_json = json.dumps(element_texts_json)

            response_text = ("Here is the screenshot with highlighted text fields. "
                             "Texts of the elements are: ") + element_texts_json

        elif '[highlight dropdowns]' in message.lower():
            wd = get_web_driver()
            highlight_elements_with_labels(wd, 'select')

            self.take_screenshot()

            all_elements = wd.find_elements(By.CSS_SELECTOR, '.highlighted-element')

            all_selector_values = {}

            i = 0
            for element in all_elements:
                select = Select(element)
                options = select.options
                selector_values = {}
                for j, option in enumerate(options):
                    selector_values[str(j)] = option.text
                    if j > 10:
                        break
                all_selector_values[str(i + 1)] = selector_values

            response_text = ("Here is the screenshot with highlighted dropdowns. "
                             "Selector values are: ") + json.dumps(all_selector_values)

        else:
            return message

        set_web_driver(wd)
        content = self.create_response_content(response_text)
        raise ValueError(content)

    def take_screenshot(self):
        wd = get_web_driver()
        screenshot = get_b64_screenshot(wd)
        screenshot_data = base64.b64decode(screenshot)
        with open(self.SCREENSHOT_FILE_NAME, "wb") as screenshot_file:
            screenshot_file.write(screenshot_data)

    def create_response_content(self, response_text):
        with open(self.SCREENSHOT_FILE_NAME, "rb") as file:
            file_id = self.client.files.create(
                file=file,
                purpose="vision",
            ).id

        content = [
            {"type": "text", "text": response_text},
            {
                "type": "image_file",
                "image_file": {"file_id": file_id}
            }
        ]
        return content

    # Function to check for Unicode escape sequences
    def remove_unicode(self, data):
        return re.sub(r'[^\x00-\x7F]+', '', data)

