from agency_swarm.tools import BaseTool
from pydantic import Field
import json
import re
from dotenv import load_dotenv

load_dotenv()

class ValidateEmailContent(BaseTool):
    """
    Validates an email draft to ensure all required fields are present and properly formatted.
    Checks for recipient email format, subject line presence, body content,
    and identifies any issues that would prevent successful email delivery.
    """

    draft: str = Field(
        ...,
        description="JSON string containing the email draft (to, subject, body)"
    )

    def run(self):
        """
        Validates the draft and returns validation results.
        Returns a JSON string with is_valid flag and any errors/warnings.
        """
        try:
            # Parse draft
            draft_data = json.loads(self.draft)

            errors = []
            warnings = []
            is_valid = True

            # Check for required fields
            if "to" not in draft_data or not draft_data["to"]:
                errors.append("Missing recipient email address")
                is_valid = False
            else:
                # Validate email format
                recipient = draft_data["to"].strip()
                # Simple email regex pattern
                email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

                # Handle multiple recipients (comma-separated)
                recipients = [r.strip() for r in recipient.split(",")]
                invalid_recipients = []

                for rec in recipients:
                    if not re.match(email_pattern, rec):
                        invalid_recipients.append(rec)

                if invalid_recipients:
                    errors.append(f"Invalid email format: {', '.join(invalid_recipients)}")
                    is_valid = False

            # Check subject
            if "subject" not in draft_data or not draft_data["subject"]:
                warnings.append("Subject line is empty - email may be marked as spam")
            else:
                subject = draft_data["subject"].strip()
                if len(subject) > 200:
                    warnings.append("Subject line is very long (>200 chars) - may be truncated")
                if len(subject) < 3:
                    warnings.append("Subject line is very short - consider making it more descriptive")

            # Check body
            if "body" not in draft_data or not draft_data["body"]:
                errors.append("Email body is empty")
                is_valid = False
            else:
                body = draft_data["body"].strip()
                if len(body) < 10:
                    warnings.append("Email body is very short - consider adding more detail")

                # Check for common issues
                if "MISSING" in body.upper():
                    warnings.append("Email body contains 'MISSING' - may need user clarification")

                # Check for signature
                if not any(closing in body for closing in ["Best regards", "Sincerely", "Thanks", "Regards", "Cheers", "Best"]):
                    warnings.append("Email may be missing a closing/signature")

            # Check for placeholder text
            placeholders = ["[INSERT", "[TODO", "XXX", "FIXME", "[User]", "[Name]"]
            for placeholder in placeholders:
                if placeholder in draft_data.get("body", ""):
                    warnings.append(f"Email contains placeholder text: {placeholder}")

            # Additional checks
            if "cc" in draft_data and draft_data["cc"]:
                cc_emails = [e.strip() for e in draft_data["cc"].split(",")]
                invalid_cc = [e for e in cc_emails if not re.match(email_pattern, e)]
                if invalid_cc:
                    errors.append(f"Invalid CC email format: {', '.join(invalid_cc)}")
                    is_valid = False

            if "bcc" in draft_data and draft_data["bcc"]:
                bcc_emails = [e.strip() for e in draft_data["bcc"].split(",")]
                invalid_bcc = [e for e in bcc_emails if not re.match(email_pattern, e)]
                if invalid_bcc:
                    errors.append(f"Invalid BCC email format: {', '.join(invalid_bcc)}")
                    is_valid = False

            # Build result
            result = {
                "is_valid": is_valid,
                "errors": errors,
                "warnings": warnings,
                "fields_checked": {
                    "recipient": "to" in draft_data and bool(draft_data.get("to")),
                    "subject": "subject" in draft_data and bool(draft_data.get("subject")),
                    "body": "body" in draft_data and bool(draft_data.get("body"))
                }
            }

            if is_valid:
                result["message"] = "Email draft is valid and ready to send"
            else:
                result["message"] = "Email draft has errors that must be fixed before sending"

            return json.dumps(result, indent=2)

        except json.JSONDecodeError as e:
            return json.dumps({
                "is_valid": False,
                "errors": [f"Invalid JSON format: {str(e)}"],
                "warnings": [],
                "message": "Cannot validate - draft is not valid JSON"
            })
        except Exception as e:
            return json.dumps({
                "is_valid": False,
                "errors": [f"Validation error: {str(e)}"],
                "warnings": [],
                "message": "Validation failed due to unexpected error"
            })


