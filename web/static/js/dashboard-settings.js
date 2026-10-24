/* ============================================================
   dashboard-settings.js — Settings editor (Obelisk Bot)
   ============================================================ */

let settingsData={};

const FIELD_HINTS={
  'TAP_HUMANIZE_ENABLED':'vary default tap duration; explicit workflow holds stay exact',
  'TAP_HOLD_MS':'base press duration (0-2000); 0 uses a plain ADB tap without duration variation',
  'TAP_HOLD_VARIANCE_PCT':'bounded +/- duration variation (0-100); values near the base are more frequent',
  'TAP_JITTER_PX':'default +/- position jitter (0-100); feature and workflow jitter settings take precedence',
  'gem_statistics_enabled':'Gem Statistics tracking + card',
  'screenshot_visible':'show Screenshot card',
  'freebies_enabled':'auto-start Freebies feature on bot launch',
  'lootbug_enabled':'auto-start Lootbug feature on bot launch',
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
  /* screenshot capture/viewer */
  'SCREENSHOT_CAPTURE_ATTEMPTS':'full capture attempts per request (1–5); each uses a new Android filename',
  'SCREENSHOT_RETRY_DELAY_S':'pause between failed full capture attempts (0–10 sec); ADB reconnect may take longer',
  'SCREENSHOT_LOG_LEVEL':'TXT = file; FULL = file + WebUI; UI = WebUI only',
  'SCREENSHOT_LOG_CACHE_HITS':'verbose cache reuse diagnostics; enable temporarily when investigating problems',
  'SCREENSHOT_VIEWER_FILES':'comma-separated filenames in ./temp/ to check (newest wins)',
  /* running detection */
  'RUNNING_ROI':'x1, y1, x2, y2 search area for game_running.png',
  'RUNNING_MATCH_THRESHOLD':'0.0-1.0 template match score',
  'RUNNING_CHECK_CACHE_AGE_S':'reuse last screenshot if younger than this',
  'RUNNING_LOG_LEVEL':'FULL | TXT | UI',
  /* freebies */
  'FREEBIES_CHECK_INTERVAL_S_FIRST':'seconds between scans after startup or activation, until the first Freebie-Gems icon is detected',
  'FREEBIES_CHECK_INTERVAL_S_SLOW':'seconds between scans after the first detection; stays in slow mode until restart or reactivation',
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
  /* founders */
  'FOUNDERS_ENABLED':'auto-start FOUNDERS BUNDLE on bot launch (requires restart)',
  'FOUNDERS_CHECK_INTERVAL_S_FIRST':'seconds between scans after startup or activation, until the first Founders Bundle is detected',
  'FOUNDERS_CHECK_INTERVAL_S_SLOW':'seconds between scans after the first detection; stays in slow mode until restart or reactivation',
  'FOUNDERS_MAX_CLAIMS_PER_CYCLE':'maximum Founders taps per cycle (1-100); fresh recheck after every tap; remaining bundles use a short retry',
  'FOUNDERS_BUSY_RETRY_S':'retry delay when another feature holds the action lock',
  'FOUNDERS_DETECT_ROI':'x1,y1,x2,y2 search area for the Founders lootbox',
  'FOUNDERS_TEMPLATE':'Founders template path relative to images/',
  'FOUNDERS_MATCH_THRESHOLD':'0.0-1.0 template match score for the Founders lootbox',
  'FOUNDERS_SCREEN_REUSE_AGE_S':'reuse game_scr.png if younger than this (sec)',
  'FOUNDERS_TAP_JITTER_PX':'random +/- pixel jitter on Founders taps',
  'FOUNDERS_LOG_LEVEL':'general worker and detection logs — FULL | TXT | UI',
  'FOUNDERS_LOG_LEVEL_CLICK':'tap event logs — FULL | TXT | UI',
  'FOUNDERS_LOG_LEVEL_BUSY':'postponed-by-lock logs — FULL | TXT | UI',
  /* lootbug */
  'LOOTBUG_CHECK_INTERVAL_S':'seconds between lootbug scans',
  'LOOTBUG_INTERVAL_VARIANCE_PCT':'random +/- percent of CHECK_INTERVAL per regular scan (0 = fixed interval, range 0-100); next countdown uses the actual scheduled time',
  'LOOTBUG_BUSY_RETRY_S':'retry delay if another feature is using ingame action lock',
  'LOOTBUG_DETECT_ROI':'x1,y1,x2,y2 search area for the lootbug',
  'LOOTBUG_MATCH_THRESHOLD':'0.0-1.0 template match score',
  'LOOTBUG_SCREEN_REUSE_AGE_S':'reuse game_scr.png if younger than this (sec)',
  'LOOTBUG_TAP_JITTER_PX':'random +/- pixel jitter on taps',
  'LOOTBUG_BUY_MAX_ATTEMPTS':'maximum Buy screenshot/tap attempts per cycle (1-100); then release the action lock without clicking Close',
  'LOOTBUG_FOUNDERS_LOOKAHEAD_S':'yield without the action lock when an enabled Founders check is due within this many seconds; 0 still yields for due checks',
  'LOOTBUG_BUY_RETRY_S':'seconds between fresh screenshot retries while the buy box is obscured; never closes the popup',
  'LOOTBUG_POST_CLICK_DELAY_S':'wait between lootbug-tap and buy-box scan',
  'LOOTBUG_LOG_LEVEL':'general worker logs — FULL | TXT | UI',
  'LOOTBUG_LOG_LEVEL_DETECT':'template-match outcome logs — FULL | TXT | UI',
  'LOOTBUG_LOG_LEVEL_CLICK':'tap event logs — FULL | TXT | UI',
  'LOOTBUG_LOG_LEVEL_BUSY':'postponed-by-lock logs — FULL | TXT | UI',
  'LOOTBUG_BONUS_TAP_JITTER_PX':'random +/- pixel jitter on buy-box tap',
  'LOOTBUG_BONUS_BUY_TEMPLATE':'buy-box template path relative to images/',
  'LOOTBUG_BONUS_BUY_ROI':'x1,y1,x2,y2 search area for the buy-box template; click the matched center once',
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
  'TAP_HOLD_MS':'ms', 'TAP_HOLD_VARIANCE_PCT':'%', 'TAP_JITTER_PX':'px',
  'SCREENSHOT_RETRY_DELAY_S':'s',
  'FOUNDERS_CHECK_INTERVAL_S_FIRST':'s','FOUNDERS_CHECK_INTERVAL_S_SLOW':'s','FOUNDERS_BUSY_RETRY_S':'s',
  'FOUNDERS_SCREEN_REUSE_AGE_S':'s',
  'FOUNDERS_TAP_JITTER_PX':'px',
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
  'FREEBIES_CHECK_INTERVAL_S_FIRST':'s','FREEBIES_CHECK_INTERVAL_S_SLOW':'s','FREEBIES_POST_OPEN_DELAY_S':'s','FREEBIES_POST_CLAIM_DELAY_S':'s',
  'FREEBIES_TAP_JITTER_PX':'px',
  /* lootbug */
  'LOOTBUG_BONUS_TAP_JITTER_PX':'px','LOOTBUG_BUY_RETRY_S':'s','LOOTBUG_FOUNDERS_LOOKAHEAD_S':'s',
  'LOOTBUG_CHECK_INTERVAL_S':'s','LOOTBUG_BUSY_RETRY_S':'s',
  'LOOTBUG_INTERVAL_VARIANCE_PCT':'%',
  'DETECT_LEVEL_INTERVAL_S':'s','DETECT_LEVEL_CACHE_MAX_AGE_S':'s',
  'DETECT_LEVEL_NMS_MIN_DX_PX':'px',
  'LOOTBUG_SCREEN_REUSE_AGE_S':'s','LOOTBUG_POST_CLICK_DELAY_S':'s',
  'LOOTBUG_TAP_JITTER_PX':'px',
  /* workflows */
  'WF_INTERVAL_VARIANCE_PCT':'%',
  'WORKFLOWS_TAP_JITTER_PX':'px',
  'WORKFLOWS_SCREEN_REUSE_AGE_S':'s',
  'WORKFLOWS_BUSY_RETRY_S':'s',
};

