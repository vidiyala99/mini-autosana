"""The cross-platform contract.

A `Backend` is anything that can take a screenshot of some visual surface and
respond to coordinate-level input. The agent loop in `shared/agent.py` is
written against this Protocol — it never imports Playwright or adb, and it
doesn't care which one is in use. Web and mobile differ in real ways
(URL vs package/.Activity, networkidle vs sleep, viewport vs resolution), but
those differences live inside backends, not in the agent.

This is the architectural statement of the project: one agent loop, many
backends. It mirrors what Autosana's product does at scale — the same
testing intelligence driving web browsers, iOS simulators, and Android
emulators.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Backend(Protocol):
    """Surface the agent operates on. Either a web page or a mobile screen."""

    name: str               # short identifier — "playwright" / "adb"
    viewport: tuple[int, int]  # width, height in pixels — used in the system prompt

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def navigate(self, target: str) -> None:
        """Open a starting location.

        - Web backend: `target` is a URL.
        - Mobile backend: `target` is `package.name/.Activity` or a known alias
          like "calculator". The backend resolves it.
        """
        ...

    async def screenshot(self) -> bytes:
        """Return PNG bytes of the current viewport."""
        ...

    async def click(self, x: int, y: int) -> None: ...
    async def type_text(self, text: str) -> None: ...
    async def key(self, key: str) -> None:
        """Press a single named key.

        Backends must accept at least: Enter, Tab, Escape, Backspace, ArrowUp,
        ArrowDown, ArrowLeft, ArrowRight. Mobile backends additionally accept
        Home and Back.
        """
        ...

    async def scroll(self, direction: str, amount: int = 400) -> None:
        """Scroll up or down. `amount` is in viewport-relative units, not
        guaranteed to map to pixels exactly — backends may translate."""
        ...

    async def settle(self, ms: int | None = None) -> None:
        """Wait until the surface is visually stable enough to screenshot.

        If `ms` is None, the backend uses its own default (web: networkidle
        with a timeout; mobile: a short fixed sleep). Pass an int to override
        when a task needs more or less waiting.
        """
        ...
