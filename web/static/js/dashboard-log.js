/* ============================================================
   dashboard-log.js — Log panel + filter (pos/neg, cross-device)
   ============================================================ */

const logPanel=document.getElementById('log-panel');
let logAutoScroll=true;
logPanel.addEventListener('scroll',()=>{logAutoScroll=logPanel.scrollTop+logPanel.clientHeight>=logPanel.scrollHeight-30});

/* ── Filter State ── */
let logFilters=[];
let logFilterOpen=false;
let _filterSyncLock=false;

/* ── Build Filter UI ── */
(function initLogFilter(){
  const hdr=document.querySelector('#card-log .card-hdr');
  const toggleBtn=hdr.querySelector('.card-toggle');

  const wrap=document.createElement('div');
  wrap.className='log-filter-area';
  wrap.addEventListener('click',e=>e.stopPropagation());

  // active-tag container
  const tags=document.createElement('div');
  tags.className='log-filter-tags';
  tags.id='log-filter-tags';
  wrap.appendChild(tags);

  // input wrapper (input + apply button)
  const inpWrap=document.createElement('div');
  inpWrap.className='log-filter-input-wrap';
  inpWrap.id='log-filter-input-wrap';

  const inp=document.createElement('input');
  inp.type='text';
  inp.className='log-filter-input';
  inp.id='log-filter-input';
  inp.placeholder='filter…';
  inp.addEventListener('keydown',e=>{
    if(e.key==='Enter'){e.preventDefault();submitLogFilter();}
    if(e.key==='Escape'){closeLogFilter();}
  });
  inpWrap.appendChild(inp);

  // apply checkmark button
  const applyBtn=document.createElement('button');
  applyBtn.className='log-filter-apply';
  applyBtn.title='Apply filter';
  applyBtn.innerHTML='<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
  applyBtn.addEventListener('click',e=>{e.stopPropagation();submitLogFilter();});
  inpWrap.appendChild(applyBtn);

  wrap.appendChild(inpWrap);

  // filter icon button
  const btn=document.createElement('button');
  btn.className='log-filter-btn';
  btn.id='log-filter-btn';
  btn.title='Filter log';
  btn.innerHTML='<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon></svg>';
  btn.addEventListener('click',e=>{e.stopPropagation();toggleLogFilter();});
  wrap.appendChild(btn);

  hdr.insertBefore(wrap,toggleBtn);
})();

function submitLogFilter(){
  const inp=document.getElementById('log-filter-input');
  addLogFilter(inp.value);
  inp.value='';
  inp.focus();
}

function toggleLogFilter(){
  if(logFilterOpen){closeLogFilter();}
  else{
    document.getElementById('log-filter-input-wrap').classList.add('open');
    setTimeout(()=>document.getElementById('log-filter-input').focus(),10);
    logFilterOpen=true;
    document.getElementById('log-filter-btn').classList.add('active');
  }
}
function closeLogFilter(){
  const inp=document.getElementById('log-filter-input');
  inp.value='';
  document.getElementById('log-filter-input-wrap').classList.remove('open');
  logFilterOpen=false;
  document.getElementById('log-filter-btn').classList.remove('active');
}

// Close filter input when clicking outside
document.addEventListener('click',e=>{
  if(!logFilterOpen)return;
  const area=document.querySelector('.log-filter-area');
  if(area&&!area.contains(e.target))closeLogFilter();
});

/* ── Sync helper ── */
function pushFiltersToServer(){
  if(_filterSyncLock)return;
  socket.emit('log_filters_update', logFilters);
}

function addLogFilter(raw){
  const val=raw.trim().toLowerCase();
  if(!val||logFilters.some(f=>f.text===val))return;
  logFilters.push({text:val, mode:'pos'});
  renderFilterTags();
  applyLogFilters();
  pushFiltersToServer();
}
function removeLogFilter(val){
  logFilters=logFilters.filter(f=>f.text!==val);
  renderFilterTags();
  applyLogFilters();
  pushFiltersToServer();
}
function toggleFilterMode(val){
  const f=logFilters.find(f=>f.text===val);
  if(f){f.mode=f.mode==='pos'?'neg':'pos';}
  renderFilterTags();
  applyLogFilters();
  pushFiltersToServer();
}