/* Descriptions shown below certain sections */
const SECTION_NOTES={
  'tapping':'<b>Humanized Taps</b>: varies the default press duration, keeping most values near the base. Default: 100 ms with +/-30% (70-130 ms). Explicit workflow hold durations stay exact; existing feature-specific position jitter takes precedence over the global default. The switch controls duration variation only. Save and restart the bot to apply. This does not guarantee undetectable automation.',
  'screenshot_capture':'All features capture full-device PNGs using separate Android files per slot and attempt. Only validated complete images replace the local cache. Failed fresh captures return no image, never an old fallback. Logs include request/capture IDs, slot, device, attempt, phase and elapsed time. Settings require a process restart.',
  'screenshot_viewer':'Shows the newest valid PNG from <code>./temp/</code> without taking a new screenshot. Plain slot filenames only, e.g. <code>game_scr.png, freebie_scr.png</code>. The viewer can display an older last successful image during capture failures.',
  'adb':'<span style="color:var(--yellow)">\u26A0 DEVICE</span> is the <b>main device</b>. If unreachable, the bot tries <b>ADB_SCAN_PORTS</b> as fallbacks.',
  'startup_defaults':'Controls which features are <b>ON</b> or <b>OFF</b> when the bot starts, and which UI panels are visible. Requires <b>restart</b> to take effect.',
  'scroll':'The game requires a <b>drag</b> gesture (finger stays down). Higher <b>duration</b> = more drag-like. Too short = flick, ignored by the game. <b>SCROLL_DEFAULT_AREA</b> is used when a feature calls <code>scroll()</code> without an explicit area.',
  'running_detection':'Detects if the game is foregrounded by matching <code>game_running.png</code> in ROI. Cached screenshots younger than <b>CACHE_AGE</b>s are reused — no extra ADB pull.',
  'freebies':'<b>Freebie-Gems</b>: startup and each activation use FIRST until the first available freebie icon is detected, then SLOW for all subsequent scans. Defaults: FIRST 300 s, SLOW 2700 s (45 minutes). Look in <b>DETECT_ROI</b>, open the menu, scroll through <b>CLAIM_ROI</b> and tap claim. Waits for the shared action lock. Settings require a bot restart.',
  'founders':'<b>FOUNDERS BUNDLE</b>: detects Founders lootboxes and taps each once. Immediately rechecks a fresh screenshot after every successful tap, up to MAX_CLAIMS_PER_CYCLE taps (default 3). Remaining bundles or failed fresh captures use a short retry. Startup and each activation use FIRST until the first bundle is detected, then SLOW for all subsequent scans. Defaults: FIRST 180 s, SLOW 3000 s (50 minutes). Independent switch; shares the action lock with other features. Auto-start is configured under Startup Defaults. Only enable if you own the Founders Bundle. Settings require a bot restart.',
  'lootbug':'<b>Auto-Lootbug</b>: every <b>CHECK_INTERVAL</b>s with random +/- <b>INTERVAL_VARIANCE_PCT</b>% (default 15%), scan <b>DETECT_ROI</b> for the Lootbug. The status countdown shows the actual scheduled next check. If found, tap it (jitter), wait, then search for <code>images/Lootbug/lootbug_buy_bonus.png</code> in <b>BONUS_BUY_ROI</b> and click the detected buy box once. Postponed if another feature is currently performing ingame actions. If the buy box is hidden by notifications, wait <b>BUY_RETRY</b>s and retry with a fresh screenshot up to BUY_MAX_ATTEMPTS (default 5). Then give up this cycle and release the action lock. An enabled Founders check due within FOUNDERS_LOOKAHEAD seconds (default 5) has priority; Lootbug waits without the lock and aborts an ongoing Buy search early if necessary. The popup is never closed automatically. The action lock stays held only during the bounded Buy search.<br><b>Gem-Bonus selection</b>: disable Auto-Lootbug, wait for a Lootbug popup, select the bonuses you want in-game, then click <b>Buy</b>. The game remembers your selection. Enable Auto-Lootbug again afterwards.<br><b>Required in-game setting</b>: enable <b>Remove lootbug gem confirmation</b> so buying requires only one click.',
  'workflows':'<b>Workflows</b>: user-defined step sequences (taps, swipes, template clicks). Edit them in the <b>Workflows</b> tab above. Master "Auto WF" toggle pauses all scheduling and blocks manual triggers. Per-WF intervals get a global variance (set here) plus optional per-WF override.',
  'detect_level':'<b>Detect Level</b>: periodically scans <b>ROI</b> for digit templates in <code>images/level/</code> (digit_0_tpl.png … digit_9_tpl.png), composes 1-3 digits left-to-right into the current level (1-999). Consumed by workflow if-conditions <b>level_eq / level_gte / level_lte</b>. Disable here to grey out those conditions in the editor.',
};

