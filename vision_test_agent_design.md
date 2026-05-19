# Vision-based browser testing agent — design plan

> A selector-free, vision-driven test agent that uses Claude to navigate and assert on web UIs.
> Built to demonstrate Autosana's core thesis: testing without brittle DOM queries.

---

## Problem statement

Selector-based testing (Playwright, Cypress, Selenium) breaks every release because it couples tests to implementation details — class names, IDs, DOM structure. Teams either spend endless hours maintaining these tests or abandon automated testing altogether.

The alternative: treat the browser like a human does. Look at the screen. Understand what's there. Act on it.

---

## What this prototype proves

1. A VLM can navigate a real web app to completion with no selectors
2. Natural language goals are sufficient test specifications
3. Vision-based assertions (`assert("Is the order confirmation visible?")`) are more meaningful than DOM checks
4. The agent loop is small, debuggable, and extensible

---

## Repo structure

```
vision-test-agent/
├── agent.py          # Core agent loop
├── browser.py        # Playwright wrapper (raw actions only)
├── vision.py         # Claude API calls — screenshot reasoning + assertions
├── actions.py        # Action schema definitions
├── config.py         # Model, max steps, screenshot dir
├── run_demo.sh       # One-command demo against saucedemo.com
├── recordings/       # GIFs and screenshot traces
├── requirements.txt
└── README.md
```

---

## Core agent loop

```
start(url, goal)
  │
  ├─ screenshot() ──────────────────────────────────────────────┐
  │                                                             │
  ├─ reason(screenshot, goal, history)                          │
  │   └─ Claude returns: { action, args, reasoning, done }      │
  │                                                             │
  ├─ if done → report(success/failure, summary)                 │
  │                                                             │
  └─ execute(action, args) ─────────────────────────────────────┘
       └─ loop (max_steps cap)
```

Each iteration: one screenshot, one Claude call, one action. Simple, auditable, and easy to debug because every step has a visual trace.

---

## Module breakdown

### `browser.py` — Playwright wrapper

Raw browser control. No selectors anywhere.

```python
class Browser:
    async def screenshot(self) -> bytes
    async def navigate(self, url: str)
    async def click(self, x: int, y: int)
    async def type(self, text: str)
    async def scroll(self, direction: str, amount: int = 300)
    async def hover(self, x: int, y: int)
```

Playwright is used only for its low-level input APIs. Every coordinate comes from Claude's interpretation of the screenshot, not from querying the DOM.

---

### `vision.py` — Claude reasoning layer

Two distinct calls to Claude:

**1. Action reasoning**

```python
async def decide_action(
    screenshot: bytes,
    goal: str,
    history: list[dict],
    step: int
) -> ActionDecision
```

System prompt tells Claude it is a browser testing agent. It receives:
- The current screenshot (base64 encoded)
- The test goal in plain English
- A compact history of previous steps

Claude responds with structured JSON:

```json
{
  "reasoning": "I can see a login form. The goal requires me to log in first.",
  "action": "click",
  "args": { "x": 412, "y": 308 },
  "done": false
}
```

**2. Visual assertion**

```python
async def assert_condition(
    screenshot: bytes,
    question: str
) -> AssertionResult
```

Used for test assertions. Claude answers yes/no with a confidence score and brief explanation. This replaces `expect(locator).toBeVisible()`.

---

### `actions.py` — Action schema

```python
@dataclass
class Action:
    name: str          # navigate | click | type | scroll | assert | done
    args: dict
    reasoning: str

@dataclass
class ActionDecision:
    action: Action
    done: bool
    success: bool | None   # only set when done=True
    summary: str | None    # human-readable result summary

@dataclass
class AssertionResult:
    passed: bool
    confidence: float      # 0.0–1.0
    explanation: str
```

---

### `agent.py` — Orchestration

```python
async def run(url: str, goal: str, max_steps: int = 20) -> RunReport:
    browser = Browser()
    history = []
    screenshots = []

    await browser.navigate(url)

    for step in range(max_steps):
        screenshot = await browser.screenshot()
        screenshots.append(screenshot)

        decision = await decide_action(screenshot, goal, history, step)

        if decision.done:
            return RunReport(
                success=decision.success,
                steps=history,
                screenshots=screenshots,
                summary=decision.summary
            )

        await execute(browser, decision.action)
        history.append(decision)

    return RunReport(success=False, summary="Max steps reached")
```

---

## Action space

