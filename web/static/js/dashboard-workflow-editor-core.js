/* ============================================================
   dashboard-workflow-editor-core.js — State, constants, helpers
   ============================================================
   Part of the workflow-editor split. Loaded BEFORE the companion
   files (-tpl, -if, -render, -dnd, -mutations). All top-level
   `let`/`const` live in the shared script scope and are visible
   to every companion file.

   Reads from /api/config/workflows/full (slug -> wf dict) and
   saves the same shape back. WF dict shape mirrors config_workflows.py.

   Step types:
     tap_roi, tap_xy, swipe, click_template, wait,
     rainbow_check, call_workflow, hold_and_wiggle,
     if (block-step with branches + else)

   Step paths (address a step inside a WF):
     "3"                           -> wf.steps[3]
     "3.branches.0.steps.1"        -> wf.steps[3].branches[0].steps[1]
     "3.else_steps.0"              -> wf.steps[3].else_steps[0]
*/

const WFE_HIDE_INACTIVE_KEY = 'wfe.hideInactive';
const WFE_IF_COLLAPSED_KEY = 'wfe.ifCollapsed';
let wfeData = {}, wfeTpls = [], wfeHideInactive = (()=>{
  try { return localStorage.getItem(WFE_HIDE_INACTIVE_KEY) === '1'; } catch(e) { return false; }
})();

const STEP_TYPES = [
  {value:'if',              label:'If / ElseIf / Else (block)'},
  {value:'tap_roi',         label:'Tap (random in ROI)'},
  {value:'tap_xy',          label:'Tap (fixed XY)'},
  {value:'swipe',           label:'Swipe / Scroll'},
  {value:'click_template',  label:'Click Template'},
  {value:'click_rotating',  label:'Click Rotating Template'},
  {value:'wait',            label:'Wait (Sleep)'},
  {value:'rainbow_check',   label:'Rainbow Floor Check'},
  {value:'call_workflow',   label:'Call Workflow'},
  {value:'hold_and_wiggle', label:'Hold & Wiggle (chained swipes)'},
];

