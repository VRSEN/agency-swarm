from pydantic import BaseModel, Field

from agency_swarm import function_tool, run_mcp


class TimeArgs(BaseModel):
    time_zone: str = Field(..., description="The time zone to get the current time for used in")
    time_format: str | None = Field(None, description="The format of the time to return")


# Define the async function that implements the tool logic using the decorator
@function_tool
async def get_unique_id() -> str:
    """Returns a unique id"""
    return "Unique ID: 12332211"


@function_tool
async def get_current_time(args: TimeArgs) -> str:
    """Returns the current time using datetime library"""
    import datetime
    from zoneinfo import ZoneInfo

    try:
        # Use the specified timezone
        tz = ZoneInfo(args.time_zone)
        current_time = datetime.datetime.now(tz)

        # Use custom format if provided, otherwise use default
        if args.time_format:
            formatted_time = current_time.strftime(args.time_format)
        else:
            formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S %Z")

        return f"Current time in {args.time_zone}: {formatted_time}"
    except Exception as e:
        return f"Error getting time for timezone {args.time_zone}: {str(e)}"


if __name__ == "__main__":
    run_mcp(tools=[get_unique_id, get_current_time], transport="stdio")
