# Mini-Autosana

> I wrote this because I wanted to feel what a customer feels when their selectorless test agent meets a screen it's never seen.

Before applying for the Autosana founding engineer role, I read their docs, picked a hypothetical persona (small mobile team, no dedicated QA), and asked: what would I want to test? How would I judge whether the product works? The full thinking is in [memo.md](memo.md).

This repo is the scrappy version of the test I'd actually want to run. It's a vision agent driving **both web (Playwright) and mobile (adb)** through the same agent loop, with a small eval harness. It does not pretend to be a benchmark — Autosana's customers don't care about my made-up tasks. It exists because I wanted real screenshots of where Haiku's grounding breaks, so my memo would have specifics behind it.

The architectural statement is in `shared/backend.py`: one `Backend` Protocol, two implementations (`web/playwright_backend.py`, `mobile/adb_backend.py`), one agent loop in `shared/agent.py` that doesn't know which surface it's testing. That mirrors what Autosana does at scale.

## What's in the box

```
shared/
  backend.py            ← the Protocol that decouples agent from platform
  agent.py              ← the loop (~140 lines, async, backend-agnostic)
  vision.py             ← Claude calls — tool_use schema, prompt cache, async, Sonnet judge
  actions.py            ← Action / StepRecord / RunReport dataclasses
  config.py             ← AGENT_MODEL, JUDGE_MODEL, pricing, viewports
web/
  playwright_backend.py ← coordinate-only Playwright wrapper, no DOM access
  tasks.py              ← 15 web tasks (saucedemo, todomvc, wikipedia)
mobile/
  adb_backend.py        ← adb-based Android backend, also coordinate-only
  tasks.py              ← 8 mobile tasks (calculator, settings, clock, chrome)
eval.py                 ← platform-agnostic matrix runner, resumable JSONL
report.py               ← results.jsonl → RESULTS.md
run_one.py              ← smoke-test one task
competitor_runs/        ← receipts from running Maestro + Mabl on the same flows
memo.md                 ← the headline artifact — read this first
demo_prep.md            ← deeper questions and architectural guesses for a demo
```

## A few engineering choices worth flagging

These are the things I'd point at in a code review:

- **No DOM, anywhere.** `web/playwright_backend.py` exposes `click(x, y)`, `type_text`, `key`, `scroll`, `screenshot` — nothing else. `mobile/adb_backend.py` exposes the same surface, backed by `adb shell input ...`. If `shared/vision.py` ever wanted to cheat with a CSS selector, it couldn't. The thesis is enforced at the API boundary, not by convention.
- **Action protocol via `tool_use`, schema enforced at the API level.** We never spend an agent step recovering from malformed JSON or a model that wrote prose when we asked for a tool call.
- **The judge is a different model from the agent.** Haiku for the agent, Sonnet 4.6 for `assert_condition`. Same-model judge gives you correlated errors — if the agent has a visual blind spot, the judge has it too, and you score the trial as a failure for the wrong reason. The judge also receives the original goal as context, so it can catch "agent succeeded at the wrong task."
- **Prompt cache on the system prompt.** Stable across all steps of a trial AND across all trials of a task with the same viewport. Cache hits are tracked separately in `StepRecord.cache_read_tokens` so the cost numbers don't lie.
- **Async + exponential backoff retry on all Anthropic calls.** A single 429 / 529 mid-eval would otherwise contaminate the success-rate signal with infrastructure noise.
- **Trial-level resumability.** `results.jsonl` is append-only with a provenance header. Re-running `eval.py` after a Ctrl-C picks up exactly where it stopped.
- **Run traces are screenshots, not log lines.** Every step writes a PNG into `web/runs/<task>_ctx<n>_t<trial>/` or the mobile equivalent. Debugging a failure means flipping through ~10 images, not parsing 200 lines of log.

## Running it

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env  # then paste your Anthropic API key

# Web smoke test
python run_one.py web sauce_login --context-window 1

# Mobile smoke test (requires Android emulator running; adb on PATH)
python run_one.py mobile calc_basic_multiply

# Dry-run the full matrix
python eval.py --tasks sauce_login calc_basic_multiply --dry-run

# Real run (~$10, ~1 hour, resumable)
python eval.py

# Aggregate
python report.py
```

## What I deliberately didn't build

Because the founders will probably ask:

- **No selectors anywhere.** Even where they'd help. The whole prototype is the constraint.
- **No `computer_20250124` (Anthropic's computer-use tool).** Tempting, but it conflicts with the cross-platform Backend abstraction — it's web-specific. The architectural statement here is "one agent, many backends." I'd happily reach for it on a web-only product.
- **No self-healing layer.** Implementing it badly would be worse than not implementing it at all. Discussed honestly in [memo.md] as a gap, not pretended-away as a feature.
- **No iOS.** macOS-only (Xcode required) and I'm on Windows. Mentioned in [demo_prep.md] as future work.
- **No statistical-power rigor.** n=5 web trials per cell, n=3 mobile. Enough that the per-task wins-grid isn't comically sparse, not enough to claim p-values. The memo is honest about this.

See [memo.md](memo.md) for the actual headline of the application — this repo is the receipt that I'll ship code, not the headline.
