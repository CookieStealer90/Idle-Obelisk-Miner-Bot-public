/* ============================================================
   dashboard-status.js — Status panel, buttons, Workflows
   ============================================================ */

/* ============ TAB TITLE SYNC (status -> after "WebUI") ============ */
let _ttbBaseTitle = null;
let _ttbLastTitleDot = null;

function _ttb_syncTabTitleAfterWebUI(isRunning){
  if(_ttbBaseTitle === null) _ttbBaseTitle = document.title || '';

  const dot = isRunning ? '\uD83D\uDFE2' : '\uD83D\uDD34';
  if(dot === _ttbLastTitleDot) return;
  _ttbLastTitleDot = dot;

  const t = _ttbBaseTitle;

  // Insert dot right after the word "WebUI" (case-insensitive). Fallback: append.
  if(/webui/i.test(t)){
    document.title = t.replace(/(webui)/i, `$1 ${dot}`);
  }else{
    document.title = `${t} ${dot}`.trim();
  }
}


// Countdown nodes are created once; state updates only change text and transform.
const scanSchedules = new Map();
function updateScanCountdown(id, data, options={}) {
  const target=document.getElementById(id);
  if(!target)return;
  // Cached templates may still wrap this ID in a span beside last-scan text.
  // Own the whole footer so the legacy text cannot create another line.
  const host=target.closest?.('.stat-sub')||target;
  if(host!==target){
    target.removeAttribute('id');
    host.id=id;
  }
  if(!host.querySelector('.scan-time')){
    host.classList.add('scan-countdown');
    host.innerHTML='<span class="scan-track" aria-hidden="true"><span class="scan-fill"></span></span><span class="scan-time"></span>';
  }
  const time=host.querySelector('.scan-time'), fill=host.querySelector('.scan-fill');
  const remaining=Math.max(0, Number(data.next_check_remaining)||0);
  const enabled=!!data.enabled && !options.blocked;
  const deadline=Number(data.next_check_ts)||0;
  let schedule=scanSchedules.get(id);
  // Deadlines identify actual schedules, including jitter and short busy retries.
  if(!enabled){
    scanSchedules.delete(id);
    schedule=null;
  }else if(!schedule || schedule.deadline!==deadline || remaining>schedule.previous+1){
    schedule={deadline, total:Math.max(1,remaining), previous:remaining};
    scanSchedules.set(id,schedule);
  }
  if(schedule)schedule.previous=remaining;
  const seconds=Math.ceil(remaining);
  const hours=Math.floor(seconds/3600), minutes=Math.floor(seconds/60)%60;
  const label=!data.enabled?'Off':options.blocked||(!remaining?'Ready':
    (hours?hours+':'+String(minutes).padStart(2,'0'):String(minutes))+':'+String(seconds%60).padStart(2,'0'));
  const mode=!enabled?'off':remaining?'waiting':'ready';
  if(time.textContent!==label)time.textContent=label;
  if(host.dataset.mode!==mode)host.dataset.mode=mode;
  const progress=!enabled?0:remaining?Math.max(0,Math.min(1,1-remaining/schedule.total)):1;
  const transform='scaleX('+progress.toFixed(4)+')';
  if(fill.style.transform!==transform)fill.style.transform=transform;
  const detail=options.detail||'';
  const title=(data.enabled?(options.blocked||('Next scan: '+label)):'Scanning disabled')+(detail?' \u00b7 '+detail:'');
  if(host.title!==title){host.title=title;host.setAttribute('aria-label',title);}
}

const statusMarkup = new WeakMap();
function setStatusMarkup(element, html){
  if(statusMarkup.get(element)===html)return;
  element.innerHTML=html;
  statusMarkup.set(element,html);
}

