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
      const events = Array.isArray(body.events) ? body.events.slice(0, 8) : [];
      const knowledge = Array.isArray(body.knowledge) ? body.knowledge.slice(-12) : [];
      if (!message) return json({ error: 'Message is required.' }, 400);
      const evidence = JSON.stringify({events,knowledge});
      const prompt = `You are the Signal Wire market-intelligence analyst, not a generic chatbot. Use ONLY the supplied dashboard evidence and learned entries. Never invent facts, prices, sources, dates, or certainty. Official data outranks commentary. A learned entry is usable only when it came from official evidence or multiple independent domains; do not learn from a single unverified lead. Combine related events and explain the strongest connection to markets. Clearly label what is confirmed, what is reported, and what is analysis. If evidence is missing, say so. Use no more than 6 short bullets and about 120 words. Structure: NOW; WHY IT MATTERS; AFFECTED; UNCERTAINTY; NEXT CHECK. No personalized buy/sell advice.\n\nEVIDENCE AND MEMORY:\n${evidence}\n\nUSER QUESTION:\n${message}`;
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
