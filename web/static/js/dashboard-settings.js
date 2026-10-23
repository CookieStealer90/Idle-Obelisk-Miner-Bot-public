/* ============================================================
   dashboard-settings.js — Settings editor (Obelisk Bot)
   ============================================================ */

let settingsData={};

const FIELD_HINTS={
  'gem_statistics_enabled':'Gem Statistics tracking + card',
  'screenshot_visible':'show Screenshot card',
  'freebies_enabled':'auto-start Freebies feature on bot launch',
  'lootbug_enabled':'auto-start Lootbug feature on bot launch',
  'lootbug_buy_bonus':'auto-start with gem-bonus purchase armed (requires lootbug_enabled=true)',
  'workflows_enabled':'master "Auto WF" toggle on bot launch (false = scheduler off)',
  'detect_level_enabled':'auto-start Detect Level feature on bot launch (required by workflow level_* if-conditions)',
  /* detect_level */
  'DETECT_LEVEL_ENABLED':'master switch for the Detect Level feature (disables level_* if-conditions)',
  'DETECT_LEVEL_ROI':'x1,y1,x2,y2 search area for digit_*_tpl.png on the base screen',
  'DETECT_LEVEL_INTERVAL_S':'seconds between level scans',
  'DETECT_LEVEL_THRESHOLD':'0.0-1.0 match score required per digit',
  'DETECT_LEVEL_CACHE_MAX_AGE_S':'reuse any recent cached screenshot younger than this (sec) before pulling fresh',
  'DETECT_LEVEL_NMS_MIN_DX_PX':'min horizontal gap between accepted digit centers (prevents stacked matches)',
  'DETECT_LEVEL_LOG_LEVEL':'FULL | TXT | UI',
  /* workflows */
  'WF_INTERVAL_VARIANCE_PCT':'global +/- variance applied to each WF interval (per-WF override possible)',
  'WORKFLOWS_TAP_JITTER_PX':'default jitter for tap_roi/tap_xy when step omits it',
  'WORKFLOWS_SCREEN_REUSE_AGE_S':'click_template: reuse wf_scr.png if younger than this (sec)',
  'WORKFLOWS_BUSY_RETRY_S':'retry delay when another feature holds the action lock',
  'WORKFLOWS_LOG_LEVEL':'general scheduler log level — FULL | TXT | UI',
  'WORKFLOWS_LOG_LEVEL_STEP':'individual step execution log — FULL | TXT | UI',
  'WORKFLOWS_LOG_LEVEL_BUSY':'postponed/rejected (lock busy) — FULL | TXT | UI',
  /* screenshot viewer */
  'SCREENSHOT_VIEWER_FILES':'comma-separated filenames in ./temp/ to check (newest wins)',
  /* running detection */
  'RUNNING_ROI':'x1, y1, x2, y2 search area for game_running.png',
  'RUNNING_MATCH_THRESHOLD':'0.0-1.0 template match score',
  'RUNNING_CHECK_CACHE_AGE_S':'reuse last screenshot if younger than this',
  'RUNNING_LOG_LEVEL':'FULL | TXT | UI',
  /* freebies */
  'FREEBIES_CHECK_INTERVAL_S':'seconds between freebie checks',
  'FREEBIES_DETECT_ROI':'x1,y1,x2,y2 where freebie icon is on base screen',
  'FREEBIES_CLAIM_ROI':'x1,y1,x2,y2 search area inside the freebie menu',
  'FREEBIES_MATCH_THRESHOLD':'0.0-1.0 template match score',
  'FREEBIES_SCROLL_ATTEMPTS':'max slow scrolls searching the claim button',
  'FREEBIES_SCROLL_TO_TOP_COUNT':'fast scrolls used to reach top first',
  'FREEBIES_POST_OPEN_DELAY_S':'wait after tapping icon before matching claim',
  'FREEBIES_TAP_JITTER_PX':'random +/- pixel jitter on taps',
  'FREEBIES_DIAMONDS_PER_CLAIM':'logged amount per claim (wired later)',
  'FREEBIES_LOG_LEVEL':'general worker logs — FULL | TXT | UI',
  'FREEBIES_LOG_LEVEL_CLAIMED':'"Freebie Claimed +X Diamonds" line — FULL | TXT | UI',
  'FREEBIES_CLOSE_ROI':'x1,y1,x2,y2 search area for close_menu.png after claim',
  'FREEBIES_POST_CLAIM_DELAY_S':'wait after claim before searching close',
  /* lootbug founders */
  'LOOTBUG_FOUNDERS_ENABLED':'only enable if you own the Founders Bundle — checks for founders lootbox each scan cycle',
  'LOOTBUG_FOUNDERS_LOG_LEVEL':'founders detection + tap events — FULL | TXT | UI',
  /* lootbug */
  'LOOTBUG_CHECK_INTERVAL_S':'seconds between lootbug scans',
  'LOOTBUG_BUSY_RETRY_S':'retry delay if another feature is using ingame action lock',
  'LOOTBUG_DETECT_ROI':'x1,y1,x2,y2 search area for the lootbug',
  'LOOTBUG_MATCH_THRESHOLD':'0.0-1.0 template match score',
  'LOOTBUG_SCREEN_REUSE_AGE_S':'reuse game_scr.png if younger than this (sec)',
  'LOOTBUG_TAP_JITTER_PX':'random +/- pixel jitter on taps',
  'LOOTBUG_POST_CLICK_DELAY_S':'wait between lootbug-tap and close-tap',
  'LOOTBUG_CLOSE_ROI':'x1,y1,x2,y2 search area for close_menu.png after click',
  'LOOTBUG_LOG_LEVEL':'general worker logs — FULL | TXT | UI',
  'LOOTBUG_LOG_LEVEL_DETECT':'template-match outcome logs — FULL | TXT | UI',
  'LOOTBUG_LOG_LEVEL_CLICK':'tap event logs — FULL | TXT | UI',
  'LOOTBUG_LOG_LEVEL_BUSY':'postponed-by-lock logs — FULL | TXT | UI',
  'LOOTBUG_BUY_GEM_UPGRADES_ENABLED':'default for gem-bonus purchase on bot start (tri-state toggle cycles to this)',
  'LOOTBUG_BONUS_DETECT_ROI':'x1,y1,x2,y2 search area for bonus_tpl_*.png inside the lootbug popup',
  'LOOTBUG_BONUS_BUY_ROI':'x1,y1,x2,y2 — double-tap target (center + jitter). 2x taps also close the popup',
  'LOOTBUG_BONUS_TAP_JITTER_PX':'random +/- pixel jitter on bonus-buy taps',
  'LOOTBUG_BONUS_DOUBLE_CLICK_DELAY_S':'pause between the two buy-taps',
  'LOOTBUG_LOG_LEVEL_BONUS':'bonus-purchase events — FULL | TXT | UI',
  /* scroll */
  'SCROLL_DEFAULT_AREA':'x1, y1, x2, y2 rectangle for scrolls with no area given',
  'SCROLL_DEFAULT_SPEED':'slow | mid | fast',
  'SCROLL_DURATION_SLOW_MS':'drag time for speed=slow',
  'SCROLL_DURATION_MID_MS':'drag time for speed=mid',
  'SCROLL_DURATION_FAST_MS':'drag time for speed=fast',
  'SCROLL_DISTANCE_SLOW_PX':'vertical travel for speed=slow',
  'SCROLL_DISTANCE_MID_PX':'vertical travel for speed=mid',
  'SCROLL_DISTANCE_FAST_PX':'vertical travel for speed=fast',
  'SCROLL_EDGE_PADDING_PX':'safety margin from area edges',
  'SCROLL_LOG_LEVEL':'FULL | TXT | UI',
};

