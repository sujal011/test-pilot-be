"""
LangChain ReAct agent that translates natural-language test steps into
agent-browser CLI commands and executes them.

base_url is injected into the system prompt so the agent knows the root of
the application under test and can build correct URLs without guessing.
"""
from __future__ import annotations

import asyncio
from typing import Any

from langchain.agents import create_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings
from app.tools.browser_tools import ALL_TOOLS
from app.utils.ws_manager import ws_manager

_BASE_SYSTEM = """\
You are a browser automation agent executing a test case against a web application.

Base URL of the application under test: {base_url}

Available agent-browser CLI patterns:
  agent-browser open <url>
  agent-browser snapshot                     # get accessibility tree with element refs
  agent-browser click <ref|selector>
  agent-browser fill <ref|selector> "<text>"
  agent-browser get text <ref|selector>
  agent-browser screenshot <filename>
  agent-browser assert-visible <selector>
  agent-browser find role <role> click --name "<name>"
  agent-browser close

Rules:
1. The browser is already on {base_url} — do NOT call open_browser again unless
   the step explicitly says to navigate to a different page.
2. Before clicking or filling, call execute_browser_action with "snapshot" to
   discover element refs (@e1, @e2 …). Prefer refs over CSS selectors.
3. If a step says "verify" or "assert", use assert-visible or get text to confirm.
4. Build sub-page URLs using the base URL, e.g. {base_url}/login, {base_url}/dashboard.
5. If a command fails, retry once with an alternative selector before giving up.
6. After each action briefly state what happened.
"""


def _system_prompt(base_url: str | None) -> str:
    url = base_url or "unknown (no base URL provided — use your best judgment)"
    return _BASE_SYSTEM.format(base_url=url)


def _build_executor(base_url: str | None) -> Agent:
    llm = ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _system_prompt(base_url)),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )

    agent = create_agent(llm, ALL_TOOLS, prompt)
    return agent


class BrowserAgent:
    """
    Stateless wrapper around LangChain AgentExecutor.

    A new executor is built per-step so the base_url can be baked into the
    system prompt without sharing mutable state across concurrent runs.
    """

    async def execute_step(
        self,
        step: str,
        run_id: str,
        base_url: str | None = None,
        chat_history: list | None = None,
    ) -> dict[str, Any]:
        """
        Execute a single natural-language test step.

        Returns a dict with:
          output             – agent's final text response
          intermediate_steps – list of (AgentAction, tool_output) tuples
        """
        await ws_manager.send_log(run_id, "info", f"▶ Step: {step}")

        executor = _build_executor(base_url)

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: executor.invoke(
                {
                    "input": step,
                    "chat_history": chat_history or [],
                }
            ),
        )

        for action, tool_output in result.get("intermediate_steps", []):
            cmd = _extract_command(action)
            await ws_manager.send_command(run_id, cmd, str(tool_output), 0)
            await ws_manager.send_log(run_id, "debug", f"  ↳ {cmd}\n{tool_output}")

        await ws_manager.send_log(run_id, "info", f"✓ {result.get('output', '')}")
        return result


def _extract_command(action: Any) -> str:
    try:
        tool_input = action.tool_input
        if isinstance(tool_input, dict):
            args = tool_input.get("args") or tool_input.get("action") or tool_input.get("url", "")
            return f"agent-browser {args}"
        return f"agent-browser {tool_input}"
    except Exception:
        return str(action)


# Singleton — safe to reuse because executors are built per-step
browser_agent = BrowserAgent()