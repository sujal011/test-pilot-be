# Agent Test Platform

AI-powered browser automation testing backend — local MVP.

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Python 3.11 |
| ORM | SQLAlchemy 2 (async) |
| DB | PostgreSQL 16 (via Docker Compose) |
| AI | LangChain + OpenAI GPT-4o |
| Browser | agent-browser CLI |
| Live logs | WebSockets |

---

## Quick start

### 1. Prerequisites

```bash
# Node / npx (for agent-browser)
node --version   # >= 18

# Install agent-browser globally
npm install -g agent-browser
agent-browser install

# Python 3.11+
python3 --version

# Docker + Docker Compose
docker compose version
```

### 2. Start PostgreSQL

```bash
docker compose up -d
```

### 3. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env .env.local          # or edit .env directly
# Set OPENAI_API_KEY=sk-...
```

### 5. Run the server

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

---

## API overview

### Projects
| Method | Path | Description |
|---|---|---|
| POST | `/projects` | Create project |
| GET | `/projects` | List projects |

### User stories
| Method | Path | Description |
|---|---|---|
| POST | `/projects/{id}/stories` | Create user story |
| GET | `/projects/{id}/stories` | List stories |

### AI test generation
| Method | Path | Description |
|---|---|---|
| POST | `/stories/{id}/generate-tests` | Generate test cases from story |

### Test cases & steps
| Method | Path | Description |
|---|---|---|
| GET | `/testcases/{id}` | Get test case with steps |
| PUT | `/test-steps/{id}` | Edit a natural-language step |

### Test execution
| Method | Path | Description |
|---|---|---|
| POST | `/testcases/{id}/run` | Start a run (returns immediately) |
| GET | `/testruns/{id}` | Get run status + summary |
| GET | `/testruns/{id}/commands` | List all replay commands |
| POST | `/testruns/{id}/replay` | Re-run stored commands without AI |

### Live logs (WebSocket)
```
ws://localhost:8000/ws/testruns/{run_id}
```

Message types:
```json
{"type": "log",     "level": "info", "message": "..."}
{"type": "command", "command": "agent-browser click #btn", "output": "...", "exit_code": 0}
{"type": "status",  "status": "running"}
{"type": "summary", "summary": "Test passed because..."}
```

### Viewport streaming (pair browsing)

agent-browser exposes its own WebSocket server for viewport frames. The backend
proxies it so the frontend only needs one connection.

```
# Start the proxy (call after the browser is open)
POST /testruns/{run_id}/stream/start

# Check proxy status
GET  /testruns/{run_id}/stream/status

# Stop the proxy
POST /testruns/{run_id}/stream/stop

# WebSocket — receive frames, send input
ws://localhost:8000/ws/testruns/{run_id}/viewport
```

**Frame message** (server → client, forwarded from agent-browser):
```json
{
  "type": "frame",
  "data": "<base64-encoded-jpeg>",
  "metadata": { "deviceWidth": 1280, "deviceHeight": 720, "scrollOffsetY": 0 }
}
```

**Input events** (client → server, forwarded to agent-browser):
```json
// Mouse click
{ "type": "input_mouse",    "eventType": "mousePressed", "x": 100, "y": 200, "button": "left", "clickCount": 1 }
// Mouse release
{ "type": "input_mouse",    "eventType": "mouseReleased", "x": 100, "y": 200, "button": "left" }
// Mouse move
{ "type": "input_mouse",    "eventType": "mouseMoved", "x": 150, "y": 250 }
// Scroll
{ "type": "input_mouse",    "eventType": "mouseWheel", "x": 100, "y": 200, "deltaX": 0, "deltaY": 100 }
// Key down/up
{ "type": "input_keyboard", "eventType": "keyDown", "key": "Enter", "code": "Enter" }
// Type character
{ "type": "input_keyboard", "eventType": "char", "text": "a" }
// With modifiers (1=Alt, 2=Ctrl, 4=Meta, 8=Shift)
{ "type": "input_keyboard", "eventType": "keyDown", "key": "c", "code": "KeyC", "modifiers": 2 }
// Touch
{ "type": "input_touch",    "eventType": "touchStart", "touchPoints": [{ "x": 100, "y": 200 }] }
```

**How it works internally:**

```
AGENT_BROWSER_STREAM_PORT=9223 is injected into every agent-browser subprocess
        ↓
agent-browser opens ws://localhost:9223  (its own stream server)
        ↓
ViewportProxy (stream_service.py) connects as a WS client to :9223
        ↓
Frames are broadcast to all frontend WS clients on /ws/testruns/{id}/viewport
Input events from frontend clients are forwarded back to :9223
```

The `AGENT_BROWSER_STREAM_PORT` env var is injected automatically by `cli_runner.py`
for every `agent-browser` subprocess — no manual configuration needed beyond setting
the port in `.env`.

---

## Example flow

```bash
# 1. Create project
curl -s -X POST http://localhost:8000/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"My App","description":"E2E tests"}' | jq .

# 2. Create user story
curl -s -X POST http://localhost:8000/projects/{project_id}/stories \
  -H 'Content-Type: application/json' \
  -d '{"title":"User login","description":"A user logs in with email and password and sees the dashboard"}' | jq .

# 3. Generate test cases (AI)
curl -s -X POST http://localhost:8000/stories/{story_id}/generate-tests | jq .

# 4. (optional) Edit a step
curl -s -X PUT http://localhost:8000/test-steps/{step_id} \
  -H 'Content-Type: application/json' \
  -d '{"natural_language_step":"Open https://myapp.com/login"}' | jq .

# 5. Run the test case
curl -s -X POST http://localhost:8000/testcases/{test_case_id}/run | jq .
# → {"id": "<run_id>", "status": "pending", ...}

# 6. Stream live logs
wscat -c ws://localhost:8000/ws/testruns/{run_id}

# 7. Fetch final result
curl -s http://localhost:8000/testruns/{run_id} | jq .
```

---

## agent-browser CLI reference

```bash
agent-browser open example.com
agent-browser snapshot                       # accessibility tree with refs
agent-browser click @e2                      # click by ref
agent-browser fill @e3 "test@example.com"    # fill by ref
agent-browser get text @e1
agent-browser screenshot page.png
agent-browser assert-visible ".dashboard"
agent-browser find role button click --name "Submit"
agent-browser close
```

---

## Architecture notes

```
app/
├── main.py            # FastAPI app, startup hooks
├── config.py          # Settings from .env
├── database.py        # Async SQLAlchemy engine + session factory
├── models/            # SQLAlchemy ORM models
│   ├── project.py     # Project, UserStory
│   ├── test_case.py   # TestCase, TestStep
│   └── test_run.py    # TestRun, ReplayCommand
├── schemas/           # Pydantic request/response models
├── routers/           # FastAPI routers (one per domain)
├── services/          # Business logic
│   ├── project_service.py
│   ├── test_case_service.py
│   ├── execution_service.py   # Orchestrates agent run
│   └── ai_service.py          # LLM test generation + summaries
├── agents/
│   └── browser_agent.py       # LangChain ReAct agent
├── tools/
│   └── browser_tools.py       # LangChain tools → agent-browser CLI
└── utils/
    ├── cli_runner.py           # subprocess wrapper
    └── ws_manager.py          # WebSocket broadcast hub
```

### Scaling path (future)
- Replace `BackgroundTasks` with **Celery + RabbitMQ** workers
- Add a **browser pool** (multiple agent-browser sessions)
- Add **auth** (JWT / OAuth2)
- Containerise the FastAPI app alongside the DB


featues=res in mind to add next 

 - regenrate the test cases or test case steps
 - refine the user story clearly