"""Load prompts and resources from directories on disk.

Prompts: Markdown files with required YAML frontmatter. The frontmatter must
include ``name`` and ``description``. The body is the prompt template — any
``{arg}`` placeholders are auto-detected as required prompt arguments.

Resources: Any file is served as a static resource. The URI is derived from
the relative path (``resource://<relpath>``). MIME type is inferred from the
file extension.
"""

import re
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import AnyUrl
from fastmcp.prompts.base import Prompt, PromptArgument
from fastmcp.resources import FileResource

from prometheus_mcp_server.logging_config import get_logger

logger = get_logger()


def _detect_placeholders(template: str) -> List[str]:
    """Extract unique ``{name}`` placeholders from a template string,
    preserving first-occurrence order."""
    seen: set[str] = set()
    result: List[str] = []
    for name in re.findall(r"\{(\w+)\}", template):
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


class TemplatePrompt(Prompt):
    """A prompt backed by a string template with ``{arg}`` placeholders."""

    template: str

    async def render(self, arguments: dict[str, Any] | None = None) -> str:
        return self.template.format(**(arguments or {}))


def load_prompts(mcp: Any, prompts_dir: str) -> int:
    """Scan *prompts_dir* and register each ``.md`` file as an MCP prompt.

    Each file must contain YAML frontmatter (``---`` delimited) with at least
    ``name`` and ``description`` keys, followed by the prompt template body.

    Returns the number of prompts registered.
    """
    prompts_path = Path(prompts_dir)
    if not prompts_path.is_dir():
        logger.warning("Prompts directory does not exist", path=prompts_dir)
        return 0

    count = 0
    for file_path in sorted(prompts_path.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix != ".md":
            logger.warning("Skipping non-markdown prompt file", path=str(file_path))
            continue

        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error(
                "Failed to read prompt file", path=str(file_path), error=str(exc)
            )
            continue

        try:
            docs = list(yaml.safe_load_all(text))
        except yaml.YAMLError as exc:
            logger.error(
                "Invalid YAML in prompt file", path=str(file_path), error=str(exc)
            )
            continue

        if len(docs) < 2 or not isinstance(docs[0], dict):
            logger.warning(
                "Prompt file missing required frontmatter, skipping",
                path=str(file_path),
            )
            continue

        meta = docs[0]
        body = str(docs[1]).strip() if docs[1] is not None else ""
        if not body:
            logger.warning("Prompt file has no body, skipping", path=str(file_path))
            continue

        name = meta.get("name")
        description = meta.get("description")
        if not name or not description:
            logger.warning(
                "Prompt frontmatter missing name or description, skipping",
                path=str(file_path),
            )
            continue

        placeholders = _detect_placeholders(body)

        prompt = TemplatePrompt(
            name=name,
            description=description,
            template=body,
            arguments=[PromptArgument(name=p, required=True) for p in placeholders]
            or None,
        )
        mcp.add_prompt(prompt)

        logger.info(
            "Registered prompt from disk",
            name=name,
            file=str(file_path),
            arguments=placeholders,
        )
        count += 1

    return count


def load_resources(mcp: Any, resources_dir: str) -> int:
    """Scan *resources_dir* and register each file as a static MCP resource.

    The resource URI is ``resource://<relative_path>``. MIME type is inferred
    from the file extension.

    Returns the number of resources registered.
    """

    resources_path = Path(resources_dir).resolve()
    if not resources_path.is_dir():
        logger.warning("Resources directory does not exist", path=resources_dir)
        return 0

    count = 0
    for file_path in sorted(resources_path.rglob("*")):
        if not file_path.is_file():
            continue

        rel = file_path.relative_to(resources_path)
        uri = AnyUrl(f"resource://{rel.as_posix()}")

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type is None:
            mime_type = "application/octet-stream"

        resource_name = rel.as_posix()
        description = f"Static resource: {rel.as_posix()}"

        try:
            resource = FileResource(
                uri=uri,
                path=file_path,
                name=resource_name,
                description=description,
                mime_type=mime_type,
            )
            mcp.add_resource(resource)

            logger.info(
                "Registered resource from disk",
                name=resource_name,
                uri=uri,
                mime_type=mime_type,
                file=str(file_path),
            )
            count += 1
        except Exception as exc:
            logger.error(
                "Failed to register resource", path=str(file_path), error=str(exc)
            )

    return count


def load_from_disk(
    mcp: Any, prompts_dir: Optional[str] = None, resources_dir: Optional[str] = None
) -> Dict[str, int]:
    """Load prompts and resources from disk directories.

    Directories that are ``None`` or do not exist are silently skipped.

    Returns a dict with counts: ``{"prompts": N, "resources": M}``.
    """
    result = {"prompts": 0, "resources": 0}

    if prompts_dir:
        result["prompts"] = load_prompts(mcp, prompts_dir)

    if resources_dir:
        result["resources"] = load_resources(mcp, resources_dir)

    if result["prompts"] or result["resources"]:
        logger.info(
            "Disk loading complete",
            prompts=result["prompts"],
            resources=result["resources"],
        )

    return result
