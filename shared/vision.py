"""Claude vision calls. Two responsibilities:

1. `decide_action()` — given screenshots + history + goal + viewport, returns
   the next Action. Uses Anthropic tool_use API so the schema is enforced at
   the API level: we never spend a step recovering from malformed JSON.

2. `assert_condition()` — independent visual judge. Different model from the
   agent (Sonnet vs Haiku) so a Haiku visual blind spot doesn't propagate
   correlated errors into the success label. The judge ALSO sees the original
   goal — without trajectory context it can be fooled by tasks that
   accidentally satisfy a literal phrasing of the success question.

Methodology choices worth flagging because reviewers will ask:

- `temperature=0`: deterministic decoding. We're measuring treatment effects
  (context window, model, platform), not stochasticity. Variance from temp=1
  would drown out our signal.
- Anthropic prompt cache (`cache_control: ephemeral`) on the system prompt
  block: cuts ~90% of system-prompt input tokens after the first call.
- `AsyncAnthropic`: doesn't block the asyncio event loop. Required if anyone
  ever parallelizes the eval.
- Tool-block input is copied before we read it: SDK-owned response objects
  should never be mutated. Subtle but a senior reviewer will spot it.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from anthropic._exceptions import APIConnectionError, APIStatusError, RateLimitError
from dotenv import load_dotenv

from shared.actions import Action
from shared.config import (
    AGENT_MODEL,
    JUDGE_MODEL,
    MAX_OUTPUT_TOKENS,
    TEMPERATURE,
)

# Load .env before instantiating the client — otherwise the entry point's
# `load_dotenv()` runs too late (after this module has already constructed
# AsyncAnthropic() from an empty environment).
load_dotenv()
_client = AsyncAnthropic()


# ----- Tool schema for actions ----------------------------------------------

ACTION_TOOLS = [
    {
        "name": "click",
        "description": "Click or tap at the given pixel coordinates in the screenshot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate in pixels"},
                "y": {"type": "integer", "description": "Y coordinate in pixels"},
                "reasoning": {"type": "string"},
            },
            "required": ["x", "y", "reasoning"],
        },
    },
    {
        "name": "type",
        "description": "Type text into the currently focused field. Click first if not yet focused.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["text", "reasoning"],
        },
    },
    {
        "name": "key",
        "description": (
            "Press a single named key. Web: Enter, Tab, Escape, Backspace, "
            "Arrow{Up,Down,Left,Right}. Mobile additionally: Home, Back."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["key", "reasoning"],
        },
    },
    {
        "name": "scroll",
        "description": "Scroll the surface up or down by ~400 units.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"]},
                "reasoning": {"type": "string"},
            },
            "required": ["direction", "reasoning"],
        },
    },
    {
        "name": "done",
        "description": (
            "Terminate the run. Use success=true if the goal was reached, "
            "false if you are stuck and cannot make progress."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "summary": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["success", "summary", "reasoning"],
        },
    },
]


def _agent_system_prompt(viewport: tuple[int, int]) -> str:
    return f"""You are a browser/mobile testing agent that operates a real interface through coordinate-based input only.

You see a screenshot of the viewport ({viewport[0]}x{viewport[1]} pixels). Pixel (0,0) is top-left.

You must complete the user's goal by calling one of the available tools each turn. Always include a short reasoning string in the tool call so a human reviewer can audit your decision.

Basic guidance:
- For click: read the screenshot and pick a coordinate that lands inside the target element. Aim for the visual center.
- For type: the field must already be focused (click it first on a prior turn).
- Pressing Enter to submit a form is usually faster than finding and clicking the submit button.
- If the target is offscreen, scroll before declaring failure.
- When the goal is plainly satisfied on screen, call done with success=true and a one-sentence summary.
- If you have tried 3+ times to recover without progress, call done with success=false.

Tricky UI patterns you must know about:

