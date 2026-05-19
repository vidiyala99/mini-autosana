"""Project-wide constants. Keep boring and explicit."""

# The agent model — cheap, fast, used for the inner loop.
AGENT_MODEL = "claude-haiku-4-5-20251001"

# The judge model — deliberately different from the agent.
# Using the same model for both means a visual blind spot in Haiku appears
# in both the agent (fails to act) and the judge (fails to notice), and the
# trial gets counted as a failure for the wrong reason. Sonnet 4.6 sees the
# screenshots independently.
JUDGE_MODEL = "claude-sonnet-4-6"

MAX_OUTPUT_TOKENS = 1024
TEMPERATURE = 0.0   # pinned. The eval reports treatment effects, not stochasticity.

# Web defaults
WEB_VIEWPORT = (1280, 800)
WEB_HEADLESS = True

# Mobile defaults (Pixel-class emulator)
MOBILE_VIEWPORT = (1080, 1920)
MOBILE_ADB_SERIAL: str | None = None   # None = use the only attached device

MAX_STEPS_DEFAULT = 22

# Anthropic Haiku 4.5 vision pricing as of 2026-05.
# Update if pricing changes — cost_usd in actions.py reads these.
HAIKU_INPUT_PRICE_PER_MTOK = 1.00
HAIKU_OUTPUT_PRICE_PER_MTOK = 5.00

# Sonnet 4.6 — used for the judge only (~few hundred calls per eval).
SONNET_INPUT_PRICE_PER_MTOK = 3.00
SONNET_OUTPUT_PRICE_PER_MTOK = 15.00

RESULTS_PATH = "results.jsonl"
REPORT_PATH = "RESULTS.md"
