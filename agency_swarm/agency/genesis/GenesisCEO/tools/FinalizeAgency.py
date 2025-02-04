from pydantic import Field, model_validator

from agency_swarm import BaseTool, get_openai_client
from agency_swarm.agency.genesis.util import change_directory


class FinalizeAgency(BaseTool):
    """
    This tool finalizes the agency structure and it's imports. Please make sure to use at only at the very end, after all agents have been created.
    """

    agency_path: str = Field(
        None,
        description="Path to the agency folder. Defaults to the agency currently being created.",
    )

    def run(self):
        target_path = self._shared_state.get("agency_path") or self.agency_path
        client = get_openai_client()

        with change_directory(target_path):
            # read agency.py
            with open("./agency.py", "r") as f:
                agency_py = f.read()

            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=examples
                + [
                    {"role": "user", "content": agency_py},
                ],
                temperature=0.0,
            )

            message = res.choices[0].message.content

            # write agency.py
            with open("./agency.py", "w") as f:
                f.write(message)

        return f"Successfully finalized {target_path} structure. You can now instruct the user to run the agency.py file."

    @model_validator(mode="after")
    def validate_agency_path(self):
        if not self._shared_state.get("agency_path") and not self.agency_path:
            raise ValueError(
                "Agency path not found. Please specify the agency_path. Ask user for clarification if needed."
            )


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
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": example_input},
    {"role": "assistant", "content": example_output},
]