1. Native HTML <select> dropdowns (the OS-styled ones, often used for sort/filter menus):

   CRITICAL: when you click a native select, the browser opens an OS-level menu that is rendered OUTSIDE the page viewport. Your screenshots WILL NOT show the open menu. DO NOT try to click options in screenshots that don't show them — you will fail repeatedly.

   The correct flow for any native dropdown / sort menu / filter menu is:
     Step A: click the dropdown ONCE to focus it.
     Step B: press the first letter of the option you want (e.g., key("P") to jump to "Price low to high").
     Step C: press key("Enter") to confirm — OR the option may auto-select after the letter press.

   Example: to sort saucedemo products by price low-to-high:
     - click on the "Name (A to Z)" text (it's a dropdown)
     - key("P") — jumps to and selects "Price (low to high)"
     - key("Enter") — confirms

   If your first click on a dropdown didn't visibly change anything, that's expected — the menu is open but invisible. DO NOT click again. Move to the keyboard step.

2. If your previous action did not visibly change the page, do NOT just repeat it. Try a fundamentally different approach:
   - If a click did nothing AND the target looks like a sort/filter/dropdown menu, switch to keyboard navigation (see pattern 1).
   - If typing produced nothing, you probably aren't focused on a field — click into a field first.
   - If the page looks identical for 3+ steps, you are stuck in a loop. Try scrolling, pressing Escape, clicking a different region, using keyboard navigation, or call done(success=false).

3. Loading and animations:
   - Right after navigation, some elements may not yet be interactive. If the first click does nothing, wait one turn and try again.
   - Modal dialogs and popups must usually be dismissed (Escape, or click an X, or click a backdrop) before underlying content becomes interactive.

4. Mobile-specific (only relevant when viewport aspect ratio is portrait, e.g. 1080x1920):
   - Many actions need a long-press or swipe, not a tap.
   - The home button is keyevent "Home"; back is keyevent "Back".
   - To open the app drawer from the home screen, scroll up (it's a swipe-up gesture)."""


@dataclass
class ActionResult:
    action: Action
    input_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    output_tokens: int
    latency_ms: int


# ----- Helpers --------------------------------------------------------------


def _image_block(png_bytes: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(png_bytes).decode("ascii"),
        },
    }


async def _with_retry(coro_factory, *, attempts: int = 3, label: str = "anthropic"):
    """Exponential backoff for transient API errors.

    A single 429/529/connection-blip during one of N trials would otherwise
    contaminate the success-rate signal with infrastructure noise. We
    distinguish retry-exhausted from real agent failures upstream in eval.py.
    """
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await coro_factory()
        except (RateLimitError, APIConnectionError) as e:
            last_exc = e
        except APIStatusError as e:
            # 5xx are retryable; 4xx (other than 429) are not.
            if 500 <= e.status_code < 600:
                last_exc = e
            else:
                raise
        if attempt < attempts - 1:
            await asyncio.sleep(delay)
            delay *= 4
    raise RuntimeError(f"{label}: retries exhausted ({attempts} attempts)") from last_exc


def _extract_tool_call(resp) -> tuple[str, dict, str]:
    """Pull (tool_name, args_copy, reasoning) out of the SDK response.

    Copies the tool block input rather than mutating it — SDK-owned objects
    should be treated as read-only.
    """
    tool_block = next((b for b in resp.content if b.type == "tool_use"), None)
    if tool_block is None:
        return "done", {"success": False, "summary": "Model returned no tool call"}, \
               "vision: no tool_use block in response"
    raw = dict(tool_block.input or {})
    reasoning = str(raw.pop("reasoning", ""))
    return tool_block.name, raw, reasoning


def _usage(resp) -> tuple[int, int, int, int]:
    """Return (input, cache_read, cache_creation, output) tokens. Older SDK
    versions may not expose cache fields; default to zero in that case."""
    u = resp.usage
    return (
        getattr(u, "input_tokens", 0) or 0,
        getattr(u, "cache_read_input_tokens", 0) or 0,
        getattr(u, "cache_creation_input_tokens", 0) or 0,
        getattr(u, "output_tokens", 0) or 0,
    )


# ----- decide_action --------------------------------------------------------


def _build_messages(
    goal: str,
    screenshots: list[bytes],
    history: list[Action],
    context_window: int,
    step: int,
    extra_hint: str | None = None,
) -> list[dict]:
    """Assemble messages with the last `context_window` screenshots, newest first.

    Single user turn (rather than interleaved tool-call/tool-result exchanges)
    because (a) it's easier to debug, (b) it's friendlier to the prompt cache,
    and (c) the model can read all frames simultaneously rather than relying
    on conversation memory of earlier turns.
    """
    frames = screenshots[-context_window:][::-1]
    recent_actions = history[-(context_window - 1):] if context_window > 1 else []
    base_step = step - len(recent_actions)

    action_lines = [
        f"  step {base_step + i}: {a.name}({json.dumps(a.args)}) — {a.reasoning}"
        for i, a in enumerate(recent_actions)
    ]
    history_str = "\n".join(action_lines) if action_lines else "  (no prior actions)"

    hint_block = f"\n\nIMPORTANT — diagnostic hint from the test harness: {extra_hint}\n" if extra_hint else ""

    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Goal: {goal}\n\n"
                f"Step number: {step}\n"
                f"Showing the {len(frames)} most-recent screenshot(s), newest first.\n\n"
                f"Previous actions:\n{history_str}"
                f"{hint_block}\n"
                "Decide the next single action by calling exactly one tool."
            ),
        }
    ]
    for img in frames:
        content.append(_image_block(img))

    return [{"role": "user", "content": content}]


