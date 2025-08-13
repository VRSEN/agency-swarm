from dotenv import load_dotenv

# Automatically load environment variables from .env when the package is imported
load_dotenv(override=True)

from .agency import Agency  # noqa: E402
from .agent_core import Agent  # noqa: E402
from .context import MasterContext  # noqa: E402
from .hooks import PersistenceHooks  # noqa: E402
from .thread import ThreadManager  # noqa: E402
from .tools import BaseTool  # noqa: E402
from .tools.send_message import SendMessage  # noqa: E402

__all__ = [
    "Agent",
    "Agency",
    "BaseTool",
    "MasterContext",
    "ThreadManager",
    "PersistenceHooks",
    "SendMessage",
]
