"""Aggregate results.jsonl into RESULTS.md.

Separate sections for web and mobile because the conditions differ — web has
the ctx=1 vs ctx=3 A/B; mobile is ctx=1 only and reports per-platform
grounding numbers. Failure taxonomy is keyword-bucketed from the run
summaries — crude but enough to seed a manual review.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from shared.config import REPORT_PATH, RESULTS_PATH


def _load(path: Path) -> tuple[dict | None, list[dict]]:
    meta: dict | None = None
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "meta" in row:
            meta = row["meta"]
        else:
            rows.append(row)
    return meta, rows


def _pct(num: int, denom: int) -> str:
    return f"{(100 * num / denom):.1f}%" if denom else "—"


def _group(rows: list[dict], key: str) -> dict:
    out: dict = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return out


def _platform_table(rows: list[dict], platform: str) -> str:
    """Headline table per platform.

    Reports TWO success rates because they tell different stories:
      - Strict success (agent claimed done AND judge agreed): the agent
        knows it succeeded and the state confirms it. This is what you'd
        accept in CI.
      - Judge-only success: the judge saw the final state and approved,
        regardless of whether the agent recognized completion. This
        surfaces the 'agent achieved the state but didn't call done' gap.

    The delta between the two numbers IS a finding — it tells you how
    often the model needs help recognizing completion vs. how often the
    real bottleneck is getting to the goal state.
    """
    if not rows:
        return "_(no trials)_"
    groups = _group(rows, "context_window")
    lines = [
        "| Condition | N | Strict | Judge-only | Hidden | p50 latency | p50 steps | $/task |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for ctx in sorted(groups):
        grp = groups[ctx]
        strict = sum(1 for r in grp if r["success"])
        judge = sum(1 for r in grp if r.get("judge_passed", False))
        # Hidden = judge passed but agent didn't claim done.
        hidden = sum(
            1 for r in grp
            if r.get("judge_passed", False) and not r.get("agent_claimed_success", False)
        )
        latencies = [r["total_latency_ms"] for r in grp if r["steps"]]
        steps = [len(r["steps"]) for r in grp if r["steps"]]
        cost = statistics.mean(r["cost_usd"] for r in grp) if grp else 0.0
        lines.append(
            f"| {platform} ctx={ctx} | {len(grp)} | {_pct(strict, len(grp))} "
            f"| {_pct(judge, len(grp))} | {hidden} "
            f"| {int(statistics.median(latencies)) if latencies else 0} ms "
            f"| {int(statistics.median(steps)) if steps else 0} "
            f"| ${cost:.4f} |"
        )
    return "\n".join(lines)


def _per_task_table(rows: list[dict]) -> str:
    by_task: dict = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_task[(r["platform"], r["task_id"])][r["context_window"]].append(r)

    if not by_task:
        return "_(no trials)_"

    all_ctx = sorted({c for cells in by_task.values() for c in cells})
    header = "| Task | " + " | ".join(f"ctx={c}" for c in all_ctx) + " |"
    sep = "|---|" + "---|" * len(all_ctx)
    lines = [header, sep]
    for (plat, tid), by_ctx in sorted(by_task.items()):
        cells = []
        for c in all_ctx:
            grp = by_ctx.get(c, [])
            wins = sum(1 for r in grp if r["success"])
            cells.append(f"{wins}/{len(grp)}" if grp else "—")
        lines.append(f"| `{plat}/{tid}` | " + " | ".join(cells) + " |")
    return "\n".join(lines)


_BUCKETS = [
    ("API retries exhausted (rate-limit)", ["retries exhausted"]),
    ("malformed tool args (model bug)", ["invalid literal for int"]),
    ("max_steps reached", ["max_steps"]),
    ("agent gave up", ["gave up", "stuck", "cannot", "unable"]),
    ("runtime error (other)", ["runtime error", "exception", "timeout"]),
    ("model returned no tool call", ["no tool call", "no tool_use"]),
]


def _taxonomy(rows: list[dict]) -> str:
    fails = [r for r in rows if not r["success"]]
    if not fails:
        return "_No failures observed._"

    buckets: Counter = Counter()
    examples: dict[str, str] = {}
    for r in fails:
        summary = (r.get("summary") or "").lower()
        placed = False
        for label, keywords in _BUCKETS:
            if any(k in summary for k in keywords):
                buckets[label] += 1
                examples.setdefault(label, f"`{r['platform']}/{r['task_id']}`: {(r['summary'] or '')[:180]}")
                placed = True
                break
        if not placed:
            buckets["other"] += 1
            examples.setdefault("other", f"`{r['platform']}/{r['task_id']}`: {(r['summary'] or '')[:180]}")

    lines = ["| Failure mode | Count | Example |", "|---|---|---|"]
    for label, count in buckets.most_common():
        lines.append(f"| {label} | {count} | {examples.get(label, '')} |")
    return "\n".join(lines)


def _headline(rows: list[dict]) -> str:
    """Two-sentence summary of what the data shows."""
    web_ctx1 = [r for r in rows if r["platform"] == "web" and r["context_window"] == 1]
    web_ctx3 = [r for r in rows if r["platform"] == "web" and r["context_window"] == 3]

    def rate(grp, field):
        if not grp: return "—"
        return f"{sum(1 for r in grp if r.get(field, False))}/{len(grp)}"

    s_ctx1 = rate(web_ctx1, "success")
    s_ctx3 = rate(web_ctx3, "success")
    j_ctx3 = rate(web_ctx3, "judge_passed")

    return (
        f"On {len(web_ctx1)+len(web_ctx3)} web trials: ctx=1 succeeded {s_ctx1} "
        f"(strict); ctx=3 succeeded {s_ctx3} (strict) / {j_ctx3} (judge-only). "
        "The strict-vs-judge-only gap counts cases where the agent achieved "
        "the goal state but didn't recognize completion — a real failure "
        "mode separate from grounding."
    )


def generate(results_path: Path, report_path: Path) -> None:
    meta, rows = _load(results_path)
    if not rows:
        report_path.write_text("# Results\n\n_No trials recorded yet._\n", encoding="utf-8")
        return

    web_rows = [r for r in rows if r["platform"] == "web"]
    mobile_rows = [r for r in rows if r["platform"] == "mobile"]
    total_cost = sum(r["cost_usd"] for r in rows)

    out: list[str] = ["# Mini-Autosana — results", ""]
    if meta:
        out += [
            f"_Recorded {meta.get('timestamp')} · "
            f"anthropic-sdk={meta.get('anthropic_sdk')} · "
            f"playwright={meta.get('playwright')} · "
            f"python={meta.get('python')} · "
            f"os={meta.get('os')}_",
            "",
        ]

    out += [
        f"Trials: **{len(rows)}** ({len(web_rows)} web, {len(mobile_rows)} mobile) · spent **${total_cost:.2f}** _(Haiku agent calls only; Sonnet judge tokens not yet tracked here)_",
        "",
        "## Headline",
        "",
        _headline(rows),
        "",
        "## Web — context window A/B",
        "",
        _platform_table(web_rows, "web"),
        "",
        "**Reading the columns:** `Strict` = agent called done(success) AND judge agreed. `Judge-only` = judge approved the final screenshot, regardless of whether agent recognized completion. `Hidden` = count where judge passed but agent didn't claim done (these inflate Judge-only above Strict).",
        "",
        "## Mobile — cross-platform grounding",
        "",
        _platform_table(mobile_rows, "mobile"),
        "",
        "Mobile uses ctx=1 only — the comparison is web-vs-mobile grounding on the same agent loop, not a context-window A/B.",
        "",
        "## Per-task breakdown (strict wins / trials)",
        "",
        _per_task_table(rows),
        "",
        "## Failure taxonomy",
        "",
        _taxonomy(rows),
        "",
        "_Taxonomy is keyword-bucketed from run summaries. For deeper "
        "analysis, walk the failure traces in `web/runs/` and `mobile/runs/`._",
        "",
        "## Known methodology limits",
        "",
        "- **Judge sees only the final screenshot.** For tasks whose success condition is met by the page's *initial* state (e.g. `todo_add_delete` checks 'is the list empty?' — and it starts empty), the judge can falsely approve a trial where the agent did nothing. The trajectory should be checked, not just the terminal state.",
        "- **Strict success is conservative.** It requires both judge agreement AND the agent self-recognizing completion via `done`. Real testing tools usually take the judge's word for it.",
        "- **n=5 web / n=3 mobile per cell.** Enough for the wins-grid to be readable but not for statistical power claims.",
        "- **Single model (Haiku 4.5).** Larger VLMs likely do better on the harder dropdown/grounding tasks.",
        "- **Coordinate-only input.** No DOM access by design. This is the same constraint that makes Autosana's selectorless pitch interesting AND hard.",
        "",
    ]
    report_path.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    generate(Path(RESULTS_PATH), Path(REPORT_PATH))
