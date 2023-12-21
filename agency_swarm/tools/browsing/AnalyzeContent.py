from agency_swarm.tools import BaseTool
from pydantic import Field
import tempfile
import base64

from agency_swarm.tools.browsing.util import get_web_driver, set_web_driver, get_b64_screenshot
from agency_swarm.util import get_openai_client


class AnalyzeContent(BaseTool):
    """
    This tool allows you to ask a question about the current webpage and get an answer using a vision model. Make sure to read the URL first with ReadURL tool.
    """
    question: str = Field(
        ..., description="Question to ask about the current webpage."
    )

    def run(self):
        wd = get_web_driver()

        client = get_openai_client()

        screenshot = get_b64_screenshot(wd)

        messages = [
            {
                "role": "system",
                "content": "As a web scraping tool, your primary task is to accurately extract and provide information in response to user queries based on webpage screenshots. When a user asks a question, analyze the provided screenshot of the webpage for relevant information. Your goal is to ensure relevant data retrieval from webpages.",
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
