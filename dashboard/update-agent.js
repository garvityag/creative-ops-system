#!/usr/bin/env node
// update-agent.js — run from Claude Code to update agent status
// Usage: node update-agent.js <agent_id> <status> [task] [project]
//
// Examples:
//   node update-agent.js desi busy "Building brand identity pack" "Fintech Rebrand"
//   node update-agent.js desi idle
//   node update-agent.js mova offline

const DASHBOARD_URL = 'https://agents.garvityagnik.in/api/status';
const SECRET = process.env.DASHBOARD_SECRET || 'your-secret-here';

const [,, agentId, status, task, project] = process.argv;

if (!agentId || !status) {
  console.log('Usage: node update-agent.js <agent_id> <status> [task] [project]');
  console.log('Status options: idle | busy | waiting | offline | active');
  process.exit(1);
}

const updates = {
  status,
  current_task: task || null,
  current_project: project || null,
};

fetch(DASHBOARD_URL, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ secret: SECRET, agent_id: agentId, updates })
})
  .then(r => r.json())
  .then(data => {
    if (data.success) {
      console.log(`✅ ${agentId.toUpperCase()} → ${status}${task ? ` (${task})` : ''}`);
    } else {
      console.error('❌ Update failed:', data.error);
    }
  })
  .catch(err => console.error('❌ Network error:', err.message));
