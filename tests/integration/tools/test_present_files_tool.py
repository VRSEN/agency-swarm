"""Integration tests for PresentFiles tool."""

from pathlib import Path

import pytest

from agency_swarm import Agent
from agency_swarm.tools.built_in import PresentFiles


def _expected_mnt_path(source_path: Path, mnt_dir: Path) -> Path:
    cwd = Path.cwd().resolve()
    resolved = source_path.resolve()
    try:
        relative = resolved.relative_to(cwd)
        return mnt_dir / relative
    except ValueError:
        anchor = resolved.anchor.strip("\\/").replace(":", "")
        if not anchor:
            anchor = "abs"
        anchor = anchor.replace("\\", "_").replace("/", "_")
        return mnt_dir / anchor / Path(*resolved.parts[1:])


@pytest.fixture
def agent_with_present_files():
    """Create an agent with PresentFiles tool."""
    return Agent(
        name="PresentFilesAgent",
        description="Test agent with file preview capability",
        instructions="Present files when requested",
        tools=[PresentFiles],
    )


class TestPresentFilesBasics:
    """Test basic file preview functionality."""

    def test_moves_common_file_types_to_mnt(self, agent_with_present_files, tmp_path, monkeypatch):
        mnt_dir = tmp_path / "mnt"
        monkeypatch.setenv("MNT_DIR", str(mnt_dir))

        sample_files = {
            "example.txt": b"sample",
            "example.csv": b"col1,col2\n1,2\n",
            "example.md": b"# Example\n",
            "example.pdf": b"%PDF-1.4\n%%EOF",
            "example.docx": b"PK\x03\x04",
            "example.png": b"\x89PNG\r\n\x1a\n",
            "example.jpg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9",
            "example.jpeg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9",
            "example.gif": b"GIF89a",
            "example.svg": b"<?xml version='1.0' encoding='UTF-8'?><svg xmlns='http://www.w3.org/2000/svg'/>",
            "example.mp3": b"ID3",
            "example.mp4": b"\x00\x00\x00\x18ftypmp42",
            "example.wav": b"RIFF",
            "example.zip": b"PK\x03\x04",
            "example.tar": b"ustar",
            "example.pptx": b"PK\x03\x04",
            "example.py": b"print('hello')\n",
            "example.js": b"console.log('hello');\n",
            "example.ts": b"console.log('hello');\n",
        }
        file_paths = []
        expected_sizes = {}
        for name, payload in sample_files.items():
            sample_file = tmp_path / name
            sample_file.write_bytes(payload)
            file_paths.append(str(sample_file))
            expected_sizes[name] = sample_file.stat().st_size

        tool = PresentFiles(files=file_paths)
        tool._caller_agent = agent_with_present_files

        result = tool.run()

        assert result.get("errors") == []
        returned_files = result.get("files", [])
        assert len(returned_files) == len(sample_files)
        returned_names = {entry["name"] for entry in returned_files}
        assert returned_names == set(sample_files.keys())
        for entry in returned_files:
            assert isinstance(entry["mime_type"], str)
            assert entry["mime_type"]
            assert entry["size_bytes"] == expected_sizes[entry["name"]]
        assert Path(entry["path"]).is_relative_to(mnt_dir)
        assert Path(entry["path"]).name == entry["name"]

    def test_moves_file_to_mnt(self, agent_with_present_files, tmp_path, monkeypatch):
        src_file = tmp_path / "report.pdf"
        src_file.write_text("%PDF-1.4\n%%EOF")
        expected_size = src_file.stat().st_size
        mnt_dir = tmp_path / "mnt"
        monkeypatch.setenv("MNT_DIR", str(mnt_dir))

        tool = PresentFiles(files=[str(src_file)])
        tool._caller_agent = agent_with_present_files

        result = tool.run()

        assert isinstance(result, dict)
        assert result.get("errors") == []
        assert len(result.get("files", [])) == 1

        file_entry = result["files"][0]
        assert file_entry["name"] == "report.pdf"
        assert file_entry["mime_type"] == "application/pdf"
        assert file_entry["size_bytes"] == expected_size

        dest_path = Path(file_entry["path"])
        assert dest_path.exists()
        assert dest_path.is_relative_to(mnt_dir)
        assert not src_file.exists()

    def test_keeps_file_already_in_mnt(self, agent_with_present_files, tmp_path, monkeypatch):
        mnt_dir = tmp_path / "mnt"
        mnt_dir.mkdir()
        existing_file = mnt_dir / "chart.png"
        existing_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        monkeypatch.setenv("MNT_DIR", str(mnt_dir))

        tool = PresentFiles(files=[str(existing_file)])
        tool._caller_agent = agent_with_present_files

        result = tool.run()

        assert result.get("errors") == []
        assert len(result.get("files", [])) == 1
        file_entry = result["files"][0]
        assert Path(file_entry["path"]).resolve() == existing_file.resolve()
        assert existing_file.exists()

    def test_overwrites_existing_file_in_mnt(self, agent_with_present_files, tmp_path, monkeypatch):
        mnt_dir = tmp_path / "mnt"
        mnt_dir.mkdir()
        src_file = tmp_path / "report.pdf"
        src_file.write_text("new")
        monkeypatch.setenv("MNT_DIR", str(mnt_dir))
        existing_file = _expected_mnt_path(src_file, mnt_dir)
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("old")

        tool = PresentFiles(files=[str(src_file)])
        tool._caller_agent = agent_with_present_files

        result = tool.run()

        assert result.get("errors") == []
        assert len(result.get("files", [])) == 1
        file_entry = result["files"][0]
        assert Path(file_entry["path"]).resolve() == existing_file.resolve()
        assert existing_file.read_text() == "new"
        assert not src_file.exists()

    def test_preserves_structure_for_same_basename(self, agent_with_present_files, tmp_path, monkeypatch):
        mnt_dir = tmp_path / "mnt"
        monkeypatch.setenv("MNT_DIR", str(mnt_dir))

        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        file_a = dir_a / "report.pdf"
        file_b = dir_b / "report.pdf"
        file_a.write_text("alpha")
        file_b.write_text("beta")

        tool = PresentFiles(files=[str(file_a), str(file_b)])
        tool._caller_agent = agent_with_present_files

        result = tool.run()

        assert result.get("errors") == []
        returned_files = result.get("files", [])
        assert len(returned_files) == 2
        paths = {Path(entry["path"]).resolve() for entry in returned_files}
        assert len(paths) == 2
        assert _expected_mnt_path(file_a, mnt_dir) in paths
        assert _expected_mnt_path(file_b, mnt_dir) in paths


