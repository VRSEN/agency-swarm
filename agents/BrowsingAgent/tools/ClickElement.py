import json
import time

from pydantic import Field
from selenium.webdriver.common.by import By

from agency_swarm.tools import BaseTool
from .util import get_b64_screenshot
from .util import get_web_driver, set_web_driver
from .util.highlights import highlight_elements_with_labels, remove_highlight_and_labels
from agency_swarm.util import get_openai_client


class ClickElement(BaseTool):
    """
    This tool clicks on an element on the current web page based on element or task description. Do not use this tool for input fields or dropdowns.
    """
    description: str = Field(
        ..., description="Description of the element to click on in natural language.",
        example="Click on the 'Sign Up' button."
    )

    def run(self):
        wd = get_web_driver()

        client = get_openai_client()

        wd = highlight_elements_with_labels(wd, 'a, button, div[onclick], div[role="button"], div[tabindex], '
                                                'span[onclick], span[role="button"], span[tabindex]')

        screenshot = get_b64_screenshot(wd)

        all_elements = wd.find_elements(By.CSS_SELECTOR, '.highlighted-element')

        all_element_texts = [element.text for element in all_elements]

        element_texts_json = {}
        for i, element_text in enumerate(all_element_texts):
            element_texts_json[str(i + 1)] = element_text

        element_texts_json = json.dumps(element_texts_json)

        messages = [
            {
                "role": "system",
                "content": """You function as an intelligent web scraping tool. Users will supply a screenshot of a 
webpage, where each clickable element is clearly highlighted in red. Alongside each of these 
elements, a unique sequence number, ranging from 1 to n, is displayed near the left side of its border. Your task is 
to process the screenshot based on the user's description of the target element and output the 
corresponding sequence number. The output should exclusively contain the sequence number of the 
identified element. If no element on the screenshot matches the user’s description, your response 
should be 'none'. In instances where the label of a clickable element is not visible or discernible 
in the screenshot, you are equipped to infer its sequence number by analyzing its position within the 
DOM structure of the page.""".replace("\n", ""),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{screenshot}",
                    },
                    {
                        "type": "text",
                        "text": f"{self.description}.\n\nText on all visible clickable elements: {element_texts_json}",
                    }
                ]
            }

        ]

        result = None
        error_count = 0
        while True:
            response = client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=messages,
                max_tokens=1024,
            )

            message = response.choices[0].message
            message_text = message.content

            if "none" in message_text.lower():
                return "No element found that matches the description. To further analyze the page, use the AnalyzeContent tool."

            # leave only numbers in message text
            message_text = ''.join([i for i in message_text if i.isdigit()])
            number = int(message_text)

            # iterate through all elements with a number in the text
            try:
                element_text = all_elements[number - 1].text
                element_text = element_text.strip() if element_text else "None"
                # Subtract 1 because sequence numbers start at 1, but list indices start at 0
                try:
                    all_elements[number - 1].click()
                except Exception as e:
                    if "element click intercepted" in str(e).lower():
                        wd.execute_script("arguments[0].click();", all_elements[number - 1])
                    else:
                        raise e

                time.sleep(3)

                result = f"Clicked on element {number}. Text on clicked element: '{element_text}'. Current URL is {wd.current_url} To further analyze the page, use the AnalyzeContent tool."
            except IndexError:
                result = "No element found that matches the description. To further analyze the page, use the AnalyzeContent tool."
            except Exception as e:
                # remove everything after stacktrace from error
                message = str(e)[:str(e).find("Stacktrace:")]
                messages.append({
                    "role": "system",
                    "content": f"Error clicking element: {message} Please try again."
                })

                if error_count > 3:
                    result = f"Error clicking element. Error: {message} To further analyze the page, use the AnalyzeContent tool."
                    break

                error_count += 1

            if result:
                break

        wd = remove_highlight_and_labels(wd)

        set_web_driver(wd)

        return result
