// api/status.js — Vercel serverless function
// Fetches status.json from your GitHub Gist and returns it
// Also handles CORS so dashboard can read it

export default async function handler(req, res) {
  // Allow your domain only
  res.setHeader('Access-Control-Allow-Origin', 'https://agents.garvityagnik.in');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  // ── GET: fetch current status from GitHub Gist ──────────────────────────
  if (req.method === 'GET') {
    try {
      const GIST_ID = process.env.GIST_ID; // set in Vercel env vars
      const GITHUB_TOKEN = process.env.GITHUB_TOKEN;

      const response = await fetch(`https://api.github.com/gists/${GIST_ID}`, {
        headers: {
          'Authorization': `token ${GITHUB_TOKEN}`,
          'Accept': 'application/vnd.github.v3+json',
        }
      });

      if (!response.ok) throw new Error('Gist fetch failed');

      const gist = await response.json();
      const statusJson = JSON.parse(gist.files['status.json'].content);

      // Inject fetch timestamp
      statusJson._fetched_at = new Date().toISOString();

      return res.status(200).json(statusJson);
    } catch (err) {
      return res.status(500).json({ error: 'Failed to fetch status', detail: err.message });
    }
  }

  // ── POST: update agent status ────────────────────────────────────────────
  if (req.method === 'POST') {
    try {
      const GIST_ID = process.env.GIST_ID;
      const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
      const DASHBOARD_SECRET = process.env.DASHBOARD_SECRET;

      // Simple auth check
      const { secret, agent_id, updates } = req.body;
      if (secret !== DASHBOARD_SECRET) {
        return res.status(401).json({ error: 'Unauthorized' });
      }

      // Fetch current status
      const getRes = await fetch(`https://api.github.com/gists/${GIST_ID}`, {
        headers: { 'Authorization': `token ${GITHUB_TOKEN}`, 'Accept': 'application/vnd.github.v3+json' }
      });
      const gist = await getRes.json();
      const current = JSON.parse(gist.files['status.json'].content);

      // Apply updates
      if (agent_id && current.agents[agent_id]) {
        Object.assign(current.agents[agent_id], updates);
        current.agents[agent_id].last_active = new Date().toISOString();
      }
      current.system.last_updated = new Date().toISOString();

      // Push back to Gist
      await fetch(`https://api.github.com/gists/${GIST_ID}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `token ${GITHUB_TOKEN}`,
          'Accept': 'application/vnd.github.v3+json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          files: { 'status.json': { content: JSON.stringify(current, null, 2) } }
        })
      });

      return res.status(200).json({ success: true, agent: agent_id, updates });
    } catch (err) {
      return res.status(500).json({ error: 'Update failed', detail: err.message });
    }
  }

  return res.status(405).json({ error: 'Method not allowed' });
}
