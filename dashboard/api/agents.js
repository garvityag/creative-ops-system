// GET  /api/agents → returns all 9 agents with status, model, token usage
// POST /api/agents → update a single agent's status
// Body for POST: { secret, agent_id, updates: { status, current_task, current_project, ... } }

import { kv } from '@vercel/kv';
import { AGENTS, AGENT_IDS } from '../lib/agentPrompts.js';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

// Static fallback data from status.json values
const STATUS_DEFAULTS = {
  aria:  { status: 'idle',    installed_in: ['claude-projects','claude-code','api'], uptime_percent: 99.8, tasks_completed_today: 0 },
  bryn:  { status: 'idle',    installed_in: ['claude-projects','api'],              uptime_percent: 100,  tasks_completed_today: 0 },
  idea:  { status: 'idle',    installed_in: ['claude-projects'],                    uptime_percent: 99.1, tasks_completed_today: 0 },
  desi:  { status: 'idle',    installed_in: ['claude-projects'],                    uptime_percent: 97.2, tasks_completed_today: 0 },
  copy:  { status: 'idle',    installed_in: ['claude-projects'],                    uptime_percent: 98.9, tasks_completed_today: 0 },
  mova:  { status: 'offline', installed_in: [],                                     uptime_percent: 98.5, tasks_completed_today: 0 },
  soci:  { status: 'offline', installed_in: [],                                     uptime_percent: 97.8, tasks_completed_today: 0 },
  nova:  { status: 'idle',    installed_in: ['claude-projects','claude-code'],      uptime_percent: 100,  tasks_completed_today: 0 },
  arch:  { status: 'idle',    installed_in: ['claude-code'],                        uptime_percent: 99.3, tasks_completed_today: 0 },
};

async function buildAgentPayload() {
  const result = {};

  for (const id of AGENT_IDS) {
    const meta = AGENTS[id];
    const defaults = STATUS_DEFAULTS[id] || {};

    // Try KV for live status
    let liveStatus = {};
    let usageStats = {};
    try {
      liveStatus = (await kv.get(`agent_status:${id}`)) || {};
      usageStats = (await kv.get(`agent_usage:${id}`)) || {};
    } catch (_) {}

    result[id] = {
      // Identity (from YAML)
      name:       meta.name,
      full_name:  meta.full_name,
      role:       meta.role,
      emoji:      meta.emoji,
      color:      meta.color,
      model:      meta.model,
      // Status (KV > defaults)
      status:                liveStatus.status                ?? defaults.status,
      current_task:          liveStatus.current_task          ?? null,
      current_project:       liveStatus.current_project       ?? null,
      installed_in:          liveStatus.installed_in          ?? defaults.installed_in,
      uptime_percent:        liveStatus.uptime_percent        ?? defaults.uptime_percent,
      tasks_completed_today: liveStatus.tasks_completed_today ?? defaults.tasks_completed_today,
      last_active:           liveStatus.last_active           ?? null,
      // Token/cost from usage tracker
      last_model:            usageStats.last_model            ?? meta.model,
      total_tokens:          usageStats.total_tokens          ?? 0,
      total_cost:            usageStats.total_cost            ?? 0,
      tasks_total:           usageStats.tasks                 ?? 0,
    };
  }

  return result;
}

export default async function handler(req, res) {
  Object.entries(corsHeaders).forEach(([k, v]) => res.setHeader(k, v));

  if (req.method === 'OPTIONS') return res.status(200).end();

  // ── GET ──────────────────────────────────────────────────────────────────────
  if (req.method === 'GET') {
    try {
      const agents = await buildAgentPayload();
      return res.status(200).json({
        agents,
        system: {
          owner: 'Garvit Yagnik',
          version: '2.0.0',
          last_updated: new Date().toISOString(),
        },
        pipeline: (await kv.get('pipeline:current').catch(() => null)) || { active_project: null, steps: [] },
        nova_alerts: (await kv.get('nova:alerts').catch(() => null)) || [],
      });
    } catch (err) {
      console.error('/api/agents GET error:', err);
      return res.status(500).json({ error: 'Failed to load agents', detail: err.message });
    }
  }

  // ── POST ─────────────────────────────────────────────────────────────────────
  if (req.method === 'POST') {
    try {
      const { secret, agent_id, updates } = req.body || {};

      if (secret !== process.env.DASHBOARD_SECRET) {
        return res.status(401).json({ error: 'Unauthorized' });
      }
      if (!agent_id || !AGENTS[agent_id]) {
        return res.status(400).json({ error: `Unknown agent: ${agent_id}` });
      }
      if (!updates || typeof updates !== 'object') {
        return res.status(400).json({ error: 'updates object required' });
      }

      const key = `agent_status:${agent_id}`;
      const current = (await kv.get(key)) || {};
      const merged = {
        ...current,
        ...updates,
        last_active: new Date().toISOString(),
      };
      await kv.set(key, merged);

      return res.status(200).json({ success: true, agent: agent_id, state: merged });
    } catch (err) {
      console.error('/api/agents POST error:', err);
      return res.status(500).json({ error: 'Update failed', detail: err.message });
    }
  }

  return res.status(405).json({ error: 'Method not allowed' });
}
