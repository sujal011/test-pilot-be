"""
Orchestrates a full test-case run.

Execution order:
  1. Load TestCase → TestSteps + UserStory.base_url
  2. If base_url is set, run  `agent-browser open <base_url>`  FIRST as a
     guaranteed step-0 before any AI-generated steps. This ensures the browser
     is always on the correct starting page regardless of what the LLM wrote.
  3. Send each natural-language step to the BrowserAgent (LangChain ReAct agent).
  4. Persist every CLI command as a ReplayCommand.
  5. Generate an LLM summary and update TestRun.status.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.browser_agent import browser_agent
from app.models.test_case import TestCase
from app.models.test_run import ReplayCommand, TestRun
from app.services.ai_service import generate_run_summary
from app.utils.cli_runner import run_cli
from app.utils.ws_manager import ws_manager


class ExecutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def run_test_case(self, test_case_id: uuid.UUID) -> TestRun:
        run = TestRun(test_case_id=test_case_id, status="pending")
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)
        return await self._run_existing(run, test_case_id)

    async def _run_existing(self, run: TestRun, test_case_id: uuid.UUID) -> TestRun:
        # Load test case with steps AND the parent user story (for base_url)
        result = await self.db.execute(
            select(TestCase)
            .options(
                selectinload(TestCase.steps),
                selectinload(TestCase.user_story),
            )
            .where(TestCase.id == test_case_id)
        )
        test_case = result.scalar_one_or_none()
        if test_case is None:
            run.status = "error"
            run.summary = f"TestCase {test_case_id} not found."
            await self.db.flush()
            return run

        base_url: str | None = (
            test_case.user_story.base_url if test_case.user_story else None
        )

        run.status = "running"
        await self.db.flush()

        run_id_str = str(run.id)
        await ws_manager.send_status(run_id_str, "running")
        await ws_manager.send_log(
            run_id_str, "info",
            f"Starting test run: {test_case.title}  "
            f"({len(test_case.steps)} steps"
            + (f"  |  base URL: {base_url}" if base_url else "")
            + ")"
        )

        step_outputs: list[str] = []
        overall_success = True
        chat_history: list = []

        # ── Step 0: guaranteed browser open ──────────────────────────────────
        if base_url:
            await ws_manager.send_log(
                run_id_str, "info",
                f"[step 0] Opening base URL: {base_url}"
            )
            open_result = await run_cli(f"open {base_url}")
            rc0 = ReplayCommand(
                test_run_id=run.id,
                command=open_result.command,
                output=open_result.combined_output,
                exit_code=open_result.exit_code,
                timestamp=datetime.utcnow(),
            )
            self.db.add(rc0)
            step_outputs.append(f"$ {open_result.command}\n{open_result.combined_output}")
            await ws_manager.send_command(
                run_id_str,
                open_result.command,
                open_result.combined_output,
                open_result.exit_code,
            )

            if not open_result.success:
                overall_success = False
                await ws_manager.send_log(
                    run_id_str, "error",
                    f"Failed to open base URL (exit {open_result.exit_code}): "
                    f"{open_result.stderr}"
                )
                # Don't proceed if we can't even open the page
                await self.db.flush()
                run.status = "failed"
                run.summary = f"Could not open base URL {base_url}: {open_result.stderr}"
                await self.db.flush()
                await self.db.refresh(run)
                await ws_manager.send_status(run_id_str, "failed")
                return run

        # ── Steps 1-N: AI agent executes each natural-language step ──────────
        for step in sorted(test_case.steps, key=lambda s: s.step_order):
            await ws_manager.send_log(
                run_id_str, "info",
                f"[{step.step_order}/{len(test_case.steps)}] {step.natural_language_step}"
            )

            try:
                agent_result = await browser_agent.execute_step(
                    step=step.natural_language_step,
                    run_id=run_id_str,
                    base_url=base_url,
                    chat_history=chat_history,
                )

                for action, tool_output in agent_result.get("intermediate_steps", []):
                    cmd_str = _extract_command_str(action)
                    rc = ReplayCommand(
                        test_run_id=run.id,
                        command=cmd_str,
                        output=str(tool_output),
                        exit_code=0,
                        timestamp=datetime.utcnow(),
                    )
                    self.db.add(rc)
                    step_outputs.append(f"$ {cmd_str}\n{tool_output}")

                from langchain_core.messages import AIMessage, HumanMessage
                chat_history.append(HumanMessage(content=step.natural_language_step))
                chat_history.append(AIMessage(content=agent_result.get("output", "")))

            except Exception as exc:
                overall_success = False
                error_msg = str(exc)
                await ws_manager.send_log(run_id_str, "error", f"Step failed: {error_msg}")

                rc = ReplayCommand(
                    test_run_id=run.id,
                    command=f"[step {step.step_order} error]",
                    output=f"ERROR: {error_msg}",
                    exit_code=1,
                    timestamp=datetime.utcnow(),
                )
                self.db.add(rc)
                step_outputs.append(f"[Step {step.step_order}] ERROR: {error_msg}")
                break

        await self.db.flush()

        # ── LLM summary ───────────────────────────────────────────────────────
        try:
            summary = await generate_run_summary(
                test_case_title=test_case.title,
                steps_output="\n\n".join(step_outputs) or "No commands executed.",
                base_url=base_url,
            )
        except Exception as exc:
            summary = f"Could not generate summary: {exc}"

        run.status = "passed" if overall_success else "failed"
        run.summary = summary
        await self.db.flush()
        await self.db.refresh(run)

        await ws_manager.send_summary(run_id_str, summary)
        await ws_manager.send_status(run_id_str, run.status)

        return run

    async def get_run(self, run_id: uuid.UUID) -> TestRun | None:
        return await self.db.get(TestRun, run_id)

    async def get_replay_commands(self, run_id: uuid.UUID) -> list[ReplayCommand]:
        result = await self.db.execute(
            select(ReplayCommand)
            .where(ReplayCommand.test_run_id == run_id)
            .order_by(ReplayCommand.timestamp)
        )
        return list(result.scalars().all())

    async def replay_run(self, run_id: uuid.UUID) -> list[str]:
        """Re-run stored commands without AI involvement."""
        commands = await self.get_replay_commands(run_id)
        outputs: list[str] = []
        for rc in commands:
            raw = rc.command.removeprefix("agent-browser ").strip()
            if raw.startswith("["):
                continue
            result = await run_cli(raw)
            outputs.append(result.combined_output)
        return outputs


def _extract_command_str(action) -> str:
    try:
        tool_input = action.tool_input
        if isinstance(tool_input, dict):
            args = (
                tool_input.get("args")
                or tool_input.get("action")
                or tool_input.get("url", "")
            )
            return f"agent-browser {args}"
        return f"agent-browser {tool_input}"
    except Exception:
        return str(action)