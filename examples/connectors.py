"""
This example demonstrates how to use openai's connector feature
with the agency swarm framework.

Pre-requisites:
- You need a Google Calendar account.
- A Google OAuth access token exported as GOOGLE_CALENDAR_ACCESS_TOKEN.

## How to get Google OAuth token:
- Go to https://developers.google.com/oauthplayground
- Enter https://www.googleapis.com/auth/calendar.events in the "Input your own scopes" field
- Click on the "Authorize APIs" button
- In the step 2, click on the "Exchange authorization code for tokens" button
- Copy access token and export it:
  GOOGLE_CALENDAR_ACCESS_TOKEN="ya29..."

Run the example with: python examples/connectors.py
Agent will be able to read visible events from your Google Calendar.
"""

import datetime
import os
import sys

from agents import HostedMCPTool

from agency_swarm import Agency, Agent

GOOGLE_CALENDAR_ACCESS_TOKEN_ENV = "GOOGLE_CALENDAR_ACCESS_TOKEN"


def _missing_token_message() -> str:
    return (
        f"SKIPPED: {GOOGLE_CALENDAR_ACCESS_TOKEN_ENV} is not set. "
        "Create a Google OAuth access token with the calendar.events scope and export it before running this example."
    )


def create_calendar_agency(access_token: str) -> Agency:
    """Create the Google Calendar connector agency with a real OAuth token."""
    current_date = datetime.datetime.now(tz=datetime.UTC).date()
    calendar_assistant = Agent(
        name="CalendarAssistant",
        instructions=(
            "You are an assistant that can access the user's Google Calendar. "
            f"Current date is {current_date}. If no matching events are visible, say that clearly."
        ),
        tools=[
            HostedMCPTool(
                tool_config={
                    "type": "mcp",
                    "server_label": "google_calendar",
                    "connector_id": "connector_googlecalendar",
                    "authorization": access_token,
                    "require_approval": "never",
                },
            )
        ],
    )
    return Agency(calendar_assistant)


def main() -> int:
    access_token = os.getenv(GOOGLE_CALENDAR_ACCESS_TOKEN_ENV)
    if not access_token:
        print(_missing_token_message(), file=sys.stderr)
        return 2

    agency = create_calendar_agency(access_token)
    response = agency.get_response_sync(
        "List up to 3 visible Google Calendar events from the last 6 months. "
        "For each event, include the title and date. If no events are visible, say so."
    )
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
