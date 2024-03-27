from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import spacy

nlp = spacy.load('en_core_web_sm')

class UserInterestProcessingTool(BaseTool):
    """
    Analyzes user input to extract travel interests and preferences using NLP.
    """

    user_input: str = Field(
        ..., description="User's textual input containing travel interests and preferences."
    )

    def run(self):
        doc = nlp(self.user_input)
        interests = {'destinations': [], 'activities': [], 'budget': '', 'dates': ''}
        # Example processing implementation
        for ent in doc.ents:
            if ent.label_ == 'GPE':
                interests['destinations'].append(ent.text)
            elif ent.label_ == 'MONEY':
                interests['budget'] = ent.text
            # Additional conditions for activities and dates could be implemented here

        return interests
