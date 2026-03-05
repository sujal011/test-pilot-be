"""
Low-level wrapper around the agent-browser CLI.

AGENT_BROWSER_STREAM_PORT is injected into every subprocess environment so
agent-browser automatically starts its viewport WebSocket server on that port,
enabling live pair-browsing without any extra configuration.
"""
from __future__ import annotations

import asyncio
import os
import shlex
from dataclasses import dataclass

from app.config import settings


@dataclass
class CLIResult:
    command: str          # full command string that was executed
    stdout: str
    stderr: str
    exit_code: int

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def combined_output(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"[stderr] {self.stderr}")
        return "\n".join(parts) or "(no output)"


def _subprocess_env() -> dict[str, str]:
    """Build env for agent-browser subprocesses, injecting the stream port."""
    env = os.environ.copy()
    if settings.AGENT_BROWSER_STREAM_PORT:
        env["AGENT_BROWSER_STREAM_PORT"] = str(settings.AGENT_BROWSER_STREAM_PORT)
    return env


async def run_cli(args: str) -> CLIResult:
    """
    Run:  agent-browser <args>

    args  – everything after the binary name, e.g. "open https://example.com"

    AGENT_BROWSER_STREAM_PORT is injected into the subprocess environment so that
    agent-browser starts its viewport WebSocket server on the configured port,
    enabling live viewport streaming to the frontend with no extra setup.
    """
    full_cmd = f"{settings.AGENT_BROWSER_CMD} {args}"
    tokens = shlex.split(full_cmd)

    try:
        proc = await asyncio.create_subprocess_exec(
            *tokens,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_subprocess_env(),
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
    except FileNotFoundError:
        return CLIResult(
            command=full_cmd,
            stdout="",
            stderr="agent-browser binary not found. Install it with: npm install -g agent-browser",
            exit_code=127,
        )

    return CLIResult(
        command=full_cmd,
        stdout=stdout_bytes.decode("utf-8", errors="replace").strip(),
        stderr=stderr_bytes.decode("utf-8", errors="replace").strip(),
        exit_code=proc.returncode or 0,
    )