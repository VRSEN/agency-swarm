from selenium.webdriver.common.by import By

from agency_swarm.tools import BaseTool
from .util import get_web_driver, set_web_driver


class WebPageSummarizer(BaseTool):
    """
    This tool summarizes the content of the current web page, extracting the main points and providing a concise summary.
    """

    def run(self):
        from agency_swarm import get_openai_client

        wd = get_web_driver()
        client = get_openai_client()

        content = wd.find_element(By.TAG_NAME, "body").text

        # only use the first 3000 words
        content = " ".join(content.split()[:3000])

        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Your task is to summarize the content of the provided webpage. The summary should be concise and informative, capturing the main points and takeaways of the page."},
                {"role": "user", "content": "Summarize the content of the following webpage:\n\n" + content},
            ],
            temperature=0.0,
        )

        return completion.choices[0].message.content

if __name__ == "__main__":
    wd = get_web_driver()
    wd.get("https://en.wikipedia.org/wiki/Python_(programming_language)")
    set_web_driver(wd)
    tool = WebPageSummarizer()
    print(tool.run())