"""
This example demonstrates how to use openai's connector feature
with the agency swarm framework.

Pre-requisites:
- You need to have a Google Calendar account with some events in the last 6 months.
- Google OAuth token.

## How to get Google OAuth token:
- Go to https://developers.google.com/oauthplayground
- Enter https://www.googleapis.com/auth/calendar.events in the "Input your own scopes" field
- Click on the "Authorize APIs" button
- In the step 2, click on the "Exchange authorization code for tokens" button
- Copy access token and paste it in the "authorization" field in the example below

Run the example with: python examples/connectors.py
Agent will be able to get past events from your Google Calendar.
"""

import datetime

from agents import HostedMCPTool

from agency_swarm import Agency, Agent

current_date = datetime.datetime.now()

calendar_assistant = Agent(
    name="CalendarAssistant",
    instructions=f"You are an assistant that can access user's Google Calendar. Current date is {current_date}.",
    tools=[
        HostedMCPTool(
            tool_config={
                "type": "mcp",
                "server_label": "google_calendar",
                "connector_id": "connector_googlecalendar",
                "authorization": "your-oauth-token",
                "require_approval": "never",
            },
        )
    ],
)

agency = Agency(calendar_assistant)

if __name__ == "__main__":
    print(agency.get_response_sync("name 3 events from my Google Calendar that happened in the last 6 months"))