class TestPresentFilesErrorHandling:
    """Test error handling and validations."""

    def test_directory_path_reports_error(self, agent_with_present_files, tmp_path, monkeypatch):
        mnt_dir = tmp_path / "mnt"
        monkeypatch.setenv("MNT_DIR", str(mnt_dir))

        tool = PresentFiles(files=[str(tmp_path)])
        tool._caller_agent = agent_with_present_files

        result = tool.run()

        assert result.get("files") == []
        assert len(result.get("errors", [])) == 1
        assert "directory" in result["errors"][0].lower()

    def test_missing_file_reports_error(self, agent_with_present_files, tmp_path, monkeypatch):
        missing_file = tmp_path / "missing.txt"
        mnt_dir = tmp_path / "mnt"
        monkeypatch.setenv("MNT_DIR", str(mnt_dir))

        tool = PresentFiles(files=[str(missing_file)])
        tool._caller_agent = agent_with_present_files

        result = tool.run()

        assert result.get("files") == []
        assert len(result.get("errors", [])) == 1
        assert "not found" in result["errors"][0].lower()

    def test_rejects_large_file(self, agent_with_present_files, tmp_path, monkeypatch):
        large_file = tmp_path / "large.bin"
        large_file.write_bytes(b"x" * 20)
        mnt_dir = tmp_path / "mnt"
        monkeypatch.setenv("MNT_DIR", str(mnt_dir))
        monkeypatch.setenv("FILE_PREVIEW_MAX_BYTES", "10")

        tool = PresentFiles(files=[str(large_file)])
        tool._caller_agent = agent_with_present_files

        result = tool.run()

        assert result.get("files") == []
        assert len(result.get("errors", [])) == 1
        assert "exceeds" in result["errors"][0].lower()
        moved_file = _expected_mnt_path(large_file, mnt_dir)
        assert moved_file.exists()
        assert not large_file.exists()

    def test_rejects_large_file_already_in_mnt(self, agent_with_present_files, tmp_path, monkeypatch):
        mnt_dir = tmp_path / "mnt"
        mnt_dir.mkdir()
        large_file = mnt_dir / "large.bin"
        large_file.write_bytes(b"x" * 20)
        monkeypatch.setenv("MNT_DIR", str(mnt_dir))
        monkeypatch.setenv("FILE_PREVIEW_MAX_BYTES", "10")

        tool = PresentFiles(files=[str(large_file)])
        tool._caller_agent = agent_with_present_files

        result = tool.run()

        assert result.get("files") == []
        assert len(result.get("errors", [])) == 1
        assert "exceeds" in result["errors"][0].lower()
        assert large_file.exists()
