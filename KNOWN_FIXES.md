# Known fixes — diagnostic and what shipped after the published eval

`RESULTS.md` is a snapshot of what the harness did when I ran it (174 trials, $13.12). Re-reading the failure traces after the fact, I found a set of infrastructure defects that — independent of model capability — were responsible for a meaningful chunk of the "0/5" cells. This doc captures the diagnostic + what I shipped.

I did not rerun the eval to update `RESULTS.md` (budget). The fixes below are in `main` and would change the numbers on any reproduction; the published numbers are honest as a snapshot of the code at the time they were generated.

---

## Headline finding from the postmortem

Three orthogonal infra defects dominate the failure profile — not "the agent is bad":

1. **`MAX_STEPS=22` was below the floor for multi-stage form flows.** Forensic trace of `web/sauce_checkout_ctx3_t1`: agent did everything correctly through step 21 (login, add to cart, fill checkout form), reached the Overview page, and ran out of steps with the Finish button one click away. All 5 ctx=3 trials of `sauce_checkout` terminated with `max_steps=22 reached without done`. `max_steps reached` accounts for **107 of 174 trials** in the failure taxonomy.
2. **`TEMPERATURE = 0.0` makes "n=5 per cell" measure timing variance, not policy variance.** Identical prompt + identical model + cached system prompt → near-identical outputs. The n=5 cells in the report are stochasticity-limited, not variance samples. Worth flagging in the methodology note (now done).
3. **The judge has a leniency override clause AND only sees the final screenshot.** Of the 44 trials where the agent self-claimed success, **25 (57%) were rejected by the judge** — text duplicated, partial completion, wrong page. This "false claim" failure mode was not surfaced in the original report. Counting over `results.jsonl` shows the symmetric pair: 32 hidden successes (agent missed completion) + 25 false claims (agent over-claimed).

---

## What I shipped (no rerun)

| Fix | File | What changed | No-rerun rationale |
|---|---|---|---|
| **A. Raise `MAX_STEPS_DEFAULT`** | `shared/config.py` | `22 → 40` | Code change only; published numbers stay frozen, but a founder who clones + runs gets a representative result on multi-step flows. |
| **B. Strengthen the `done` tool description** | `shared/vision.py` | Rewrote from 2-line generic ("if the goal was reached") to 5-line spec with explicit positive trigger ("AS SOON AS the success condition is visible"), negative trigger ("3+ attempts without page change"), and call-out that done is not optional. | Targets the 32 hidden successes. |
| **C. Delete judge leniency clause** | `shared/vision.py` | Removed *"Be strict but not pedantic. If the user goal is plainly satisfied on the screen, answer passed=true even if the question's exact phrasing has some ambiguity."* The question is now the contract; the goal is context only. | Tightens precision for any future run. |
| **D. Pass trajectory screenshots to the judge** | `shared/vision.py` + `shared/agent.py` | `assert_condition` now accepts `trajectory_screenshots`; agent passes the last 2 frames before the terminal screenshot. | Closes the "initial state == success state" false-positive class (`todo_add_delete`). |
| **E. Add `False claim` column to the report** | `report.py` | Symmetric to `Hidden`. Existing rows in `results.jsonl` already carry `agent_claimed_success` + `judge_passed`, so the column populates from frozen data — no rerun needed. | Surfaces the 25 false claims that the original report hid. |
| **F. Track Sonnet judge tokens going forward** | `shared/vision.py`, `shared/actions.py`, `eval.py` | `JudgeResult` carries token usage; `RunReport.judge_cost_usd()` exists; `eval.py._serialize()` writes it. Footnote added to `RESULTS.md` calling out that historical $X.XX is Haiku-only. | Future cost numbers are honest; the historical "$13.12 _Haiku-only_" stays footnoted because the historical token counts weren't logged. |
| **G. Log coordinate coercion fallbacks** | `shared/agent.py` | `logger.warning` when `_coerce_xy` regex path triggers. | Visibility into model-tool-protocol drift. Was silent before. |

---

## What I deferred (would require a rerun, or is bigger than a one-day push)

| Defect | Why deferred |
|---|---|
| **Temperature > 0 for the eval matrix.** Would give real per-trial variance. | Requires a rerun, and the existing temperature=0 choice is defensible (it's measuring treatment effects on context window / model / platform — adding policy noise would muddy that signal). The right move is to *document* it (now done in the methodology note), not to flip it before a rerun budget is available. |
| **Refactor to proper `tool_use` / `tool_result` interleaving across steps.** Current code passes a single user message per step with action history as text and screenshots as image blocks. Proper interleaved-message structure would let the model reason natively about "I just did X, the page now shows Y." | ~1 day of work; changes the agent's behavior enough that published numbers would no longer represent the current code at all. Punted to a v2. |
| **Per-task `max_steps` overrides.** The right floor depends on the task (login = 8, checkout = 30). The global bump to 40 is a workaround; per-task is the real fix. | Easy but not urgent — the global bump unblocks the worst cells. |
| **Step-level judge checkpoints.** One judge call per step instead of per trial would catch "agent took a wrong door at step 7" earlier. | Cost goes up ~10× on the judge side. Worth it for a production agent, overkill for an eval. |

---

## What a reader should take from this doc

The point of this repo is to be *honest about where agents break*, not to ship a polished marketing surface. `RESULTS.md` is the snapshot of an early version of the harness. This doc + the diffs in `main` are the receipt that, post-eval, I sat with the failure traces, found the infra defects underneath the surface symptoms (dropdown wall, hidden successes), and shipped the cheap fixes.

If you re-run the eval against the current code, the floor on multi-stage form flows should rise sharply (Fix A alone), the judge should be tighter (Fixes C + D), and the cost number will be honest about both models (Fix F). I'd expect web ctx=3 strict pass to land somewhere in the 35-50% range after these fixes, but I haven't measured — that's the next experiment.
