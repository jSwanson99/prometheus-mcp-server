"""Tests for the disk_loader module."""

import pytest
from fastmcp import FastMCP, Client

from prometheus_mcp_server.disk_loader import (
    _detect_placeholders,
    load_prompts,
    load_resources,
    load_from_disk,
)


# ---------------------------------------------------------------------------
# Placeholder detection
# ---------------------------------------------------------------------------


class TestDetectPlaceholders:
    def test_no_placeholders(self):
        assert _detect_placeholders("No placeholders here.") == []

    def test_single_placeholder(self):
        assert _detect_placeholders("Hello {name}!") == ["name"]

    def test_multiple_placeholders(self):
        result = _detect_placeholders("{greeting} {name}, welcome to {place}!")
        assert result == ["greeting", "name", "place"]

    def test_repeated_placeholders_deduplicated(self):
        result = _detect_placeholders("{x} and {x} again")
        assert result == ["x"]


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def _prompt(name="test", description="A test prompt", body="Hello {name}!"):
    """Helper to build a valid prompt file string with frontmatter."""
    return f"---\nname: {name}\ndescription: {description}\n---\n{body}"


class TestLoadPrompts:
    def test_nonexistent_directory(self):
        mcp = FastMCP("test")
        count = load_prompts(mcp, "/nonexistent/path")
        assert count == 0

    def test_empty_directory(self, tmp_path):
        mcp = FastMCP("test")
        count = load_prompts(mcp, str(tmp_path))
        assert count == 0

    def test_ignores_non_md(self, tmp_path):
        (tmp_path / "data.json").write_text('{"key": "value"}')
        (tmp_path / "notes.txt").write_text("some notes")
        mcp = FastMCP("test")
        count = load_prompts(mcp, str(tmp_path))
        assert count == 0

    def test_load_md_with_frontmatter(self, tmp_path):
        (tmp_path / "analyze.md").write_text(
            _prompt("analyze", "Analyze a topic", "Please analyze {topic} in detail.")
        )
        mcp = FastMCP("test")
        count = load_prompts(mcp, str(tmp_path))
        assert count == 1

    def test_skip_missing_frontmatter(self, tmp_path):
        (tmp_path / "bare.md").write_text("Hello {name}, no frontmatter here.")
        mcp = FastMCP("test")
        count = load_prompts(mcp, str(tmp_path))
        assert count == 0

    def test_skip_missing_name(self, tmp_path):
        (tmp_path / "noname.md").write_text(
            "---\ndescription: has desc but no name\n---\nHello!"
        )
        mcp = FastMCP("test")
        count = load_prompts(mcp, str(tmp_path))
        assert count == 0

    def test_skip_missing_description(self, tmp_path):
        (tmp_path / "nodesc.md").write_text(
            "---\nname: nodesc\n---\nHello!"
        )
        mcp = FastMCP("test")
        count = load_prompts(mcp, str(tmp_path))
        assert count == 0

    def test_skip_empty_body(self, tmp_path):
        (tmp_path / "empty.md").write_text(
            "---\nname: empty\ndescription: empty body\n---\n"
        )
        mcp = FastMCP("test")
        count = load_prompts(mcp, str(tmp_path))
        assert count == 0

    def test_prompt_without_placeholders(self, tmp_path):
        (tmp_path / "static.md").write_text(
            _prompt("static", "A static prompt", "Hello, world!")
        )
        mcp = FastMCP("test")
        count = load_prompts(mcp, str(tmp_path))
        assert count == 1

    def test_subdirectory_prompts(self, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "nested.md").write_text(
            _prompt("nested", "A nested prompt", "About {topic}.")
        )
        mcp = FastMCP("test")
        count = load_prompts(mcp, str(tmp_path))
        assert count == 1

    @pytest.mark.asyncio
    async def test_prompt_renders_correctly(self, tmp_path):
        (tmp_path / "greet.md").write_text(
            _prompt("greet", "Greet someone", "Hello {name}, welcome to {place}!")
        )
        mcp = FastMCP("test")
        load_prompts(mcp, str(tmp_path))

        async with Client(mcp) as client:
            result = await client.get_prompt(
                "greet", arguments={"name": "Alice", "place": "Wonderland"}
            )
            assert len(result.messages) == 1
            assert "Hello Alice, welcome to Wonderland!" in result.messages[0].content.text

    @pytest.mark.asyncio
    async def test_prompt_no_args_renders(self, tmp_path):
        (tmp_path / "static.md").write_text(
            _prompt("static", "A static prompt", "This is a static prompt.")
        )
        mcp = FastMCP("test")
        load_prompts(mcp, str(tmp_path))

        async with Client(mcp) as client:
            result = await client.get_prompt("static", arguments={})
            assert "This is a static prompt." in result.messages[0].content.text

    @pytest.mark.asyncio
    async def test_prompt_listed(self, tmp_path):
        (tmp_path / "listed.md").write_text(
            _prompt("listed", "A listed prompt", "A prompt about {thing}.")
        )
        mcp = FastMCP("test")
        load_prompts(mcp, str(tmp_path))

        async with Client(mcp) as client:
            prompts = await client.list_prompts()
            names = [p.name for p in prompts]
            assert "listed" in names


