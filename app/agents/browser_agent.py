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


def _build_executor(base_url: str | None) -> Any:
    llm = ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
    )

    agent = create_agent(model=llm, tools=ALL_TOOLS, system_prompt=_system_prompt(base_url))
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

        messages = []
        if chat_history:
            messages.extend(chat_history)
        messages.append(("user", step))

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: executor.invoke(
                {
                    "messages": messages,
                }
            ),
        )

        messages_out = result.get("messages", [])
        output = ""
        if messages_out:
            last_msg = messages_out[-1]
            if hasattr(last_msg, "content"):
                if getattr(last_msg, "type", "") == "ai" and isinstance(last_msg.content, list) and len(last_msg.content) > 0:
                    if isinstance(last_msg.content[0], dict) and "text" in last_msg.content[0]:
                        output = last_msg.content[0]["text"]
                    else:
                        output = str(last_msg.content)
                elif isinstance(last_msg.content, str):
                    output = last_msg.content
                else:
                    output = str(last_msg.content)

        for i, msg in enumerate(messages_out):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_output = ""
                    for next_msg in messages_out[i+1:]:
                        if getattr(next_msg, "type", "") == "tool" and getattr(next_msg, "tool_call_id", "") == tool_call.get("id"):
                            tool_output = next_msg.content
                            break
                    cmd = _extract_command(tool_call)
                    await ws_manager.send_command(run_id, cmd, str(tool_output), 0)
                    await ws_manager.send_log(run_id, "debug", f"  ↳ {cmd}\n{tool_output}")

        await ws_manager.send_log(run_id, "info", f"✓ {output}")
        return {"output": output, "messages": messages_out}


def _extract_command(action: Any) -> str:
    try:
        if isinstance(action, dict) and "args" in action:
            tool_input = action["args"]
        else:
            tool_input = getattr(action, "tool_input", None)

        if isinstance(tool_input, dict):
            args = tool_input.get("args") or tool_input.get("action") or tool_input.get("url", "")
            return f"agent-browser {args}"
        elif tool_input:
            return f"agent-browser {tool_input}"
    except Exception:
        pass
    return str(action)


# Singleton — safe to reuse because executors are built per-step
browser_agent = BrowserAgent()