function renderFilterTags(){
  const c=document.getElementById('log-filter-tags');
  c.innerHTML='';
  logFilters.forEach(f=>{
    const tag=document.createElement('span');
    tag.className='log-filter-tag'+(f.mode==='neg'?' neg':'');
    tag.title='Click to toggle include/exclude';
    const label=document.createElement('span');
    label.className='log-filter-tag-label';
    label.textContent=f.text;
    label.addEventListener('click',e=>{e.stopPropagation();toggleFilterMode(f.text);});
    tag.appendChild(label);
    const x=document.createElement('span');
    x.className='log-filter-tag-x';
    x.title='Remove filter';
    x.innerHTML='&times;';
    x.addEventListener('click',e=>{e.stopPropagation();removeLogFilter(f.text);});
    tag.appendChild(x);
    c.appendChild(tag);
  });
  const hasPos=logFilters.some(f=>f.mode==='pos');
  const hasNeg=logFilters.some(f=>f.mode==='neg');
  const btn=document.getElementById('log-filter-btn');
  btn.classList.toggle('has-filters-pos',hasPos&&!hasNeg);
  btn.classList.toggle('has-filters-neg',hasNeg&&!hasPos);
  btn.classList.toggle('has-filters-mix',hasPos&&hasNeg);
  btn.classList.toggle('has-filters',logFilters.length>0);
}

function matchesFilters(msg){
  if(!logFilters.length)return true;
  const m=(msg||'').toLowerCase();
  const posFilters=logFilters.filter(f=>f.mode==='pos');
  const negFilters=logFilters.filter(f=>f.mode==='neg');
  if(negFilters.length&&negFilters.some(f=>m.includes(f.text)))return false;
  if(posFilters.length&&!posFilters.some(f=>m.includes(f.text)))return false;
  return true;
}

function applyLogFilters(){
  const entries=logPanel.querySelectorAll('.log-entry');
  entries.forEach(el=>{
    const msgEl=el.querySelector('.log-msg');
    const text=msgEl?msgEl.textContent:el.textContent;
    el.style.display=matchesFilters(text)?'':'none';
  });
  if(logAutoScroll)logPanel.scrollTop=logPanel.scrollHeight;
}

/* ── Receive filter sync from server ── */
socket.on('log_filters_sync',(data)=>{
  if(!Array.isArray(data))return;
  _filterSyncLock=true;
  logFilters=data;
  renderFilterTags();
  applyLogFilters();
  _filterSyncLock=false;
});

/* ── Core log append ── */
socket.on('log_entry',(entry)=>{appendLog(entry)});

function appendLog(entry){
  const div=document.createElement('div');
  div.className='log-entry';
  const cls=logMsgClass(entry.msg);
  div.innerHTML=`<span class="log-ts">${esc(entry.ts)}</span> <span class="log-msg ${cls}">${esc(entry.msg)}</span>`;
  if(!matchesFilters(entry.msg))div.style.display='none';
  logPanel.appendChild(div);
  while(logPanel.children.length>500)logPanel.removeChild(logPanel.firstChild);
  if(logAutoScroll)logPanel.scrollTop=logPanel.scrollHeight;
}

function logMsgClass(msg){
  if(!msg)return'';
  const m=msg.toUpperCase();
  if(m.includes('ERR')||m.includes('FATAL'))return'err';
  if(m.includes('[PERK]'))return'perk';
  if(m.includes('[GEM]')||m.includes('💎'))return'gem';
  if(m.includes('[WF'))return'wf';
  if(m.includes('[PILOT]')||m.includes('[WAVE-PILOT]'))return'pilot';
  return'';
}

fetch('/api/logs').then(r=>r.json()).then(logs=>{logs.forEach(e=>appendLog(e))}).catch(()=>{});