/* Unit suffixes for settings fields */
const FIELD_UNITS={
  /* adb */
  'ADB_CONNECT_TIMEOUT':'s',
  /* timers */
  'MAIN_LOOP_TICK':'s',
  /* workflow intervals */
  'wf1_interval':'s','wf2_interval':'s','wf3_interval':'s','wf4_interval':'s','wf5_interval':'s','wf6_interval':'s',
  /* scroll */
  'SCROLL_DURATION_SLOW_MS':'ms','SCROLL_DURATION_MID_MS':'ms','SCROLL_DURATION_FAST_MS':'ms',
  'SCROLL_DISTANCE_SLOW_PX':'px','SCROLL_DISTANCE_MID_PX':'px','SCROLL_DISTANCE_FAST_PX':'px',
  'SCROLL_EDGE_PADDING_PX':'px',
  /* running detection */
  'RUNNING_CHECK_CACHE_AGE_S':'s',
  /* freebies */
  'FREEBIES_CHECK_INTERVAL_S':'s','FREEBIES_POST_OPEN_DELAY_S':'s','FREEBIES_POST_CLAIM_DELAY_S':'s',
  'FREEBIES_TAP_JITTER_PX':'px',
  /* lootbug */
  'LOOTBUG_CHECK_INTERVAL_S':'s','LOOTBUG_BUSY_RETRY_S':'s',
  'DETECT_LEVEL_INTERVAL_S':'s','DETECT_LEVEL_CACHE_MAX_AGE_S':'s',
  'DETECT_LEVEL_NMS_MIN_DX_PX':'px',
  'LOOTBUG_SCREEN_REUSE_AGE_S':'s','LOOTBUG_POST_CLICK_DELAY_S':'s',
  'LOOTBUG_TAP_JITTER_PX':'px',
  'LOOTBUG_BONUS_TAP_JITTER_PX':'px','LOOTBUG_BONUS_DOUBLE_CLICK_DELAY_S':'s',
  /* workflows */
  'WF_INTERVAL_VARIANCE_PCT':'%',
  'WORKFLOWS_TAP_JITTER_PX':'px',
  'WORKFLOWS_SCREEN_REUSE_AGE_S':'s',
  'WORKFLOWS_BUSY_RETRY_S':'s',
};

