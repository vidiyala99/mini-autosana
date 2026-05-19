"""Action protocol shared between the agent and the vision layer.

Actions are returned by Claude as tool_use blocks (see vision.py). Each Action
carries the human-readable reasoning Claude wrote alongside it, which we log
to the run trace so failures can be diagnosed by reading the trace, not by
re-running the agent.

`StepRecord` also tracks cached vs fresh input tokens, since the methodology
fixes turned on Anthropic's prompt cache for the system prompt and earlier
screenshots. Cached tokens are billed at ~10% of fresh tokens; reporting the
two separately is what lets us tell an honest cost story.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Action:
    name: str  # click | type | scroll | key | done
    args: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""


@dataclass
class StepRecord:
    step: int
    screenshot_path: str
    action: Action
    input_tokens: int               # fresh input tokens billed at full rate
    cache_read_tokens: int          # cached tokens billed at ~10%
    cache_creation_tokens: int      # writes into the cache; billed at ~125% of fresh
    output_tokens: int
    latency_ms: int


@dataclass
class RunReport:
    task_id: str
    platform: str           # "web" or "mobile"
    goal: str
    context_window: int     # 1 or N — for web A/B. Mobile pins to 1 in v1.
    trial: int
    success: bool
    agent_claimed_success: bool   # decoupled from `success` so we can analyze drift
    judge_passed: bool
    summary: str
    steps: list[StepRecord]
    total_input_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    total_output_tokens: int
    total_latency_ms: int
    # Sonnet judge token counts — defaulted to 0 because historical rows in
    # results.jsonl predate this field. New runs populate them so the headline
    # cost number can include the judge instead of footnoting it.
    judge_input_tokens: int = 0
    judge_output_tokens: int = 0

    def cost_usd(
        self,
        in_price_per_mtok: float,
        out_price_per_mtok: float,
        cache_read_discount: float = 0.10,
        cache_creation_premium: float = 1.25,
    ) -> float:
        fresh_in = self.total_input_tokens * in_price_per_mtok
        cache_read = self.total_cache_read_tokens * in_price_per_mtok * cache_read_discount
        cache_write = self.total_cache_creation_tokens * in_price_per_mtok * cache_creation_premium
        out = self.total_output_tokens * out_price_per_mtok
        return (fresh_in + cache_read + cache_write + out) / 1_000_000

    def judge_cost_usd(
        self,
        judge_in_price_per_mtok: float,
        judge_out_price_per_mtok: float,
    ) -> float:
        return (
            self.judge_input_tokens * judge_in_price_per_mtok
            + self.judge_output_tokens * judge_out_price_per_mtok
        ) / 1_000_000
