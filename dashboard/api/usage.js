// GET  /api/usage → token usage, cost per agent, daily/monthly totals
// POST /api/usage → log a new usage entry
// Body for POST: { secret, agent, model, provider, tokens_in, tokens_out, cost_usd, task_summary }

import { kv } from '@vercel/kv';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

// Cost per 1k tokens (input/output) for known models
const MODEL_COSTS = {
  'claude-sonnet-4-20250514': { in: 0.003, out: 0.015 },
  'claude-haiku-4-20250514':  { in: 0.00025, out: 0.00125 },
  'openrouter/openhermes':    { in: 0.0002, out: 0.0002 },
  'groq/mixtral':             { in: 0.00027, out: 0.00027 },
};

function calcCost(model, tokens_in, tokens_out) {
  const rates = MODEL_COSTS[model] || { in: 0, out: 0 };
  return (tokens_in * rates.in + tokens_out * rates.out) / 1000;
}

async function getDailyTotals(date) {
  const key = `usage:${date}`;
  const entries = (await kv.get(key)) || [];
  return entries.reduce(
    (acc, e) => {
      acc.tokens += e.total_tokens || 0;
      acc.cost += e.cost_usd || 0;
      acc.calls += 1;
      return acc;
    },
    { tokens: 0, cost: 0, calls: 0, entries }
  );
}

async function getAgentBreakdown() {
  const agentIds = ['aria','bryn','idea','desi','copy','mova','soci','nova','arch'];
  const breakdown = {};
  for (const id of agentIds) {
    const stats = (await kv.get(`agent_usage:${id}`)) || {};
    breakdown[id] = {
      total_tokens: stats.total_tokens || 0,
      total_cost:   stats.total_cost   || 0,
      tasks:        stats.tasks        || 0,
      last_model:   stats.last_model   || null,
      last_used:    stats.last_used    || null,
    };
  }
  return breakdown;
}

export default async function handler(req, res) {
  Object.entries(corsHeaders).forEach(([k, v]) => res.setHeader(k, v));

  if (req.method === 'OPTIONS') return res.status(200).end();

  // ── GET ──────────────────────────────────────────────────────────────────────
  if (req.method === 'GET') {
    try {
      const today = new Date().toISOString().slice(0, 10);
      const monthPrefix = today.slice(0, 7);

      // Build last 7 days
      const dailyHistory = [];
      for (let i = 0; i < 7; i++) {
        const d = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
        const totals = await getDailyTotals(d);
        dailyHistory.push({ date: d, ...totals, entries: undefined });
      }

      // Today detail
      const todayData = await getDailyTotals(today);

      // Monthly sum from daily history (7 days only, extend later)
      const monthlyCost = dailyHistory.reduce((s, d) => s + d.cost, 0);
      const monthlyTokens = dailyHistory.reduce((s, d) => s + d.tokens, 0);

      // Per-agent breakdown
      const by_agent = await getAgentBreakdown();

      return res.status(200).json({
        today: {
          date:   today,
          tokens: todayData.tokens,
          cost:   todayData.cost,
          calls:  todayData.calls,
          log:    todayData.entries.slice(0, 50),
        },
        monthly: {
          month:  monthPrefix,
          tokens: monthlyTokens,
          cost:   monthlyCost,
        },
        by_agent,
        daily_history: dailyHistory,
      });
    } catch (err) {
      console.error('/api/usage GET error:', err);
      return res.status(500).json({ error: 'Failed to load usage', detail: err.message });
    }
  }

  // ── POST ─────────────────────────────────────────────────────────────────────
  if (req.method === 'POST') {
    try {
      const {
        secret,
        agent = 'aria',
        model = 'claude-sonnet-4-20250514',
        provider = 'anthropic',
        tokens_in = 0,
        tokens_out = 0,
        cost_usd,
        task_summary = '',
      } = req.body || {};

      if (secret !== process.env.DASHBOARD_SECRET) {
        return res.status(401).json({ error: 'Unauthorized' });
      }

      const actualCost = cost_usd ?? calcCost(model, tokens_in, tokens_out);
      const entry = {
        timestamp:    new Date().toISOString(),
        agent,
        model,
        provider,
        tokens_in,
        tokens_out,
        total_tokens: tokens_in + tokens_out,
        cost_usd:     actualCost,
        task_summary: task_summary.slice(0, 120),
      };

      // Append to daily log
      const today = new Date().toISOString().slice(0, 10);
      const dailyKey = `usage:${today}`;
      const daily = (await kv.get(dailyKey)) || [];
      daily.unshift(entry);
      await kv.set(dailyKey, daily.slice(0, 200), { ex: 60 * 60 * 24 * 7 });

      // Update per-agent totals
      const agentKey = `agent_usage:${agent}`;
      const agentStats = (await kv.get(agentKey)) || { total_tokens: 0, total_cost: 0, tasks: 0 };
      agentStats.total_tokens += entry.total_tokens;
      agentStats.total_cost   += actualCost;
      agentStats.tasks        += 1;
      agentStats.last_model    = model;
      agentStats.last_used     = entry.timestamp;
      await kv.set(agentKey, agentStats);

      return res.status(200).json({ success: true, entry });
    } catch (err) {
      console.error('/api/usage POST error:', err);
      return res.status(500).json({ error: 'Log failed', detail: err.message });
    }
  }

  return res.status(405).json({ error: 'Method not allowed' });
}
