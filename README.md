# 🎨 Creative Ops System — agents.garvityagnik.in

> A self-expanding multi-agent system for a solo creative professional.  
> 9 AI agents + a live tracking dashboard deployed at [agents.garvityagnik.in](https://agents.garvityagnik.in)

---

## Repo Structure

```
creative-ops-system/
├── agents/                  ← Agent YAML instruction files
│   ├── aria.yaml
│   ├── bryn.yaml
│   ├── idea.yaml
│   ├── desi.yaml
│   ├── mova.yaml
│   ├── copy.yaml
│   ├── soci.yaml
│   ├── arch.yaml
│   └── nova.yaml
│
├── dashboard/               ← Vercel project (agents.garvityagnik.in)
│   ├── api/
│   │   └── status.js        ← Serverless API (reads/writes GitHub Gist)
│   ├── public/
│   │   └── index.html       ← Live dashboard UI
│   ├── vercel.json
│   └── update-agent.js      ← CLI script for Claude Code
│
├── system.yaml              ← Master agent config
├── status.json              ← Source of truth (also synced to GitHub Gist)
└── README.md
```

---

## Agent Roster

| Agent | Role | Priority |
|-------|------|----------|
| **ARIA** | Master Orchestrator | Always Active |
| **DESI** | Design & Asset Production | #1 |
| **IDEA** | Creative Concept & Ideation | #2 |
| **MOVA** | Motion & Video Production | #3 |
| **BRYN** | Brief Analyst & Strategist | #4 |
| **COPY** | Content & Copywriting | #5 |
| **SOCI** | Social Media & Campaigns | #6 |
| **NOVA** | HR & Auto-Expansion | #7 ✳ |
| **ARCH** | Workflow Architect | #8 |

---

## Quick Start

### Use agents in Claude Projects
1. Open any `.yaml` file in `/agents/`
2. Copy the `system_prompt:` section
3. Paste into a Claude Project's instructions

### Use agents via API
```python
import yaml, anthropic

with open('agents/desi.yaml') as f:
    agent = yaml.safe_load(f)

client = anthropic.Anthropic()
response = client.messages.create(
    model=agent['model'],
    max_tokens=4096,
    system=agent['system_prompt'],
    messages=[{"role": "user", "content": "your task here"}]
)
```

### Update agent status (Claude Code)
```bash
export DASHBOARD_SECRET=your-secret
node dashboard/update-agent.js desi busy "Building brand kit" "Fintech Rebrand"
node dashboard/update-agent.js desi idle
```

---

## Dashboard Deployment

See [dashboard/SETUP.md](dashboard/SETUP.md) for full Vercel deployment guide.

**Environment variables needed in Vercel:**
- `GIST_ID` — GitHub Gist ID for status.json
- `GITHUB_TOKEN` — GitHub token with gist scope
- `DASHBOARD_SECRET` — Your private update secret

---

## Status Values

| Status | Meaning |
|--------|---------|
| `active` | Running a pipeline step |
| `busy` | Working on a task |
| `waiting` | Needs your approval |
| `idle` | Online, nothing to do (shows funny message) |
| `offline` | Not installed in any platform |
