from pydantic import Field, BaseModel
from typing import List, Literal

from agency_swarm import get_openai_client


def format_file_deps(v):
    client = get_openai_client()
    result = ''
    for file in v:
        # extract dependencies from the file using openai
        with open(file, 'r') as f:
            content = f.read()

        class Dependency(BaseModel):
            type: Literal['class', 'function', 'import'] = Field(..., description="The type of the dependency.")
            name: str = Field(..., description="The name of the dependency, matching the import or definition.")

        class Dependencies(BaseModel):
            dependencies: List[Dependency] = Field([], description="The dependencies extracted from the file.")

            def append_dependencies(self):
                functions = [dep.name for dep in self.dependencies if dep.type == 'function']
                classes = [dep.name for dep in self.dependencies if dep.type == 'class']
                imports = [dep.name for dep in self.dependencies if dep.type == 'import']
                variables = [dep.name for dep in self.dependencies if dep.type == 'variable']
                nonlocal result
                result += f"File path: {file}\n"
                result += f"Functions: {functions}\nClasses: {classes}\nImports: {imports}\nVariables: {variables}\n\n"

        completion = client.beta.chat.completions.parse(
            messages=[
                {
                    "role": "system",
                    "content": "You are a world class dependency resolved. You must extract the dependencies from the file provided."
                },
                {
                    "role": "user",
                    "content": f"Extract the dependencies from the file '{file}'."
                }
            ],
            model="gpt-4o-mini",
            temperature=0,
            response_format=Dependencies
        )

        if completion.choices[0].message.refusal:
            raise ValueError(completion.choices[0].message.refusal)

        model = completion.choices[0].message.parsed

        model.append_dependencies()

    return result