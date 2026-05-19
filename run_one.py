"""Run a single task end-to-end. The thing you call to smoke-test the agent.

Usage:
    python run_one.py web sauce_login
    python run_one.py mobile calc_basic_multiply
    python run_one.py web sauce_login --context-window 3 --max-steps 25
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from shared.agent import run_task
from shared.config import MAX_STEPS_DEFAULT


load_dotenv()


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("platform", choices=["web", "mobile"])
    p.add_argument("task_id")
    p.add_argument("--context-window", type=int, default=1)
    p.add_argument("--max-steps", type=int, default=MAX_STEPS_DEFAULT)
    args = p.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set. Copy .env.example to .env and fill it in.")

    if args.platform == "web":
        from web.playwright_backend import PlaywrightBackend
        from web.tasks import TASKS_BY_ID
        if args.task_id not in TASKS_BY_ID:
            raise SystemExit(f"unknown web task: {args.task_id}. Known: {sorted(TASKS_BY_ID)}")
        task = TASKS_BY_ID[args.task_id]
        backend = PlaywrightBackend()
        target = task.url
    else:
        from mobile.adb_backend import AdbBackend
        from mobile.tasks import MOBILE_TASKS_BY_ID
        if args.task_id not in MOBILE_TASKS_BY_ID:
            raise SystemExit(f"unknown mobile task: {args.task_id}. Known: {sorted(MOBILE_TASKS_BY_ID)}")
        task = MOBILE_TASKS_BY_ID[args.task_id]
        backend = AdbBackend()
        target = task.target

    report = await run_task(
        backend=backend,
        platform=args.platform,
        task_id=task.id,
        url_or_target=target,
        goal=task.goal,
        success_check=task.success_check,
        context_window=args.context_window,
        max_steps=args.max_steps,
        run_dir=Path(f"{args.platform}/runs/{task.id}_ctx{args.context_window}_smoke"),
    )

    print(f"\n{'PASS' if report.success else 'FAIL'} — {args.platform}/{report.task_id}")
    print(f"  steps:       {len(report.steps)}")
    print(f"  agent_claim: {report.agent_claimed_success}")
    print(f"  judge_pass:  {report.judge_passed}")
    print(f"  tokens:      {report.total_input_tokens} in (+{report.total_cache_read_tokens} cached) / {report.total_output_tokens} out")
    print(f"  latency:     {report.total_latency_ms} ms total")
    print(f"  summary:     {report.summary}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
