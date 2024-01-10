import base64
import os

from agency_swarm import BaseTool, get_openai_client
from agency_swarm.tools.browsing.util import get_web_driver


class ExportFile(BaseTool):
    """This tool converts full web page into a file and returns its id. That you can then use to analyze it with myfiles_browser tool."""

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

        # Save the PDF to a file
        with open('page.pdf', 'wb') as f:
            f.write(pdf_bytes)

        file_id = client.files.create(file=pdf_bytes, purpose="assistants").id

        # update caller agent assistant
        self.caller_agent.file_ids.append(file_id)

        client.beta.assistants.update(
            assistant_id=self.caller_agent.id,
            file_ids=self.caller_agent.file_ids
        )

        # delete file
        os.remove('page.pdf')

        return ("Success. File uploaded to OpenAI with id: " + file_id +
                " You can use myfiles_browser tool to analyze it.")