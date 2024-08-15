import json
import re

from agency_swarm.agents import Agent
from agency_swarm.tools.oai import FileSearch
from typing_extensions import override
import base64


class BrowsingAgent(Agent):
    SCREENSHOT_FILE_NAME = "screenshot.jpg"

    def __init__(self, selenium_config=None, **kwargs):
        from .tools.util.selenium import set_selenium_config
        super().__init__(
            name="BrowsingAgent",
            description="This agent is designed to navigate and search web effectively.",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[],
            tools_folder="./tools",
            temperature=0,
            max_prompt_tokens=16000,
            model="gpt-4o",
            validation_attempts=25,
            **kwargs
        )
        if selenium_config is not None:
            set_selenium_config(selenium_config)

        self.prev_message = ""

    @override
    def response_validator(self, message):
        from .tools.util.selenium import get_web_driver, set_web_driver
        from .tools.util import highlight_elements_with_labels, remove_highlight_and_labels
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.select import Select

        # Filter out everything in square brackets
        filtered_message = re.sub(r'\[.*?\]', '', message).strip()
        
        if filtered_message and self.prev_message == filtered_message:
            raise ValueError("Do not repeat yourself. If you are stuck, try a different approach or search in google for the page you are looking for directly.")
        
        self.prev_message = filtered_message

        if "[send screenshot]" in message.lower():
            wd = get_web_driver()
            remove_highlight_and_labels(wd)
            self.take_screenshot()
            response_text = "Here is the screenshot of the current web page:"

        elif '[highlight clickable elements]' in message.lower():
            wd = get_web_driver()
            highlight_elements_with_labels(wd, 'a, button, div[onclick], div[role="button"], div[tabindex], '
                                               'span[onclick], span[role="button"], span[tabindex]')
            self._shared_state.set("elements_highlighted", 'a, button, div[onclick], div[role="button"], div[tabindex], '
                                               'span[onclick], span[role="button"], span[tabindex]')

            self.take_screenshot()

            all_elements = wd.find_elements(By.CSS_SELECTOR, '.highlighted-element')

            all_element_texts = [element.text for element in all_elements]

            element_texts_json = {}
            for i, element_text in enumerate(all_element_texts):
                element_texts_json[str(i + 1)] = self.remove_unicode(element_text)
            
            element_texts_json = {k: v for k, v in element_texts_json.items() if v}

            element_texts_formatted = ", ".join([f"{k}: {v}" for k, v in element_texts_json.items()])

            response_text = ("Here is the screenshot of the current web page with highlighted clickable elements. \n\n"
                             "Texts of the elements are: " + element_texts_formatted + ".\n\n"
                             "Elements without text are not shown, but are available on screenshot. \n"
                             "Please make sure to analyze the screenshot to find the clickable element you need to click on.")

        elif '[highlight text fields]' in message.lower():
            wd = get_web_driver()
            highlight_elements_with_labels(wd, 'input, textarea')
            self._shared_state.set("elements_highlighted", "input, textarea")

            self.take_screenshot()

            all_elements = wd.find_elements(By.CSS_SELECTOR, '.highlighted-element')

            all_element_texts = [element.text for element in all_elements]

            element_texts_json = {}
            for i, element_text in enumerate(all_element_texts):
                element_texts_json[str(i + 1)] = self.remove_unicode(element_text)

            element_texts_formatted = ", ".join([f"{k}: {v}" for k, v in element_texts_json.items()])

            response_text = ("Here is the screenshot of the current web page with highlighted text fields: \n"
                             "Texts of the elements are: " + element_texts_formatted + ".\n"
                             "Please make sure to analyze the screenshot to find the text field you need to fill.")

        elif '[highlight dropdowns]' in message.lower():
            wd = get_web_driver()
            highlight_elements_with_labels(wd, 'select')
            self._shared_state.set("elements_highlighted", "select")

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

            all_selector_values = {k: v for k, v in all_selector_values.items() if v}
            all_selector_values_formatted = ", ".join([f"{k}: {v}" for k, v in all_selector_values.items()])

            response_text = ("Here is the screenshot with highlighted dropdowns. \n"
                             "Selector values are: " + all_selector_values_formatted + ".\n"
                             "Please make sure to analyze the screenshot to find the dropdown you need to select.")

        else:
            return message

        set_web_driver(wd)
        content = self.create_response_content(response_text)
        raise ValueError(content)

    def take_screenshot(self):
        from .tools.util.selenium import get_web_driver
        from .tools.util import get_b64_screenshot
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