if __name__ == "__main__":
    # Test email validation with various scenarios
    print("Testing ValidateEmailContent...")

    # Test 1: Valid complete email
    print("\n1. Valid complete email:")
    draft = json.dumps({
        "to": "john@acmecorp.com",
        "subject": "Shipment Delay Update",
        "body": "Hi John,\n\nI wanted to let you know about a delay in your shipment. It will arrive Tuesday instead of Monday.\n\nBest regards,\nSarah"
    })
    tool = ValidateEmailContent(draft=draft)
    result = tool.run()
    print(result)

    # Test 2: Missing recipient
    print("\n2. Missing recipient:")
    draft = json.dumps({
        "subject": "Test Subject",
        "body": "Test body"
    })
    tool = ValidateEmailContent(draft=draft)
    result = tool.run()
    print(result)

    # Test 3: Invalid email format
    print("\n3. Invalid email format:")
    draft = json.dumps({
        "to": "not-an-email",
        "subject": "Test",
        "body": "Test body content"
    })
    tool = ValidateEmailContent(draft=draft)
    result = tool.run()
    print(result)

    # Test 4: Empty subject and body
    print("\n4. Empty subject (warning):")
    draft = json.dumps({
        "to": "valid@example.com",
        "subject": "",
        "body": "This has content but no subject"
    })
    tool = ValidateEmailContent(draft=draft)
    result = tool.run()
    print(result)

    # Test 5: Multiple recipients
    print("\n5. Multiple recipients (one invalid):")
    draft = json.dumps({
        "to": "john@example.com, invalid-email, sarah@test.com",
        "subject": "Team Update",
        "body": "Hello everyone,\n\nHere's the update.\n\nBest regards,\nManager"
    })
    tool = ValidateEmailContent(draft=draft)
    result = tool.run()
    print(result)

    # Test 6: Placeholder text
    print("\n6. Contains placeholder text:")
    draft = json.dumps({
        "to": "client@example.com",
        "subject": "Proposal",
        "body": "Dear [Name],\n\nPlease review the attached proposal.\n\nBest regards,\n[User]"
    })
    tool = ValidateEmailContent(draft=draft)
    result = tool.run()
    print(result)

    # Test 7: Very short body
    print("\n7. Very short body (warning):")
    draft = json.dumps({
        "to": "test@example.com",
        "subject": "Quick note",
        "body": "Thanks"
    })
    tool = ValidateEmailContent(draft=draft)
    result = tool.run()
    print(result)

    # Test 8: With CC and BCC
    print("\n8. With valid CC and BCC:")
    draft = json.dumps({
        "to": "primary@example.com",
        "cc": "manager@example.com, team@example.com",
        "bcc": "archive@example.com",
        "subject": "Project Update",
        "body": "Here's the latest update on the project.\n\nBest regards,\nTeam Lead"
    })
    tool = ValidateEmailContent(draft=draft)
    result = tool.run()
    print(result)

    # Test 9: Long subject line
    print("\n9. Very long subject line:")
    draft = json.dumps({
        "to": "user@example.com",
        "subject": "This is an extremely long subject line that goes on and on and on and contains way too much information that should probably be in the body of the email instead of the subject line because it exceeds the recommended length",
        "body": "Short body"
    })
    tool = ValidateEmailContent(draft=draft)
    result = tool.run()
    print(result)

    # Test 10: Missing body
    print("\n10. Missing body:")
    draft = json.dumps({
        "to": "recipient@example.com",
        "subject": "Empty Email"
    })
    tool = ValidateEmailContent(draft=draft)
    result = tool.run()
    print(result)

    print("\nAll tests completed!")
