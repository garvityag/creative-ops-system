# Dashboard Deployment Guide

## Architecture

```
agents.garvityagnik.in
    (Vercel — /dashboard folder)
           ↕
    GitHub Gist (status.json)
           ↑
    You update via:
    1. Dashboard UI click
    2. node update-agent.js (Claude Code)
    3. POST /api/status (API/n8n/Make)
```

---

## Step 1 — GitHub Gist

1. Go to https://gist.github.com
2. Filename: `status.json`
3. Paste contents of `/status.json` from repo root
4. Create as **secret gist**
5. Copy Gist ID from URL: `gist.github.com/username/THIS_IS_IT`

---

## Step 2 — GitHub Token

1. https://github.com/settings/tokens → New classic token
2. Scope: only `gist`
3. Copy token immediately

---

## Step 3 — Connect Repo to Vercel

1. Push this repo to GitHub
2. Go to https://vercel.com → New Project
3. Import your GitHub repo
4. **Important:** Set Root Directory to `dashboard`
5. Deploy

---

## Step 4 — Environment Variables

In Vercel → Project → Settings → Environment Variables:

| Key | Value |
|-----|-------|
| `GIST_ID` | Gist ID from Step 1 |
| `GITHUB_TOKEN` | Token from Step 2 |
| `DASHBOARD_SECRET` | Any secret (e.g. `garv-ops-2026`) |

Redeploy after adding vars.

---

## Step 5 — Custom Domain

Vercel → Project → Settings → Domains:
1. Add `agents.garvityagnik.in`
2. Copy the CNAME record shown
3. Add it to your domain registrar's DNS settings
4. Wait 5–10 mins

---

## Step 6 — Update Agent Status

### Dashboard UI
Click agent → Quick Update buttons in right panel
(First time: enter your DASHBOARD_SECRET when prompted)

### Claude Code / Terminal
```bash
export DASHBOARD_SECRET=garv-ops-2026
node dashboard/update-agent.js desi busy "Building brand kit" "Fintech Rebrand"
node dashboard/update-agent.js desi idle
node dashboard/update-agent.js mova offline
```

### API (n8n / Make.com / custom)
```
POST https://agents.garvityagnik.in/api/status
Content-Type: application/json

{
  "secret": "garv-ops-2026",
  "agent_id": "desi",
  "updates": {
    "status": "busy",
    "current_task": "Building brand kit",
    "current_project": "Fintech Rebrand"
  }
}
```

---

## Update installed_in

Edit `status.json` directly in your GitHub Gist.
Under each agent, set the `installed_in` array:

```json
"desi": {
  "installed_in": ["claude-projects", "figma", "api"]
}
```

Options: `claude-projects`, `claude-code`, `api`, `n8n`, `make`
