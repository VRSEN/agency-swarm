import base64

from agency_swarm import BaseTool, get_openai_client
from agency_swarm.tools.browsing.util import get_web_driver


class ExportFile(BaseTool):
    """This tool converts a web page to a PDF and returns its id. You must always communicate the id to the user."""

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

        return "Success. File uploaded to OpenAI with id: " + file_id + " Please tell the user to use this id with the SendMessage tool."