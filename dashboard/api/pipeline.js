// GET  /api/pipeline → current active pipeline status
// POST /api/pipeline → update pipeline step
// Body for POST: { secret, action: 'start'|'step'|'complete'|'reset', ...data }

import { kv } from '@vercel/kv';
import { AGENTS } from '../lib/agentPrompts.js';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

// Standard pipeline step template per agent
function buildStep(agent_id, state = 'pending') {
  const a = AGENTS[agent_id];
  if (!a) return null;
  return {
    agent_id,
    name:  a.name,
    emoji: a.emoji,
    color: a.color,
    state, // pending | current | done | skipped
    started_at:   null,
    completed_at: null,
    output_summary: null,
  };
}

// Full pipeline for a full creative workflow
const PIPELINE_TEMPLATES = {
  full:    ['bryn', 'idea', 'desi', 'copy', 'mova', 'soci'],
  design:  ['bryn', 'idea', 'desi'],
  content: ['bryn', 'copy', 'soci'],
  motion:  ['bryn', 'idea', 'desi', 'mova'],
  social:  ['copy', 'soci'],
};

export default async function handler(req, res) {
  Object.entries(corsHeaders).forEach(([k, v]) => res.setHeader(k, v));

  if (req.method === 'OPTIONS') return res.status(200).end();

  const KV_KEY = 'pipeline:current';

  // ── GET ──────────────────────────────────────────────────────────────────────
  if (req.method === 'GET') {
    try {
      const pipeline = (await kv.get(KV_KEY)) || { active_project: null, steps: [] };
      return res.status(200).json(pipeline);
    } catch (err) {
      return res.status(500).json({ error: 'Failed to load pipeline', detail: err.message });
    }
  }

  // ── POST ─────────────────────────────────────────────────────────────────────
  if (req.method === 'POST') {
    try {
      const { secret, action, ...data } = req.body || {};

      if (secret !== process.env.DASHBOARD_SECRET) {
        return res.status(401).json({ error: 'Unauthorized' });
      }

      let pipeline = (await kv.get(KV_KEY)) || { active_project: null, steps: [] };

      switch (action) {

        // Start a new pipeline
        case 'start': {
          const { project_name, template = 'full', custom_agents } = data;
          const agentList = custom_agents || PIPELINE_TEMPLATES[template] || PIPELINE_TEMPLATES.full;
          pipeline = {
            active_project: project_name || 'Untitled Project',
            template,
            started_at: new Date().toISOString(),
            steps: agentList
              .map((id, i) => buildStep(id, i === 0 ? 'current' : 'pending'))
              .filter(Boolean),
          };
          break;
        }

        // Mark current step done, advance to next
        case 'step': {
          const { output_summary } = data;
          const ci = pipeline.steps?.findIndex(s => s.state === 'current');
          if (ci >= 0) {
            pipeline.steps[ci].state = 'done';
            pipeline.steps[ci].completed_at = new Date().toISOString();
            if (output_summary) pipeline.steps[ci].output_summary = output_summary;
          }
          const ni = pipeline.steps?.findIndex((s, i) => i > ci && s.state === 'pending');
          if (ni >= 0) {
            pipeline.steps[ni].state = 'current';
            pipeline.steps[ni].started_at = new Date().toISOString();

            // Also update that agent's status in KV
            try {
              const agentId = pipeline.steps[ni].agent_id;
              const agentKey = `agent_status:${agentId}`;
              const agentStatus = (await kv.get(agentKey)) || {};
              agentStatus.status = 'busy';
              agentStatus.current_project = pipeline.active_project;
              agentStatus.last_active = new Date().toISOString();
              await kv.set(agentKey, agentStatus);
            } catch (_) {}
          }
          break;
        }

        // Update a specific step directly
        case 'update_step': {
          const { agent_id, updates: stepUpdates } = data;
          const idx = pipeline.steps?.findIndex(s => s.agent_id === agent_id);
          if (idx >= 0) Object.assign(pipeline.steps[idx], stepUpdates);
          break;
        }

        // Mark pipeline complete
        case 'complete': {
          pipeline.steps?.forEach(s => { if (s.state !== 'done') s.state = 'done'; });
          pipeline.completed_at = new Date().toISOString();
          pipeline.active = false;
          break;
        }

        // Reset / clear pipeline
        case 'reset': {
          pipeline = { active_project: null, steps: [] };
          break;
        }

        default:
          return res.status(400).json({ error: `Unknown action: ${action}` });
      }

      await kv.set(KV_KEY, pipeline);
      return res.status(200).json({ success: true, pipeline });

    } catch (err) {
      console.error('/api/pipeline POST error:', err);
      return res.status(500).json({ error: 'Pipeline update failed', detail: err.message });
    }
  }

  return res.status(405).json({ error: 'Method not allowed' });
}
