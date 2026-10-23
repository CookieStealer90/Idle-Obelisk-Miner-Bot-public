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


function updateStatus(d) {
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
  /* Show total diamonds + claim count in parentheses, e.g. "28 💎 (1x)" */
  document.getElementById('s-gem-val').innerHTML = claims>0
    ? `${diamonds}<span class="ico">\u{1F48E}</span> <span style="font-size:.7em;color:var(--text-dim)">(${claims}x)</span>`
    : `0<span class="ico">\u{1F48E}</span>`;
  const nextEl = document.getElementById('s-gem-next');
  if(!fb.enabled){
    nextEl.innerHTML = `<span style="color:var(--text-dim)">off</span>`;
  } else {
    const rem = fb.next_check_remaining||0;
    nextEl.innerHTML = rem>0
      ? `<span style="color:var(--yellow)">next ${fmtSec(rem)}</span>`
      : `<span style="color:var(--green)">Ready</span>`;
  }

  /* Action lock indicator under Game tile (small, dim) */
  const al = d.action_lock||{};
  const alEl = document.getElementById('s-action-lock');
  if(alEl){
    alEl.innerHTML = al.locked
      ? `<span style="color:var(--yellow)">action: busy</span>`
      : `<span style="color:var(--text-dim)">action: idle</span>`;
  }

  /* Level tile */
  const dl = d.detect_level||{};
  const lvlVal = document.getElementById('s-level-val');
  const lvlNext = document.getElementById('s-level-next');
  if(lvlVal && lvlNext){
    if(!dl.enabled){
      lvlVal.innerHTML = `<span style="color:var(--text-dim)">disabled</span>`;
      lvlVal.className = 'stat-value';
      lvlNext.innerHTML = `<span style="color:var(--text-dim)">off</span>`;
    } else if(!dl.armed){
      lvlVal.innerHTML = `<span style="color:var(--red)">&#x2014;</span>`;
      lvlVal.className = 'stat-value';
      lvlNext.innerHTML = `<span style="color:var(--red)" title="Place digit_*_tpl.png into images/level/">no digit templates</span>`;
    } else if(dl.current==null){
      lvlVal.innerHTML = `<span style="color:var(--text-dim)">&#x2014;</span>`;
      lvlVal.className = 'stat-value';
      const err = dl.last_error ? ` title="${esc(dl.last_error)}"` : '';
      lvlNext.innerHTML = `<span style="color:var(--yellow)"${err}>unknown</span>`;
    } else {
      const age = (typeof dl.last_age === 'number') ? dl.last_age : null;
      const interval = 60;
      const stale = age!=null && age > interval*2;
      const color = stale ? 'var(--yellow)' : 'var(--green)';
      lvlVal.innerHTML = `<span style="color:${color}">${dl.current}</span>`;
      lvlVal.className = 'stat-value';
      const rem = dl.next_check_remaining||0;
      const ageStr = age!=null ? `${fmtSec(age)} ago` : '';
      lvlNext.innerHTML = rem>0
        ? `<span style="color:var(--text-dim)">next ${fmtSec(rem)}${ageStr?' \u00B7 '+ageStr:''}</span>`
        : `<span style="color:var(--green)">Ready</span>`;
    }
  }

  /* Lootbug tile */
  const lb = d.lootbug||{};
  const lbVal = document.getElementById('s-lootbug-val');
  const lbNext = document.getElementById('s-lootbug-next');
  if(lbVal && lbNext){
    const clicks = lb.clicked||0;
    const bonuses = lb.bonus_count||0;
    if(!lb.enabled){
      lbVal.innerHTML = `<span style="color:var(--red)">Off</span>`;
      lbVal.className = 'stat-value';
      lbNext.innerHTML = `<span style="color:var(--text-dim)">off</span>`;
    } else if(lb.enabled && !lb.buy_bonus){
      lbVal.innerHTML = `<span style="color:var(--orange)">Active</span> <span style="font-size:.7em;color:var(--text-dim)">(${clicks}x)</span>`;
      lbVal.className = 'stat-value';
      const rem = lb.next_check_remaining||0;
      lbNext.innerHTML = rem>0
        ? `<span style="color:var(--yellow)">next ${fmtSec(rem)}</span>`
        : `<span style="color:var(--green)">Ready</span>`;
    } else {
      const bonusSuffix = bonuses>0 ? ` <span style="font-size:.7em;color:var(--text-dim)">+${bonuses}\u{1F48E}</span>` : '';
      lbVal.innerHTML = `<span style="color:var(--green)">Active</span><span class="ico">\u{1F48E}</span> <span style="font-size:.7em;color:var(--text-dim)">(${clicks}x)</span>${bonusSuffix}`;
      lbVal.className = 'stat-value';
      const rem = lb.next_check_remaining||0;
      lbNext.innerHTML = rem>0
        ? `<span style="color:var(--yellow)">next ${fmtSec(rem)}</span>`
        : `<span style="color:var(--green)">Ready</span>`;
    }
  }

}

function updateButtons(d) {
  setBtn('btn-auto',d.workflows_master_enabled,'\u26D3\uFE0F Workflows');
  const fb=d.freebies||{};
  setBtn('btn-freebies',fb.enabled,'\uD83C\uDF81 Freebies');
  const lb=d.lootbug||{};
  /* Tri-state: off (red) -> on without bonus (orange) -> on + bonus (green) */
  let lbMode = 'off';
  if(lb.enabled && !lb.buy_bonus) lbMode = 'partial';
  else if(lb.enabled && lb.buy_bonus) lbMode = 'on';
  const lbLabel = lb.founders_enabled ? '\uD83D\uDC1B Lootbug & Founders' : '\uD83D\uDC1B Lootbug';
  setBtn3('btn-lootbug',lbMode,lbLabel);
}

function setBtn(id,isOn,label){const el=document.getElementById(id);if(!el)return;el.textContent=label;el.classList.toggle('on',!!isOn);el.classList.toggle('off',!isOn)}

function setBtn3(id,mode,label){
  const el=document.getElementById(id);if(!el)return;
  el.textContent=label;
  el.classList.toggle('on',mode==='on');
  el.classList.toggle('warn',mode==='partial');
  el.classList.toggle('off',mode==='off');
}

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

