(()=>{
'use strict';
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const setText=(sel,value)=>{const el=$(sel);if(el)el.textContent=String(value??'')};
const safeUrl=u=>/^https?:\/\//i.test(String(u||''))?String(u):'#';
const fmtTime=v=>{const d=new Date(v);if(!Number.isFinite(d.getTime()))return'Unknown time';return d.toLocaleString(undefined,{day:'2-digit',month:'short',year:'numeric',hour:'numeric',minute:'2-digit',hour12:true})};
const ago=v=>{const d=new Date(v),ms=Date.now()-d.getTime();if(!Number.isFinite(ms)||ms<0)return'just now';const m=Math.floor(ms/60000);return m<1?'just now':m<60?`${m}m ago`:m<1440?`${Math.floor(m/60)}h ago`:fmtTime(v)};
const DEFAULT_THRESHOLD=50;
const state={all:[],knowledge:{entries:[]},source:'all',loaded:false};
const threshold=$('#threshold'),category=$('#category'),verification=$('#verification'),source=$('#source'),detail=$('#detail');
const unique=a=>[...new Set((a||[]).filter(Boolean))];
const sourceRows=x=>Array.isArray(x?.sources)&&x.sources.length?x.sources:[{name:x?.source||'Unknown source',domain:x?.domain||'unknown',url:x?.url||'',published:x?.published,tier:x?.source_tier||'discovery',excerpt:x?.excerpt||''}];
const domainCount=x=>unique(sourceRows(x).map(s=>String(s.domain||'').replace(/^www\./,'').toLowerCase()).filter(d=>d&&d!=='unknown')).length;
const evidenceCode=x=>{const v=String(x?.verification||'').toLowerCase();if(v==='confirmed'||v==='confirmed-official'||v==='confirmed official data')return'confirmed';if(v==='verified'||v==='corroborated-report'||v==='corroborated'||v==='partially-confirmed')return'verified';return'single-source'};
const independentlyChecked=x=>evidenceCode(x)!=='single-source'&&domainCount(x)>=2;
const tierName=x=>({official:'Official', 'major-financial':'Major financial', specialist:'Specialist', discovery:'Discovery'}[x?.source_tier]||'Discovery');
const confidenceName=x=>({high:'High confidence',medium:'Medium confidence',low:'Low confidence'}[x?.confidence]||'Unstated confidence');
const statusName=x=>x?.verification_label||(evidenceCode(x)==='confirmed'?'Confirmed official data':independentlyChecked(x)?'Corroborated across 2+ domains':'Reported lead — verify carefully');
const filtered=()=>state.all.filter(x=>Number(x?.score||0)>=Number(threshold?.value||DEFAULT_THRESHOLD)&&(category?.value==='all'||x.category===category.value)&&(verification?.value==='all'||evidenceCode(x)===verification.value)&&(source?.value==='all'||sourceRows(x).some(s=>s.name===source.value)));
function sourceOptions(){
  if(!source)return;
  const current=state.source||source.value||'all';
  const names=unique(state.all.flatMap(x=>sourceRows(x).map(s=>s.name))).sort((a,b)=>a.localeCompare(b));
  source.innerHTML='<option value="all">All sources</option>'+names.map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join('');
  source.value=names.includes(current)?current:'all';state.source=source.value;
}
function card(x){
  const checked=independentlyChecked(x),sources=sourceRows(x),status=statusName(x);
  return `<article class="card ${checked?'verified':''}" tabindex="0" role="button" data-id="${esc(x.id)}" aria-label="View details: ${esc(x.title)}">
    <div class="card-top"><span class="badge ${checked?'checked':'unverified'}">${checked?'✓ ': '! '}${esc(status)}</span><span class="score">${esc(x.score??'—')}<small>/100</small></span></div>
    <div class="card-labels"><span>${esc(tierName(x))}</span><span>${esc(confidenceName(x))}</span><span>${esc(x.level||'Medium')} importance</span></div>
    <h2>${esc(x.title||'Untitled event')}</h2>
    <p class="why"><b>Why it matters:</b> ${esc(x.why_it_matters||x.market_relevance||'Market relevance is still being assessed.')}</p>
    <p class="summary">${esc(x.summary||x.excerpt||'No concise source summary was available.')}</p>
    <div class="tags">${(x.affected_assets||x.reasons||[]).slice(0,4).map(r=>`<span>${esc(r)}</span>`).join('')}</div>
    <div class="meta">${esc(x.category||'General')} · ${esc(x.freshness||ago(x.published))} · ${sources.length} source${sources.length===1?'':'s'}${x.connections?.length?' · '+esc(x.connections[0]):''}</div>
    <span class="view">View evidence →</span>
  </article>`;
}
function renderPulse(rows){
  const lead=rows[0];
  if(!lead){setText('#pulseTitle',state.loaded?'No high-value signals match this view':'Preparing the current signal');setText('#pulseText',state.loaded?'Lower the threshold or clear a filter to see the retained intelligence.':'Loading the highest-impact evidence.');setText('#pulseScore','—');setText('#pulseMeta',state.loaded?'No matching events':'Checking evidence');return;}
  setText('#pulseTitle',lead.title||'Current market signal');
  setText('#pulseText',(lead.why_it_matters||lead.market_relevance||'Material event under review.')+' '+statusName(lead));
  setText('#pulseScore',`${lead.score??'—'}/100`);
  setText('#pulseMeta',`${confidenceName(lead)} · ${tierName(lead)} · ${ago(lead.published)}`);
}
function render(){
  const rows=filtered();renderPulse(rows);setText('#total',rows.length);setText('#verifiedCount',rows.filter(independentlyChecked).length);
  const cards=$('#cards');if(cards)cards.innerHTML=rows.length?rows.map(card).join(''):'<div class="loading">No material signals match these filters. Try lowering the score or clearing a filter.</div>';
  const count=state.knowledge?.entries?.length||0;setText('#knowledgeCount',`${count} learned pattern${count===1?'':'s'}`);setText('#knowledgeSummary',count?`${count} evidence-backed patterns retained from official or independently corroborated events.`:'No verified patterns have been retained yet.');
  try{localStorage.setItem('sw-filter-v2',JSON.stringify({t:threshold?.value||35,c:category?.value||'all',v:verification?.value||'all',s:source?.value||'all'}));}catch{}
}
function openDetail(id){
  const x=state.all.find(v=>String(v.id)===String(id));if(!x||!detail)return;
  const checked=independentlyChecked(x),sources=sourceRows(x),status=statusName(x);
  const sourceHtml=sources.map(s=>`<li><b>${esc(s.name||'Source')}</b><small>${esc(s.domain||'')}</small><span class="source-time">${esc(fmtTime(s.published||x.published))}</span><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">Open original ↗</a></li>`).join('');
  $('#detailBody').innerHTML=`<span class="badge ${checked?'checked':'unverified'}">${checked?'✓ ':'! '}${esc(status)}</span><h2>${esc(x.title||'Untitled event')}</h2><p class="detail-summary">${esc(x.summary||x.excerpt||'No source summary was available.')}</p><dl>
    <dt>What is confirmed</dt><dd>${esc(x.confirmed_facts||x.summary||'Only the linked source report is confirmed at this stage.')}</dd>
    <dt>Verification</dt><dd>${esc(status)} · ${esc(confidenceName(x))}</dd>
    <dt>Why it matters</dt><dd>${esc(x.why_it_matters||x.market_relevance||'Not available')}</dd>
    <dt>Relevance score</dt><dd>${esc(x.score??'—')}/100 · ${esc(x.level||'')} — a prioritisation measure of breadth, magnitude, urgency, source quality, and corroboration; not a price forecast.</dd>
    <dt>Published</dt><dd>${esc(fmtTime(x.published))} (${esc(x.timestamp_type||'published')}) · ${esc(x.freshness||ago(x.published))}</dd>
    ${x.affected_assets?.length?`<dt>Potentially affected</dt><dd>${x.affected_assets.map(esc).join(', ')}</dd>`:''}
    ${x.connections?.length?`<dt>Market connections</dt><dd>${x.connections.map(esc).join(' · ')} <small>(analysis, not confirmed causation)</small></dd>`:''}
    ${x.speculation?`<dt>What remains speculative</dt><dd>${esc(x.speculation)}</dd>`:''}
  </dl><h3>Evidence used</h3><ul class="source-list">${sourceHtml||'<li>No source records were retained.</li>'}</ul><p class="disclaimer">Signal Wire preserves original links and timestamps. A connection describes a plausible transmission path, not a guaranteed market outcome.</p>`;
  if(typeof detail.showModal==='function')detail.showModal();else detail.setAttribute('open','');
  $('#closeDetail')?.focus();
}
async function fetchSnapshot(){
  const urls=['/api/data?ts='+Date.now(),`data.json?ts=${Date.now()}`,'/api/items?ts='+Date.now()];let last;
  for(const url of urls){try{const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw Error(`published data returned ${r.status}`);const d=await r.json();if(Array.isArray(d.items))return d;}catch(e){last=e;}}
  throw last||Error('No data endpoint responded');
}
async function load(){
  try{
    const d=await fetchSnapshot();state.all=d.items||[];state.knowledge=d.knowledge||{entries:[]};state.loaded=true;sourceOptions();
    const health=Object.values(d.source_health||{});const good=health.filter(x=>x&&x.ok).length;setText('#sources',good||'—');setText('#updated',ago(d.last_refresh));
    const h=$('#health');if(h){h.classList.toggle('offline',good===0);h.innerHTML=`<i></i>${good?`${good} sources online`:'Source health unavailable'}`;}
    const errors=Array.isArray(d.errors)?d.errors:[];const error=$('#error');if(error){error.textContent=errors.length?`Some sources are temporarily unavailable; other sources are still being used. ${errors.slice(0,2).join(' · ')}`:'';error.classList.toggle('hidden',!errors.length);}
    render();
  }catch(e){const error=$('#error');if(error){error.textContent='Could not load published intelligence data. The last good view is preserved if available. '+e.message;error.classList.remove('hidden');}if(!state.loaded){setText('#pulseTitle','Signal Wire is waiting for data');setText('#pulseText','The feed is temporarily unavailable. Try Reload data in a moment.');setText('#cards','Data unavailable');}}
}
function setAi(open){const panel=$('#aiPanel'),scrim=$('#aiScrim'),toggle=$('#aiToggle');if(!panel)return;panel.classList.toggle('closed',!open);panel.setAttribute('aria-hidden',String(!open));if(scrim){scrim.hidden=!open;scrim.classList.toggle('visible',open);}toggle?.setAttribute('aria-expanded',String(open));$('#aiDockButton')?.setAttribute('aria-expanded',String(open));document.body.classList.toggle('ai-open',open);if(open)setTimeout(()=>$('#chatInput')?.focus(),180);}
function addMsg(role,text){const log=$('#chatLog');if(!log)return null;const el=document.createElement('div');el.className=`chat-msg ${role}`;el.textContent=text;log.appendChild(el);log.scrollTop=log.scrollHeight;return el;}
const PUBLIC_AI='https://signal-wire-ai.maxiwalker0707.workers.dev';
async function askAI(body){
  const saved=localStorage.getItem('sw-ai-endpoint')||'';const candidates=unique([saved,location.origin+'/api/chat',PUBLIC_AI]);let last;
  for(const endpoint of candidates){try{const r=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw Error(`backend returned ${r.status}`);const d=await r.json();if(d.reply)return d;last=Error(d.error||'No answer returned');}catch(e){last=e;}}
  throw last||Error('No AI endpoint responded');
}
function setup(){
  try{const p=JSON.parse(localStorage.getItem('sw-filter-v2')||'null');if(p){if(threshold)threshold.value=p.t||DEFAULT_THRESHOLD;if(category)category.value=p.c||'all';if(verification)verification.value=p.v||'all';state.source=p.s||'all';}}catch{}
  if(threshold){setText('#thresholdValue',threshold.value);threshold.addEventListener('input',()=>{setText('#thresholdValue',threshold.value);render();});}
  [category,verification,source].forEach(e=>e?.addEventListener('change',()=>{if(e===source)state.source=source.value;render();}));
  $('#cards')?.addEventListener('click',e=>{const c=e.target.closest('.card');if(c)openDetail(c.dataset.id);});
  $('#cards')?.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.closest('.card')){e.preventDefault();openDetail(e.target.closest('.card').dataset.id);}});
  $('#closeDetail')?.addEventListener('click',()=>detail?.close?.());detail?.addEventListener('click',e=>{if(e.target===detail)detail.close?.();});
  $('#method')?.addEventListener('click',()=>{const el=$('#methodology'),hidden=el?.classList.toggle('hidden');$('#method')?.setAttribute('aria-expanded',String(!hidden));});
  $('#refresh')?.addEventListener('click',load);$('#aiToggle')?.addEventListener('click',()=>setAi(true));$('#aiDockButton')?.addEventListener('click',()=>setAi(true));$('#aiClose')?.addEventListener('click',()=>setAi(false));$('#aiScrim')?.addEventListener('click',()=>setAi(false));document.addEventListener('keydown',e=>{if(e.key==='Escape'){setAi(false);if(detail?.open)detail.close();}});
  const endpoint=$('#aiEndpoint'),status=$('#aiStatus'),saved=localStorage.getItem('sw-ai-endpoint')||'';if(endpoint)endpoint.value=saved;if(saved&&status)status.textContent='Using the private endpoint saved in this browser; public fallback remains available.';
  $('#saveEndpoint')?.addEventListener('click',()=>{const v=endpoint?.value.trim()||'';if(v&&!/^https:\/\//i.test(v)){if(status)status.textContent='Use an https:// URL, or leave this empty for the public analyst.';return;}if(v)localStorage.setItem('sw-ai-endpoint',v);else localStorage.removeItem('sw-ai-endpoint');if(status)status.textContent=v?'Private endpoint saved; public fallback remains available.':'Public analyst ready.';});
  $('#aiClear')?.addEventListener('click',()=>{const log=$('#chatLog');if(log)log.innerHTML='<div class="chat-msg assistant">Chat cleared. Ask about the strongest evidence or a market connection.</div>';});
  $('#chatForm')?.addEventListener('submit',async e=>{e.preventDefault();const input=$('#chatInput'),text=input?.value.trim();if(!text)return;addMsg('user',text);input.value='';const pending=addMsg('assistant','Working from the current evidence…');const context=filtered().slice(0,6).map(x=>({title:x.title,summary:(x.summary||'').slice(0,320),excerpt:(x.excerpt||'').slice(0,420),category:x.category,score:x.score,verification:x.verification,verification_label:x.verification_label,published:x.published,timestamp_type:x.timestamp_type,connections:(x.connections||[]).slice(0,4),why_it_matters:x.why_it_matters,source_tier:x.source_tier,confidence:x.confidence,affected_assets:(x.affected_assets||[]).slice(0,5),sources:sourceRows(x).slice(0,3).map(s=>({name:s.name,domain:s.domain,url:s.url,published:s.published,tier:s.tier}))}));try{const d=await askAI({message:text,events:context,knowledge:(state.knowledge.entries||[]).slice(-8)});if(pending)pending.textContent=d.reply;}catch(err){if(pending){pending.textContent='The public analyst is temporarily unavailable. The dashboard evidence is still available in the event cards and original source links.';pending.classList.add('error-msg');}}});
  load();setInterval(load,60000);
}
setup();
})();
