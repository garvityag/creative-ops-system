// POST /api/chat
// Routes messages to the correct AI model based on agent config or explicit model choice
// Body: { agent_id, message, model?, history?: [{role, content}] }
// Returns: { response, model, tokens, cost, provider }

import Anthropic from '@anthropic-ai/sdk';
import OpenAI from 'openai';
import { getAgent } from '../lib/agentPrompts.js';
import { kv } from '@vercel/kv';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

// Model routing table
// format: "provider:model_id"
const MODEL_ROUTES = {
  // Claude (Anthropic direct)
  'claude-sonnet':              { provider: 'claude',      model_id: 'claude-sonnet-4-20250514' },
  'claude-sonnet-4-20250514':   { provider: 'claude',      model_id: 'claude-sonnet-4-20250514' },
  'claude-haiku':               { provider: 'claude',      model_id: 'claude-haiku-4-20250514'  },
  'claude-haiku-4-20250514':    { provider: 'claude',      model_id: 'claude-haiku-4-20250514'  },
  // OpenRouter
  'openhermes':                 { provider: 'openrouter',  model_id: 'teknium/openhermes-2.5-mistral-7b' },
  'openrouter/openhermes':      { provider: 'openrouter',  model_id: 'teknium/openhermes-2.5-mistral-7b' },
  'openrouter/llama3':          { provider: 'openrouter',  model_id: 'meta-llama/llama-3-8b-instruct' },
  // Groq
  'groq':                       { provider: 'groq',        model_id: 'mixtral-8x7b-32768' },
  'groq/mixtral':               { provider: 'groq',        model_id: 'mixtral-8x7b-32768' },
  'groq/llama3':                { provider: 'groq',        model_id: 'llama3-8b-8192' },
  // Ollama (local only — only works if caller is local)
  'ollama':                     { provider: 'ollama',      model_id: 'phi3:mini' },
  'ollama/phi3':                { provider: 'ollama',      model_id: 'phi3:mini' },
  'ollama/tinydolphin':         { provider: 'ollama',      model_id: 'tinydolphin' },
};

// Cost per 1k tokens (input/output)
const COSTS = {
  claude:     { in: 0.003,    out: 0.015 },
  openrouter: { in: 0.0002,   out: 0.0002 },
  groq:       { in: 0.00027,  out: 0.00027 },
  ollama:     { in: 0,        out: 0 },
};

function getCost(provider, tokens_in, tokens_out) {
  const r = COSTS[provider] || { in: 0, out: 0 };
  return (tokens_in * r.in + tokens_out * r.out) / 1000;
}

// ── Provider callers ─────────────────────────────────────────────────────────

async function callClaude(model_id, system_prompt, history, message) {
  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  const messages = [...history, { role: 'user', content: message }];
  const resp = await client.messages.create({
    model: model_id,
    max_tokens: 1536,
    system: system_prompt,
    messages,
  });
  return {
    text:       resp.content[0].text,
    tokens_in:  resp.usage.input_tokens,
    tokens_out: resp.usage.output_tokens,
  };
}

async function callOpenRouter(model_id, system_prompt, history, message) {
  const client = new OpenAI({
    apiKey:  process.env.OPENROUTER_API_KEY,
    baseURL: 'https://openrouter.ai/api/v1',
    defaultHeaders: {
      'HTTP-Referer': 'https://agents.garvityagnik.in',
      'X-Title': 'NEXUS AI System',
    },
  });
  const messages = [
    { role: 'system', content: system_prompt },
    ...history,
    { role: 'user', content: message },
  ];
  const resp = await client.chat.completions.create({ model: model_id, messages, max_tokens: 1536 });
  return {
    text:       resp.choices[0].message.content,
    tokens_in:  resp.usage?.prompt_tokens    || 0,
    tokens_out: resp.usage?.completion_tokens || 0,
  };
}

async function callGroq(model_id, system_prompt, history, message) {
  const client = new OpenAI({
    apiKey:  process.env.GROQ_API_KEY,
    baseURL: 'https://api.groq.com/openai/v1',
  });
  const messages = [
    { role: 'system', content: system_prompt },
    ...history,
    { role: 'user', content: message },
  ];
  const resp = await client.chat.completions.create({ model: model_id, messages, max_tokens: 1536 });
  return {
    text:       resp.choices[0].message.content,
    tokens_in:  resp.usage?.prompt_tokens    || 0,
    tokens_out: resp.usage?.completion_tokens || 0,
  };
}

