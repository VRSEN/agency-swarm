import inspect
import json
import os
from abc import ABC
from typing import Dict, Union, Any
from typing import Literal, List

from deepdiff import DeepDiff
from pydantic import BaseModel

from agency_swarm.tools import BaseTool
from agency_swarm.util.oai import get_openai_client


class DefaultTools(BaseModel):
    type: Literal["code_interpreter", "retrieval"]


class BaseAgent(ABC):
    @property
    def assistant(self):
        if self._assistant is None:
            raise Exception("Assistant is not initialized. Please run init_assistant() first.")
        return self._assistant

    @assistant.setter
    def assistant(self, value):
        self._assistant = value

    def __init__(self, id: str = None, name: str = None, description: str = None, instructions: str = "",
                 tools: List[Union[BaseTool, DefaultTools]] = None, files: Union[List[str], str] = None,
                 metadata: Dict[str, str] = None, model: str = "gpt-4-1106-preview"):

        self.id = id
        self.name = name if name else self.__class__.__name__
        self.description = description
        self.instructions = instructions  # can be file path
        self.tools = tools if tools else []  # Instance variable for tools
        self.files = files if files else []  # can be file or folder path
        self.metadata = metadata if metadata else {}
        self.model = model

        self._assistant: Any = None
        self.functions: List[BaseTool] = []

        if os.path.isfile(self.get_instructions_path()):
            self.instructions = self._read_instructions()

        if isinstance(self.files, str):
            if os.path.isdir(self.files):
                self.files = os.listdir(self.files)
                self.files = [os.path.join(self.files, file) for file in self.files]
                self.files = self._upload_files()
            elif os.path.isfile(self.files):
                self.files = [self.files]
                self.files = self._upload_files()

        for tool in self.tools:
            self.add_tool(tool)

        if not self.name:
            self.name = self.__class__.__name__

        self.client = get_openai_client()

    def init_assistant(self):
        # check if settings.json exists
        path = self.get_settings_path()

        # load assistant from id
        if self.id:
            self.assistant = self.client.beta.assistants.retrieve(self.id)
            # update assistant if parameters are different
            if not self._check_parameters(self.assistant.model_dump()):
                self._update_assistant()
            return

        # load assistant from settings
        if os.path.exists(path):
            with open(path, 'r') as f:
                settings = json.load(f)
                # iterate settings and find the assistant with the same name
                for assistant_settings in settings:
                    if assistant_settings['name'] == self.name:
                        self.assistant = self.client.beta.assistants.retrieve(assistant_settings['id'])
                        self.id = assistant_settings['id']
                        # update assistant if parameters are different
                        if not self._check_parameters(self.assistant.model_dump()):
                            print("Updating assistant..." + self.name)
                            self._update_assistant()
                        self._update_settings()
                        return
        # create assistant if settings.json does not exist or assistant with the same name does not exist
        self.assistant = self.client.beta.assistants.create(
            name=self.name,
            description=self.description,
            instructions=self.instructions,
            tools=self.tools,
            file_ids=self.files,
            metadata=self.metadata,
            model=self.model
        )

        self.id = self.assistant.id

        self._save_settings()

    def _update_assistant(self):
        params = self.get_params()
        params = {k: v for k, v in params.items() if v is not None}
        self.assistant = self.client.beta.assistants.update(
            self.id,
            **params,
        )
        self._update_settings()

    def _check_parameters(self, assistant_settings):
        if self.name != assistant_settings['name']:
            return False
        if self.description != assistant_settings['description']:
            return False
        if self.instructions != assistant_settings['instructions']:
            return False
        if DeepDiff(self.tools, assistant_settings['tools'], ignore_order=True) != {}:
            return False
        if set(self.files) != set(assistant_settings['file_ids']):
            return False
        if DeepDiff(self.metadata, assistant_settings['metadata'], ignore_order=True) != {}:
            return False
        if self.model != assistant_settings['model']:
            return False
        return True

    def _save_settings(self):
        path = self.get_settings_path()
        # check if settings.json exists
        if not os.path.isfile(path):
            with open(path, 'w') as f:
                json.dump([self.assistant.model_dump()], f, indent=4)
        else:
            settings = []
            with open(path, 'r') as f:
                settings = json.load(f)
                settings.append(self.assistant.model_dump())
            with open(path, 'w') as f:
                json.dump(settings, f, indent=4)

    def _update_settings(self):
        path = os.path.join(self.get_class_folder_path(), 'settings.json')
        # check if settings.json exists
        if os.path.isfile(path):
            settings = []
            with open(path, 'r') as f:
                settings = json.load(f)
                for i, assistant_settings in enumerate(settings):
                    if assistant_settings['id'] == self.id:
                        settings[i] = self.assistant.model_dump()
                        break
            with open(path, 'w') as f:
                json.dump(settings, f, indent=4)

    def _read_instructions(self):
        with open(self.get_instructions_path(), 'r') as f:
            return f.read()

    def _upload_files(self):
        file_ids = []
        for file in self.files:
            file = self.client.files.create(file=open(file, 'rb'), purpose="assistants")
            file_ids.append(file.id)
        return file_ids

    def get_instructions_path(self):
        return os.path.join(self.get_class_folder_path(), self.instructions)

    def get_settings_path(self):
        return os.path.join(self.get_class_folder_path(), 'settings.json')

    def get_class_folder_path(self):
        return os.path.abspath(os.path.dirname(inspect.getfile(self.__class__)))

    def set_params(self, **params):
        for k, v in params.items():
            setattr(self, k, v)

    def get_params(self):
        return {
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "tools": self.tools,
            "file_ids": self.files,
            "metadata": self.metadata,
            "model": self.model
        }

    def add_tool(self, tool):
        if isinstance(tool, dict) and tool['type'] in ["code_interpreter", "retrieval"]:
            self.tools.append({
                "type": tool['type'],
            })
        elif issubclass(tool, BaseTool):
            self.tools.append({
                "type": "function",
                "function": tool.openai_schema
            })
            self.functions.append(tool)
        else:
            raise Exception("Invalid tool type.")

    def delete_assistant(self):
        self.client.beta.assistants.delete(self.id)