| Action | Args | Description |
|---|---|---|
| `navigate` | `url: str` | Load a URL |
| `click` | `x: int, y: int` | Click at pixel coordinates |
| `type` | `text: str` | Type into the focused element |
| `scroll` | `direction: str, amount: int` | Scroll up or down |
| `assert` | `question: str` | Visual true/false assertion via Claude |
| `done` | `success: bool, summary: str` | Terminate the run |

No selectors. No `aria-label` queries. No DOM traversal.

---

## Prompt design

### Action reasoning prompt

```
You are a browser testing agent. Your job is to complete the following goal by interacting with the browser.

Goal: {goal}

You will receive:
- A screenshot of the current browser state
- A history of actions taken so far

Respond ONLY with valid JSON in this format:
{
  "reasoning": "<what you see and why you're taking this action>",
  "action": "<navigate|click|type|scroll|assert|done>",
  "args": { ... },
  "done": false,
  "success": null,
  "summary": null
}

Rules:
- For click: provide x,y pixel coordinates based on what you see in the screenshot
- For assert: provide a yes/no question about the current screen state
- When the goal is complete, set done=true, success=true, and write a summary
- If you are stuck or the goal is impossible, set done=true, success=false
- Maximum {max_steps} steps total
```

### Assertion prompt

```
You are verifying a test assertion by looking at a browser screenshot.

Question: {question}

Answer with JSON only:
{
  "passed": true or false,
  "confidence": 0.0 to 1.0,
  "explanation": "<one sentence>"
}
```

---

## Demo scenario — saucedemo.com checkout

Target site: `https://www.saucedemo.com` (purpose-built e-commerce test site, no auth required for demo accounts)

**Goal:**
```
Log in with username 'standard_user' and password 'secret_sauce',
add the first product to the cart, proceed to checkout,
fill in the shipping form with any valid details,
and verify the order confirmation screen appears.
```

**Expected step trace:**
1. Navigate to saucedemo.com
2. Click username field → type `standard_user`
3. Click password field → type `secret_sauce`
4. Click login button
5. Click "Add to cart" on first product
6. Click cart icon
7. Click "Checkout"
8. Fill first name, last name, zip code
9. Click "Continue"
10. Click "Finish"
11. Assert: "Is there an order confirmation message on screen?" → `passed: true`
12. Done(success=true)

---

## Output and reporting

Each run produces:

```
run_2024_01_15_143022/
├── report.json          # Full structured run report
├── step_01.png          # Screenshot at each step
├── step_02.png
├── ...
└── demo.gif             # Assembled GIF for README
```

`report.json` structure:
```json
{
  "goal": "...",
  "success": true,
  "steps": 12,
  "duration_seconds": 34.2,
  "assertions": [
    { "question": "Is there an order confirmation message?", "passed": true, "confidence": 0.97 }
  ],
  "step_log": [ ... ]
}
```

---

## Stack

| Layer | Tool | Why |
|---|---|---|
| Browser control | Playwright (Python) | Stable async API, raw input methods, cross-browser |
| Vision reasoning | `claude-sonnet-4-20250514` | Best multimodal reasoning, fast enough for interactive loops |
| Orchestration | Python async/await | Simple, debuggable, no framework overhead |
| Screenshot assembly | Pillow + imageio | Lightweight GIF generation for the README demo |

---

## Config

```python
# config.py
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 1024
MAX_STEPS = 20
SCREENSHOT_DIR = "recordings"
HEADLESS = True           # set False to watch it live
VIEWPORT = (1280, 800)
```

---

## CLI

```bash
# Install
pip install playwright anthropic pillow imageio
playwright install chromium

# Run demo
python agent.py \
  --url https://www.saucedemo.com \
  --goal "Log in as standard_user and complete a checkout" \
  --max-steps 20 \
  --record

# Run against any site
python agent.py \
  --url https://your-app.com \
  --goal "Verify that the signup form submits successfully"
```

---

## What this is not

- Not a replacement for unit tests
- Not trying to be a general-purpose RPA tool
- Not production-hardened (no retry logic, no parallel runs, no CI integration)

This is a focused proof-of-concept of one idea: **a VLM can replace selectors as the perception layer in a test agent.** That's the bet Autosana is making at scale. This shows it works on a real site in under 200 lines of Python.

---

## Build order

1. `browser.py` — get raw Playwright actions working
2. `vision.py` — Claude screenshot → JSON action decision
3. `agent.py` — wire the loop
4. Test manually on saucedemo.com, watch it run
5. Add assertion support (`vision.assert_condition`)
6. Add screenshot logging and GIF export
7. Write README with the recorded demo embedded

Estimated build time: 4–6 hours.
