# Trying to be an Autosana customer first

_Application memo for the founding engineer role · Aakash Vidiyala · May 19, 2026_

---

## I am

> A small mobile team — six engineers, no QA hire, shipping a React Native iOS+Android app every two weeks. Maestro covers the happy paths; ~2 hours of manual smoke testing per release covers the rest. We've talked about hiring a QA engineer for months and keep deferring it because the work doesn't compose — it's all one-off "is this still working?" checks.

Why this matters: every claim below is constrained by this scale — small team, two-week cadence, low tolerance for flake. Generic memos read as generic because the persona is generic.

---

## The test scenario I'd want Autosana to run for me

> Open app → log in (mocked auth in QA build) → browse the product list → add the cheapest item to cart → checkout → assert the order confirmation screen shows the right total. Run on iPhone 14 and Pixel 7. Run after each PR that touches the product list, cart, or checkout screens. (This is the e-commerce shape of `sauce_checkout`, which my prototype *attempts* end-to-end against the web equivalent but currently fails 0/5 on — the dropdown-grounding wall and the step-budget exhaustion I describe below. That's the "I want a test agent" half of why I'm writing — and `KNOWN_FIXES.md` has the post-eval diagnostic and what I shipped after the snapshot.)

Per-test budget I'd accept: **25 cents** and **90 seconds** of wall clock. Above that and the math stops working for our team size.

---

## How I'd judge you on it

In priority order:

1. **First-run success rate** on this exact flow. I want **≥95%** before I trust you in CI. Below that and I'm reading agent traces every morning instead of code.
2. **Post-UI-change success rate** — the self-healing claim. I rename a button from "Checkout" to "Place Order". Does the test still pass without me re-recording it? I'd accept **≥75%** here, far below the no-change number, but I want to *see the gap*.
3. **Debuggability when a test fails.** When the agent says "I think this failed," can I see the screen it gave up on, the action it almost took, and one paragraph of why? I'd judge this by reading 3 failure reports and timing how long it takes me to form a hypothesis.
4. **Cost per test run.** I'd want to budget **~$50/month** for this team's full regression suite. If a single checkout test costs more than **25¢** I have a problem at our deploy frequency.
5. **CI integration friction.** Specifically: time from `git clone` to a green test running on a PR. **Under 1 hour**.

---

## What I tried instead — receipts

I ran the equivalent of this flow on the competitors I could actually touch so I'd know what I was comparing you to.

### Maestro on Android — a flow my own agent runs

Full write-up + artifacts: `competitor_runs/maestro/` (YAML flow, crash log, emulator info).

I installed Maestro CLI 2.5.1 and pointed it at the same Android 17 emulator my agent ran 24 mobile trials on. The flow I wrote was a 3-line YAML mirroring my own `mobile/settings_open_display` task:

```yaml
appId: com.android.settings
---
- launchApp
- tapOn: "Display"
- assertVisible: "Brightness level"
```

**It didn't run.** Maestro's bundled native gRPC libs (`libio_grpc_netty_shaded_netty_transport_native_epoll_x86_64.so`) fail to `dlopen` on Android 17's 16KB-page system image, the instrumentation process is killed by `lowmemorykiller`, and the gRPC server never binds. Maestro times out after ~23s.

This is itself a receipt. Two takeaways:

1. **Maestro is on-device instrumentation; my agent isn't.** Maestro runs a JVM process inside the emulator and talks to it over gRPC. When the OS layout changes (16KB pages is the new default for Android 15+ AVDs), it needs to ship a new build. My agent grounds on screenshot pixels and dispatches `adb shell input tap x y` — no native code on the device side, so OS updates don't touch it.
2. **The YAML is the entire contract, and it's selectors.** Even setting aside today's crash, `tapOn: "Display"` and `assertVisible: "Brightness level"` are literal text matchers. Rename "Display" to "Display & sound" (Android has done it before) and the flow silently breaks. This is the selector-coupling problem Autosana is built to remove.

Time spent: ~25 min from `curl` of the CLI zip to giving up on the driver crash and writing this up. That's the honest number.

### Mabl on web — not run

I didn't run Mabl. Honest reason: it requires an interactive trial signup and email verification, and I had a finite morning budget. I read the docs, the public case studies, and one ~2hr YouTube walk-through; that's not the same as touching it, and I'm not going to pretend otherwise. If we talked, the first 5 minutes would be me asking what your install looks like vs theirs.

### Quick rating table (subjective, n=1)

