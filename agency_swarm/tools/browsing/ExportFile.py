import base64
import os

from agency_swarm import BaseTool, get_openai_client
from agency_swarm.tools.browsing.util import get_web_driver


class ExportFile(BaseTool):
    """This tool converts the current full web page into a file and returns its file_id. You can then analyze this file using the myfiles_browser tool."""

    def run(self):
        wd = get_web_driver()

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

        file_id = client.files.create(file=pdf_bytes, purpose="assistants").id

        # update caller agent assistant
        self.caller_agent.file_ids.append(file_id)

        client.beta.assistants.update(
            assistant_id=self.caller_agent.id,
            file_ids=self.caller_agent.file_ids
        )

        return ("Success. File exported with id: " + file_id +
                " You can now use myfiles_browser tool to analyze the contents of this webpage.")