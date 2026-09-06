# Dhan Trader — Android app (WebView wrapper)

A thin native Android shell that loads the existing Dhan-Claude Trader web UI
(`web/` — FastAPI + htmx on `uvicorn`, port 8501) inside a full-screen WebView.
It reuses the entire web frontend; the app adds only: a first-run screen to set
the server URL, pull-to-refresh, back-button navigation, and a Home/Refresh menu.

## How it connects

The phone must be able to reach the PC running the trading server. Two ways:

1. **Same Wi-Fi (LAN):** start the server bound to your LAN, then enter the PC's
   IP in the app, e.g. `http://192.168.1.20:8501`.
   - Run it with: `python -m uvicorn web.server:app --host 0.0.0.0 --port 8501`
     (the shipped `run_web.bat` binds `127.0.0.1`, which the phone can't reach —
     use `0.0.0.0` for phone access, and allow port 8501 through the PC firewall).
2. **Anywhere (tunnel):** expose the server with a Cloudflare Tunnel (as the
   mobile-API spec intends) and enter the `https://…` URL in the app.

The app lands on `/live`. Cleartext HTTP is allowed for LAN use.

## Building the APK

### Option A — CI (no local toolchain)
Push to GitHub; the workflow `.github/workflows/android.yml` builds a debug APK on
a runner and uploads it under the run's **Artifacts** (`dhan-trader-debug-apk`).
You can also trigger it manually from the **Actions** tab (`workflow_dispatch`).

### Option B — Android Studio
Open the `android-app/` folder in Android Studio (Giraffe+). It will download the
Gradle wrapper and SDK, then **Build > Build APK(s)**.

### Option C — Command line
Requires JDK 17 + Android SDK. From `android-app/`:

```
gradle wrapper --gradle-version 8.7   # first time only, creates ./gradlew
./gradlew :app:assembleDebug          # -> app/build/outputs/apk/debug/app-debug.apk
```

## Notes

- `minSdk` 26, `targetSdk`/`compileSdk` 34, package `com.dhanclaude.trader`.
- The **release** APK is unsigned as configured here; the CI builds the **debug**
  APK, which installs fine for personal use. To publish, add a signing config.
- This wrapper is only as secure as the server it points at — keep the server on
  your LAN or behind an authenticated tunnel; never expose it open to the internet.