| Criterion | Maestro | What I'd want from Autosana |
|---|---|---|
| Time to first green test | n/a — couldn't boot driver on Android 17 / 16KB pages | Under 15 min, OS-version-agnostic |
| Survives a button rename | No (`tapOn: "Display"` is literal text) | Yes, with visible "I healed this" indicator |
| Failure debug experience | `adb logcat` + JVM stack trace | Screenshots + the agent's reasoning trace |
| Dependency on OS contract | High (on-device native code) | Low (screenshot-only) |

---

## Where I expect Autosana would shine vs Maestro / Mabl

Three specific bets, grounded in the receipts above:

1. **Self-healing across the deliberate-UI-change case.** Maestro's `tapOn: "Display"` literally cannot survive a rename. Your docs claim self-healing handles this; my prototype suggests Haiku-class VLMs can ground on a renamed button if the surrounding context is similar. The question I'd want answered is *how often* and *with what failure mode*.
2. **Mobile + web parity.** Maestro is mobile-first; Mabl is web-first. You're claiming both — and my prototype's architecture (one Backend protocol, two implementations) suggests this is achievable cleanly, but I'd want to see how Autosana handles the *cost asymmetry*: a mobile screenshot is ~3x the tokens of a web screenshot at the same DPI.
3. **Test-as-code-diff.** Your docs mention generating tests from code diffs. This is the thing that would make me actually pay — automatic regression coverage on the PR that just changed the checkout screen. Maestro and Mabl both require me to *write* tests. Generating them is a fundamentally different value proposition.

---

## 3 questions I'd ask on a demo

1. **What's the failure mode when your agent meets a paywall, SSO, or feature-flag wall it has never seen?** The interesting answer is not "it logs in" — it's *how* you decide between completing the auth, treating it as out-of-scope, or surfacing it as "agent is unsure, human?"
2. **How do you decide when a self-healed pass should still be flagged?** A test that "passed" after the agent rerouted through 3 unexpected screens probably means something is broken. What does that show up as in the dashboard?
3. **What's the per-customer infra cost shape?** I'm asking because the architecture choice (shared multi-tenant emulators vs dedicated per-customer browsers/devices) determines who you can afford to sell to. I'd love to know how you've been thinking about that.

---

## The scrappy version I built

I built a vision agent that does roughly what I think Autosana's agent does — same idea, much less polish, no self-healing, no diff-driven generation. It runs on **both web (Playwright) and Android (adb)** through the same agent loop, and includes a small eval harness so I could actually look at where it breaks.

**Repo:** https://github.com/vidiyala99/mini-autosana

I ran it on 174 trials (150 web + 24 mobile) using Claude Haiku 4.5 as the agent and Sonnet 4.6 as an independent visual judge. The numbers, deliberately unspun:

| Setup | Strict pass | Judge-only pass |
|---|---|---|
| Single-frame agent (ctx=1) | **0/75** | 15/75 |
| 3-frame context (ctx=3) | **16/75 (21%)** | 31/75 (41%) |
| Mobile (ctx=1) | 3/24 | 5/24 |

What I learned from each row:

- **Single-frame agents are categorically broken on multi-step tasks.** 0/75 — not noise, structural. The model, given only the current screenshot at temperature=0, picks the same action over and over until max_steps. This isn't a Haiku-specific problem; it's true of any VLM agent without trajectory memory.
- **Three frames of context lifts simple tasks from 0% to 80-100%.** `sauce_login` 4/5, `wiki_einstein_to_relativity` 5/5, `todo_add_one` 3/5. Where context history is enough, it's *very* enough.
- **The strict-vs-judge-only gap (21% → 41%) is its own finding.** Half the "ctx=3 failures" are cases where the agent reached the goal state but didn't call `done`. That's a separate failure mode from grounding — it's about self-awareness of completion. I'd want to ask you how Autosana handles it.
- **The hard tasks fail on a different axis.** Saucedemo's native HTML `<select>` for sorting opens an OS-level menu that's *outside the screenshot* — the agent literally cannot see the options. I added a keyboard-navigation hint to the system prompt; on `sauce_add_cheapest` the agent now correctly presses `key("P")` + `key("Enter")` to sort, but then misses the add-to-cart button by 60px because Haiku's grounding precision on small targets is the next bottleneck.

The point isn't the 21% number. It's that I now know *exactly where the walls are*, which is the question I'd want to be working on with you.

It's the receipt for "I'm not just writing about agents — I've felt where they fail." The README links to specific architectural choices that I'd be happy to discuss if you want to go deep.

---

_Thanks for reading. I'd love 15 minutes to ask you the three questions above and hear which parts of this memo are obviously wrong._

— Aakash Vidiyala
