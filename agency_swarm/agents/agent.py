import inspect
import json
import os
from typing import Dict, Union, Any, Type
from typing import List

from deepdiff import DeepDiff

from agency_swarm.tools import BaseTool
from agency_swarm.tools import Retrieval, CodeInterpreter
from agency_swarm.util.oai import get_openai_client


class Agent():
    @property
    def assistant(self):
        if self._assistant is None:
            raise Exception("Assistant is not initialized. Please run init_oai() first.")
        return self._assistant

    @assistant.setter
    def assistant(self, value):
        self._assistant = value

    @property
    def functions(self):
        return [tool for tool in self.tools if issubclass(tool, BaseTool)]

    def __init__(self, id: str = None, name: str = None, description: str = None, instructions: str = "",
                 tools: List[Union[Type[BaseTool], Type[Retrieval], Type[CodeInterpreter]]] = None,
                 files_folder: Union[List[str], str] = None,
                 file_ids: List[str] = None, metadata: Dict[str, str] = None, model: str = "gpt-4-1106-preview"):

        self.id = id
        self.name = name if name else self.__class__.__name__
        self.description = description
        self.instructions = instructions  # can be file path
        self.tools = tools if tools else []
        self.files_folder = files_folder
        self.file_ids = file_ids if file_ids else []
        self.metadata = metadata if metadata else {}
        self.model = model

        self._assistant: Any = None

        self.client = get_openai_client()

        if os.path.isfile(self.instructions):
            self._read_instructions(self.instructions)
        if os.path.isfile(self.get_instructions_class_path()):
            self._read_instructions(self.get_instructions_class_path())

        self._upload_files()

    def init_oai(self):
        # check if settings.json exists
        path = self.get_settings_path()

        # load assistant from id
        if self.id:
            self.assistant = self.client.beta.assistants.retrieve(self.id)
            # update assistant if parameters are different
            if not self._check_parameters(self.assistant.model_dump()):
                self._update_assistant()
            return self

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
                            print("Updating assistant... " + self.name)
                            self._update_assistant()
                        self._update_settings()
                        return self
        # create assistant if settings.json does not exist or assistant with the same name does not exist
        self.assistant = self.client.beta.assistants.create(
            name=self.name,
            description=self.description,
            instructions=self.instructions,
            tools=self.get_oai_tools(),
            file_ids=self.file_ids,
            metadata=self.metadata,
            model=self.model
        )

        self.id = self.assistant.id

        self._save_settings()

        return self

    def _update_assistant(self):
        params = {
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "tools": self.get_oai_tools(),
            "file_ids": self.file_ids,
            "metadata": self.metadata,
            "model": self.model
        }
        params = {k: v for k, v in params.items() if v}
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
        tools_diff = DeepDiff(self.get_oai_tools(), assistant_settings['tools'], ignore_order=True)
        if tools_diff != {}:
            return False
        if set(self.file_ids) != set(assistant_settings['file_ids']):
            return False
        metadata_diff = DeepDiff(self.metadata, assistant_settings['metadata'], ignore_order=True)
        if metadata_diff != {}:
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
        path = self.get_settings_path()
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

    def _read_instructions(self, path):
        with open(path, 'r') as f:
            self.instructions =  f.read()

    def _upload_files(self):
        if isinstance(self.files_folder, str):
            f_path = self.files_folder

            if not os.path.isdir(f_path):
                f_path = os.path.join(self.get_class_folder_path(), self.files_folder)

            if os.path.isdir(f_path):
                f_paths = os.listdir(f_path)
                f_paths = [os.path.join(f_path, f) for f in f_paths]

                for f_path in f_paths:
                    file_id = self._get_id_from_file(f_path)
                    if file_id:
                        print("File already uploaded. Skipping... " + os.path.basename(f_path))
                        self.file_ids.append(file_id)
                    else:
                        print("Uploading new file... " + os.path.basename(f_path))
                        with open(f_path, 'rb') as f:
                            file_id = self.client.files.create(file=f, purpose="assistants").id
                            self.file_ids.append(file_id)
                            self._add_id_to_file(f_path, file_id)

                    if Retrieval not in self.tools:
                        print("Detected files without Retrieval. Adding Retrieval tool...")
                        self.add_tool(Retrieval)
            else:
                raise Exception("Files folder path is not a directory.")

    def _add_id_to_file(self, f_path, id):
        """Add file id to file name"""
        if os.path.isfile(f_path):
            file_name, file_ext = os.path.splitext(f_path)
            f_path_new = file_name + "_" + id + file_ext
            os.rename(f_path, f_path_new)
            return f_path_new
        else:
            raise Exception("File path is not a file.")

    def _get_id_from_file(self, f_path):
        """Get file id from file name"""
        if os.path.isfile(f_path):
            file_name, file_ext = os.path.splitext(f_path)
            file_name = os.path.basename(file_name)
            file_name = file_name.split("_")
            if len(file_name) > 1:
                return file_name[-1] if "file-" in file_name[-1] else None
            else:
                return None
        else:
            raise Exception("File path is not a file.")

    def get_instructions_class_path(self):
        return os.path.join(self.get_class_folder_path(), self.instructions)

    def get_settings_path(self):
        return os.path.join("./", 'settings.json')

    def get_class_folder_path(self):
        return os.path.abspath(os.path.dirname(inspect.getfile(self.__class__)))

    def set_params(self, **params):
        for k, v in params.items():
            setattr(self, k, v)

    def add_tool(self, tool):
        if not isinstance(tool, type):
            raise Exception("Tool must not be initialized.")
        if issubclass(tool, Retrieval):
            self.tools.append(tool)
        elif issubclass(tool, CodeInterpreter):
            self.tools.append(tool)
        elif issubclass(tool, BaseTool):
            self.tools.append(tool)
        else:
            raise Exception("Invalid tool type.")

    def add_instructions(self, manifesto: str):
        self.instructions = manifesto + "\n\n" + self.instructions

    def get_oai_tools(self):
        tools = []
        for tool in self.tools:
            if not isinstance(tool, type):
                raise Exception("Tool must not be initialized.")

            if issubclass(tool, Retrieval):
                tools.append(tool().model_dump())
            elif issubclass(tool, CodeInterpreter):
                tools.append(tool().model_dump())
            elif issubclass(tool, BaseTool):
                tools.append({
                    "type": "function",
                    "function": tool.openai_schema
                })
            else:
                raise Exception("Invalid tool type.")
        return tools

    def delete_assistant(self):
        self.client.beta.assistants.delete(self.id)
        self._delete_settings()

    def _delete_settings(self):
        path = self.get_settings_path()
        # check if settings.json exists
        if os.path.isfile(path):
            settings = []
            with open(path, 'r') as f:
                settings = json.load(f)
                for i, assistant_settings in enumerate(settings):
                    if assistant_settings['id'] == self.id:
                        settings.pop(i)
                        break
            with open(path, 'w') as f:
                json.dump(settings, f, indent=4)