function updateStatus(d) {
  const reloadEl = document.getElementById('workflow-reload-status');
  if(reloadEl){
    const status = d.workflows_reload_status;
    reloadEl.textContent = status==='pending' ? ' Reload requested; waiting for an idle scheduler.'
      : status==='applied' ? ' Reload completed.'
      : status==='error' ? ' Reload failed: '+(d.workflows_reload_error||'unknown error') : '';
  }
  const g = d.gems||{}, cd = d.cooldowns||{};

  const gameEl = document.getElementById('s-game');
  const dot = document.getElementById('status-dot');
  if(d.game_running){gameEl.textContent='ACTIVE';gameEl.className='stat-value green';dot.style.background='var(--green)'}
  else{gameEl.textContent='STOPPED';gameEl.className='stat-value red';dot.style.background='var(--red)'}

  // Sync tab favicon with the already-rendered status indicator (status-dot)
  _ttb_syncTabTitleAfterWebUI(!!d.game_running);

  const fb = d.freebies||{};
  const claims = fb.claimed||0;
  const diamonds = fb.diamonds||0;
  document.getElementById('s-gem-val').title = 'Estimated gems from claim taps; reward not verified in game';
  /* Show total diamonds + claim count in parentheses, e.g. "28 💎 (1x)" */
  setStatusMarkup(document.getElementById('s-gem-val'), claims>0
    ? `${diamonds}<span class="ico">\u{1F48E}</span> <span style="font-size:.7em;color:var(--text-dim)">(${claims}x)</span>`
    : `0<span class="ico">\u{1F48E}</span>`);
  updateScanCountdown('s-gem-next',fb);

  /* Action lock indicator under Game tile (small, dim) */
  const al = d.action_lock||{};
  const alEl = document.getElementById('s-action-lock');
  if(alEl){
    setStatusMarkup(alEl, al.locked
      ? `<span style="color:var(--yellow)">action: busy</span>`
      : `<span style="color:var(--text-dim)">action: idle</span>`);
  }

  /* Level tile */
  const dl = d.detect_level||{};
  const lvlVal = document.getElementById('s-level-val');
  const lvlNext = document.getElementById('s-level-next');
  if(lvlVal && lvlNext){
    if(!dl.enabled){
      setStatusMarkup(lvlVal, `<span style="color:var(--text-dim)">disabled</span>`);
      lvlVal.className = 'stat-value';
      updateScanCountdown('s-level-next',dl);
    } else if(!dl.armed){
      setStatusMarkup(lvlVal, `<span style="color:var(--red)">&#x2014;</span>`);
      lvlVal.className = 'stat-value';
      updateScanCountdown('s-level-next',dl,{blocked:'Setup',detail:'Place digit_*_tpl.png into images/level/'});
    } else if(dl.current==null){
      setStatusMarkup(lvlVal, `<span style="color:var(--text-dim)">&#x2014;</span>`);
      lvlVal.className = 'stat-value';
      updateScanCountdown('s-level-next',dl,{detail:dl.last_error||'Level not detected yet'});
    } else {
      const age = (typeof dl.last_age === 'number') ? dl.last_age : null;
      const interval = 60;
      const stale = age!=null && age > interval*2;
      const color = stale ? 'var(--yellow)' : 'var(--green)';
      setStatusMarkup(lvlVal, `<span style="color:${color}">${dl.current}</span>`);
      lvlVal.className = 'stat-value';
      updateScanCountdown('s-level-next',dl,{detail:dl.last_error||(age!=null?'Last detection: '+fmtSec(age)+' ago':'')});
    }
  }

  /* Lootbug tile */
  const lb = d.lootbug||{};
  const lbVal = document.getElementById('s-lootbug-val');
  const lbNext = document.getElementById('s-lootbug-next');
  if(lbVal && lbNext){
    const clicks = lb.clicked||0;
    if(!lb.enabled){
      setStatusMarkup(lbVal, `<span style="color:var(--red)">Off</span>`);
      lbVal.className = 'stat-value';
      updateScanCountdown('s-lootbug-next',lb);
    } else {
      setStatusMarkup(lbVal, `<span style="color:var(--green)">Active</span> <span style="font-size:.7em;color:var(--text-dim)">(${clicks}x)</span>`);
      lbVal.className = 'stat-value';
      updateScanCountdown('s-lootbug-next',lb);
    }
  }

  /* Independent Founders tile */
  const founders = d.founders||{};
  const foundersVal = document.getElementById('s-founders-val');
  const foundersNext = document.getElementById('s-founders-next');
  if(foundersVal && foundersNext){
    setStatusMarkup(foundersVal, founders.enabled
      ? `<span style="color:var(--green)">Active</span> <span style="font-size:.7em;color:var(--text-dim)">(${founders.clicked||0}x)</span>`
      : `<span style="color:var(--red)">Off</span>`);
    updateScanCountdown('s-founders-next',founders);
  }
}


function updateButtons(d) {
  setBtn('btn-auto',d.workflows_master_enabled,'\u26D3\uFE0F Workflows');
  const fb=d.freebies||{};
  setBtn('btn-freebies',fb.enabled,'\uD83C\uDF81 Freebies');
  const lb=d.lootbug||{};
  setBtn('btn-lootbug',lb.enabled,'\uD83D\uDC1B Lootbug');
  setBtn('btn-founders',(d.founders||{}).enabled,'\uD83D\uDCE6 FOUNDERS BUNDLE');
}

function setBtn(id,isOn,label){const el=document.getElementById(id);if(!el)return;el.textContent=label;el.classList.toggle('on',!!isOn);el.classList.toggle('off',!isOn)}

/* ============ WORKFLOWS (dynamic) ============ */
function updateWorkflows(d) {
  const container = document.getElementById('wf-rows');
  if(!container)return;
  const list = d.workflows||[];
  const masterOn = !!d.workflows_master_enabled;
  const card = document.getElementById('card-wf');
  if(card) card.style.display = masterOn ? '' : 'none';
  if(!masterOn){ container.innerHTML = ''; return; }

  if(list.length===0){
    container.innerHTML = `<div style="font-size:.65rem;color:var(--text-dim);padding:6px 4px">No workflows defined. Add one in the Configuration &rarr; Workflows tab.</div>`;
    return;
  }
  let html='';
  for(const wf of list){
    if(wf.inactive)continue;
    const on=wf.enabled, active=on&&masterOn;
    const eta=active?(wf.next_remaining>0?fmtSec(wf.next_remaining):'now'):'--';
    let rowCls='wf-row';
    if(wf.running)rowCls+=' src-pilot';
    else if(active)rowCls+=' src-manual';
    else rowCls+=' inactive';
    const dis = masterOn ? '' : 'disabled';
    html+=`<div class="${rowCls}">
      <div class="wf-info"><div class="wf-name">${esc(wf.name)}</div>${wf.description?`<div class="wf-desc">${esc(wf.description)}</div>`:''}</div>
      <div class="wf-eta-box"><div class="wf-eta">${eta}</div><div class="wf-eta-sub">${wf.step_count} step(s) \u00B7 ${Math.round(wf.interval_s)}s</div></div>
      <button class="btn warn" style="padding:4px 10px;font-size:.68rem" onclick="cmd('wf_run:${esc(wf.slug)}')" ${dis} title="Run once">&#x25B6;</button>
      <button class="btn ${on?'on':'off'}" style="padding:4px 8px;font-size:.62rem;min-width:38px" onclick="cmd('wf_auto:${esc(wf.slug)}')" ${dis}>Auto</button>
    </div>`;
  }
  if(!html){
    html = `<div style="font-size:.65rem;color:var(--text-dim);padding:6px 4px">All workflows are marked inactive.</div>`;
  }
  container.innerHTML = html;
}

