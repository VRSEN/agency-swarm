from typing import Literal

from agency_swarm.util.tracking.langfuse_tracker import LangfuseTracker
from agency_swarm.util.tracking.sqlite_tracker import SQLiteTracker


def get_tracker_by_name(tracker_type: Literal["sqlite", "langfuse"] = "sqlite"):
    if tracker_type == "langfuse":
        return LangfuseTracker()
    return SQLiteTracker()
