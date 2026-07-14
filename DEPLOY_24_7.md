# Running the API 24/7 (laptop off)

Keep signals generating and phone push notifications alive around the clock by
hosting the FastAPI layer (`api/`) on an always-on machine. The desktop Streamlit
app is unaffected — this is a separate, headless process.

> **What this does / doesn't do.** It runs the background scheduler (prepares +
> risk-checks signals on a timer) and serves the API your phone talks to. It still
> does **not** auto-place orders — every trade needs your confirm from the phone
> (`POST /signals/{id}/confirm`, two-step preserved). The kill-switch and risk gate
> still apply.

---

## 0. One-time external setup (you must do these — they need your login)

1. **Supabase** (free) — for login/auth.
   - Create a project at supabase.com. In *Settings → API* copy `Project URL`
     (`SUPABASE_URL`), the `service_role` key (`SUPABASE_SERVICE_ROLE_KEY`), and the
     JWT secret (`SUPABASE_JWT_SECRET`).
   - Create one table `push_tokens (user_id text primary key, token text, updated_at timestamptz default now())`.
   - Create your single login user under *Authentication → Users*.
2. **Firebase** (free) — for push notifications.
   - Create a project, add Cloud Messaging, download a service-account JSON.
     Set `FCM_PROJECT_ID` and `FCM_SERVICE_ACCOUNT_JSON_PATH` (path to that JSON on
     the host).
3. **Dhan token** — the access token lasts ~30 days. Re-paste it in the app's
   Settings (or the host's `settings.local.json`) when it expires; unattended running
   will start failing on expiry until you do.

Put all secrets in the host's environment or a `.env` next to the code (never commit).

---

## Host option A — Oracle Cloud Free Tier (₹0/month, always-on)

Genuinely free forever ARM VM. Ubuntu.

```bash
# on the VM
sudo apt update && sudo apt install -y python3-pip git
git clone <your-repo> dhan && cd dhan
pip install -r requirements.txt
# put your secrets in /etc/dhan.env (SUPABASE_*, FCM_*, DHAN_*, SIGNAL_SOURCE, TRADE_MODE=PAPER)
```

Create a systemd service so it runs 24/7 and restarts on crash:

```ini
# /etc/systemd/system/dhan-api.service
[Unit]
Description=Dhan-Claude Trader API
After=network-online.target

[Service]
WorkingDirectory=/home/ubuntu/dhan
EnvironmentFile=/etc/dhan.env
ExecStart=/usr/bin/python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
User=ubuntu

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now dhan-api
sudo systemctl status dhan-api           # should be active (running)
curl http://127.0.0.1:8000/health        # {"status":"ok"}
```

Note it binds `127.0.0.1` only — the internet reaches it **only** through the
authenticated tunnel below, never directly.

---

## Host option B — cheap VPS (~₹350–500/month)

Identical to option A (same systemd unit) on Lightsail / DigitalOcean / Hetzner /
any Indian VPS. Most reliable, least fiddly.

---

## Host option C — Raspberry Pi / spare machine at home

Same systemd unit on the Pi. Your Dhan/Supabase keys never leave your house.
Depends on your home internet + power staying up.

---

## Expose it to your phone — securely (all options)

Use a free **Cloudflare Tunnel** + **Cloudflare Access** (email-gated login). This
gives a stable HTTPS URL and puts a login wall in front so your broker-credentialed
API is never open to the internet.

```bash
# install cloudflared on the host, then:
cloudflared tunnel login
cloudflared tunnel create dhan
# route a hostname to the local API:
cloudflared tunnel route dns dhan api.yourdomain.com
# config ~/.cloudflared/config.yml:
#   tunnel: <tunnel-id>
#   credentials-file: /home/ubuntu/.cloudflared/<tunnel-id>.json
#   ingress:
#     - hostname: api.yourdomain.com
#       service: http://127.0.0.1:8000
#     - service: http_status:404
cloudflared tunnel run dhan               # or a second systemd service
```

Then in the Cloudflare Zero Trust dashboard: add an **Access application** for
`api.yourdomain.com` with an email policy limited to your own email. Now every
request must pass Cloudflare's login before it reaches the API — belt on top of the
API's own JWT auth.

**Never skip this.** The API holds your Dhan access token; do not expose port 8000
to the internet directly.

---

## Alternative: Docker

```dockerfile
# Dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
```bash
docker build -t dhan-api .
docker run -d --restart unless-stopped --env-file /etc/dhan.env -p 127.0.0.1:8000:8000 dhan-api
```

---

## Verify it's alive

- `curl https://api.yourdomain.com/health` (through Access) → `{"status":"ok"}`
- `journalctl -u dhan-api -f` (systemd) shows scheduler ticks every
  `SIGNAL_COOLDOWN_SECONDS`.
- Keep `TRADE_MODE=PAPER` until you've completed the Go-Live gates.

---

## Cost summary

| Option | Ongoing | Notes |
|--------|---------|-------|
| Oracle Free Tier | ₹0/mo | free forever; occasional idle-reclaim risk |
| Cheap VPS | ~₹350–500/mo | most reliable, set-and-forget |
| Raspberry Pi (home) | ~₹4k once + ~₹30/mo power | keys stay home; needs home uptime |

Cloudflare Tunnel + Access are free on all three.