/* Descriptions shown below certain sections */
const SECTION_NOTES={
  'screenshot_viewer':'Defines which files in <code>./temp/</code> are checked for the sidebar screenshot viewer. The <b>newest</b> matching file is shown. Edit as comma-separated filenames, e.g. <code>game_scr.png, freebie_scr.png</code>.',
  'adb':'<span style="color:var(--yellow)">\u26A0 DEVICE</span> is the <b>main device</b>. If unreachable, the bot tries <b>ADB_SCAN_PORTS</b> as fallbacks.',
  'startup_defaults':'Controls which features are <b>ON</b> or <b>OFF</b> when the bot starts, and which UI panels are visible. Requires <b>restart</b> to take effect.',
  'scroll':'The game requires a <b>drag</b> gesture (finger stays down). Higher <b>duration</b> = more drag-like. Too short = flick, ignored by the game. <b>SCROLL_DEFAULT_AREA</b> is used when a feature calls <code>scroll()</code> without an explicit area.',
  'running_detection':'Detects if the game is foregrounded by matching <code>game_running.png</code> in ROI. Cached screenshots younger than <b>CACHE_AGE</b>s are reused — no extra ADB pull.',
  'freebies':'<b>Auto-Freebies</b>: every <b>CHECK_INTERVAL</b>s, look for the freebie icon in <b>DETECT_ROI</b>. If found, open menu, scroll through <b>CLAIM_ROI</b> and tap claim.',
  'lootbug_founders':'<b>Founders Lootbox</b>: checked once per Lootbug scan cycle. If a founders lootbox is detected in its ROI it is tapped and the popup dismissed automatically. <span style="color:var(--yellow)">&#x26A0; Only activate if you have purchased the Founders Bundle.</span>',
  'lootbug':'<b>Auto-Lootbug</b>: every <b>CHECK_INTERVAL</b>s, scan <b>DETECT_ROI</b> for the Lootbug. If found, tap it (jitter), wait, then dismiss the popup via <b>close_menu.png</b> in <b>CLOSE_ROI</b>. Postponed if another feature is currently performing ingame actions.<br><b>Gem-Bonus</b> (optional): if <b>BUY_GEM_UPGRADES_ENABLED</b> and <code>images/Lootbug/bonus_tpl_*.png</code> matches inside <b>BONUS_DETECT_ROI</b>, double-tap <b>BONUS_BUY_ROI</b> instead of close — the 2x tap also dismisses the popup.',
  'workflows':'<b>Workflows</b>: user-defined step sequences (taps, swipes, template clicks). Edit them in the <b>Workflows</b> tab above. Master "Auto WF" toggle pauses all scheduling and blocks manual triggers. Per-WF intervals get a global variance (set here) plus optional per-WF override.',
  'detect_level':'<b>Detect Level</b>: periodically scans <b>ROI</b> for digit templates in <code>images/level/</code> (digit_0_tpl.png … digit_9_tpl.png), composes 1-3 digits left-to-right into the current level (1-999). Consumed by workflow if-conditions <b>level_eq / level_gte / level_lte</b>. Disable here to grey out those conditions in the editor.',
};

