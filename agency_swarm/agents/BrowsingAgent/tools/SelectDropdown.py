from typing import Dict
from pydantic import Field, model_validator
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select

from agency_swarm.tools import BaseTool
from .util import get_web_driver, set_web_driver
from .util.highlights import remove_highlight_and_labels


class SelectDropdown(BaseTool):
    """
    This tool selects an option in a dropdown on the current web page based on the description of that element and which option to select.

    Before using this tool make sure to highlight dropdown elements on the page by outputting '[highlight dropdowns]' message.
    """

    key_value_pairs: Dict[str, str] = Field(...,
        description="A dictionary where the key is the sequence number of the dropdown element and the value is the index of the option to select.",
        examples=[{"1": 0, "2": 1}, {"3": 2}]
    )

    @model_validator(mode='before')
    @classmethod
    def check_key_value_pairs(cls, data):
        if not data.get('key_value_pairs'):
            raise ValueError(
                "key_value_pairs is required. Example format: "
                "key_value_pairs={'1': 0, '2': 1}"
            )
        return data

    def run(self):
        wd = get_web_driver()

        if 'select' not in self._shared_state.get("elements_highlighted", ""):
            raise ValueError("Please highlight dropdown elements on the page first by outputting '[highlight dropdowns]' message. You must output just the message without calling the tool first, so the user can respond with the screenshot.")

        all_elements = wd.find_elements(By.CSS_SELECTOR, '.highlighted-element')

        try:
            for key, value in self.key_value_pairs.items():
                key = int(key)
                element = all_elements[key - 1]

                select = Select(element)

                # Select the first option (index 0)
                select.select_by_index(int(value))
            result = f"Success. Option is selected in the dropdown. To further analyze the page, output '[send screenshot]' command."
        except Exception as e:
            result = str(e)

        remove_highlight_and_labels(wd)

        set_web_driver(wd)

        return result