function loadSettings(){fetch('/api/config/settings').then(r=>r.json()).then(data=>{settingsData=data;renderSettings(data)}).catch(()=>{})}

function renderSettings(data){
  const c=document.getElementById('cfg-container');
  let h='';
  for(const[section,vals]of Object.entries(data)){
    if(typeof vals!=='object'||vals===null)continue;
    const sectionLabel = section==='tapping' ? 'Humanized Taps' : section==='founders' ? 'FOUNDERS BUNDLE' : section==='startup_defaults' ? 'Startup Defaults' : section;
    h+=`<div class="cfg-section"><div class="cfg-section-title" onclick="toggleCfgSection(this)">${sectionLabel}</div><div class="cfg-fields">`;
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
    const original=settingsData[s]?.[k];
    if(inp.dataset.ftype==='array'){
      const numeric=Array.isArray(original)&&typeof original[0]==='number';
      v=v===''?[]:v.split(',').map(x=>numeric?Number(x.trim()):x.trim());
    }else if(typeof original==='boolean')v=(v==='true');
    else if(typeof original==='number')v=v===''?null:Number(v.replace(',','.'));

    data[s][k]=v;
  });
  fetch('/api/config/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(r=>r.json()).then(r=>{if(r.ok)showToast('Settings saved \u2705 — restart the bot to apply');else showToast('Save failed: '+(r.error||''),true)}).catch(e=>showToast('Save error: '+e,true));
}

loadSettings();