function loadSettings(){fetch('/api/config/settings').then(r=>r.json()).then(data=>{settingsData=data;renderSettings(data)}).catch(()=>{})}

function renderSettings(data){
  const c=document.getElementById('cfg-container');
  let h='';
  for(const[section,vals]of Object.entries(data)){
    if(typeof vals!=='object'||vals===null)continue;
    h+=`<div class="cfg-section"><div class="cfg-section-title" onclick="toggleCfgSection(this)">${section}</div><div class="cfg-fields">`;
    if(SECTION_NOTES[section]){
      h+=`<div style="font-size:.58rem;color:var(--text-dim);padding:4px 0 6px;line-height:1.4">${SECTION_NOTES[section]}</div>`;
    }
    for(const[key,val]of Object.entries(vals)){
      const id=`cfg-${section}-${key}`;
      const unit=FIELD_UNITS[key]||'';

      if(typeof val==='boolean'){
        h+=`<div class="cfg-row"><span class="cfg-key" title="${key}">${key}</span><input class="cfg-val bool" id="${id}" type="text" value="${val}" readonly onclick="toggleBool(this)" data-section="${section}" data-key="${key}"><span class="cfg-unit"></span></div>`;
      }else if(Array.isArray(val)){
        h+=`<div class="cfg-row"><span class="cfg-key" title="${key}">${key}</span><input class="cfg-val" id="${id}" type="text" value="${val.join(', ')}" data-section="${section}" data-key="${key}" data-ftype="array"><span class="cfg-unit"></span></div>`;
      }else{
        const hint=FIELD_HINTS[key]||'';
        h+=`<div class="cfg-row"><span class="cfg-key" title="${hint||key}">${key}${hint?' <span style="color:var(--text-dim);font-size:.55rem">('+hint+')</span>':''}</span><input class="cfg-val" id="${id}" type="text" value="${val}" data-section="${section}" data-key="${key}"><span class="cfg-unit">${unit}</span></div>`;
      }
    }
    h+='</div></div>';
  }
  c.innerHTML=h;
}

function toggleCfgSection(el){el.classList.toggle('open');el.nextElementSibling.classList.toggle('open')}
function toggleBool(el){el.value=el.value==='true'?'false':'true'}

function saveSettings(){
  const inputs=document.querySelectorAll('#cfg-container .cfg-val');
  const data={};
  inputs.forEach(inp=>{
    const s=inp.dataset.section,k=inp.dataset.key;
    if(!data[s])data[s]={};
    let v=inp.value.trim();
    /* Normalize decimal comma → dot (German locale fix) */
    if(inp.dataset.ftype!=='array' && v!=='true' && v!=='false'){
      v=v.replace(',','.');
    }
    if(inp.dataset.ftype==='array'){
      v=v.split(',').map(x=>{const n=parseFloat(x.trim().replace(',','.'));return isNaN(n)?x.trim():n});
    }else if(v==='true')v=true;
    else if(v==='false')v=false;
    else if(!isNaN(v)&&v!=='')v=parseFloat(v);

    data[s][k]=v;
  });
  fetch('/api/config/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(r=>r.json()).then(r=>{if(r.ok)showToast('Settings saved \u2705');else showToast('Save failed: '+(r.error||''),true)}).catch(e=>showToast('Save error: '+e,true));
}

loadSettings();
