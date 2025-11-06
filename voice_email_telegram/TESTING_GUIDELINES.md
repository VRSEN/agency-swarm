# Testing Guidelines for voice_email_telegram

## Overview

These guidelines help Tusk AI generate high-quality, maintainable tests for the voice email telegram agency system.

## Test Structure

### Directory Organization

```
voice_email_telegram/
├── tests/
│   ├── __init__.py
│   ├── test_agency_startup.py       # Agency-level tests
│   ├── test_agents_configuration.py  # Agent configuration tests
│   ├── fixtures/                     # Shared fixtures
│   │   ├── __init__.py
│   │   ├── mock_data.py             # Mock email/voice data
│   │   └── test_helpers.py          # Helper functions
│   ├── ceo/
│   │   ├── test_classify_intent.py
│   │   └── test_workflow_coordinator.py
│   ├── email_specialist/
│   │   ├── test_rube_mcp_client.py
│   │   ├── test_draft_email.py
│   │   └── test_email_validation.py
│   ├── memory_manager/
│   │   ├── test_mem0_operations.py
│   │   └── test_contact_learning.py
│   └── voice_handler/
│       ├── test_voice_processing.py
│       └── test_telegram_integration.py
```

### Naming Conventions

- **Test files**: `test_[module_name].py`
- **Test functions**: `test_[function_name]_[scenario]`
- **Test classes**: `Test[ClassName]` (optional, for grouping)

**Examples:**
```python
# Good
def test_classify_intent_email_drafting()
def test_rube_mcp_client_handles_auth_failure()
def test_mem0_search_returns_empty_for_new_user()

# Bad
def test_1()
def test_function()
def email_test()
```

## What to Test (Symbol Selection)

### ✅ DO Test

1. **Agent Tools** - All custom tools in `*/tools/`
   - Input validation
   - External API interactions (mocked)
   - Error handling
   - Edge cases

2. **Business Logic**
   - Intent classification
   - Email drafting logic
   - Memory learning algorithms
   - Voice processing workflows

3. **Integration Points**
   - Agency communication flows
   - Tool execution within agents
   - State machine transitions

4. **Configuration & Initialization**
   - Agent setup
   - Model settings
   - Tool loading

### ❌ DON'T Test

1. **Simple imports** - `__init__.py` files with only imports
2. **Framework code** - Agency Swarm internals
3. **Third-party libraries** - Composio/Rube SDK, ElevenLabs, Mem0
4. **Simple getters/setters** - Properties with no logic

## Pytest Patterns

### Fixtures for Setup

```python
import pytest
from pathlib import Path

@pytest.fixture
def mock_email_data():
    """Sample email data for testing."""
    return {
        "to": "test@example.com",
        "subject": "Test Subject",
        "body": "Test email body content"
    }

@pytest.fixture
def mock_composio_response():
    """Mock successful Composio API response."""
    return {
        "success": True,
        "data": {"message_id": "msg_123"}
    }

@pytest.fixture
def temp_config_dir(tmp_path):
    """Temporary directory for config files."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir
```

### Parametrization for Multiple Scenarios

```python
@pytest.mark.parametrize("email,expected", [
    ("valid@example.com", True),
    ("invalid-email", False),
    ("", False),
    ("@example.com", False),
])
def test_email_validation(email, expected):
    result = validate_email(email)
    assert result == expected
```

### Mocking External Dependencies

```python
def test_rube_mcp_client_sends_email(monkeypatch):
    """Test RubeMCPClient sends email via Composio API."""

    # Mock requests.post
    def mock_post(url, **kwargs):
        class MockResponse:
            status_code = 200
            def json(self):
                return {"success": True, "data": {"message_id": "123"}}
        return MockResponse()

    monkeypatch.setattr("requests.post", mock_post)

    # Test the tool
    from email_specialist.tools.RubeMCPClient import RubeMCPClient

    client = RubeMCPClient(
        action="gmail_send_email",
        params={"to": "test@example.com", "subject": "Test"}
    )
    result = client.run()

    assert "success" in result
    assert "message_id" in result
```

### Capturing Output

```python
def test_agency_logging(capsys):
    """Test that agency logs startup messages."""
    from agency import agency

    captured = capsys.readouterr()
    assert "Agency loaded" in captured.out or captured.out == ""
```

## Edge Cases to Test

### 1. Data Validation

```python
def test_draft_email_with_empty_recipient():
    """Should raise ValueError for empty recipient."""
    with pytest.raises(ValueError, match="recipient"):
        draft_email(to="", subject="Test", body="Body")

def test_draft_email_with_very_long_body():
    """Should handle emails with 10,000+ characters."""
    long_body = "x" * 10000
    result = draft_email(to="test@example.com", subject="Test", body=long_body)
    assert len(result["body"]) == 10000
```

### 2. Authentication & Authorization

```python
def test_rube_mcp_client_with_invalid_api_key(monkeypatch):
    """Should handle 401 authentication errors gracefully."""
    def mock_post(url, **kwargs):
        class MockResponse:
            status_code = 401
            def json(self):
                return {"error": "Invalid API key"}
        return MockResponse()

    monkeypatch.setattr("requests.post", mock_post)

    client = RubeMCPClient(action="gmail_send_email", params={})
    result = client.run()

    assert "error" in result.lower()
    assert "401" in result
```