async function callOllama(model_id, system_prompt, history, message) {
  const ollamaUrl = process.env.OLLAMA_URL || 'http://localhost:11434';
  const messages = [
    { role: 'system', content: system_prompt },
    ...history,
    { role: 'user', content: message },
  ];
  const resp = await fetch(`${ollamaUrl}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: model_id, messages, stream: false }),
  });
  if (!resp.ok) throw new Error(`Ollama error: ${resp.status}`);
  const data = await resp.json();
  return { text: data.message?.content || '', tokens_in: 0, tokens_out: 0 };
}

// ── Main handler ─────────────────────────────────────────────────────────────

export default async function handler(req, res) {
  Object.entries(corsHeaders).forEach(([k, v]) => res.setHeader(k, v));

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  try {
    const { agent_id = 'aria', message, model: modelOverride, history = [] } = req.body || {};

    if (!message) return res.status(400).json({ error: 'message is required' });

    const agent = getAgent(agent_id);
    if (!agent) return res.status(400).json({ error: `Unknown agent: ${agent_id}` });

    // Determine model
    const modelKey = modelOverride || agent.model || 'claude-sonnet-4-20250514';
    const route = MODEL_ROUTES[modelKey] || MODEL_ROUTES['claude-sonnet'];

    // Sanitize history to {role, content} pairs only
    const cleanHistory = (Array.isArray(history) ? history : [])
      .slice(-10) // last 10 turns
      .map(h => ({ role: h.role, content: h.content }))
      .filter(h => h.role && h.content);

    let result;
    const startTime = Date.now();

    switch (route.provider) {
      case 'claude':
        result = await callClaude(route.model_id, agent.system_prompt, cleanHistory, message);
        break;
      case 'openrouter':
        result = await callOpenRouter(route.model_id, agent.system_prompt, cleanHistory, message);
        break;
      case 'groq':
        result = await callGroq(route.model_id, agent.system_prompt, cleanHistory, message);
        break;
      case 'ollama':
        result = await callOllama(route.model_id, agent.system_prompt, cleanHistory, message);
        break;
      default:
        // Claude fallback
        result = await callClaude('claude-sonnet-4-20250514', agent.system_prompt, cleanHistory, message);
    }

    const elapsed = Date.now() - startTime;
    const cost = getCost(route.provider, result.tokens_in, result.tokens_out);

    // Log usage to KV (non-blocking)
    try {
      const today = new Date().toISOString().slice(0, 10);
      const entry = {
        timestamp:    new Date().toISOString(),
        agent:        agent_id,
        model:        route.model_id,
        provider:     route.provider,
        tokens_in:    result.tokens_in,
        tokens_out:   result.tokens_out,
        total_tokens: result.tokens_in + result.tokens_out,
        cost_usd:     cost,
        task_summary: message.slice(0, 80),
      };
      const dailyLog = (await kv.get(`usage:${today}`)) || [];
      dailyLog.unshift(entry);
      await kv.set(`usage:${today}`, dailyLog.slice(0, 200), { ex: 60 * 60 * 24 * 7 });

      const agentStats = (await kv.get(`agent_usage:${agent_id}`)) || { total_tokens: 0, total_cost: 0, tasks: 0 };
      agentStats.total_tokens += entry.total_tokens;
      agentStats.total_cost   += cost;
      agentStats.tasks        += 1;
      agentStats.last_model    = route.model_id;
      agentStats.last_used     = entry.timestamp;
      await kv.set(`agent_usage:${agent_id}`, agentStats);
    } catch (_) {}

    return res.status(200).json({
      response:   result.text,
      agent:      agent_id,
      agent_name: agent.name,
      model:      route.model_id,
      provider:   route.provider,
      tokens: {
        in:    result.tokens_in,
        out:   result.tokens_out,
        total: result.tokens_in + result.tokens_out,
      },
      cost_usd:   cost,
      elapsed_ms: elapsed,
    });

  } catch (err) {
    console.error('/api/chat error:', err);

    // Claude fallback if non-Claude provider fails
    if (!err.message?.includes('claude')) {
      try {
        const { agent_id = 'aria', message, history = [] } = req.body || {};
        const agent = getAgent(agent_id);
        const fallback = await callClaude(
          'claude-sonnet-4-20250514',
          agent?.system_prompt || 'You are a helpful assistant.',
          history.slice(-6).map(h => ({ role: h.role, content: h.content })),
          message
        );
        return res.status(200).json({
          response:   fallback.text,
          agent:      agent_id,
          model:      'claude-sonnet-4-20250514',
          provider:   'claude (fallback)',
          tokens:     { in: fallback.tokens_in, out: fallback.tokens_out, total: fallback.tokens_in + fallback.tokens_out },
          cost_usd:   getCost('claude', fallback.tokens_in, fallback.tokens_out),
          elapsed_ms: 0,
          fallback:   true,
        });
      } catch (fbErr) {
        return res.status(500).json({ error: 'All providers failed', detail: fbErr.message });
      }
    }

    return res.status(500).json({ error: 'Chat failed', detail: err.message });
  }
}
