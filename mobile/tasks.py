"""Mobile task suite for Android.

Targets a Google-APIs (Play Store) Pixel emulator image — what Android Studio
gives you by default for API 33-34. Verified app availability:
Settings, Clock, Chrome, Files, Contacts, Calendar, Maps, Photos.

If you switch to an AOSP-only image these tasks will still mostly work
(Settings + Chrome are universal), but the Google-app tasks will fail at
the navigate() step.

Each task carries:
- `target`: passed to AdbBackend.navigate(). Either an alias (resolved in
  adb_backend._APP_ALIASES) or a fully-qualified package/.Activity string.
- `goal`: natural language for the agent.
- `success_check`: yes/no question asked of the judge on the final screenshot.
- `difficulty`: easy | medium | hard — for slicing results.

Mobile tasks are deliberately smaller in scope than web tasks. The mobile
prototype demonstrates cross-platform architecture; it isn't a benchmark by
itself. 8 tasks is enough to surface grounding differences across screen
densities and touch-target sizes without burning the API budget.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MobileTask:
    id: str
    app: str               # alias used for display + navigate()
    target: str            # passed to backend.navigate()
    goal: str
    success_check: str
    difficulty: str


MOBILE_TASKS: list[MobileTask] = [
    # --- Settings (universal — works on any Android image) ---------------
    MobileTask(
        id="settings_open",
        app="settings",
        target="settings",
        goal="Open the Android Settings app. It should already be opening — just verify the Settings home screen is showing.",
        success_check="Is the Settings app's main screen visible (showing categories like Network & internet, Connected devices, Apps, Notifications, etc.)?",
        difficulty="easy",
    ),
    MobileTask(
        id="settings_open_display",
        app="settings",
        target="settings",
        goal=(
            "Open the Display settings screen. From the Settings home, "
            "scroll to find the Display row and tap it."
        ),
        success_check="Is the screen showing the Display settings, with options like Brightness, Dark theme, Screen timeout, or Wallpaper visible?",
        difficulty="medium",
    ),
    MobileTask(
        id="settings_toggle_dark_theme",
        app="settings",
        target="settings",
        goal=(
            "Navigate to Display settings and toggle the Dark theme switch. "
            "Note whether it was on or off before, and switch it to the opposite state."
        ),
        success_check="Is the screen visibly in a different color theme than the default light theme? (Success means the screen is now predominantly dark.)",
        difficulty="hard",
    ),
    MobileTask(
        id="settings_open_about_phone",
        app="settings",
        target="settings",
        goal=(
            "From Settings, scroll to the bottom and find the 'About phone' or 'About emulated device' row, then tap it to open."
        ),
        success_check="Is the screen showing About-phone information, with rows like Device name, Phone number, Model, Android version, or IP address visible?",
        difficulty="medium",
    ),

    # --- Clock (deeper navigation, multi-tab UI) -------------------------
    MobileTask(
        id="clock_open_alarm_tab",
        app="clock",
        target="clock",
        goal=(
            "Open the Clock app and switch to the Alarm tab. The tabs are "
            "typically at the bottom of the screen (Alarm, Clock, Timer, Stopwatch)."
        ),
        success_check="Is the Clock app showing the Alarm view (a list of alarms, possibly empty, with an Add or + button visible), NOT the analog/digital clock face or Timer view?",
        difficulty="medium",
    ),
    MobileTask(
        id="clock_add_alarm",
        app="clock",
        target="clock",
        goal=(
            "Open the Clock app, switch to the Alarm tab, and add a new "
            "alarm for 7:30 AM. Tap the + (add) button, set the time to 7:30 AM, and confirm/save the alarm."
        ),
        success_check="Is there a visible alarm entry for 7:30 AM (or 07:30) in the alarm list?",
        difficulty="hard",
    ),

    # --- Chrome (bridges to the web — interesting cross-modal test) ------
    MobileTask(
        id="chrome_open",
        app="chrome",
        target="chrome",
        goal=(
            "Open Chrome. If a first-run setup, terms of service, or sign-in prompt appears, dismiss or accept it through to a browsable state — tap 'Accept & continue', 'Use without an account', 'No thanks', or similar buttons as needed until you reach a usable Chrome browser screen."
        ),
        success_check="Is the Chrome browser in a usable state (showing either a Google search page, a 'New Tab' page with shortcuts, or a regular web page) and NOT a first-run setup, terms-of-service, or sign-in screen?",
        difficulty="medium",
    ),

    # --- Home / launcher (no app launch, pure gesture) -------------------
    MobileTask(
        id="launcher_app_drawer",
        app="home",
        target="home",
        goal=(
            "From the home screen, open the app drawer (the full grid of "
            "installed apps). On Pixel-style launchers this is done by swiping up from the bottom edge of the screen, or sometimes by tapping a small handle at the bottom."
        ),
        success_check="Is the app drawer visible — a scrollable grid or alphabetical list of installed app icons (typically more than 6-8 apps visible at once, NOT just the limited dock at the bottom of the home screen)?",
        difficulty="medium",
    ),
]


MOBILE_TASKS_BY_ID = {t.id: t for t in MOBILE_TASKS}
