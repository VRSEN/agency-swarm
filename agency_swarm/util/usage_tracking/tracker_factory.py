from typing import Literal

from agency_swarm.util.usage_tracking.langfuse_tracker import LangfuseUsageTracker
from agency_swarm.util.usage_tracking.sqlite_tracker import SQLiteUsageTracker


def get_tracker(tracker_type: Literal["sqlite", "langfuse"] = "sqlite"):
    if tracker_type == "langfuse":
        return LangfuseUsageTracker()
    return SQLiteUsageTracker()