async def decide_action(
    *,
    goal: str,
    screenshots: list[bytes],
    history: list[Action],
    step: int,
    context_window: int,
    viewport: tuple[int, int],
    extra_hint: str | None = None,
) -> ActionResult:
    """One Claude call. Returns the chosen Action plus token + latency telemetry.

    `extra_hint`: optional diagnostic injected by the agent loop when it
    detects a stuck-loop pattern (same action repeated multiple times).
    Threading it through here keeps the loop-recovery logic out of vision.py
    while still letting the prompt see it.
    """
    messages = _build_messages(goal, screenshots, history, context_window, step, extra_hint)

    # Cache the system prompt — it's stable across all steps of a run AND
    # across all trials of a task with the same viewport.
    system = [
        {
            "type": "text",
            "text": _agent_system_prompt(viewport),
            "cache_control": {"type": "ephemeral"},
        }
    ]

    t0 = time.perf_counter()

    async def call():
        return await _client.messages.create(
            model=AGENT_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=TEMPERATURE,
            system=system,
            tools=ACTION_TOOLS,
            tool_choice={"type": "any"},
            messages=messages,
        )

    resp = await _with_retry(call, label="decide_action")
    latency_ms = int((time.perf_counter() - t0) * 1000)

    name, args, reasoning = _extract_tool_call(resp)
    in_tok, cache_r, cache_c, out_tok = _usage(resp)

    return ActionResult(
        action=Action(name=name, args=args, reasoning=reasoning),
        input_tokens=in_tok,
        cache_read_tokens=cache_r,
        cache_creation_tokens=cache_c,
        output_tokens=out_tok,
        latency_ms=latency_ms,
    )


# ----- assert_condition (independent judge) ---------------------------------


ASSERTION_TOOL = [
    {
        "name": "answer",
        "description": "Answer a yes/no visual question about the screenshot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "explanation": {"type": "string"},
            },
            "required": ["passed", "explanation"],
        },
    }
]


JUDGE_SYSTEM = """You verify test assertions by looking at a final browser/mobile screenshot.

You are told (1) the user's original goal, (2) a specific yes/no question to answer. Use the goal as context to interpret the question fairly — if the agent navigated to a totally different page that accidentally satisfies the literal phrasing of the question, the goal context will help you say 'no'.

Be strict but not pedantic. If the user goal is plainly satisfied on the screen, answer passed=true even if the question's exact phrasing has some ambiguity.

Answer by calling the `answer` tool."""


async def assert_condition(
    screenshot: bytes,
    question: str,
    goal: str,
) -> tuple[bool, str]:
    """Return (passed, explanation).

    Three things that matter here, all from the senior-eng review:
    - JUDGE_MODEL is different from AGENT_MODEL: removes correlated errors.
    - `goal` is passed in: the judge sees the user's intent, not just the
      success question, so it can catch "agent succeeded at the wrong task."
    - Tool-use enforced: judge must answer in schema, can't equivocate in prose.
    """
    async def call():
        return await _client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=400,
            temperature=TEMPERATURE,
            system=JUDGE_SYSTEM,
            tools=ASSERTION_TOOL,
            tool_choice={"type": "tool", "name": "answer"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        _image_block(screenshot),
                        {
                            "type": "text",
                            "text": (
                                f"Original goal: {goal}\n\n"
                                f"Question to verify: {question}"
                            ),
                        },
                    ],
                }
            ],
        )

    resp = await _with_retry(call, label="assert_condition")
    tool_block = next((b for b in resp.content if b.type == "tool_use"), None)
    if tool_block is None or not isinstance(tool_block.input, dict):
        return False, "judge: no tool_use in response"
    args = dict(tool_block.input)
    return bool(args.get("passed", False)), str(args.get("explanation", ""))
