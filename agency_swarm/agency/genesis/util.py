import os
from pathlib import Path


def check_agency_path(self):
    if not self.shared_state.get("default_folder"):
        self.shared_state.set('default_folder', Path.cwd())

    if not self.shared_state.get("agency_path") and not self.agency_name:
        available_agencies = os.listdir("./")
        available_agencies = [agency for agency in available_agencies if os.path.isdir(agency)]
        raise ValueError(f"Please specify an agency. Available agencies are: {available_agencies}")
    elif not self.shared_state.get("agency_path") and self.agency_name:
        if not os.path.exists(os.path.join("./", self.agency_name)):
            available_agencies = os.listdir("./")
            available_agencies = [agency for agency in available_agencies if os.path.isdir(agency)]
            raise ValueError(f"Agency {self.agency_name} not found. Available agencies are: {available_agencies}")
        self.shared_state.set("agency_path", os.path.join("./", self.agency_name))


def check_agent_path(self):
    agent_path = os.path.join(self.shared_state.get("agency_path"), self.agent_name)
    if not os.path.exists(agent_path):
        available_agents = os.listdir(self.shared_state.get("agency_path"))
        available_agents = [agent for agent in available_agents if
                            os.path.isdir(os.path.join(self.shared_state.get("agency_path"), agent))]
        raise ValueError(f"Agent {self.agent_name} not found. Available agents are: {available_agents}")
