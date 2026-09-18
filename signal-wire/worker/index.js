const cors={
  'Access-Control-Allow-Origin':'*',
  'Access-Control-Allow-Headers':'Content-Type',
  'Access-Control-Allow-Methods':'POST, OPTIONS'
};
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{...cors,'Content-Type':'application/json','Cache-Control':'no-store'}});
function compactEvents(events){return events.slice(0,6).map(e=>({title:String(e.title||'').slice(0,180),summary:String(e.summary||'').slice(0,320),excerpt:String(e.excerpt||'').slice(0,420),why_it_matters:String(e.why_it_matters||'').slice(0,240),verification:e.verification,verification_label:e.verification_label,source_tier:e.source_tier,confidence:e.confidence,published:e.published,timestamp_type:e.timestamp_type,connections:Array.isArray(e.connections)?e.connections.slice(0,4):[],affected_assets:Array.isArray(e.affected_assets)?e.affected_assets.slice(0,5):[],sources:Array.isArray(e.sources)?e.sources.slice(0,3).map(s=>({name:s.name,domain:s.domain,url:s.url,published:s.published,tier:s.tier})):[]}));}
function fallback(events){const e=events[0];if(!e)return'NOW: No current Signal Wire events were supplied.\nWHY IT MATTERS: I cannot assess market impact without current evidence.\nAFFECTED: Not established.\nUNCERTAINTY: High — no event evidence was provided.\nNEXT CHECK: Refresh the dashboard and ask again.';const status=e.verification_label||e.verification||'Unverified';const assets=(e.affected_assets||[]).slice(0,4).join(', ')||'Not established';const link=e.sources?.[0]?.name||'the supplied source';return`NOW: ${e.title||'Current event'} — ${e.summary||e.excerpt||'A current report is under review.'}\nWHY IT MATTERS: ${e.why_it_matters||'This may matter to markets, but the transmission path is not yet established.'}\nAFFECTED: ${assets}. ${e.connections?.[0]||'No specific market connection is confirmed.'}\nUNCERTAINTY: ${status}; confidence is ${e.confidence||'not stated'}. Treat market effects as analysis, not fact.\nNEXT CHECK: Recheck ${link} and look for an official or independent confirmation.`;}
function validReply(value){let r=String(value||'').replace(/<think>[\s\S]*?<\/think>/gi,'').trim();if(!r||r.length>1500||!/\bNOW\s*:/i.test(r)||!/\bWHY IT MATTERS\s*:/i.test(r)||/Justify high market impact|visuals with|To continue your thought|\b思路\b|He committed a/i.test(r))return'';return r;}
export default {async fetch(request,env){
  if(request.method==='OPTIONS')return new Response(null,{headers:cors});
  if(request.method!=='POST')return json({error:'POST a question to this endpoint.'},405);
  try{
    const body=await request.json();const message=String(body.message||'').trim().slice(0,1600);if(!message)return json({error:'Message is required.'},400);
    const events=Array.isArray(body.events)?compactEvents(body.events):[];const knowledge=Array.isArray(body.knowledge)?body.knowledge.slice(-8):[];
    const system='You are Signal Wire, a concise financial-market intelligence analyst. Return ONLY the final answer, never hidden reasoning, commentary, or a generic chatbot preamble. Use only the supplied evidence. Never invent facts, sources, dates, numbers, causal links, or certainty. Official evidence outranks reporting. Discovery leads are not confirmed alone. Keep to five short lines, each beginning exactly with NOW:, WHY IT MATTERS:, AFFECTED:, UNCERTAINTY:, or NEXT CHECK:. Distinguish facts from analysis. No buy/sell advice.';
    const user=`CURRENT EVIDENCE:\n${JSON.stringify({events,knowledge})}\n\nUSER QUESTION:\n${message}`;
    let reply='';
    try{const result=await env.AI.run('@cf/zai-org/glm-4.7-flash',{messages:[{role:'system',content:system},{role:'user',content:user}],max_tokens:280,temperature:0.1});reply=validReply(result?.response||result?.choices?.[0]?.text);}catch{}
    return json({reply:reply||fallback(events)});
  }catch(error){return json({reply:fallback([]),degraded:true});}
}};