const STEP_FIELDS = {
  'tap_roi': [
    {k:'roi',              label:'ROI (x1,y1,x2,y2)', type:'roi'},
    {k:'jitter',           label:'Jitter (px)',       type:'num', step:1},
    {k:'count',            label:'Count (repeats)',   type:'num', step:1, hint:'Blank/1 = single tap. Higher = repeat N times with interval.'},
    {k:'count_interval_s', label:'Count Interval (s)',type:'num', step:0.05, hint:'Sleep between repeats when Count > 1.'},
    {k:'sleep_after',      label:'Sleep After (s)',   type:'num', step:0.05},
  ],
  'tap_xy': [
    {k:'x',                label:'X',                 type:'num', step:1},
    {k:'y',                label:'Y',                 type:'num', step:1},
    {k:'jitter',           label:'Jitter (px)',       type:'num', step:1},
    {k:'hold_ms',          label:'Hold (ms)',         type:'num', step:50, hint:'Blank = default (~100ms). Set e.g. 5000 for 5s burst-fire / long-press.'},
    {k:'count',            label:'Count (repeats)',   type:'num', step:1, hint:'Blank/1 = single tap. Higher = repeat N times with interval.'},
    {k:'count_interval_s', label:'Count Interval (s)',type:'num', step:0.05, hint:'Sleep between repeats when Count > 1.'},
    {k:'sleep_after',      label:'Sleep After (s)',   type:'num', step:0.05},
  ],
  'swipe': [
    {k:'direction',        label:'Direction',         type:'select', options:['up','down']},
    {k:'speed',            label:'Speed',             type:'select', options:['slow','mid','fast']},
    {k:'area',             label:'Area (x1,y1,x2,y2, blank=default)', type:'roi'},
    {k:'duration_ms',      label:'Duration (ms)',     type:'num', step:50, hint:'Blank = use speed preset. Longer duration = longer drag hold => faster inertial scroll in-game.'},
    {k:'distance_px',      label:'Distance (px)',     type:'num', step:10, hint:'Blank = use speed preset. Game scroll velocity scales with drag distance.'},
    {k:'count',            label:'Count (repeats)',   type:'num', step:1, hint:'Blank/1 = single swipe. Higher = repeat N times with interval.'},
    {k:'count_interval_s', label:'Count Interval (s)',type:'num', step:0.05, hint:'Sleep between repeats when Count > 1.'},
    {k:'sleep_after',      label:'Sleep After (s)',   type:'num', step:0.05},
  ],
  'click_template': [
    {k:'template',            label:'Template (./images/workflows/)', type:'tpl'},
    {k:'roi',                 label:'ROI (x1,y1,x2,y2)',              type:'roi'},
    {k:'threshold',           label:'Threshold',                      type:'num', step:0.01},
    {k:'offset_x',            label:'Offset X',                       type:'num', step:1},
    {k:'offset_y',            label:'Offset Y',                       type:'num', step:1},
    {k:'jitter',              label:'Jitter (px)',                    type:'num', step:1},
    {k:'clicks',              label:'Clicks (repeat)',                type:'num', step:1},
    {k:'click_interval_s',    label:'Click Interval (s)',             type:'num', step:0.05},
    {k:'hold_ms',             label:'Hold (ms)',                      type:'num', step:50, hint:'Blank = default (~100ms). Set e.g. 5000 for 5s burst-fire / long-press. Applied to every click when Clicks > 1.'},
    {k:'optional',            label:'Optional (no fail if missing)',  type:'bool'},
    {k:'use_prev_screenshot', label:'Use Prev Screenshot',            type:'bool'},
    {k:'sleep_after',         label:'Sleep After (s)',                type:'num', step:0.05},
  ],
  'click_rotating': [
    {k:'template',            label:'Template (./images/workflows/)', type:'tpl'},
    {k:'roi',                 label:'ROI (x1,y1,x2,y2)',              type:'roi'},
    {k:'threshold',           label:'Threshold',                      type:'num', step:0.01},
    {k:'rotations',           label:'Rotations (N evenly over 360°)', type:'num', step:1, hint:'How many rotated copies of the template to test. 24 = 15° steps. Higher = better angle precision but slower first match (cached afterwards).'},
    {k:'mask',                label:'Mask',                           type:'select', options:['circle','none'], hint:'circle = use an inscribed circular mask so only the center disk of the template is matched (recommended for round emblems like star signs — avoids corner artifacts from rotation, expect true-match scores ~0.95+). none = match the full square (fall-back for non-circular templates; uses the same metric as click_template, threshold ~0.8).'},
    {k:'downscale',           label:'Downscale (1=full, 2=half)',     type:'num', step:1, hint:'Pre-scale screen + template by 1/N before matching. 2 = ~10x faster overall and usually still accurate enough. Use 1 if precision suffers on small templates. Cached separately per downscale value.'},
    {k:'offset_x',            label:'Offset X',                       type:'num', step:1},
    {k:'offset_y',            label:'Offset Y',                       type:'num', step:1},
    {k:'jitter',              label:'Jitter (px)',                    type:'num', step:1},
    {k:'clicks',              label:'Clicks (repeat)',                type:'num', step:1},
    {k:'click_interval_s',    label:'Click Interval (s)',             type:'num', step:0.05},
    {k:'hold_ms',             label:'Hold (ms)',                      type:'num', step:50, hint:'Blank = default (~100ms). Applied to every click when Clicks > 1.'},
    {k:'optional',            label:'Optional (no fail if missing)',  type:'bool'},
    {k:'use_prev_screenshot', label:'Use Prev Screenshot',            type:'bool'},
    {k:'log_mode',            label:'Log Mode',                       type:'select', options:['both','hit_only','miss_only','none'], hint:'Which log lines to emit (workflow log_level_step still controls FULL/TXT/UI routing).'},
    {k:'sleep_after',         label:'Sleep After (s)',                type:'num', step:0.05},
  ],
  'wait': [
    {k:'seconds',             label:'Seconds',                        type:'num', step:0.1},
  ],
  'rainbow_check': [
    {k:'roi',                    label:'ROI (x1,y1,x2,y2)',           type:'roi'},
    {k:'sat_min',                label:'Saturation Min (0..255)',     type:'num', step:1},
    {k:'val_min',                label:'Value Min (0..255)',          type:'num', step:1},
    {k:'min_sat_pixels',         label:'Min Saturated Pixels',        type:'num', step:100},
    {k:'min_hue_buckets',        label:'Min Active Hue Buckets',      type:'num', step:1},
    {k:'min_pixels_per_bucket',  label:'Min Pixels / Bucket',         type:'num', step:10},
    {k:'hue_buckets',            label:'Hue Buckets (total)',         type:'num', step:1},
    {k:'min_hue_entropy',        label:'Min Hue Entropy (0..log2 N)', type:'num', step:0.05},
    {k:'optional',               label:'Optional (no abort if miss)', type:'bool'},
    {k:'use_prev_screenshot',    label:'Use Prev Screenshot',         type:'bool'},
    {k:'sleep_after',            label:'Sleep After (s)',             type:'num', step:0.05},
  ],
  'call_workflow': [
    {k:'target',              label:'Target Workflow',                type:'wf'},
    {k:'sleep_after',         label:'Sleep After (s)',                type:'num', step:0.05},
  ],
  'hold_and_wiggle': [
    {k:'roi',                 label:'ROI (x1,y1,x2,y2)',              type:'roi'},
    {k:'duration_s',          label:'Duration (s)',                   type:'num', step:0.1},
    {k:'step_ms',             label:'Step Duration (ms)',             type:'num', step:10},
    {k:'max_step_px',         label:'Max Step Size (px)',             type:'num', step:5},
    {k:'sleep_after',         label:'Sleep After (s)',                type:'num', step:0.05},
  ],
  /* 'if' is rendered separately (block-step) */
};

