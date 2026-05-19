"""Playwright-backed implementation of `shared.Backend` for the web.

Deliberately no selector-based methods. Playwright is used here only for its
low-level mouse/keyboard input and screenshot APIs — every coordinate comes
from the VLM's interpretation of pixels, never from a DOM query. That
constraint is the whole pitch of the project.

The other thing worth noting is `settle()`: replaces the previous flat
600ms sleep with `wait_for_load_state("networkidle", ...)` — same behavior
on simple pages, but on slow real-world sites (Wikipedia article loads, ad
pixels) it actually waits rather than racing the screenshot ahead of the
render. That alone cuts a class of flakes we'd otherwise blame on the agent.
"""

from __future__ import annotations

from playwright.async_api import Browser as PWBrowser
from playwright.async_api import Page, async_playwright

from shared.config import WEB_HEADLESS, WEB_VIEWPORT


_KEY_MAP = {
    "Enter": "Enter",
    "Tab": "Tab",
    "Escape": "Escape",
    "Backspace": "Backspace",
    "ArrowUp": "ArrowUp",
    "ArrowDown": "ArrowDown",
    "ArrowLeft": "ArrowLeft",
    "ArrowRight": "ArrowRight",
}


class PlaywrightBackend:
    name: str = "playwright"
    viewport: tuple[int, int] = WEB_VIEWPORT

    def __init__(self, headless: bool = WEB_HEADLESS) -> None:
        self._pw = None
        self._browser: PWBrowser | None = None
        self._page: Page | None = None
        self._headless = headless

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Backend not started — call start() first")
        return self._page

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        context = await self._browser.new_context(
            viewport={"width": self.viewport[0], "height": self.viewport[1]}
        )
        self._page = await context.new_page()

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def navigate(self, target: str) -> None:
        await self.page.goto(target, wait_until="domcontentloaded")

    async def screenshot(self) -> bytes:
        return await self.page.screenshot(type="png", full_page=False)

    async def click(self, x: int, y: int) -> None:
        await self.page.mouse.click(x, y)

    async def type_text(self, text: str) -> None:
        await self.page.keyboard.type(text, delay=20)

    async def key(self, key: str) -> None:
        await self.page.keyboard.press(_KEY_MAP.get(key, key))

    async def scroll(self, direction: str, amount: int = 400) -> None:
        dy = amount if direction == "down" else -amount
        await self.page.mouse.wheel(0, dy)

    async def settle(self, ms: int | None = None) -> None:
        """Wait until the page is visually stable.

        Default behavior: wait for `networkidle` with a generous timeout,
        falling back gracefully if the page never quiets (some pages have
        long-polling connections that hold networkidle forever).

        If `ms` is given, treat it as a flat sleep instead — useful when the
        caller knows the page will not go idle (e.g. video backgrounds).
        """
        if ms is not None:
            await self.page.wait_for_timeout(ms)
            return
        try:
            await self.page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            # networkidle didn't fire — fall back to a short sleep so the
            # caller can still progress instead of hanging.
            await self.page.wait_for_timeout(600)
