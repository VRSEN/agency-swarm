from agency_swarm import BaseTool


class CheckCurrentDir(BaseTool):
    """
    This tool checks the current directory.
    """

    def run(self):
        import os

        return os.getcwd()
