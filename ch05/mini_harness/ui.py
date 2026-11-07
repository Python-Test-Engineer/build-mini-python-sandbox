"""ui.py - the shared Rich presentation layer for the chapter demos.

Every chapter ships the same file. Demos call the small ``UI`` API instead of
printing raw ANSI codes, so the look stays consistent across stages while each
chapter can pick its own accent colour.

Colours are configurable in three ways:

* pass an accent to the constructor: ``UI(accent="magenta")``;
* select a preset with ``MINI_HARNESS_THEME=dark|light|mono``;
* override individual colours with the ``MINI_HARNESS_*`` variables below.

Examples::

    uv run mini_harness/demo.py
    MINI_HARNESS_ACCENT=magenta uv run mini_harness/demo.py
    MINI_HARNESS_THEME=mono uv run mini_harness/demo.py

``NO_COLOR`` is honoured by Rich, so redirecting output or disabling colour
still leaves readable text.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Iterable, Sequence

from rich import box as rich_box
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# Colour and box names are Rich style strings. The defaults work on both light
# and dark terminals; the light preset darkens the muted text.
THEME_ENV = {
    "accent": "MINI_HARNESS_ACCENT",
    "success": "MINI_HARNESS_SUCCESS",
    "warning": "MINI_HARNESS_WARNING",
    "error": "MINI_HARNESS_ERROR",
    "info": "MINI_HARNESS_INFO",
    "muted": "MINI_HARNESS_MUTED",
    "title": "MINI_HARNESS_TITLE",
    "box_name": "MINI_HARNESS_BOX",
}

ICONS = {
    "info": "i",
    "success": "+",
    "warning": "!",
    "error": "x",
    "skip": "-",
    "accent": "*",
}


@dataclass(frozen=True)
class Theme:
    """The small palette shared by every chapter."""

    accent: str = "cyan"
    success: str = "green"
    warning: str = "yellow"
    error: str = "red"
    info: str = "blue"
    muted: str = "bright_black"
    title: str = "bold white"
    box_name: str = "ROUNDED"
    icons: bool = True

    @classmethod
    def from_env(cls, accent: str | None = None) -> "Theme":
        """Load a preset, then apply explicit environment overrides.

        ``accent`` is the per-chapter colour and wins over the environment so
        a chapter demo is consistent even when a global theme is set.
        """
        presets = {
            "dark": cls(),
            "light": cls(
                muted="grey50",
                title="bold black",
                info="blue",
            ),
            "mono": cls(
                accent="white",
                success="white",
                warning="white",
                error="white",
                info="white",
                muted="grey50",
                title="bold white",
                icons=False,
            ),
        }
        preset = os.environ.get("MINI_HARNESS_THEME", "dark").strip().lower()
        theme = presets.get(preset, cls())

        changes: dict[str, object] = {}
        if accent:
            changes["accent"] = accent
        for field, env_name in THEME_ENV.items():
            value = os.environ.get(env_name)
            if value:
                changes[field] = value.strip()
        if os.environ.get("MINI_HARNESS_ICONS", "").strip().lower() in {
            "0",
            "false",
            "no",
            "off",
        }:
            changes["icons"] = False

        return replace(theme, **changes) if changes else theme


class UI:
    """Render headers, notes, results, commands and tables with Rich."""

    def __init__(
        self,
        theme: Theme | None = None,
        *,
        accent: str | None = None,
        title: str | None = None,
        console: Console | None = None,
    ) -> None:
        if theme is None:
            theme = Theme.from_env(accent=accent)
        elif accent:
            theme = replace(theme, accent=accent)
        self.theme = theme
        self.title = title
        # ``highlight=False`` keeps code and paths from being recoloured by
        # Rich's automatic highlighter.
        self.console = console or Console(highlight=False)

    @property
    def _box(self):
        """Return the configured Rich box, falling back to rounded."""
        return getattr(rich_box, self.theme.box_name.upper(), rich_box.ROUNDED)

    def _style(self, kind: str) -> str:
        return {
            "accent": self.theme.accent,
            "success": self.theme.success,
            "warning": self.theme.warning,
            "error": self.theme.error,
            "info": self.theme.info,
            "skip": self.theme.muted,
        }.get(kind, self.theme.info)

    def _icon(self, kind: str) -> str:
        return ICONS.get(kind, ICONS["info"]) if self.theme.icons else ""

    def header(
        self,
        title: str | None = None,
        subtitle: str | None = None,
        *,
        badge: str | None = None,
    ) -> None:
        """Print the chapter title in a coloured panel."""
        heading = title or self.title or "mini harness"
        body = Text()
        body.append(heading, style=self.theme.title)
        if subtitle:
            body.append("\n" + subtitle, style=self.theme.muted)
        if badge:
            body.append("\n" + badge, style=self.theme.accent)
        self.console.print(
            Panel(
                body,
                border_style=self.theme.accent,
                box=self._box,
                padding=(1, 2),
            )
        )

    def section(self, title: str) -> None:
        """Print a rule that separates two parts of a demo."""
        self.console.print(
            Rule(
                Text(title, style=f"bold {self.theme.accent}"),
                style=self.theme.accent,
                align="left",
            )
        )

    def note(
        self,
        label: str,
        message: str,
        *,
        kind: str = "info",
        icon: str | None = None,
    ) -> None:
        """Print a coloured card with a short label."""
        style = self._style(kind)
        glyph = self._icon(kind) if icon is None else icon
        title = Text()
        if glyph:
            title.append(f"{glyph} ", style=style)
        title.append(label, style=f"bold {style}")
        self.console.print(
            Panel(
                Text(str(message)),
                title=title,
                title_align="left",
                border_style=style,
                box=self._box,
                padding=(0, 1),
            )
        )

    def result(self, label: str, text: str, *, kind: str | None = None) -> None:
        """Print an observation, inferring its colour from the error code."""
        if kind is None:
            kind = self._infer_kind(text)
        self.note(label, text, kind=kind)

    def explain(
        self,
        title: str,
        what: str,
        why: str,
        *,
        kind: str = "accent",
    ) -> None:
        """Print a teaching block: what just happened and why it matters.

        Demos put one explainer after each output section so a learner can
        read the result and then the reasoning without leaving the terminal.
        """
        style = self._style(kind)
        body = Text()
        body.append("What: ", style=f"bold {style}")
        body.append(what)
        body.append("\n")
        body.append("Why:  ", style=f"bold {style}")
        body.append(why)
        self.console.print(
            Panel(
                body,
                title=Text(f"explainer - {title}", style=f"bold {style}"),
                title_align="left",
                border_style=style,
                box=self._box,
                padding=(0, 1),
            )
        )

    def _infer_kind(self, text: str) -> str:
        upper = str(text).lstrip().upper()
        if upper.startswith("OK"):
            return "success"
        if upper.startswith("ERROR"):
            return "error"
        if "TIMEOUT" in upper:
            return "warning"
        if upper.startswith("SKIP"):
            return "skip"
        return "info"

    def command(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        title: str = "command",
    ) -> None:
        """Show a command as a quoted, wrapped shell line."""
        body = Text()
        if cwd is not None:
            body.append(f"cwd: {cwd}\n", style=self.theme.muted)
        body.append("$ ", style=f"bold {self.theme.accent}")
        body.append(
            " ".join(self._display_arg(str(part)) for part in argv),
            style=self.theme.title,
        )
        self.console.print(
            Panel(
                body,
                title=Text(title, style=f"bold {self.theme.accent}"),
                title_align="left",
                border_style=self.theme.accent,
                box=self._box,
                padding=(0, 1),
            )
        )

    @staticmethod
    def _display_arg(arg: str) -> str:
        """Quote an argument for display without shell-specific syntax."""
        if arg and not any(char.isspace() for char in arg):
            return arg
        if not arg:
            return '""'
        escaped = arg.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def table(
        self,
        title: str,
        headers: Sequence[str],
        rows: Iterable[Sequence[object]],
    ) -> None:
        """Print a compact table using the shared palette."""
        table = Table(
            title=Text(title, style=f"bold {self.theme.accent}"),
            box=self._box,
            border_style=self.theme.accent,
            header_style=f"bold {self.theme.accent}",
        )
        for header in headers:
            table.add_column(str(header), overflow="fold")
        for row in rows:
            table.add_row(*(str(cell) for cell in row))
        self.console.print(table)

    def done(self, message: str) -> None:
        """Close a demo with a success card."""
        self.note("Done", message, kind="success")
