"""Platform-agnostic matrix runner.

Runs the full eval across both platforms (web + mobile) and conditions.
Sequential by design — Playwright + Anthropic API are both rate-limited
enough that parallelism inside a single eval costs more debug time than it
saves. Resumable: rows append to results.jsonl as they finish, so a
Ctrl-C mid-run loses at most one trial.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform as platform_mod
import sys
import time
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

import anthropic
from shared.actions import RunReport
from shared.agent import run_task
from shared.config import (
    HAIKU_INPUT_PRICE_PER_MTOK,
    HAIKU_OUTPUT_PRICE_PER_MTOK,
    RESULTS_PATH,
    SONNET_INPUT_PRICE_PER_MTOK,
    SONNET_OUTPUT_PRICE_PER_MTOK,
)


load_dotenv()


WEB_CONDITIONS = [1, 3]      # ctx=1 vs ctx=3 A/B on the web side
MOBILE_CONDITIONS = [1]      # mobile in v1: ctx=1 only, demonstrates cross-platform
DEFAULT_TRIALS_WEB = 5
DEFAULT_TRIALS_MOBILE = 3


def _serialize(report: RunReport) -> dict:
    d = asdict(report)
    d["cost_usd"] = report.cost_usd(HAIKU_INPUT_PRICE_PER_MTOK, HAIKU_OUTPUT_PRICE_PER_MTOK)
    d["judge_cost_usd"] = report.judge_cost_usd(
        SONNET_INPUT_PRICE_PER_MTOK, SONNET_OUTPUT_PRICE_PER_MTOK,
    )
    return d


def _already_completed(path: Path) -> set[tuple[str, str, int, int]]:
    """Set of (platform, task_id, context_window, trial) tuples already in results."""
    if not path.exists():
        return set()
    done: set[tuple[str, str, int, int]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "meta" in row:  # provenance header
            continue
        done.add((row["platform"], row["task_id"], row["context_window"], row["trial"]))
    return done


def _provenance_header() -> dict:
    """Recorded once per results.jsonl. Lets us reproduce evals later."""
    try:
        import playwright  # type: ignore
        pw_version = getattr(playwright, "__version__", "unknown")
    except Exception:
        pw_version = "not installed"
    return {
        "meta": {
            "timestamp": int(time.time()),
            "anthropic_sdk": anthropic.__version__,
            "playwright": pw_version,
            "python": sys.version.split()[0],
            "os": f"{platform_mod.system()} {platform_mod.release()}",
        }
    }


# ----- backend factories ----------------------------------------------------


async def _make_web_backend():
    from web.playwright_backend import PlaywrightBackend
    return PlaywrightBackend()


async def _make_mobile_backend():
    from mobile.adb_backend import AdbBackend
    return AdbBackend()


# ----- matrix builders ------------------------------------------------------


def _build_web_matrix(task_filter: list[str] | None, trials: int) -> list[tuple]:
    from web.tasks import TASKS
    tasks = [t for t in TASKS if not task_filter or t.id in task_filter]
    out = []
    for task in tasks:
        for trial in range(trials):
            for ctx in WEB_CONDITIONS:
                out.append(("web", task, ctx, trial))
    return out


def _build_mobile_matrix(task_filter: list[str] | None, trials: int) -> list[tuple]:
    from mobile.tasks import MOBILE_TASKS
    tasks = [t for t in MOBILE_TASKS if not task_filter or t.id in task_filter]
    out = []
    for task in tasks:
        for trial in range(trials):
            for ctx in MOBILE_CONDITIONS:
                out.append(("mobile", task, ctx, trial))
    return out


# ----- single trial ---------------------------------------------------------


async def _run_one(platform_name: str, task, ctx: int, trial: int) -> RunReport:
    if platform_name == "web":
        backend = await _make_web_backend()
        target = task.url
    elif platform_name == "mobile":
        backend = await _make_mobile_backend()
        target = task.target
    else:
        raise ValueError(f"unknown platform: {platform_name}")

    run_dir = Path(f"{platform_name}/runs/{task.id}_ctx{ctx}_t{trial}")
    return await run_task(
        backend=backend,
        platform=platform_name,
        task_id=task.id,
        url_or_target=target,
        goal=task.goal,
        success_check=task.success_check,
        context_window=ctx,
        trial=trial,
        run_dir=run_dir,
    )


# ----- main -----------------------------------------------------------------


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--platforms", nargs="+", default=["web", "mobile"], choices=["web", "mobile"])
    p.add_argument("--trials-web", type=int, default=DEFAULT_TRIALS_WEB)
    p.add_argument("--trials-mobile", type=int, default=DEFAULT_TRIALS_MOBILE)
    p.add_argument("--tasks", nargs="*", default=None, help="Limit to these task ids")
    p.add_argument("--results", default=RESULTS_PATH)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set. Copy .env.example to .env and fill it in.")

    matrix: list[tuple] = []
    if "web" in args.platforms:
        matrix += _build_web_matrix(args.tasks, args.trials_web)
    if "mobile" in args.platforms:
        matrix += _build_mobile_matrix(args.tasks, args.trials_mobile)

    results_path = Path(args.results)
    done = _already_completed(results_path)
    pending = [m for m in matrix if (m[0], m[1].id, m[2], m[3]) not in done]

    print(f"Matrix: {len(matrix)} trials | done: {len(done)} | pending: {len(pending)}")
    if args.dry_run:
        for plat, task, ctx, trial in pending:
            print(f"  {plat:6s} {task.id:30s} ctx={ctx} trial={trial}")
        return

    # Write provenance header if file is new.
    if not results_path.exists():
        results_path.write_text(json.dumps(_provenance_header()) + "\n", encoding="utf-8")

    total_start = time.perf_counter()
    running_cost = 0.0
    with results_path.open("a", encoding="utf-8") as f:
        for i, (plat, task, ctx, trial) in enumerate(pending, 1):
            label = f"[{i}/{len(pending)}] {plat} {task.id} ctx={ctx} trial={trial}"
            print(f"\n{label}")
            try:
                report = await _run_one(plat, task, ctx, trial)
            except Exception as e:
                print(f"  ERROR: {e!r}")
                err = {
                    "platform": plat,
                    "task_id": task.id,
                    "context_window": ctx,
                    "trial": trial,
                    "success": False,
                    "agent_claimed_success": False,
                    "judge_passed": False,
                    "summary": f"runtime error: {e!r}",
                    "steps": [],
                    "total_input_tokens": 0,
                    "total_cache_read_tokens": 0,
                    "total_cache_creation_tokens": 0,
                    "total_output_tokens": 0,
                    "total_latency_ms": 0,
                    "cost_usd": 0.0,
                    "goal": task.goal,
                }
                f.write(json.dumps(err) + "\n")
                f.flush()
                continue

            row = _serialize(report)
            f.write(json.dumps(row) + "\n")
            f.flush()
            running_cost += row["cost_usd"]
            print(
                f"  {'PASS' if report.success else 'FAIL'} | "
                f"steps={len(report.steps)} | "
                f"cost=${row['cost_usd']:.4f} | "
                f"running=${running_cost:.2f}"
            )

    elapsed = time.perf_counter() - total_start
    print(f"\nDone. {len(pending)} trials in {elapsed:.0f}s. Spent ${running_cost:.2f}.")


if __name__ == "__main__":
    asyncio.run(main())
