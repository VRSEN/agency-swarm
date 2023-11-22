import os


def create_agent_template(path="./"):
    agent_name = input("Enter agent name: ")
    agent_description = input("Enter agent description: ")

    # create manifesto if it doesn't exist
    if not os.path.isfile(path + "agency_manifesto.md"):
        with open(path + "agency_manifesto.md", "w") as f:
            f.write("As a member of our Agency, please find below the guiding principles and values that constitute "
                    "our Agency Manifesto:\n\n")

    folder_name = agent_name.lower().replace(" ", "_").strip()

    path = os.path.join(path, folder_name) + "/"

    if os.path.isdir(path):
        raise Exception("Folder already exists.")

    os.mkdir(path)

    class_name = agent_name.title().replace(" ", "").strip()

    with open(path + class_name + ".py", "w") as f:
        f.write(agent_template.format(
            class_name=class_name,
            agent_name=agent_name,
            agent_description=agent_description
        ))

    with open(path + "instructions.md", "w") as f:
        f.write("Below are the specific instructions tailored for you to effectively carry out your assigned role:\n\n")

    os.mkdir(path + "files")

    print("Agent folder created successfully.")


agent_template = """from agency_swarm.agents import BaseAgent

# from agency_swarm.tools import Retrieval, CodeInterpreter


class {class_name}(BaseAgent):
    def __init__(self):
        super().__init__(
            name="{agent_name}",
            description="{agent_description}",
            instructions="./instructions.md",
            files_folder="./files",
            tools=[]
        )
"""
