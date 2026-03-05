"""
LLM-powered services:
  - generate_test_cases  : create test cases + steps from a user story
  - generate_run_summary : summarise a completed test run
"""
from __future__ import annotations

import json
import re

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings
from app.schemas import GeneratedTestCase

# ── Test-case generation ──────────────────────────────────────────────────────

GENERATION_PROMPT = """\
You are a senior QA engineer. Given the user story below, generate comprehensive
test cases with natural-language steps that can be automated with a browser agent.

User Story Title: {title}
User Story Description: {description}
Base URL: {base_url}

Rules:
1. The FIRST step of EVERY test case MUST be:
   "Open {base_url}"
   This is non-negotiable — the browser must always start at the given URL.
2. Use the base URL to build concrete navigation steps, e.g.:
   "Open {base_url}/login"  or  "Open {base_url}/dashboard"
3. Steps must be unambiguous natural-language instructions a browser agent can act on.
4. Cover happy paths AND edge cases (invalid input, empty fields, wrong credentials, etc.).
5. Each step should be a single atomic action or assertion.

Example steps:
  "Open {base_url}/login"
  "Enter email test@example.com into the email field"
  "Enter password 123456 into the password field"
  "Click the Login button"
  "Verify that the dashboard heading is visible"

Return a JSON array of test case objects. Each object must have:
  - title: string
  - description: string
  - steps: array of strings (natural language steps)

Return ONLY valid JSON. No markdown fences, no extra text.
"""


async def generate_test_cases(
    title: str,
    description: str,
    base_url: str | None,
) -> list[GeneratedTestCase]:
    llm = ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
    )

    url_display = base_url or "https://example.com  (no URL provided — use a realistic placeholder)"
    prompt = GENERATION_PROMPT.format(
        title=title,
        description=description or "(no description)",
        base_url=url_display,
    )

    response = await llm.ainvoke(prompt)
    raw = response.content.strip()

    # Strip markdown fences if the model added them
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    data = json.loads(raw)
    return [GeneratedTestCase(**item) for item in data]


# ── Run summary ───────────────────────────────────────────────────────────────

SUMMARY_PROMPT = """\
You are a QA engineer reviewing the output of an automated browser test run.

Test Case: {test_case_title}
Base URL:  {base_url}

Steps executed and their CLI outputs:
{steps_output}

Write a concise summary (3-5 sentences) explaining:
1. Whether the test passed or failed overall
2. Which steps succeeded and which failed
3. The likely root cause if there were failures
"""


async def generate_run_summary(
    test_case_title: str,
    steps_output: str,
    base_url: str | None = None,
) -> str:
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        openai_api_key=settings.OPENAI_API_KEY,
        temperature=0,
    )

    prompt = SUMMARY_PROMPT.format(
        test_case_title=test_case_title,
        base_url=base_url or "unknown",
        steps_output=steps_output,
    )
    response = await llm.ainvoke(prompt)
    return response.content.strip()