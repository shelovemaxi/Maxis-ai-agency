const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS'
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors });
    if (request.method !== 'POST') return json({ error: 'POST a message to this endpoint.' }, 405);
    if (!env.GEMINI_API_KEY) return json({ error: 'GEMINI_API_KEY is not configured.' }, 503);
    try {
      const body = await request.json();
      const message = String(body.message || '').trim().slice(0, 2000);
      const events = Array.isArray(body.events) ? body.events.slice(0, 30) : [];
      if (!message) return json({ error: 'Message is required.' }, 400);
      const evidence = JSON.stringify(events);
      const prompt = `You are Signal Wire AI, an evidence-aware economic and market intelligence analyst. Answer the user's question using ONLY the dashboard evidence below. Never invent facts, prices, sources, or certainty. Distinguish reported facts from your interpretation. Treat an event as independently corroborated only when its verification says verified and its sources include at least two distinct domains. If the evidence is insufficient, say so. Do not give personalized financial advice or instructions to buy/sell. Be concise but useful.\n\nDASHBOARD EVIDENCE:\n${evidence}\n\nUSER QUESTION:\n${message}`;
      const api = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${encodeURIComponent(env.GEMINI_API_KEY)}`;
      const upstream = await fetch(api, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }], generationConfig: { temperature: 0.2, maxOutputTokens: 700 } }) });
      const result = await upstream.json();
      if (!upstream.ok) return json({ error: 'Gemini request failed.' }, 502);
      const reply = result?.candidates?.[0]?.content?.parts?.map(p => p.text || '').join(' ').trim();
      return reply ? json({ reply }) : json({ error: 'Gemini returned no answer.' }, 502);
    } catch (error) {
      return json({ error: 'Invalid request.' }, 400);
    }
  }
};
