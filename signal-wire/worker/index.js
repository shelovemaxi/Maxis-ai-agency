const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...cors, 'Content-Type': 'application/json' }
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method === 'GET' && (url.pathname === '/' || url.pathname === '/health')) {
      return json({ ok: true, service: 'signal-wire-ai', configured: Boolean(env.AI || env.GEMINI_API_KEY), provider: env.AI ? 'cloudflare-ai' : 'gemini' });
    }
    if (request.method !== 'POST' || (url.pathname !== '/' && url.pathname !== '/api/chat')) return json({ error: 'Use POST /api/chat.' }, 404);
    if (!env.AI && !env.GEMINI_API_KEY) return json({ error: 'No AI provider is configured.' }, 503);
    try {
      const body = await request.json();
      const message = String(body.message || '').trim().slice(0, 2000);
      const events = Array.isArray(body.events) ? body.events.slice(0, 30) : [];
      if (!message) return json({ error: 'Message is required.' }, 400);
      const prompt = `You are Signal Wire AI, an evidence-aware economic and market intelligence analyst. Answer using ONLY the dashboard evidence below. Never invent facts, sources, or certainty. Distinguish reported facts from interpretation. Treat an event as independently corroborated only when verification is verified and sources include at least two distinct domains. If evidence is insufficient, say so. Do not give personalized financial advice or buy/sell instructions. Be concise but useful.\n\nDASHBOARD EVIDENCE:\n${JSON.stringify(events)}\n\nUSER QUESTION:\n${message}`;
      let reply = '';
      if (env.AI) {
        const out = await env.AI.run('@cf/meta/llama-3.1-8b-instruct-fp8-fast', {
          messages: [
            { role: 'system', content: 'You are Signal Wire AI. Follow the evidence-only analyst rules in the user prompt.' },
            { role: 'user', content: prompt }
          ],
          max_tokens: 700,
          temperature: 0.2
        });
        reply = out?.response || '';
      } else {
        const api = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${encodeURIComponent(env.GEMINI_API_KEY)}`;
        const upstream = await fetch(api, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }], generationConfig: { temperature: 0.2, maxOutputTokens: 700 } })
        });
        const result = await upstream.json();
        if (!upstream.ok) return json({ error: 'Gemini request failed.' }, 502);
        reply = result?.candidates?.[0]?.content?.parts?.map(p => p.text || '').join(' ').trim() || '';
      }
      return reply ? json({ reply }) : json({ error: 'AI returned no answer.' }, 502);
    } catch (error) {
      return json({ error: 'AI request failed.', detail: String(error?.message || error) }, 502);
    }
  }
};