"""
LangChain tools that the browser-automation agent can call.

Tool 1  – run_cli_command     : generic pass-through for any agent-browser args
Tool 2  – open_browser        : convenience wrapper for `agent-browser open <url>`
Tool 3  – execute_browser_action : convenience wrapper for snapshot / click / fill / assert etc.
"""
from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.utils.cli_runner import CLIResult, run_cli


# ── schemas ───────────────────────────────────────────────────────────────────

class RunCLIInput(BaseModel):
    args: str = Field(
        description="Everything that comes after 'agent-browser'. "
        "Example: 'click #submit'  or  'fill @e3 \"hello\"'"
    )


class OpenBrowserInput(BaseModel):
    url: str = Field(description="The full URL to open in the browser.")


class BrowserActionInput(BaseModel):
    action: str = Field(
        description=(
            "A single agent-browser action string (without the 'agent-browser' prefix). "
            "Examples:\n"
            "  snapshot\n"
            "  click @e2\n"
            "  fill @e3 \"test@example.com\"\n"
            "  get text @e1\n"
            "  screenshot page.png\n"
            "  assert-visible \".dashboard\"\n"
            "  close"
        )
    )


# ── implementation helpers ────────────────────────────────────────────────────

def _fmt(result: CLIResult) -> str:
    lines = [f"$ {result.command}"]
    if result.stdout:
        lines.append(result.stdout)
    if result.stderr:
        lines.append(f"[stderr] {result.stderr}")
    lines.append(f"[exit {result.exit_code}]")
    return "\n".join(lines)


def _run(args: str) -> str:
    return _fmt(asyncio.run(run_cli(args)))


# ── tool functions ────────────────────────────────────────────────────────────

def run_cli_command(args: str) -> str:
    """Run any agent-browser command by passing raw args."""
    return _run(args)


def open_browser(url: str) -> str:
    """Open a URL in the headless browser."""
    return _run(f"open {url}")


def execute_browser_action(action: str) -> str:
    """Execute a browser action (click, fill, snapshot, assert-visible, etc.)."""
    return _run(action)


# ── exported LangChain tools ──────────────────────────────────────────────────

run_cli_tool = StructuredTool.from_function(
    func=run_cli_command,
    name="run_cli_command",
    description=(
        "Run any agent-browser CLI command. "
        "Pass everything after 'agent-browser' as `args`. "
        "Example args: 'click #submit'  or  'fill @e3 \"hello\"'"
    ),
    args_schema=RunCLIInput,
)

open_browser_tool = StructuredTool.from_function(
    func=open_browser,
    name="open_browser",
    description="Open a URL in the browser. Provide the full URL.",
    args_schema=OpenBrowserInput,
)

execute_browser_action_tool = StructuredTool.from_function(
    func=execute_browser_action,
    name="execute_browser_action",
    description=(
        "Execute a single browser action: snapshot, click, fill, get text, "
        "screenshot, assert-visible, close, etc. "
        "Provide the full action string (without 'agent-browser' prefix)."
    ),
    args_schema=BrowserActionInput,
)

ALL_TOOLS = [run_cli_tool, open_browser_tool, execute_browser_action_tool]