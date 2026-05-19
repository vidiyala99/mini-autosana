# Demo prep — for after the email lands

_Not linked from the cold email. Lives here for the founder who scrolls the repo._

_The memo asked you 3 questions. This file is the deeper version of that — the things I'd want to dig into in a 30-minute demo, the architectural guesses I'd want validated or corrected, and one product gap I noticed._

---

## 3 architectural guesses I'm making about Autosana

I tried to derive these from your public material. If any are wrong I'd love to hear *why* — the gap between my model and reality is usually where the interesting engineering lives.

### Guess 1: The agent isn't a single model call per step

<TODO: write a paragraph. Hypothesis: you have a planner model + an executor model + maybe a verifier. The executor is the cheap fast VLM; the planner is rarer and beefier; the verifier runs at task end. Reasoning: this is the standard architecture for cost-efficient agent loops and matches the cost shape any agent-testing business has to hit. Where I might be wrong: maybe you use extended thinking instead, or maybe one model with structured prompting is enough.>

### Guess 2: Self-healing isn't pure VLM grounding

<TODO: write a paragraph. Hypothesis: self-healing combines visual grounding (Claude/GPT/etc) with a memory of the previous successful trajectory and the DOM/accessibility tree as a tiebreaker. The marketing claim is "no selectors" but the engineering reality probably uses accessibility info as a heuristic. Reasoning: pure pixel grounding wouldn't reliably survive material UI changes; you'd need something to anchor the "I'm still on the right page" judgment. Where I might be wrong: maybe set-of-marks or coordinate caching is enough; maybe you have a fine-tuned grounding model that makes this moot.>

### Guess 3: Emulator/browser pool is the hardest infra problem

<TODO: write a paragraph. Hypothesis: cold-starting an Android emulator is 20-40s; cold-starting Chromium is 1-2s. At scale, customer test runs need warm pools with snapshot restore, and that's where most of the operational complexity lives. Reasoning: it's what the "Build out infrastructure that manages simulators, emulators, and browsers" line in the JD is hinting at. Where I might be wrong: maybe you outsource to Browserstack/Sauce for now; maybe customers' tests are batched in ways that hide the cold-start.>

---

## 5 questions I'd ask in the demo (deeper than the 3 in the memo)

1. **What's your cost-per-passed-test trend over the last 6 months?** I'd expect this to be one of the most-watched internal numbers — and the story it tells (going up? down? flat?) probably maps to which axis you're optimizing this quarter.
2. **When a customer's test starts failing intermittently — same flow, same build, different outcomes — what's your support playbook?** This is the question that separates "we have an agent" from "we have a product." The answer is also the one I'd most want to *help* with.
3. **Do you let customers see the agent's reasoning trace?** Or is it abstracted away as "the agent did X, Y, Z"? I have a strong prior here (show it, customers love it, debugging compounds) but I'd want to know what you've actually heard from users.
4. **How do you decide what to ship next?** Specifically: how does information flow from the shared customer Slack channels to roadmap decisions? I noticed the JD calls this out as the work; I'd love to see the actual mechanism.
5. **What's the one thing you'd change about the YC pitch if you re-wrote it today?** Less an engineering question, more a "where has the company learned the most since launch" question.

---

## One product gap I noticed

<TODO: pick ONE concrete gap from docs.autosana.ai. Candidates to investigate:
- Paywall / SSO handling (do the docs mention it?)
- Feature-flag-gated screens (does the agent know about feature flags?)
- Localization / RTL (is the agent's grounding language-aware?)
- Cost reporting / per-test attribution (can a customer see "this PR cost $X to test"?)
- Test failure attribution (when a test fails, is it the agent, the app, or the test description?)

Pick the one you can defend. Write ~3 paragraphs:
1. What I noticed (be specific, cite the doc page if possible)
2. Why I think it matters for a customer
3. How I might approach it in week 1 — be honest that I'm guessing without seeing the codebase
>

---

## One idea I'd want to ship in my first 2 weeks

<TODO: pick something small enough that 2 weeks is credible, concrete enough that it's not a hand-wave, and adjacent to something they already have. Candidates:

- A "test cost preview" feature that runs in the PR check and tells the developer "this PR will cost ~$0.40 to test on the current suite" — uses your existing run telemetry, costs nothing to add, big delighter
- A flake classifier that takes failed runs and bins them into "real failure" / "model variance" / "page non-determinism" — uses existing data, easy to A/B against current handling
- An agent trace differ — given two runs of the same flow, find the step where they diverged and surface as "you used to do X here, now you're doing Y"

Write ~4 paragraphs: what it is, why it'd land with customers, what data/access I'd need to build it, what could go wrong.
>

---

## Things I'd test in week 2

A list of experiments I'd want to run that this prototype doesn't cover yet, ordered by what I expect to learn most from:

1. **Local VLM vs frontier model on the same task suite.** Specifically Molmo-7B (Allen AI, purpose-trained on element-grounding) running locally on a single 4070-class GPU, vs Haiku 4.5 on the API. The interesting axis isn't *which wins on success rate* — it's *what's the cost-quality frontier*. A 60% success rate at $0/trial may be better economics than 85% at $0.05/trial depending on the volume, and Autosana's customer mix probably has both shapes. The `Backend` protocol in this repo already makes the model swap a single-file change.
2. **Set-of-marks overlays.** Numbered boxes drawn over interactive elements before sending the screenshot to the model. Well-known to dominate raw-pixel grounding (SeeAct, WebVoyager). The catch: requires DOM access to enumerate elements, which is in tension with the "no selectors" thesis. The interesting question is *where* on the tradeoff curve Autosana sits, not whether to use it.
3. **Anthropic `computer_20250124` tool comparison.** Their dedicated computer-use-trained model variant. I didn't use it here because it conflicts with the cross-platform Backend abstraction (it's web-only). But for the *web* side specifically, I'd want a head-to-head against my vanilla `tool_use` setup — if it wins by 20+ points, that's enough to justify a web-specific code path inside the agent. If it wins by 5, probably not worth the architectural complexity.
4. **Self-healing across a deliberate UI change.** Take a passing test, rename one button text, see if the agent recovers via visual grounding. This is the central marketing claim of the entire product — running my own version of it would be the first thing I'd do with internal Slack channel access.

---

_I'd be happy to be wrong about any of the above — the point isn't to be right on day -1, it's to show I've already started forming opinions on the things that matter._

— <TODO: your name>
