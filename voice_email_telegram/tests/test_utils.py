import os
import sys

import pytest

# Add the project root directory to the Python path to allow for absolute imports.
# This makes the test runner able to find the 'voice_email_telegram' package.
# The project root is two levels up from the current test file's directory.
# (voice_email_telegram/tests/test_utils.py -> voice_email_telegram/tests -> voice_email_telegram -> project_root)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from voice_email_telegram.utils import truncate_text, validate_email  # noqa: E402


@pytest.mark.parametrize(
    "email, expected",
    [
        # Test scenario: Happy path with a well-formed email
        ("user@example.com", True),
        # Test scenario: Email with subdomains and multiple dots in the domain
        ("john.doe@sub.domain.com", True),
        # Test scenario: Email address with length of 254
        (
            "very.long.email.address."
            "with.many.parts.to.exceed.the.limit"
            "@very.long.domain.name.with.many.parts."
            "to.exceed.the.limit.com",
            True,
        ),
        # Test scenario: Email with domain ending in a dot and no TLD
        ("user@domain.", False),
        # Test scenario: Email with special characters in the local part
        ("user+tag@example.com", True),
        # [Tusk] FAILING TEST
        # Test scenario: Email address with special characters in the domain part
        ("user@domain!.com", False),
    ],
)
def test_validate_email_scenarios(email: str, expected: bool):
    """
    Tests the validate_email function with various email formats.
    """
    # Act: Call the function with the test input email.
    result = validate_email(email)

    # Assert: Check if the function's output matches the expected boolean value.
    assert result is expected


@pytest.mark.parametrize(
    "text_input, max_length, expected_output",
    [
        # Test scenario: text is longer than max_length (>=3), should be truncated with ellipsis
        (
            "This is a very long string that needs to be truncated.",
            20,
            "This is a very lo...",
        ),
        # Test scenario: text is shorter than max_length, should return original text
        ("Short text", 20, "Short text"),
        # Test scenario: Input is None, should return an empty string
        (None, 20, ""),
        # Test scenario: Text with Unicode characters (emojis)
        (
            "Hello world! 😊😊",
            10,
            "Hello w...",
        ),
        # Test scenario: max_length is exactly 3, should return "..."
        ("Some long text", 3, "..."),
    ],
)
def test_truncate_text_scenarios(
    text_input: str, max_length: int, expected_output: str
):
    """
    Tests the truncate_text function with various inputs and scenarios.
    """
    # Act: Call the function with the test input
    result = truncate_text(text_input, max_length)

    # Assert: Check if the result matches the expected outcome and length
    assert result == expected_output

    if text_input is None:
        assert len(result) == 0
    elif len(text_input) > max_length:
        assert len(result) == max_length
    else:
        assert len(result) == len(text_input)
