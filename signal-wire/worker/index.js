const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS'
};
function json(data,status=200){return new Response(JSON.stringify(data),{status,headers:{...cors,'Content-Type':'application/json','Cache-Control':'no-store'}})}
function compactEvents(events){return events.slice(0,6).map(e=>({title:String(e.title||'').slice(0,180),summary:String(e.summary||'').slice(0,320),excerpt:String(e.excerpt||'').slice(0,420),verification:e.verification,verification_label:e.verification_label,source_tier:e.source_tier,confidence:e.confidence,published:e.published,connections:Array.isArray(e.connections)?e.connections.slice(0,4):[],affected_assets:Array.isArray(e.affected_assets)?e.affected_assets.slice(0,5):[],sources:Array.isArray(e.sources)?e.sources.slice(0,3).map(s=>({name:s.name,domain:s.domain,url:s.url,published:s.published,tier:s.tier})):[]}))}
export default {async fetch(request,env){
  if(request.method==='OPTIONS')return new Response(null,{headers:cors});
  if(request.method!=='POST')return json({error:'POST a question to this endpoint.'},405);
  if(!env.GEMINI_API_KEY)return json({error:'The public analyst is not configured yet.'},503);
  try{
    const body=await request.json();const message=String(body.message||'').trim().slice(0,1600);if(!message)return json({error:'Message is required.'},400);
    const events=Array.isArray(body.events)?compactEvents(body.events):[];const knowledge=Array.isArray(body.knowledge)?body.knowledge.slice(-8):[];
    const prompt=`You are Signal Wire's concise financial-market intelligence analyst. You are not a generic chatbot and you are not a trading adviser. Use ONLY the current evidence and memory below. Never invent a fact, source, date, number, price, causal link, or certainty. Official evidence outranks reporting; a specialist or discovery lead is not confirmed alone. Combine duplicate or related reports. Clearly distinguish CONFIRMED from REPORTED and ANALYSIS. Explain one or two strongest market transmission paths, identify potentially affected assets/sectors, and say when evidence is insufficient. Use at most 6 short bullets and 110 words. Format exactly with short labels: NOW; WHY IT MATTERS; AFFECTED; UNCERTAINTY; NEXT CHECK. Do not give buy/sell instructions.\n\nCURRENT EVIDENCE:\n${JSON.stringify({events,knowledge})}\n\nQUESTION:\n${message}`;
    const api=`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${encodeURIComponent(env.GEMINI_API_KEY)}`;
    const upstream=await fetch(api,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({contents:[{parts:[{text:prompt}]}],generationConfig:{temperature:0.15,maxOutputTokens:420}})});
    const result=await upstream.json();if(!upstream.ok)return json({error:'The analyst provider returned an error.'},502);
    const reply=result?.candidates?.[0]?.content?.parts?.map(p=>p.text||'').join(' ').trim();return reply?json({reply}):json({error:'The analyst returned no answer.'},502);
  }catch(error){return json({error:'The analyst could not process this request.'},400)}
}};
