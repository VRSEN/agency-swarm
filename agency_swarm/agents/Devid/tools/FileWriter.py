from typing import List, Literal, Optional

import json

import os
from instructor import llm_validator, OpenAISchema

from agency_swarm import get_openai_client
from agency_swarm.tools import BaseTool
from pydantic import Field, field_validator
import re

from .util import format_file_deps

history = [
            {
                "role": "system",
                "content": "As a top-tier software engineer focused on developing programs incrementally, you are entrusted with the creation or modification of files based on user requirements. It's imperative to operate under the assumption that all necessary dependencies are pre-installed and accessible, and the file in question will be deployed in an appropriate environment. Furthermore, it is presumed that all other modules or files upon which this file relies are accurate and error-free. Your output should be encapsulated within a code block, without specifying the programming language. Prior to embarking on the coding process, you must outine a methodical, step-by-step plan to precisely fulfill the requirements—no more, no less. It is crucial to ensure that the final code block is a complete file, without any truncation. This file should embody a flawless, fully operational program, inclusive of all requisite imports and functions, devoid of any placeholders, unless specified otherwise by the user."
            },
        ]


class FileWriter(BaseTool):
    """This tools allows you to write new files or modify existing files according to specified requirements. In 'write' mode, it creates a new file or overwrites an existing one. In 'modify' mode, it modifies an existing file according to the provided requirements.
    Note: This tool does not have access to other files within the project. You must provide all necessary details to ensure that the generated file can be used in conjunction with other files in this project."""
    file_path: str = Field(
        ..., description="The path of the file to write or modify. Will create directories if they don't exist."
    )
    requirements: str = Field(
        ...,
        description="The comprehensive requirements explaning how the file should be written or modified. This should be a detailed description of what the file should contain, inlcuding example inputs, desired behaviour and ideal outputs. It must not contain any code or implementation details."
    )
    details: str = Field(
        None, description="Additional details like error messages, or class, function, and variable names from other files that this file depends on."
    )
    documentation: Optional[str] = Field(
        None, description="Relevant documentation extracted with the myfiles_browser tool. You must pass all the relevant code from the documentaion, as this tool does not have access to those files."
    )
    mode: Literal["write", "modify"] = Field(
        ..., description="The mode of operation for the tool. 'write' is used to create a new file or overwrite an existing one. 'modify' is used to modify an existing file."
    )
    file_dependencies: List[str] = Field(
        [],
        description="Paths to other files that the file being written depends on.",
        examples=["/path/to/dependency1.py", "/path/to/dependency2.css", "/path/to/dependency3.js"]
        )
    library_dependencies: List[str] = Field(
        [],
        description="Any library dependencies required for the file to be written.",
        examples=["numpy", "pandas"]
    )
    one_call_at_a_time: bool = True

    def run(self):
        client = get_openai_client()

        file_dependencies = format_file_deps(self.file_dependencies)

        library_dependencies = ", ".join(self.library_dependencies)

        filename = os.path.basename(self.file_path)

        if self.mode == "write":
            message = f"Please write {filename} file that meets the following requirements: '{self.requirements}'.\n"
        else:
            message = f"Please rewrite the {filename} file according to the following requirements: '{self.requirements}'.\n"

        if file_dependencies:
            message += f"\nHere are the dependencies from other project files: {file_dependencies}."
        if library_dependencies:
            message += f"\nUse the following libraries: {library_dependencies}"
        if self.details:
            message += f"\nAdditional Details: {self.details}"
        if self.documentation:
            message += f"\nDocumentation: {self.documentation}"

        if self.mode == "modify":
            message += f"\nThe existing file content is as follows:"

            try:
                with open(self.file_path, 'r') as file:
                    prev_content = file.read()
                    message += f"\n\n```{prev_content}```"
            except Exception as e:
                return f'Error reading {self.file_path}: {e}'

        history.append({
                "role": "user",
                "content": message
            })

        messages = history.copy()

        # use the last 5 messages
        messages = messages[-5:]

        # add system message upfront
        messages.insert(0, history[0])

        n = 0
        error_message = ""
        while n < 3:
            resp = client.chat.completions.create(
                messages=messages,
                model="gpt-4-turbo",
                temperature=0,
            )

            content = resp.choices[0].message.content

            messages.append(
                {
                    "role": "assistant",
                    "content": content
                }
            )

            pattern = r"```(?:[a-zA-Z]+\n)?(.*?)```"
            match = re.findall(pattern, content, re.DOTALL)
            if match:
                code = match[-1].strip()
                try:
                    self.validate_content(code)

                    history.append(
                        {
                            "role": "assistant",
                            "content": content
                        }
                    )

                    break
                except Exception as e:
                    print(f"Error: {e}. Trying again.")
                    error_message = str(e)
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Error: {e}. Please try again."
                        }
                    )
            else:
                messages.append(
                    {
                        "role": "user",
                        "content": f"Error: Could not find the code block in the response. Please try again."
                    }
                )

            n += 1

        if n == 3 or not code:
            history.append(
                {
                    "role": "assistant",
                    "content": content
                }
            )
            history.append(
                {
                    "role": "user",
                    "content": error_message
                }
            )
            return "Error: Could not generate a valid file: " + error_message

        try:
            # create directories if they don't exist
            dir_path = os.path.dirname(self.file_path)
            if dir_path != "" and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)

            with open(self.file_path, 'w') as file:
                file.write(code)
            return f'Successfully wrote to file: {self.file_path}. Please make sure to now test the program. Below is the content of the file:\n\n```{content}```\n\nPlease now verify the integrity of the file and test it.'
        except Exception as e:
            return f'Error writing to file: {e}'

    @field_validator("file_dependencies", mode="after")
    @classmethod
    def validate_file_dependencies(cls, v):
        for file in v:
            if not os.path.exists(file):
                raise ValueError(f"File dependency '{file}' does not exist.")
        return v

    def validate_content(self, v):
        client = get_openai_client()

        llm_validator(
            statement="Check if the code is bug-free. Code should be considered in isolation, with the understanding that it is part of a larger, fully developed program that strictly adheres to these standards of completeness and correctness. All files, elements, components, functions, or modules referenced within this snippet are assumed to exist in other parts of the project and are also devoid of any errors, ensuring a cohesive and error-free integration across the entire software solution. Certain placeholders may be present.",
                      client=client,
                      model="gpt-4-turbo",
                      temperature=0,
                      allow_override=False
                      )(v)

        return v

    @field_validator("requirements", mode="after")
    @classmethod
    def validate_requirements(cls, v):
        if "placeholder" in v:
            raise ValueError("Requirements contain placeholders. "
                             "Please never user placeholders. Instead, implement only the code that you are confident about.")

        # check if code is included in requirements
        pattern = r'(```)((.*\n){5,})(```)'
        if re.search(pattern, v):
            raise ValueError(
                "Requirements contain a code snippet. Please never include code snippets in requirements. "
                "Requirements must be a description of the complete file to be written. You can include specific class, function, and variable names, but not the actual code."
            )

        return v

    @field_validator("details", mode="after")
    @classmethod
    def validate_details(cls, v):
        if len(v) == 0:
            raise ValueError("Details are required. Remember this tool does not have access to other files. Please provide additional details like relevant documentation, error messages, or class, function, and variable names from other files that this file depends on.")
        return v

    @field_validator("documentation", mode="after")
    @classmethod
    def validate_documentation(cls, v):
        # check if documentation contains code
        pattern = r'(```)((.*\n){5,})(```)'
        pattern2 = r'(`)(.*)(`)'
        if not (re.search(pattern, v) or re.search(pattern2, v)):
            raise ValueError(
                "Documentation does not contain a code snippet. Please provide relevant documentation extracted with the myfiles_browser tool. You must pass all the relevant code snippets information, as this tool does not have access to those files."
            )


if __name__ == "__main__":
    tool = FileWriter(
        requirements="Write a program that takes a list of integers as input and returns the sum of all the integers in the list.",
        mode="write",
        file_path="test.py",
    )
    print(tool.run())
