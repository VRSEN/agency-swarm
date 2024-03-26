import os
from typing import List

from pydantic import Field, model_validator, field_validator

from agency_swarm import BaseTool, get_openai_client
from agency_swarm.util import create_agent_template


class FinalizeAgency(BaseTool):
    """
    This tool finalizes the agency structure and it's imports. Please make sure to use at only at the very end, after all agents have been created.
    """
    agency_path: str = Field(
        None, description="Path to the agency folder. Defaults to the agency currently being created."
    )

    def run(self):
        agency_path = None
        if self.shared_state.get("agency_path"):
            os.chdir(self.shared_state.get("agency_path"))
            agency_path = self.shared_state.get("agency_path")
        else:
            os.chdir(self.agency_path)
            agency_path = self.agency_path

        client = get_openai_client()

        # read agency.py
        with open("./agency.py", "r") as f:
            agency_py = f.read()
            f.close()

        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=examples + [
                {'role': "user", 'content': agency_py},
            ],
            temperature=0.0,
        )

        message = res.choices[0].message.content

        # write agency.py
        with open("./agency.py", "w") as f:
            f.write(message)
            f.close()

        return f"Successfully finalized {agency_path} structure. You can now instruct the user to run the agency.py file."

    @model_validator(mode="after")
    def validate_agency_path(self):
        if not self.shared_state.get("agency_path") and not self.agency_path:
            raise ValueError("Agency path not found. Please specify the agency_path. Ask user for clarification if needed.")


SYSTEM_PROMPT = """"Please read the file provided by the user and fix all the imports and indentation accordingly. 

Only output the full valid python code and nothing else."""

example_input = """
from agency_swarm import Agency

from CEO import CEO
from NewsAnalysisAgent import NewsAnalysisAgent
from PriceTrackingAgent import PriceTrackingAgent


agency = Agency([ceo, [ceo, news_analysis],
 [ceo, price_tracking],
 [news_analysis, price_tracking]],
shared_instructions='./agency_manifesto.md')

if __name__ == '__main__':
    agency.demo_gradio()
"""

example_output = """from agency_swarm import Agency
from CEO import CEO
from NewsAnalysisAgent import NewsAnalysisAgent
from PriceTrackingAgent import PriceTrackingAgent

ceo = CEO()
news_analysis = NewsAnalysisAgent()
price_tracking = PriceTrackingAgent()

agency = Agency([ceo, [ceo, market_analyst],
                 [ceo, news_curator],
                 [market_analyst, news_curator]],
                shared_instructions='./agency_manifesto.md')
    
if __name__ == '__main__':
    agency.demo_gradio()"""

examples = [
    {'role': "system", 'content': SYSTEM_PROMPT},
    {'role': "user", 'content': example_input},
    {'role': "assistant", 'content': example_output}
]
