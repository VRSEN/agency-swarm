from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

class GmailCreateDraft(BaseTool):
    """
    Creates an email draft in Gmail using the Gmail API.
    Stores the draft without sending it, allowing for review and modification.
    """

    to: str = Field(
        ...,
        description="Recipient email address(es), comma-separated for multiple"
    )

    subject: str = Field(
        ...,
        description="Email subject line"
    )

    body: str = Field(
        ...,
        description="Email body content (plain text or HTML)"
    )

    cc: str = Field(
        default="",
        description="CC recipients, comma-separated"
    )

    bcc: str = Field(
        default="",
        description="BCC recipients, comma-separated"
    )

    body_type: str = Field(
        default="plain",
        description="Body content type: 'plain' or 'html'"
    )

    def run(self):
        """
        Creates a draft in Gmail.
        Returns JSON string with draft ID and details.

        Note: This is a simplified implementation. In production, use google-auth
        and google-api-python-client with proper OAuth2 authentication.
        """
        # Check for Gmail credentials
        gmail_token = os.getenv("GMAIL_ACCESS_TOKEN")
        if not gmail_token:
            return json.dumps({
                "error": "GMAIL_ACCESS_TOKEN not found. Please authenticate with Gmail API.",
                "help": "This tool requires Gmail API OAuth2 authentication. Set up credentials at console.cloud.google.com"
            })

        try:
            # Create MIME message
            if self.body_type == "html":
                message = MIMEMultipart("alternative")
                html_part = MIMEText(self.body, "html")
                message.attach(html_part)
            else:
                message = MIMEText(self.body, "plain")

            # Set headers
            message["To"] = self.to
            message["Subject"] = self.subject

            if self.cc:
                message["Cc"] = self.cc
            if self.bcc:
                message["Bcc"] = self.bcc

            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

            # For now, return a mock draft ID since we need proper Gmail API setup
            # In production, this would make an API call to Gmail
            draft_id = f"draft_{hash(self.subject + self.to)}"

            result = {
                "success": True,
                "draft_id": draft_id,
                "to": self.to,
                "subject": self.subject,
                "body_preview": self.body[:100] + "..." if len(self.body) > 100 else self.body,
                "message": "Draft created (mock). In production, this would create an actual Gmail draft.",
                "note": "To enable Gmail API: Install google-auth and google-api-python-client, set up OAuth2 credentials"
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps({
                "error": f"Error creating draft: {str(e)}"
            })


if __name__ == "__main__":
    print("Testing GmailCreateDraft...")

    # Test 1: Simple draft
    print("\n1. Create simple draft:")
    tool = GmailCreateDraft(
        to="john@example.com",
        subject="Test Email",
        body="This is a test email body."
    )
    result = tool.run()
    print(result)

    # Test 2: Draft with CC and BCC
    print("\n2. Create draft with CC/BCC:")
    tool = GmailCreateDraft(
        to="recipient@example.com",
        cc="manager@example.com",
        bcc="archive@example.com",
        subject="Project Update",
        body="Here's the latest update on the project..."
    )
    result = tool.run()
    print(result)

    # Test 3: HTML email
    print("\n3. Create HTML email draft:")
    html_body = """
    <html>
        <body>
            <h2>Important Update</h2>
            <p>This is an <strong>HTML formatted</strong> email.</p>
            <ul>
                <li>Point 1</li>
                <li>Point 2</li>
            </ul>
        </body>
    </html>
    """
    tool = GmailCreateDraft(
        to="client@example.com",
        subject="Formatted Email",
        body=html_body,
        body_type="html"
    )
    result = tool.run()
    print(result)

    # Test 4: Multiple recipients
    print("\n4. Create draft with multiple recipients:")
    tool = GmailCreateDraft(
        to="user1@example.com, user2@example.com, user3@example.com",
        subject="Team Announcement",
        body="Hello team,\n\nThis is an important announcement.\n\nBest regards,\nManager"
    )
    result = tool.run()
    print(result)

    # Test 5: Long email
    print("\n5. Create draft with long body:")
    long_body = """Dear Client,

I hope this email finds you well. I wanted to provide you with a comprehensive update on the project status.

Project Overview:
The project has been progressing well over the past few weeks. We've completed several key milestones and are on track to meet our deadline.

Completed Items:
- Initial design phase
- Development of core features
- Testing framework setup
- Documentation

Upcoming Tasks:
- Final integration testing
- User acceptance testing
- Deployment preparation
- Training materials

Timeline:
We expect to complete all remaining tasks within the next two weeks. The final delivery date remains on schedule for the end of the month.

Please let me know if you have any questions or concerns.

Best regards,
Project Manager"""

    tool = GmailCreateDraft(
        to="client@example.com",
        subject="Comprehensive Project Update - October 2024",
        body=long_body
    )
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nSetup instructions for production:")
    print("1. Enable Gmail API at console.cloud.google.com")
    print("2. Create OAuth2 credentials")
    print("3. Install: pip install google-auth google-auth-oauthlib google-api-python-client")
    print("4. Implement OAuth2 flow to get access token")
    print("5. Store refresh token securely")