### 3. Async Operations & Timing

```python
import asyncio

@pytest.mark.asyncio
async def test_voice_handler_timeout():
    """Should timeout after 30 seconds."""
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            process_voice_input(slow_audio_file),
            timeout=30
        )
```

### 4. Network Failures

```python
def test_rube_mcp_client_handles_network_error(monkeypatch):
    """Should handle connection errors gracefully."""
    import requests

    def mock_post(url, **kwargs):
        raise requests.ConnectionError("Network unreachable")

    monkeypatch.setattr("requests.post", mock_post)

    client = RubeMCPClient(action="gmail_send_email", params={})
    result = client.run()

    assert "error" in result.lower()
    assert "network" in result.lower() or "connection" in result.lower()
```

## Mocking Patterns

### External APIs (Composio/Rube)

```python
@pytest.fixture
def mock_composio_api(monkeypatch):
    """Mock all Composio API calls."""
    responses = {
        "gmail_send_email": {"success": True, "message_id": "123"},
        "gmail_fetch_emails": {"success": True, "emails": []},
        "gmail_create_draft": {"success": True, "draft_id": "456"},
    }

    def mock_post(url, **kwargs):
        action = url.split("/")[-2].lower()

        class MockResponse:
            status_code = 200
            def json(self):
                return responses.get(action, {"error": "Unknown action"})

        return MockResponse()

    monkeypatch.setattr("requests.post", mock_post)
    return responses
```

### Environment Variables

```python
@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set required environment variables."""
    monkeypatch.setenv("COMPOSIO_API_KEY", "test_key_123")
    monkeypatch.setenv("GMAIL_CONNECTION_ID", "conn_123")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot_token_123")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "eleven_key_123")
```

### File Operations

```python
def test_save_draft_to_disk(tmp_path):
    """Test saving draft to temporary file."""
    draft_file = tmp_path / "draft.json"

    draft = {"to": "test@example.com", "body": "Test"}
    save_draft(draft, draft_file)

    assert draft_file.exists()
    loaded = load_draft(draft_file)
    assert loaded == draft
```

## Test Data Organization

### fixtures/mock_data.py

```python
"""Reusable test data."""

SAMPLE_EMAIL = {
    "to": "recipient@example.com",
    "from": "sender@example.com",
    "subject": "Test Subject",
    "body": "This is a test email body.",
    "timestamp": "2025-11-06T12:00:00Z"
}

SAMPLE_VOICE_INPUT = {
    "file_path": "/tmp/voice.ogg",
    "duration": 15.5,
    "format": "ogg",
    "user_id": "12345"
}

SAMPLE_CONTACT = {
    "name": "John Doe",
    "email": "john@example.com",
    "preferences": {
        "greeting": "Hi John",
        "tone": "professional"
    }
}
```

## Performance Guidelines

### Fast Tests

- **Mock all external APIs** - No real HTTP calls
- **Use in-memory data** - Avoid disk I/O when possible
- **Skip slow operations** - Mark with `@pytest.mark.slow`

```python
@pytest.mark.slow
def test_full_email_workflow_integration():
    """End-to-end test (marked slow)."""
    # This test actually calls APIs
    pass
```

### Test Isolation

Each test should be completely independent:

```python
# Good - independent
def test_user_preferences():
    user = create_test_user()
    set_preference(user, "tone", "casual")
    assert get_preference(user, "tone") == "casual"

# Bad - depends on other tests
def test_user_preferences():
    # Assumes user already exists from previous test
    assert get_preference("tone") == "casual"
```

## Assertion Patterns

### Clear, Specific Assertions

```python
# Good
assert result["success"] is True
assert result["email"]["to"] == "test@example.com"
assert len(result["emails"]) == 3

# Bad
assert result  # Too vague
assert result == expected_result  # Hard to debug when fails
```

### Error Messages

```python
# Good
assert len(emails) > 0, f"Expected emails but got empty list"
assert status_code == 200, f"Expected 200 but got {status_code}: {response.text}"

# Bad
assert len(emails) > 0
assert status_code == 200
```

## Coverage Goals

- **Critical paths**: 90%+ coverage
  - RubeMCPClient
  - Intent classification
  - Email drafting logic

- **Integration code**: 70%+ coverage
  - Agency communication
  - Tool execution

- **Configuration**: 50%+ coverage
  - Agent initialization
  - Model settings

## Test Execution

### Running Tests Locally

```bash
# All tests
pytest voice_email_telegram/tests/ -v

# Specific file
pytest voice_email_telegram/tests/test_agency_startup.py -v

# With coverage
pytest voice_email_telegram/tests/ --cov=voice_email_telegram --cov-report=html

# Fast tests only (skip slow integration tests)
pytest voice_email_telegram/tests/ -v -m "not slow"
```

### Tusk Integration

Tusk will automatically:
1. Detect test files matching `test_*.py` pattern
2. Run tests on every PR commit
3. Generate new tests for uncovered code
4. Report failures in PR comments

## Examples

See [tests/](./tests/) directory for complete examples of:
- `test_agency_startup.py` - Agency initialization tests
- `test_agents_configuration.py` - Agent configuration tests

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Tusk Best Practices](https://docs.usetusk.ai/)
- [Agency Swarm Testing Guide](https://github.com/VRSEN/agency-swarm)
