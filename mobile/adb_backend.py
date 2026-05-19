"""adb-backed implementation of `shared.Backend` for Android.

We use adb directly (not Appium / UI Automator) because:

1. Same philosophy as the web side: no selectors. Every action is a pixel
   tap or a key event. The agent sees what a human sees.
2. Fewer moving parts. Appium needs a server, drivers, capabilities, port
   forwarding. adb is one binary with one stdio interface.
3. The bytes flow is honest. `adb exec-out screencap -p` returns PNG on
   stdout; `adb shell input tap x y` returns nothing. Nothing in between.

Windows-specific note: we use `asyncio.create_subprocess_exec` (no shell)
because `screencap`'s stdout is binary and cmd.exe's text-mode line-ending
translation will corrupt the PNG header otherwise. This is a real, observed
failure mode on Windows that bites everyone the first time they try.
"""

from __future__ import annotations

import asyncio
import os
import shutil

from shared.config import MOBILE_ADB_SERIAL, MOBILE_VIEWPORT


# Friendly aliases → package/.Activity. The agent says "settings", we
# resolve it. Verified on Google Play Services emulator image; if you
# switch to AOSP-only, some packages won't exist.
_APP_ALIASES = {
    "settings": "com.android.settings/.Settings",
    "clock": "com.google.android.deskclock/com.android.deskclock.DeskClock",
    "files": "com.google.android.documentsui/com.android.documentsui.LauncherActivity",
    "chrome": "com.android.chrome/com.google.android.apps.chrome.Main",
    "contacts": "com.google.android.contacts/com.android.contacts.activities.PeopleActivity",
    "calendar": "com.google.android.calendar/com.android.calendar.AllInOneActivity",
    "home": "HOME",  # special — pressed via keyevent, not am start
}


# adb names vs the protocol's names. We translate so the agent stays
# platform-agnostic in its action vocabulary.
_KEY_MAP = {
    "Enter": "KEYCODE_ENTER",
    "Tab": "KEYCODE_TAB",
    "Escape": "KEYCODE_ESCAPE",
    "Backspace": "KEYCODE_DEL",
    "ArrowUp": "KEYCODE_DPAD_UP",
    "ArrowDown": "KEYCODE_DPAD_DOWN",
    "ArrowLeft": "KEYCODE_DPAD_LEFT",
    "ArrowRight": "KEYCODE_DPAD_RIGHT",
    "Home": "KEYCODE_HOME",
    "Back": "KEYCODE_BACK",
}


class AdbError(RuntimeError):
    pass


class AdbBackend:
    name: str = "adb"
    viewport: tuple[int, int] = MOBILE_VIEWPORT

    def __init__(self, serial: str | None = MOBILE_ADB_SERIAL) -> None:
        self._serial = serial
        adb = os.environ.get("ADB_PATH") or shutil.which("adb")
        if adb is None or not os.path.exists(adb):
            # Common Android Studio install locations on Windows.
            for candidate in (
                os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
                os.path.expandvars(r"%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
            ):
                if os.path.exists(candidate):
                    adb = candidate
                    break
        if adb is None or not os.path.exists(adb):
            raise AdbError(
                "adb not found. Set ADB_PATH in .env to the full path of "
                "adb.exe, OR add Android SDK platform-tools to your PATH."
            )
        self._adb = adb

    # ----- adb plumbing --------------------------------------------------

    def _base_args(self) -> list[str]:
        return [self._adb, "-s", self._serial] if self._serial else [self._adb]

    async def _run(self, *args: str, capture: bool = False) -> bytes:
        """Run an adb command. Returns stdout bytes if capture=True, else b''."""
        proc = await asyncio.create_subprocess_exec(
            *self._base_args(), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise AdbError(
                f"adb {' '.join(args)} failed (rc={proc.returncode}): "
                f"{err.decode(errors='replace')[:300]}"
            )
        return out if capture else b""

    async def _shell(self, *args: str) -> None:
        """`adb shell` for fire-and-forget input/am commands."""
        await self._run("shell", *args)

    # ----- lifecycle -----------------------------------------------------

    async def start(self) -> None:
        # Sanity check: at least one device attached.
        out = await self._run("devices", capture=True)
        # Output is `List of devices attached\n<serial>\tdevice\n...`. Look
        # for at least one line matching "<serial>\tdevice".
        lines = [ln.strip() for ln in out.decode(errors="replace").splitlines()[1:] if ln.strip()]
        attached = [ln for ln in lines if "\tdevice" in ln]
        if not attached:
            raise AdbError(
                "No Android device attached. Start an emulator (Android Studio "
                "AVD Manager) or connect a device with USB debugging enabled."
            )
        # Go home before each run so we start from a known surface.
        await self._shell("input", "keyevent", "KEYCODE_HOME")
        await asyncio.sleep(0.5)

    async def stop(self) -> None:
        # adb is stateless; nothing to tear down. Leaving the emulator
        # running between trials is a feature — cold-starting an emulator
        # takes 20-40s and we want trials to be cheap.
        return

    # ----- navigate ------------------------------------------------------

    async def navigate(self, target: str) -> None:
        """Open an app. `target` is either an alias (`calculator`) or a fully
        qualified `package/.Activity` string.

        The special alias `home` presses the home button instead of starting
        an app — useful for tasks that begin from the launcher."""
        resolved = _APP_ALIASES.get(target.lower(), target)
        if resolved == "HOME":
            await self._shell("input", "keyevent", "KEYCODE_HOME")
        else:
            await self._shell("am", "start", "-n", resolved)
        await self.settle(1500)  # apps need more time than web pages

    # ----- input ---------------------------------------------------------

    async def screenshot(self) -> bytes:
        # `exec-out` instead of `shell` is critical here: shell would PTY-ify
        # the connection and corrupt the binary PNG. exec-out gives us raw
        # bytes on stdout. Without this on Windows, every PNG has its
        # 0x0A bytes turned into 0x0D 0x0A and decoders explode.
        return await self._run("exec-out", "screencap", "-p", capture=True)

    async def click(self, x: int, y: int) -> None:
        await self._shell("input", "tap", str(x), str(y))

    async def type_text(self, text: str) -> None:
        # `input text` doesn't handle spaces; we send word by word with
        # KEYCODE_SPACE between. Special characters are escaped per adb's
        # weird rules — for our task suite plain alphanumerics + spaces
        # cover everything.
        words = text.split(" ")
        for i, word in enumerate(words):
            if word:
                await self._shell("input", "text", word)
            if i < len(words) - 1:
                await self._shell("input", "keyevent", "KEYCODE_SPACE")

    async def key(self, key: str) -> None:
        keycode = _KEY_MAP.get(key, f"KEYCODE_{key.upper()}")
        await self._shell("input", "keyevent", keycode)

    async def scroll(self, direction: str, amount: int = 400) -> None:
        cx = self.viewport[0] // 2
        cy = self.viewport[1] // 2
        # Swipe direction is opposite of scroll direction: to scroll "down"
        # (reveal content below), the finger swipes UP the screen.
        if direction == "down":
            y1, y2 = cy + amount // 2, cy - amount // 2
        else:
            y1, y2 = cy - amount // 2, cy + amount // 2
        await self._shell("input", "swipe", str(cx), str(y1), str(cx), str(y2), "300")

    async def settle(self, ms: int | None = None) -> None:
        await asyncio.sleep((ms if ms is not None else 800) / 1000.0)
