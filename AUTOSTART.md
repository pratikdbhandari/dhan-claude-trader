# Auto-Start Guide (Windows)

How to launch Dhan-Claude Trader with one double-click, and optionally start it
automatically at login / before market open.

> Note: this automates **launching the app**. It does NOT auto-login to Dhan — Dhan's
> personal API has no consumer OAuth. You enter the Dhan access token once on the
> **Settings** page (it persists in `~/.dhan_claude_trader/settings.local.json` and
> lasts ~30 days), and re-paste it when it expires.

---

## Option 1 — Double-click launcher (simplest)

1. In the project folder, double-click **`run_app.bat`**.
2. A terminal opens, Streamlit starts, and your browser opens `http://localhost:8501`.
3. Keep the terminal window open while trading; close it to stop the app.

---

## Option 2 — Auto-start at Windows login (Task Scheduler)

1. Press `Win + R`, type `taskschd.msc`, Enter — Task Scheduler opens.
2. **Create Basic Task** → name it `Dhan-Claude Trader`.
3. Trigger: **When I log on** (or **Daily** at e.g. 09:00 for pre-market).
4. Action: **Start a program** → Program/script: browse to **`run_app.bat`** in the
   project folder.
5. Finish. The app now launches automatically on that trigger.

To run it slightly before market open, use a **Daily** trigger at **09:00 IST** on weekdays.

---

## Option 3 — Startup folder (launch on every login)

1. Press `Win + R`, type `shell:startup`, Enter.
2. Right-click `run_app.bat` → **Create shortcut**, move the shortcut into the Startup folder.
3. The app launches each time you log in.

---

## First-run checklist (installed PC, non-developer)

1. Double-click `run_app.bat` → app opens.
2. Go to the **⚙️ Settings** page (left sidebar).
3. Click **Get Dhan Token**, generate it on Dhan, paste **Client ID + Access Token**.
4. (Optional) paste AI keys (Groq/Cerebras free tiers work well); set Signal source.
5. Click **💾 Save settings**, then **🔌 Test All connections** → all green = ready.
6. Keep **Trade mode = PAPER** for your 15-day paper run.

Stopping the app: close the terminal window (or `Ctrl+C` in it).