# ---------------------------------------------------------------------------
# Resource loading
# ---------------------------------------------------------------------------


class TestLoadResources:
    def test_nonexistent_directory(self):
        mcp = FastMCP("test")
        count = load_resources(mcp, "/nonexistent/path")
        assert count == 0

    def test_empty_directory(self, tmp_path):
        mcp = FastMCP("test")
        count = load_resources(mcp, str(tmp_path))
        assert count == 0

    def test_load_text_file(self, tmp_path):
        (tmp_path / "readme.md").write_text("# README\nHello")
        mcp = FastMCP("test")
        count = load_resources(mcp, str(tmp_path))
        assert count == 1

    def test_load_multiple_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("file a")
        (tmp_path / "b.json").write_text('{"key": "val"}')
        (tmp_path / "c.yaml").write_text("key: val")
        mcp = FastMCP("test")
        count = load_resources(mcp, str(tmp_path))
        assert count == 3

    def test_subdirectory_resources(self, tmp_path):
        subdir = tmp_path / "docs"
        subdir.mkdir()
        (subdir / "guide.md").write_text("# Guide")
        mcp = FastMCP("test")
        count = load_resources(mcp, str(tmp_path))
        assert count == 1

    @pytest.mark.asyncio
    async def test_resource_content_readable(self, tmp_path):
        (tmp_path / "data.txt").write_text("Hello from disk!")
        mcp = FastMCP("test")
        load_resources(mcp, str(tmp_path))

        async with Client(mcp) as client:
            result = await client.read_resource("resource://data.txt")
            text = result[0].text if hasattr(result[0], "text") else str(result[0])
            assert "Hello from disk!" in text

    @pytest.mark.asyncio
    async def test_resource_listed(self, tmp_path):
        (tmp_path / "info.txt").write_text("Some info")
        mcp = FastMCP("test")
        load_resources(mcp, str(tmp_path))

        async with Client(mcp) as client:
            resources = await client.list_resources()
            uris = [str(r.uri) for r in resources]
            assert any("info.txt" in u for u in uris)

    @pytest.mark.asyncio
    async def test_nested_resource_uri(self, tmp_path):
        subdir = tmp_path / "runbooks"
        subdir.mkdir()
        (subdir / "alert.md").write_text("# Alert Runbook")
        mcp = FastMCP("test")
        load_resources(mcp, str(tmp_path))

        async with Client(mcp) as client:
            resources = await client.list_resources()
            uris = [str(r.uri) for r in resources]
            assert any("runbooks/alert.md" in u for u in uris)


# ---------------------------------------------------------------------------
# Integration: load_from_disk
# ---------------------------------------------------------------------------


class TestLoadFromDisk:
    def test_both_none(self):
        mcp = FastMCP("test")
        result = load_from_disk(mcp)
        assert result == {"prompts": 0, "resources": 0}

    def test_both_dirs(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "ask.md").write_text(
            _prompt("ask", "Ask about a topic", "Tell me about {topic}.")
        )

        resources_dir = tmp_path / "resources"
        resources_dir.mkdir()
        (resources_dir / "doc.md").write_text("# Doc")

        mcp = FastMCP("test")
        result = load_from_disk(
            mcp,
            prompts_dir=str(prompts_dir),
            resources_dir=str(resources_dir),
        )
        assert result["prompts"] == 1
        assert result["resources"] == 1

    def test_only_prompts(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "q.md").write_text(
            _prompt("q", "Question prompt", "Question about {topic}.")
        )

        mcp = FastMCP("test")
        result = load_from_disk(mcp, prompts_dir=str(prompts_dir))
        assert result["prompts"] == 1
        assert result["resources"] == 0

    def test_only_resources(self, tmp_path):
        resources_dir = tmp_path / "resources"
        resources_dir.mkdir()
        (resources_dir / "file.txt").write_text("content")

        mcp = FastMCP("test")
        result = load_from_disk(mcp, resources_dir=str(resources_dir))
        assert result["prompts"] == 0
        assert result["resources"] == 1
