"""Eval progress check. Reads results.jsonl directly — no API calls, no dependencies.

Usage:
    python status.py
"""

import json
from collections import defaultdict
from pathlib import Path


def main() -> None:
    path = Path("results.jsonl")
    if not path.exists():
        print("No results.jsonl yet — eval hasn't started writing.")
        return

    rows = []
    meta = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if "meta" in r:
            meta = r["meta"]
        else:
            rows.append(r)

    if not rows:
        print("results.jsonl exists but has no trial rows yet.")
        return

    web = [r for r in rows if r["platform"] == "web"]
    mobile = [r for r in rows if r["platform"] == "mobile"]
    total_cost = sum(r.get("cost_usd", 0) for r in rows)

    # Assumed full matrix sizes — match eval.py defaults.
    web_target = 15 * 2 * 5     # 15 tasks × 2 conditions × 5 trials
    mobile_target = 8 * 1 * 3   # 8 tasks × 1 condition × 3 trials
    target = web_target + mobile_target

    print(f"Trials: {len(rows)}/{target}  ({len(rows)*100//target}%)")
    print(f"  web:    {len(web)}/{web_target}")
    print(f"  mobile: {len(mobile)}/{mobile_target}")
    print(f"Spent: ${total_cost:.2f}")
    if meta:
        print(f"Run started: timestamp {meta.get('timestamp')}")
    print()

    # Per-condition pass rate
    for plat in ("web", "mobile"):
        plat_rows = [r for r in rows if r["platform"] == plat]
        if not plat_rows:
            continue
        ctx_groups = defaultdict(list)
        for r in plat_rows:
            ctx_groups[r["context_window"]].append(r)
        print(f"{plat}:")
        for ctx in sorted(ctx_groups):
            grp = ctx_groups[ctx]
            wins = sum(1 for r in grp if r["success"])
            pct = 100 * wins // max(len(grp), 1)
            print(f"  ctx={ctx}: {wins}/{len(grp)} ({pct}%)")
        print()

    # Per-task breakdown
    print("Per-task (wins/trials by condition):")
    by_task = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_task[(r["platform"], r["task_id"])][r["context_window"]].append(r["success"])
    for (plat, tid) in sorted(by_task):
        ctx_results = by_task[(plat, tid)]
        cells = []
        for ctx in sorted(ctx_results):
            wins = sum(ctx_results[ctx])
            n = len(ctx_results[ctx])
            cells.append(f"ctx{ctx}={wins}/{n}")
        print(f"  {plat:6s} {tid:30s}  {'  '.join(cells)}")


if __name__ == "__main__":
    main()
