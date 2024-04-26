import base64
import os

from agency_swarm.tools import BaseTool
from .util import get_web_driver


class ExportFile(BaseTool):
    """This tool converts the current full web page into a file and returns its file_id. You can then analyze this file using the myfiles_browser tool."""

    def run(self):
        wd = get_web_driver()
        from agency_swarm import get_openai_client
        client = get_openai_client()

        # Define the parameters for the PDF
        params = {
            'landscape': False,
            'displayHeaderFooter': False,
            'printBackground': True,
            'preferCSSPageSize': True,
        }

        # Execute the command to print to PDF
        result = wd.execute_cdp_cmd('Page.printToPDF', params)
        pdf = result['data']

        pdf_bytes = base64.b64decode(pdf)

        # Save the PDF to a file
        with open("exported_file.pdf", "wb") as f:
            f.write(pdf_bytes)

        file_id = client.files.create(file=open("exported_file.pdf", "rb"), purpose="assistants",).id

        self.shared_state.set("file_id", file_id)

        return "Success. File exported with id: `" + file_id + "` You can now send this file id back to the user."


if __name__ == "__main__":
    wd = get_web_driver()
    wd.get("https://www.google.com")
    tool = ExportFile()
    tool.run()