const WF_META_FIELDS = [
  {k:'name',                  label:'Name',                  type:'text'},
  {k:'description',           label:'Description',           type:'text'},
  {k:'interval_s',            label:'Interval (s)',          type:'num', step:1},
  {k:'interval_variance_pct', label:'Variance % (blank=use global)', type:'num', step:1},
  {k:'enabled_default',       label:'Enabled on Startup',    type:'bool'},
  {k:'log_level',             label:'Log Level (general)',   type:'loglevel'},
  {k:'log_level_step',        label:'Log Level (step)',      type:'loglevel'},
  {k:'log_level_busy',        label:'Log Level (busy)',      type:'loglevel'},
  {k:'ignore_action_lock',    label:'Ignore Action Lock',    type:'bool', hint:'Run this workflow even when a feature (Freebies/Lootbug) is currently holding the action lock. Use ONLY for very small, defensively-checked workflows (e.g. "if popup is visible, click close — otherwise nothing"). Larger workflows may interleave taps with feature actions and disrupt other flows. Note: this does NOT preempt another running workflow — workflows are still serialized on the scheduler thread. The is_game_running() check is unaffected.'},
];

const LOG_LEVELS = ['', 'FULL', 'TXT', 'UI'];

const CONDITION_KINDS = [
  {value:'template_visible',     label:'Template visible'},
  {value:'template_not_visible', label:'Template NOT visible'},
  {value:'level_eq',             label:'Level == value',  needsLevel:true},
  {value:'level_gte',            label:'Level >= value',  needsLevel:true},
  {value:'level_lte',            label:'Level <= value',  needsLevel:true},
  {value:'last_step_ok',         label:'Last step was OK'},
  {value:'last_step_failed',     label:'Last step FAILED'},
];

/* ============ LOAD ============ */
function loadWorkflows(){
  Promise.all([
    fetch('/api/config/workflows/full').then(r=>r.json()),
    fetch('/api/config/templates').then(r=>r.json()),
  ]).then(([wf,tpls])=>{
    wfeData = (wf && typeof wf === 'object' && !wf.error) ? wf : {};
    wfeTpls = Array.isArray(tpls) ? tpls : [];
    renderWorkflowEditor();
  }).catch(e=>{
    document.getElementById('wfe-container').innerHTML =
      '<div class="scr-placeholder">Error loading workflows: '+esc(String(e))+'</div>';
  });
}

function _wfeGetOpenState(){
  const open = {};
  document.querySelectorAll('.wfe-wf-hdr.open').forEach(hdr=>{
    const body = hdr.nextElementSibling;
    if(body && body.dataset.wfkey) open[body.dataset.wfkey] = true;
  });
  return open;
}

function _detectLevelEnabled(){
  try {
    const dl = (typeof botState !== 'undefined' ? (botState||{}) : {}).detect_level || {};
    return !!dl.enabled && !!dl.armed;
  } catch(e) { return false; }
}

/* ============ PATH HELPERS ============ */
function _walkStep(wf, path){
  if(!wf || !path) return null;
  const parts = String(path).split('.');
  let cur = wf.steps;
  for(let i=0;i<parts.length;i++){
    const p = parts[i];
    if(Array.isArray(cur)){
      const idx = parseInt(p);
      if(isNaN(idx) || idx<0 || idx>=cur.length) return null;
      cur = cur[idx];
    } else if(cur && typeof cur === 'object'){
      cur = cur[p];
    } else return null;
  }
  return cur;
}

function _walkParent(wf, path){
  const parts = String(path).split('.');
  const lastIdx = parseInt(parts[parts.length-1]);
  if(isNaN(lastIdx)) return [null, -1];
  let cur = wf.steps;
  for(let i=0;i<parts.length-1;i++){
    const p = parts[i];
    if(Array.isArray(cur)){
      cur = cur[parseInt(p)];
    } else if(cur && typeof cur === 'object'){
      cur = cur[p];
    } else return [null, -1];
  }
  return [cur, lastIdx];
}

function _pathDepth(path){
  const s = String(path);
  let d = 0;
  if(/\.branches\.\d+\.steps\./.test('.'+s+'.')) d++;
  if(/\.else_steps\./.test('.'+s+'.')) d++;
  return d;
}

