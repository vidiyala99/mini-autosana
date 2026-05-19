# Mini-Autosana — results

_Recorded 1779172674 · anthropic-sdk=0.102.0 · playwright=unknown · python=3.12.10 · os=Windows 11_

Trials: **174** (150 web, 24 mobile) · spent **$13.12** _(Haiku agent calls only; Sonnet judge tokens not yet tracked here)_

## Headline

On 150 web trials: ctx=1 succeeded 0/75 (strict); ctx=3 succeeded 16/75 (strict) / 31/75 (judge-only). The strict-vs-judge-only gap counts cases where the agent achieved the goal state but didn't recognize completion — a real failure mode separate from grounding.

## Web — context window A/B

| Condition | N | Strict | Judge-only | Hidden | p50 latency | p50 steps | $/task |
|---|---|---|---|---|---|---|---|
| web ctx=1 | 75 | 0.0% | 20.0% | 15 | 41951 ms | 22 | $0.0578 |
| web ctx=3 | 75 | 21.3% | 41.3% | 15 | 38227 ms | 15 | $0.0931 |

**Reading the columns:** `Strict` = agent called done(success) AND judge agreed. `Judge-only` = judge approved the final screenshot, regardless of whether agent recognized completion. `Hidden` = count where judge passed but agent didn't claim done (these inflate Judge-only above Strict).

## Mobile — cross-platform grounding

| Condition | N | Strict | Judge-only | Hidden | p50 latency | p50 steps | $/task |
|---|---|---|---|---|---|---|---|
| mobile ctx=1 | 24 | 12.5% | 20.8% | 2 | 42073 ms | 22 | $0.0752 |

Mobile uses ctx=1 only — the comparison is web-vs-mobile grounding on the same agent loop, not a context-window A/B.

## Per-task breakdown (strict wins / trials)

| Task | ctx=1 | ctx=3 |
|---|---|---|
| `mobile/chrome_open` | 0/3 | — |
| `mobile/clock_add_alarm` | 0/3 | — |
| `mobile/clock_open_alarm_tab` | 0/3 | — |
| `mobile/launcher_app_drawer` | 0/3 | — |
| `mobile/settings_open` | 3/3 | — |
| `mobile/settings_open_about_phone` | 0/3 | — |
| `mobile/settings_open_display` | 0/3 | — |
| `mobile/settings_toggle_dark_theme` | 0/3 | — |
| `web/sauce_add_cheapest` | 0/5 | 0/5 |
| `web/sauce_checkout` | 0/5 | 0/5 |
| `web/sauce_login` | 0/5 | 4/5 |
| `web/sauce_logout` | 0/5 | 0/5 |
| `web/sauce_sort_price_desc` | 0/5 | 0/5 |
| `web/todo_add_delete` | 0/5 | 0/5 |
| `web/todo_add_one` | 0/5 | 3/5 |
| `web/todo_clear_completed` | 0/5 | 0/5 |
| `web/todo_complete_middle` | 0/5 | 0/5 |
| `web/todo_filter_active` | 0/5 | 0/5 |
| `web/wiki_einstein_to_relativity` | 0/5 | 5/5 |
| `web/wiki_random` | 0/5 | 1/5 |
| `web/wiki_search_einstein` | 0/5 | 2/5 |
| `web/wiki_search_python` | 0/5 | 0/5 |
| `web/wiki_today_featured` | 0/5 | 1/5 |

## Failure taxonomy

| Failure mode | Count | Example |
|---|---|---|
| max_steps reached | 107 | `web/sauce_login`: max_steps=22 reached without done | judge: The screenshot shows the Swag Labs login page, not the products inventory page. The user has not yet logged in — the username and passwor |
| other | 25 | `web/sauce_add_cheapest`: Successfully logged in with standard_user, sorted products by price (low to high), and added the cheapest product (Sauce Labs Onesie at $7.99) to the cart. The cart now shows 1 ite |
| runtime error (other) | 23 | `web/sauce_sort_price_desc`: runtime error: BadRequestError("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic AP |

_Taxonomy is keyword-bucketed from run summaries. For deeper analysis, walk the failure traces in `web/runs/` and `mobile/runs/`._

## Known methodology limits

- **Judge sees only the final screenshot.** For tasks whose success condition is met by the page's *initial* state (e.g. `todo_add_delete` checks 'is the list empty?' — and it starts empty), the judge can falsely approve a trial where the agent did nothing. The trajectory should be checked, not just the terminal state.
- **Strict success is conservative.** It requires both judge agreement AND the agent self-recognizing completion via `done`. Real testing tools usually take the judge's word for it.
- **n=5 web / n=3 mobile per cell.** Enough for the wins-grid to be readable but not for statistical power claims.
- **Single model (Haiku 4.5).** Larger VLMs likely do better on the harder dropdown/grounding tasks.
- **Coordinate-only input.** No DOM access by design. This is the same constraint that makes Autosana's selectorless pitch interesting AND hard.
