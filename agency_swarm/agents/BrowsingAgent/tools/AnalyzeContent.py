import base64

from agency_swarm.tools import BaseTool
from pydantic import Field

from .util import get_web_driver, set_web_driver, get_b64_screenshot
from agency_swarm.util import get_openai_client


class AnalyzeContent(BaseTool):
    """
    This tool analyzes the current web browser window content and allows you to ask a question about its contents. Make sure to read
    the URL first with ReadURL tool or navigate to the right page with ClickElement tool. Do not use this tool to get 
    direct links to other pages. It is not intended to be used for navigation. To analyze the full web page, instead of just the current window, use ExportFile tool.
    """
    question: str = Field(
        ..., description="Question to ask about the contents of the current webpage."
    )

    def run(self):
        wd = get_web_driver()

        client = get_openai_client()

        screenshot = get_b64_screenshot(wd)

        # save screenshot locally
        # with open("screenshot.png", "wb") as fh:
        #     fh.write(base64.b64decode(screenshot))

        messages = [
            {
                "role": "system",
                "content": "As a web scraping tool, your primary task is to accurately extract and provide information in response to user queries based on webpage screenshots. When a user asks a question, analyze the provided screenshot of the webpage for relevant information. Your goal is to ensure relevant data retrieval from webpages. If some elements are obscured by pop ups, notify the user about how to close them. If there might be additional information on the page regarding the user's question by scrolling up or down, notify the user about it as well.",
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
                        "text": f"{self.question}",
                    }
                ]
            }

        ]

        response = client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=messages,
            max_tokens=1024,
        )

        message = response.choices[0].message
        message_text = message.content

        set_web_driver(wd)

        return message_text
