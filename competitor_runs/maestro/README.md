# Maestro receipt — couldn't run on Android 17 / 16KB pages

## What I tried

Install Maestro CLI 2.5.1 (the latest as of 2026-05-19), point it at the same Android emulator my agent ran 24 mobile trials against, and execute one flow.

**Flow file** (`settings_open_display.yaml`):
```yaml
appId: com.android.settings
---
- launchApp
- tapOn: "Display"
- assertVisible: "Brightness level"
```

That YAML is a fair, minimal Maestro flow for the same task my agent attempts as `mobile/settings_open_display` (where my agent scored 0/3, ctx=1).

## What happened

```
$ maestro test settings_open_display.yaml
Maestro Android driver did not start up in time
  ---  emulator [ emulator-5554 ] & port [ dadb.open( tcp:7001 ) ]

Elapsed: 23.5s
```

Maestro installs two APKs on boot (`dev.mobile.maestro` + `dev.mobile.maestro.test`) and starts a gRPC server via `am instrument`. On my emulator the instrumentation process crashes before the server binds. From `adb logcat`:

```
dlopen failed: library "libio_grpc_netty_shaded_netty_transport_native_epoll_x86_64.so" not found
lowmemorykiller: Kill 'dev.mobile.maestro' (4384) ... oom_score_adj 0 ... min watermark is breached
Process dev.mobile.maestro (pid 4384) has died: fg FGS
Crash of app dev.mobile.maestro running instrumentation ComponentInfo{dev.mobile.maestro.test/...}
```

Full crash excerpt is in `crash_logcat.txt`.

## Emulator (`emulator_info.txt`)

```
ro.product.model = sdk_gphone16k_x86_64
ro.build.version.release = 17
ro.product.cpu.abi = x86_64
16KB page size: yes
```

This is the **Android 17 system image with 16KB memory pages**, which Google made the default for new AVDs in late 2025. Maestro 2.5.1 ships native libraries built against the older 4KB layout — they fail to `dlopen`, the test runner crashes, and the gRPC server never comes up.

## What I take from this

1. **Maestro's correctness depends on a moving OS contract.** It runs as on-device instrumentation, so when Android changes its page size, ABI, or test runner host, the library has to ship a new build to keep working. My agent grounds on screenshot pixels and dispatches `adb shell input tap x y` — there's no native code on the device side, so the OS update doesn't touch it.
2. **The selector-coupling in the YAML is *the* whole interface.** Even with Maestro running, the contract is `tapOn: "Display"` and `assertVisible: "Brightness level"` — literal text. Rename "Display" to "Display & sound" (which Android has done before) and that line silently breaks.
3. **The two failure modes are independent.** "Maestro didn't run" (today's experience) and "Maestro ran but selector broke" (the more common case) are different fragility surfaces; a self-healing visual agent collapses both into one (the agent re-grounds on whatever the new label is).

## Files in this directory

- `settings_open_display.yaml` — the flow
- `emulator_info.txt` — env captured at run time
- `crash_logcat.txt` — relevant `adb logcat` excerpt
- (No screenshots — the run never reached an interactive step.)

## What I didn't do, and would if I had a free afternoon

- Boot a stock API 34 / 4KB-page emulator, get Maestro running, capture the "rename a button → flow breaks" receipt. The qualitative point doesn't change but the demo lands better with a screenshot.
- Mabl free trial: skipped because it required interactive signup and email verification I didn't want to do at 9am.
