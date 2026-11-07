"""file_tools.py - the model-facing file tools.

A tool has two jobs:

1. validate the arguments it receives from the model;
2. turn every sandbox outcome into a short observation string.

Observation strings are deliberately not exceptions. A model that asks for
``../../etc/passwd`` should see ``ERROR[PATH]: ...`` and continue, not crash the
session. This module is the boundary where Python errors become conversation
content.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .sandbox import Sandbox, SandboxError


@dataclass(frozen=True)
class ToolSpec:
    """The prompt-visible contract for one tool."""

    name: str
    description: str
    args: tuple[str, ...]


# The list is ordered for a stable prompt. A real harness may render these as
# JSON schemas; a small book can keep the contract readable.
TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "list_files",
        "List one folder inside the workspace. Paths are workspace-relative.",
        ("path",),
    ),
    ToolSpec(
        "read_file",
        "Read a UTF-8 text file inside the workspace with line numbers.",
        ("path",),
    ),
    ToolSpec(
        "write_file",
        "Create or replace a text file inside the workspace.",
        ("path", "content"),
    ),
    ToolSpec(
        "edit_file",
        "Replace unique old text with new text in a workspace file.",
        ("path", "old_text", "new_text", "replace_all"),
    ),
    ToolSpec(
        "delete_file",
        "Delete one regular file inside the workspace.",
        ("path",),
    ),
)


def tool_names() -> list[str]:
    """Return the tool names in prompt order."""
    return [spec.name for spec in TOOL_SPECS]


def _arg(args: dict[str, Any], name: str, *, default: Any = ...) -> Any:
    """Fetch a required or defaulted argument with a clear error message."""
    if name in args:
        return args[name]
    if default is not ...:
        return default
    raise SandboxError("ARGS", f"missing argument: {name}")


def _string_arg(args: dict[str, Any], name: str, *, default: Any = ...) -> str:
    """Fetch an argument and require it to be a string."""
    value = _arg(args, name, default=default)
    if not isinstance(value, str):
        raise SandboxError("ARGS", f"argument {name!r} must be a string")
    return value


def _format_read(text: str, *, max_lines: int = 400, max_line_bytes: int = 4000) -> str:
    """Format text with line numbers, bounds and a truncation marker."""
    lines = text.splitlines()
    shown = lines[:max_lines]

    formatted: list[str] = []
    for number, line in enumerate(shown, start=1):
        # A single generated line can be enormous (minified code, base64).
        # Truncate by characters for display; the read limit already bounds
        # total bytes.
        if len(line) > max_line_bytes:
            line = line[:max_line_bytes] + " ... [line truncated]"
        formatted.append(f"{number:>4} | {line}")

    if len(lines) > max_lines:
        formatted.append(f"     ... ({len(lines) - max_lines} more lines)")

    # An empty file still needs a visible success marker.
    return "\n".join(formatted) if formatted else "(empty file)"


def _tool_list_files(sandbox: Sandbox, args: dict[str, Any]) -> str:
    """List a directory and render one entry per line."""
    path = _string_arg(args, "path", default=".")
    entries = sandbox.list_dir(path)

    if not entries:
        return f"EMPTY: {path}"

    lines: list[str] = []
    for entry in entries:
        if entry.kind == "dir":
            lines.append(f"dir  {entry.name}/")
        elif entry.kind == "file":
            lines.append(f"file {entry.name} ({entry.size} bytes)")
        elif entry.kind == "link":
            # A link is listed but never followed by a listing.
            lines.append(f"link {entry.name} (not followed)")
        else:
            lines.append(f"oth  {entry.name}")

    return "\n".join(lines)


def _tool_read_file(sandbox: Sandbox, args: dict[str, Any]) -> str:
    """Read a file and number its lines for the model."""
    path = _string_arg(args, "path")
    text = sandbox.read_text(path)
    return _format_read(text, max_line_bytes=sandbox.limits.max_line_bytes)


def _tool_write_file(sandbox: Sandbox, args: dict[str, Any]) -> str:
    """Write a file and report the exact path and byte count."""
    path = _string_arg(args, "path")
    content = _string_arg(args, "content")
    resolved = sandbox.write_text(path, content)
    size = len(content.encode("utf-8"))
    return f"OK: wrote {size} bytes to {resolved.relative}"


def _tool_edit_file(sandbox: Sandbox, args: dict[str, Any]) -> str:
    """Edit a file with unique-match-by-default semantics."""
    path = _string_arg(args, "path")
    old_text = _string_arg(args, "old_text")
    new_text = _string_arg(args, "new_text")
    replace_all = args.get("replace_all", False)
    if not isinstance(replace_all, bool):
        raise SandboxError("ARGS", "replace_all must be true or false")

    updated = sandbox.edit_text(
        path,
        old_text,
        new_text,
        count=0 if replace_all else 1,
    )
    return f"OK: edited {path} ({len(updated.encode('utf-8'))} bytes now)"


def _tool_delete_file(sandbox: Sandbox, args: dict[str, Any]) -> str:
    """Delete one file and report the model-facing path."""
    path = _string_arg(args, "path")
    resolved = sandbox.delete_file(path)
    return f"OK: deleted {resolved.relative}"


# Dispatch is a plain dictionary so a reader can see every tool in one place.
_DISPATCH: dict[str, Callable[[Sandbox, dict[str, Any]], str]] = {
    "list_files": _tool_list_files,
    "read_file": _tool_read_file,
    "write_file": _tool_write_file,
    "edit_file": _tool_edit_file,
    "delete_file": _tool_delete_file,
}


def run_tool(sandbox: Sandbox, name: str, args: dict[str, Any] | None = None) -> str:
    """Run one tool by name and return an observation string.

    Every expected failure is converted into ``ERROR[CODE]: message``. An
    unexpected exception is also caught and labelled ``INTERNAL`` so a bug in a
    tool cannot take down the whole session. The traceback belongs in the
    server log, not in the model's context.
    """
    arguments = {} if args is None else args
    handler = _DISPATCH.get(name)
    if handler is None:
        return f"ERROR[UNKNOWN_TOOL]: no tool named {name!r}"

    try:
        return handler(sandbox, arguments)
    except SandboxError as exc:
        return f"ERROR[{exc.code}]: {exc.message}"
    except Exception as exc:  # noqa: BLE001 - tools must never crash the loop
        return f"ERROR[INTERNAL]: {type(exc).__name__}: {exc}"
