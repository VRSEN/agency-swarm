"""
Tests for multimodal tool outputs (images and files).
"""

import json

from agency_swarm.tools.utils import parse_multimodal_output


class TestMultimodalOutputParsing:
    """Test parsing of multimodal outputs from tools."""

    def test_preserves_valid_dict_output(self):
        """Should preserve valid multimodal dict output."""
        data = {"type": "image_url", "image_url": {"url": "data:image/png;base64,ABC"}}
        result = parse_multimodal_output(data)
        assert result == data

    def test_preserves_valid_list_output(self):
        """Should preserve valid multimodal list output."""
        data = [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,ABC"}},
            {"type": "file", "file": {"file_id": "file-123"}},
        ]
        result = parse_multimodal_output(data)
        assert result == data

    def test_converts_invalid_dict_to_json_string(self):
        """Should encode non-multimodal dicts as JSON strings."""
        data = {"key": "value", "number": 42}
        result = parse_multimodal_output(data)
        assert result == json.dumps(data)

    def test_parses_valid_json_string(self):
        """Should parse JSON string that matches multimodal format."""
        data = {"type": "image_url", "image_url": {"url": "data:image/png;base64,ABC"}}
        json_str = json.dumps(data)
        result = parse_multimodal_output(json_str)
        assert result == data

    def test_preserves_invalid_json_string(self):
        """Should preserve string that doesn't match multimodal format."""
        text = "This is just plain text"
        result = parse_multimodal_output(text)
        assert result == text

    def test_converts_non_json_string(self):
        """Should preserve non-JSON string as-is."""
        text = "not valid json {{"
        result = parse_multimodal_output(text)
        assert result == text

    def test_converts_number_to_string(self):
        """Should convert numbers to strings."""
        assert parse_multimodal_output(42) == "42"
        assert parse_multimodal_output(3.14) == "3.14"

    def test_converts_none_to_string(self):
        """Should convert None to string."""
        assert parse_multimodal_output(None) == "None"

    def test_converts_boolean_to_string(self):
        """Should convert booleans to strings."""
        assert parse_multimodal_output(True) == "True"
        assert parse_multimodal_output(False) == "False"

    def test_converts_empty_list_to_string(self):
        """Should encode empty list outputs as JSON."""
        result = parse_multimodal_output([])
        assert result == json.dumps([])

    def test_converts_mixed_list_to_string(self):
        """Should stringify lists containing invalid multimodal items."""
        data = [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,ABC"}},
            {"invalid": "item"},
        ]
        result = parse_multimodal_output(data)
        assert result == json.dumps(data)

    def test_converts_non_serializable_dict_to_json_string(self):
        """Should encode unknown types via JSON default handler."""
        from datetime import datetime

        data = {"created_at": datetime(2024, 1, 1)}
        result = parse_multimodal_output(data)
        assert result == json.dumps(data, default=str)


class TestMultimodalOutputFormats:
    """Test specific multimodal output formats."""

    def test_base64_image_format(self):
        """Should handle base64-encoded image format."""
        # Simple 1x1 transparent PNG
        base64_img = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        output = {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{base64_img}"},
        }
        result = parse_multimodal_output(output)
        assert result == output

    def test_file_reference_format(self):
        """Should handle file reference format."""
        output = {"type": "file", "file": {"file_id": "file-6F2ksmvXxt4VdoqmHRw6kL"}}
        result = parse_multimodal_output(output)
        assert result == output

    def test_multiple_images_format(self):
        """Should handle multiple images in list."""
        output = [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,IMG1"}},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,IMG2"}},
        ]
        result = parse_multimodal_output(output)
        assert result == output

    def test_mixed_multimodal_types(self):
        """Should handle mixed images and files in list."""
        output = [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,ABC"}},
            {"type": "file", "file": {"file_id": "file-123"}},
        ]
        result = parse_multimodal_output(output)
        assert result == output
