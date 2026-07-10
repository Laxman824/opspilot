# Deployment Guide — Streamlit Community Cloud (free)

Target: a public URL like `https://<your-app>.streamlit.app` for the demo link.

## Prerequisites
- GitHub account, and this `opspilot/` folder pushed as a repo (public is simplest).
- Your Gemini API key from https://aistudio.google.com/apikey.

## Step 1 — Push the repo to GitHub

```bash
cd opspilot
git init
git add .
git commit -m "OpsPilot — agentic request triage POC"
# create an empty repo named opspilot on github.com first, then:
git remote add origin https://github.com/<your-username>/opspilot.git
git branch -M main
git push -u origin main
```

**Verify before pushing:** `git status` must NOT list `.env` or `opspilot.db`
(`.gitignore` already excludes them). If `.env` ever shows up, stop and fix — never
push the API key.

## Step 2 — Create the Streamlit Cloud app

1. Go to https://share.streamlit.io → sign in with GitHub → **Create app**.
2. Repository: `<your-username>/opspilot` · Branch: `main` · Main file path: `app.py`.
3. **Advanced settings** (before deploying):
   - Python version: **3.12** (or 3.11).
   - **Secrets** — paste exactly:
     ```toml
     GEMINI_API_KEY = "your-real-key-here"
     ```
4. Click **Deploy**. First build takes 2–5 minutes.

The app reads the key from `st.secrets` automatically when `.env` is absent
(`config.py` handles both), so no code change is needed.

## Step 3 — Verify the deployment

- Sidebar shows **"Gemini API connected"** ✅ (if it shows offline mode, the secret
  name is wrong — it must be exactly `GEMINI_API_KEY`).
- Process inbox sample #1 end-to-end; check the trace renders and the Dashboard tab
  fills in.
- Process #10 right after #1 to confirm the memory demo works on the deployed instance.

## Things to know about the free tier (not bugs)

| Behavior | Why / what to do |
|---|---|
| **App "sleeps" after ~12h without visitors** and shows a "wake up" button | Free-tier hibernation. **Open your URL 10 minutes before any demo/review** so evaluators never see the wake screen. |
| **SQLite data disappears** after a reboot/redeploy | Cloud storage is ephemeral. Fine for a demo (fresh slate each time); mention "Postgres in production" if asked. |
| A reviewer opening the app sees earlier cases from the same running instance | The DB persists while the instance is awake. If you want a clean slate before sharing, reboot the app (Manage app → Reboot). |
| Occasional slow first response | Cold model call + free-tier latency; subsequent runs are faster. |

## Troubleshooting

| Symptom | Fix |
|---|---|
| **ModuleNotFoundError** during build | A dependency is missing from `requirements.txt`. All four are listed (`streamlit`, `google-genai`, `pandas`, `python-dotenv`) — if you add imports, add them there too, commit, push; the app auto-redeploys. |
| **"Error installing requirements"** | Open "Manage app" → build logs. Most common cause: typo in `requirements.txt` or an unsupported Python version — set 3.12 in Advanced settings. |
| **Sidebar says offline fallback on cloud** | Secret missing/misnamed. Manage app → Settings → Secrets → key must be `GEMINI_API_KEY` in TOML format shown above. Save → app restarts automatically. |
| **429 / quota errors during demo** | Expected under heavy clicking — the resilience chain handles it (retries → flash-lite → offline mode with cases routed to human review). Slow down between runs; each request uses 3–4 calls of the ~10/min budget. Worst case the app keeps working in fallback mode — say so, it's a feature. |
| **`no such table: cases`** | Only possible if the DB file was deleted mid-session in an old build — already fixed (`init_db()` runs on every rerun). If ever seen: refresh the page. |
| **App URL 404s / build stuck** | Manage app → Reboot. If stuck again, Delete app and re-create (settings + secrets must be re-entered). |
| **Changed code, cloud didn't update** | Cloud deploys from GitHub, not your disk: `git add -A && git commit -m "update" && git push`. It redeploys automatically within ~1 min. |
| **Key leaked / needs rotation** | Delete the key in AI Studio → create a new one → update Streamlit Secrets (cloud) and `.env` (local). Never commit it. |

## Backup plan for the demo

Even with a live URL, record the ≤3-minute screen video (the brief accepts it) and keep
it in the submission. If the cloud app misbehaves during a live walkthrough, you switch
to the video without breaking stride: `streamlit run app.py` locally is the second
backup.
