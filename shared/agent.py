"""Agent orchestration loop. Backend-agnostic.

This file does not import Playwright. It does not import adb. It does not
know whether it's testing a web page or a mobile screen. It receives a
`Backend` and treats it as the only thing that exists. That property is the
architectural payoff of `shared/backend.py`.

Each iteration: screenshot → decide_action → execute → settle → repeat.
Every step writes a PNG into the run directory so a reviewer can replay any
trial as a slideshow without re-running the agent.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from shared.actions import Action, RunReport, StepRecord
from shared.backend import Backend
from shared.config import MAX_STEPS_DEFAULT
from shared.vision import assert_condition, decide_action

logger = logging.getLogger(__name__)


_CLICK_LOOP_RADIUS_PX = 80


def _stuck_loop_hint(history: list[Action]) -> str | None:
    """Detect the 'agent is repeating itself' failure mode.

    Two patterns trigger the hint:
      1. Exact-repeat: last 3 actions are functionally identical.
      2. Fuzzy click loop: last 3 actions are all clicks within an 80px
         radius of each other. Catches the failure mode where the agent
         varies coordinates slightly each step (sometimes due to the
         malformed-args quirk producing different rescued values) but is
         really trying to hit the same dead element.

    Returns a diagnostic hint or None.
    """
    if len(history) < 3:
        return None
    last3 = history[-3:]
    first = last3[0]

    def same(a: Action, b: Action) -> bool:
        return a.name == b.name and a.args == b.args

    # Pattern 1: exact repeat
    if same(first, last3[1]) and same(first, last3[2]):
        return (
            f"You have called {first.name}({first.args}) three times in a row "
            "and the page has not changed. This action is not working. "
            "Try a fundamentally different approach — switch to keyboard "
            "navigation (key('Tab'), key('ArrowDown'), key('Enter'), or "
            "key('P') etc. for letter shortcuts), scroll to reveal hidden "
            "elements, or call done(success=false)."
        )

    # Pattern 2: fuzzy click loop
    def click_xy(a: Action) -> tuple[int, int] | None:
        if a.name != "click":
            return None
        try:
            return _coerce_xy(a.args)
        except Exception:
            return None

    pts = [click_xy(a) for a in last3]
    if all(p is not None for p in pts):
        xs = [p[0] for p in pts if p]  # type: ignore[index]
        ys = [p[1] for p in pts if p]  # type: ignore[index]
        if max(xs) - min(xs) <= _CLICK_LOOP_RADIUS_PX and max(ys) - min(ys) <= _CLICK_LOOP_RADIUS_PX:
            return (
                f"Your last three clicks have all been within ~80 pixels of "
                f"each other (near ({xs[-1]}, {ys[-1]})) and the page has "
                "not changed. The element you're targeting is likely a "
                "native HTML <select> dropdown — its open menu is rendered "
                "outside the screenshot and is invisible to you. STOP "
                "clicking. Use keyboard navigation: try key('P') (or the "
                "first letter of your target option), then key('Enter'). "
                "Letters jump to matching options; arrow keys also work."
            )
    return None


def _coerce_xy(args: dict) -> tuple[int, int]:
    """Robust extraction of (x, y) from possibly-malformed click args.

    Anthropic's tool API doesn't strictly enforce input_schema server-side,
    so Haiku will occasionally return integer-typed fields as strings or
    lists. Three failure modes observed in the wild:

    - `x = "52, 155"`            → both coords packed into x as a string
    - `x = "[173]"`              → list-stringified
    - `x = '1175, "y": 85'`      → JSON fragment leaked into x

    Strategy: extract every integer we can find from the raw values; if
    we get ≥2, use the first two. Otherwise fall back to int() and let
    the original error propagate.
    """
    rx, ry = args.get("x"), args.get("y")
    if isinstance(rx, int) and isinstance(ry, int):
        return rx, ry
    try:
        return int(rx), int(ry)  # handles plain numeric strings
    except (TypeError, ValueError):
        pass
    candidates: list[int] = []
    for v in (rx, ry):
        if v is None:
            continue
        candidates.extend(int(n) for n in re.findall(r"-?\d+", str(v)))
    if len(candidates) >= 2:
        logger.warning(
            "click-arg coercion fallback: tool returned non-integer "
            "coordinates %r — extracted (%d, %d) from regex. "
            "If this fires often it indicates a tool-use protocol bug "
            "worth fixing upstream rather than papering over.",
            args, candidates[0], candidates[1],
        )
        return candidates[0], candidates[1]
    raise ValueError(f"could not extract (x, y) from click args: {args!r}")


async def _execute(backend: Backend, action: Action) -> None:
    """Dispatch one Action against the backend. Done/Navigate are handled by
    the caller, not the backend. Click args go through `_coerce_xy` to
    survive the malformed-tool-args failure mode."""
    name, args = action.name, action.args
    if name == "click":
        x, y = _coerce_xy(args)
        await backend.click(x, y)
    elif name == "type":
        await backend.type_text(str(args["text"]))
    elif name == "key":
        await backend.key(str(args["key"]))
    elif name == "scroll":
        await backend.scroll(str(args.get("direction", "down")))
    await backend.settle()


async def run_task(
    *,
    backend: Backend,
    platform: str,
    task_id: str,
    url_or_target: str,
    goal: str,
    success_check: str,
    context_window: int = 1,
    trial: int = 0,
    max_steps: int = MAX_STEPS_DEFAULT,
    run_dir: Path | None = None,
) -> RunReport:
    """Execute one trial. The backend is started + stopped here so each trial
    is isolated — fresh browser context or fresh app start every time."""
    if run_dir is None:
        run_dir = Path(f"runs/{platform}/{task_id}_ctx{context_window}_t{trial}_{int(time.time())}")
    run_dir.mkdir(parents=True, exist_ok=True)

    await backend.start()

    actions_log = (run_dir / "actions.jsonl").open("w", encoding="utf-8")
    screenshots: list[bytes] = []
    history: list[Action] = []
    steps: list[StepRecord] = []
    total_in = total_cr = total_cc = total_out = total_lat = 0
    final_summary = "max steps reached"
    agent_claimed_success = False
    judge_passed = False
    judge_input_tokens = 0
    judge_output_tokens = 0
    success = False

    try:
        await backend.navigate(url_or_target)
        await backend.settle()

        for step in range(max_steps):
            shot = await backend.screenshot()
            screenshots.append(shot)
            shot_path = run_dir / f"step_{step:02d}.png"
            shot_path.write_bytes(shot)

            hint = _stuck_loop_hint(history)
            result = await decide_action(
                goal=goal,
                screenshots=screenshots,
                history=history,
                step=step,
                context_window=context_window,
                viewport=backend.viewport,
                extra_hint=hint,
            )
            total_in += result.input_tokens
            total_cr += result.cache_read_tokens
            total_cc += result.cache_creation_tokens
            total_out += result.output_tokens
            total_lat += result.latency_ms

            steps.append(
                StepRecord(
                    step=step,
                    screenshot_path=str(shot_path),
                    action=result.action,
                    input_tokens=result.input_tokens,
                    cache_read_tokens=result.cache_read_tokens,
                    cache_creation_tokens=result.cache_creation_tokens,
                    output_tokens=result.output_tokens,
                    latency_ms=result.latency_ms,
                )
            )
            actions_log.write(json.dumps({
                "step": step,
                "action": result.action.name,
                "args": result.action.args,
                "reasoning": result.action.reasoning,
            }) + "\n")
            actions_log.flush()

            if result.action.name == "done":
                agent_claimed_success = bool(result.action.args.get("success", False))
                final_summary = str(result.action.args.get("summary", ""))
                break

            history.append(result.action)
            await _execute(backend, result.action)
        else:
            final_summary = f"max_steps={max_steps} reached without done"

        # Independent visual judge. Sonnet, with the goal as context.
        # Pass up to 2 trajectory screenshots so the judge can distinguish
        # "agent reached the success state" from "initial state == success
        # state" (the todo_add_delete false-positive class).
        final_shot = await backend.screenshot()
        (run_dir / "final.png").write_bytes(final_shot)
        trajectory_tail = screenshots[-3:-1] if len(screenshots) >= 2 else None
        judge = await assert_condition(
            final_shot, success_check, goal,
            trajectory_screenshots=trajectory_tail,
        )
        judge_passed = judge.passed
        judge_input_tokens = judge.input_tokens
        judge_output_tokens = judge.output_tokens
        success = agent_claimed_success and judge_passed
        final_summary = (
            f"{final_summary} | judge: {judge.explanation}"
            if judge.explanation else final_summary
        )

    finally:
        actions_log.close()
        await backend.stop()

    return RunReport(
        task_id=task_id,
        platform=platform,
        goal=goal,
        context_window=context_window,
        trial=trial,
        success=success,
        agent_claimed_success=agent_claimed_success,
        judge_passed=judge_passed,
        summary=final_summary,
        steps=steps,
        total_input_tokens=total_in,
        total_cache_read_tokens=total_cr,
        total_cache_creation_tokens=total_cc,
        total_output_tokens=total_out,
        total_latency_ms=total_lat,
        judge_input_tokens=judge_input_tokens,
        judge_output_tokens=judge_output_tokens,
    )
