// POST /api/task
// Submits a task to a specific agent, calls Claude API, returns pipeline plan
// Body: { task: string, context?: string, agent_id?: string }

import Anthropic from '@anthropic-ai/sdk';
import { getAgent, AGENTS } from '../lib/agentPrompts.js';
import { kv } from '@vercel/kv';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

export default async function handler(req, res) {
  Object.entries(corsHeaders).forEach(([k, v]) => res.setHeader(k, v));

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  try {
    const { task, context = '', agent_id = 'aria' } = req.body || {};

    if (!task) return res.status(400).json({ error: 'task is required' });

    const agent = getAgent(agent_id);
    if (!agent) return res.status(400).json({ error: `Unknown agent: ${agent_id}` });

    const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

    // Build user prompt
    const userPrompt = context
      ? `Context: ${context}\n\nTask: ${task}`
      : `Task: ${task}`;

    const startTime = Date.now();

    const message = await client.messages.create({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 2048,
      system: agent.system_prompt,
      messages: [{ role: 'user', content: userPrompt }],
    });

    const elapsed = Date.now() - startTime;
    const responseText = message.content[0].text;
    const tokensIn = message.usage.input_tokens;
    const tokensOut = message.usage.output_tokens;
    const costUsd = (tokensIn * 0.003 + tokensOut * 0.015) / 1000;

    // Log usage to KV
    const usageEntry = {
      timestamp: new Date().toISOString(),
      agent: agent_id,
      model: 'claude-sonnet-4-20250514',
      provider: 'anthropic',
      task_summary: task.slice(0, 100),
      tokens_in: tokensIn,
      tokens_out: tokensOut,
      total_tokens: tokensIn + tokensOut,
      cost_usd: costUsd,
      elapsed_ms: elapsed,
    };

    try {
      const today = new Date().toISOString().slice(0, 10);
      const usageKey = `usage:${today}`;
      const existing = (await kv.get(usageKey)) || [];
      existing.unshift(usageEntry);
      await kv.set(usageKey, existing.slice(0, 200), { ex: 60 * 60 * 24 * 7 }); // 7 days TTL

      // Update per-agent token totals
      const agentKey = `agent_usage:${agent_id}`;
      const agentStats = (await kv.get(agentKey)) || { total_tokens: 0, total_cost: 0, tasks: 0 };
      agentStats.total_tokens += tokensIn + tokensOut;
      agentStats.total_cost += costUsd;
      agentStats.tasks += 1;
      agentStats.last_model = 'claude-sonnet-4-20250514';
      agentStats.last_used = new Date().toISOString();
      await kv.set(agentKey, agentStats);

      // Update agent status to idle after task
      const agentStatusKey = `agent_status:${agent_id}`;
      const agentStatus = (await kv.get(agentStatusKey)) || {};
      agentStatus.status = 'idle';
      agentStatus.last_active = new Date().toISOString();
      agentStatus.tasks_completed_today = (agentStatus.tasks_completed_today || 0) + 1;
      agentStatus.last_model = 'claude-sonnet-4-20250514';
      await kv.set(agentStatusKey, agentStatus);
    } catch (kvErr) {
      console.error('KV write failed (non-fatal):', kvErr.message);
    }

    return res.status(200).json({
      success: true,
      agent: agent_id,
      agent_name: agent.name,
      response: responseText,
      model: 'claude-sonnet-4-20250514',
      tokens: { in: tokensIn, out: tokensOut, total: tokensIn + tokensOut },
      cost_usd: costUsd,
      elapsed_ms: elapsed,
    });

  } catch (err) {
    console.error('/api/task error:', err);
    return res.status(500).json({ error: 'Task failed', detail: err.message });
  }
}