/* Used by collect + condition kind change (resolves any dot-path starting at wf.steps). */
function _resolveFromSteps(wf, path){
  if(!wf || !path) return null;
  const parts = String(path).split('.');
  let cur = wf.steps;
  for(let i=0;i<parts.length;i++){
    const p = parts[i];
    if(Array.isArray(cur)){
      cur = cur[parseInt(p)];
    } else if(cur && typeof cur === 'object'){
      cur = cur[p];
    } else return null;
  }
  return cur;
}

/* ============ COLLECT ============ */
function collectWorkflows(){
  document.querySelectorAll('.wfe-wf-body').forEach(body=>{
    const slug = body.dataset.wfkey;
    if(!wfeData[slug]) return;
    const wf = wfeData[slug];
    /* meta fields (only direct WF-level inputs) */
    body.querySelectorAll(':scope > .wfe-fields [data-wfmeta]').forEach(el=>{
      const k = el.dataset.wfmeta;
      let v = el.value;
      const ft = el.dataset.ftype;
      if(el.tagName==='SELECT' && (v==='true'||v==='false')) v = (v==='true');
      else if(ft==='num'){ v = (v===''?null:parseFloat(v)); }
      else if(v==='') v = (k==='log_level'||k==='log_level_step'||k==='log_level_busy'||k==='interval_variance_pct') ? null : '';
      wf[k] = v;
    });
    /* All step field inputs have data-path = absolute dot-path like "3.jitter"
       or "3.branches.0.steps.1.roi". Parse path: last segment is the field key. */
    body.querySelectorAll('input[data-path], select[data-path], textarea[data-path]').forEach(el=>{
      const path = el.dataset.path;
      if(!path) return;
      const parts = path.split('.');
      const fieldKey = parts[parts.length-1];
      const stepPath = parts.slice(0, -1).join('.');
      const step = _walkStep(wf, stepPath);
      if(!step) return;
      const ft = el.dataset.ftype;
      let v = el.value;
      if(el.tagName==='SELECT' && (v==='true'||v==='false')) v = (v==='true');
      else if(ft==='num' && v!=='') v = parseFloat(v);
      else if(ft==='roi') v = v.trim()==='' ? [] : v.split(',').map(s=>Number(s.trim()));
      else if(ft==='num' && v==='') v = null;
      step[fieldKey] = v;
    });
    /* If-block per-step options (on_missing_template) */
    body.querySelectorAll('[data-ifopt]').forEach(el=>{
      const stepPath = el.dataset.stepPath;
      const k = el.dataset.ifopt;
      const step = _walkStep(wf, stepPath);
      if(step) step[k] = el.value;
    });
    /* Condition fields: data-cond-path on wrapper, data-cond-field on input */
    body.querySelectorAll('.wfe-cond').forEach(condBox=>{
      const condPath = condBox.dataset.condPath;
      const condObj = _resolveFromSteps(wf, condPath);
      if(!condObj || typeof condObj !== 'object') return;
      condBox.querySelectorAll('[data-cond-field]').forEach(el=>{
        const k = el.dataset.condField;
        let v = el.value;
        const ft = el.dataset.ftype;
        if(ft==='num' && v!=='') v = parseFloat(v);
        else if(ft==='num' && v==='') v = null;
        else if(ft==='roi') v = v.trim()==='' ? [] : v.split(',').map(s=>Number(s.trim()));
        condObj[k] = v;
      });
    });
  });
  _wfeStripNullSteps(wfeData);
  return wfeData;
}

function _wfeStripNullSteps(data){
  const cleanList = (arr)=>{
    if(!Array.isArray(arr)) return;
    for(let i=arr.length-1;i>=0;i--){
      const st = arr[i];
      if(!st || typeof st !== 'object' || Array.isArray(st)){
        arr.splice(i,1); continue;
      }
      if(st.type === 'if'){
        (st.branches||[]).forEach(br=>{ if(br && typeof br==='object') cleanList(br.steps); });
        if(Array.isArray(st.else_steps)) cleanList(st.else_steps);
      }
    }
  };
  for(const slug of Object.keys(data||{})){
    const wf = data[slug];
    if(wf && Array.isArray(wf.steps)) cleanList(wf.steps);
  }
}

/* ============ SAVE ============ */
function saveWorkflows(){
  const data = collectWorkflows();
  fetch('/api/config/workflows/full',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(data)
  }).then(r=>r.json()).then(r=>{
    if(r.ok) showToast('Workflows saved \u2705 — use Reload to apply');
    else showToast('Save failed: '+(r.error||''), true);
  }).catch(e=>showToast('Save error: '+e, true));
}
