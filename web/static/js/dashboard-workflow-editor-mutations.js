/* ============================================================
   dashboard-workflow-editor-mutations.js — Workflow/step ops
   ============================================================
   CRUD-style mutations for workflows and steps, plus the help
   overlay and the initial loadWorkflows() call that kicks the
   editor off once all companion scripts are loaded.
*/

/* ============ WORKFLOW-LEVEL MUTATIONS ============ */
function moveWf(slug, dir){
  const openState = _wfeGetOpenState();
  collectWorkflows();
  const slugs = Object.keys(wfeData).sort((a,b)=>parseInt(wfeData[a]?.order??999)-parseInt(wfeData[b]?.order??999));
  const i = slugs.indexOf(slug);
  if(i<0) return;
  const j = i+dir;
  if(j<0||j>=slugs.length) return;
  [slugs[i],slugs[j]] = [slugs[j],slugs[i]];
  slugs.forEach((s,k)=>{ wfeData[s].order = (k+1)*10; });
  renderWorkflowEditor(openState);
}

function toggleHideInactive(){
  const openState = _wfeGetOpenState();
  collectWorkflows();
  wfeHideInactive = !wfeHideInactive;
  try { localStorage.setItem(WFE_HIDE_INACTIVE_KEY, wfeHideInactive ? '1' : '0'); } catch(e) {}
  renderWorkflowEditor(openState);
}

function delWorkflow(slug){
  if(!confirm(`Delete workflow "${slug}"?`)) return;
  collectWorkflows();
  delete wfeData[slug];
  renderWorkflowEditor();
}

function addWorkflow(){
  collectWorkflows();
  const inp = document.getElementById('wfe-new-slug');
  const rawName = (inp?.value||'').trim();
  let slug = rawName.toLowerCase().replace(/[^a-z0-9_]/g,'_').replace(/_+/g,'_').replace(/^_|_$/g,'');
  if(!slug){ showToast('Enter a name first', true); return; }
  if(wfeData[slug]){ showToast('Slug already exists', true); return; }
  const maxOrder = Math.max(0, ...Object.values(wfeData).map(w=>parseInt(w?.order??0)));
  wfeData[slug] = {
    name: rawName,
    description: '',
    order: maxOrder + 10,
    enabled_default: false,
    inactive: false,
    interval_s: 60,
    interval_variance_pct: null,
    log_level: null,
    log_level_step: null,
    log_level_busy: null,
    steps: [],
  };
  inp.value = '';
  renderWorkflowEditor({[slug]:true});
}

/* Workflow copy: inline rename row under the source WF header */
function copyWorkflow(slug){
  collectWorkflows();
  const slot = document.getElementById('wfe-copy-'+slug);
  if(!slot) return;
  const wf = wfeData[slug];
  if(!wf) return;
  const defaultName = (wf.name || slug) + ' (Copy)';
  slot.style.display = '';
  slot.innerHTML = `
    <div class="wfe-copy-inner">
      <span class="wfe-copy-label">Copy as:</span>
      <input id="wfe-copy-input-${esc(slug)}" class="wfe-copy-input" value="${esc(defaultName)}" onkeydown="if(event.key==='Enter')confirmCopyWorkflow('${esc(slug)}');if(event.key==='Escape')cancelCopyWorkflow('${esc(slug)}')">
      <button class="btn primary wfe-mini" onclick="confirmCopyWorkflow('${esc(slug)}')">Create</button>
      <button class="btn wfe-mini" onclick="cancelCopyWorkflow('${esc(slug)}')">Cancel</button>
      <div class="wfe-copy-err" id="wfe-copy-err-${esc(slug)}"></div>
    </div>`;
  const input = document.getElementById('wfe-copy-input-'+slug);
  if(input){ input.focus(); input.select(); }
}

function cancelCopyWorkflow(slug){
  const slot = document.getElementById('wfe-copy-'+slug);
  if(slot){ slot.style.display = 'none'; slot.innerHTML = ''; }
}

function confirmCopyWorkflow(sourceSlug){
  const input = document.getElementById('wfe-copy-input-'+sourceSlug);
  const errEl = document.getElementById('wfe-copy-err-'+sourceSlug);
  const rawName = (input?.value||'').trim();
  const newSlug = rawName.toLowerCase().replace(/[^a-z0-9_]/g,'_').replace(/_+/g,'_').replace(/^_|_$/g,'');
  if(!newSlug){ if(errEl){ errEl.textContent = 'Enter a name.'; } if(input){ input.classList.add('wfe-err'); } return; }
  if(wfeData[newSlug]){ if(errEl){ errEl.textContent = `Slug "${newSlug}" already exists.`; } if(input){ input.classList.add('wfe-err'); } return; }
  collectWorkflows();
  const clone = JSON.parse(JSON.stringify(wfeData[sourceSlug]||{}));
  clone.name = rawName;
  const maxOrder = Math.max(0, ...Object.values(wfeData).map(w=>parseInt(w?.order??0)));
  clone.order = maxOrder + 10;
  clone.enabled_default = false;
  wfeData[newSlug] = clone;
  showToast(`Workflow "${rawName}" created`);
  renderWorkflowEditor({[newSlug]:true, [sourceSlug]:true});
}

function onInactiveToggle(slug, el){
  const openState = _wfeGetOpenState();
  collectWorkflows();
  if(wfeData[slug]) wfeData[slug].inactive = !!el.checked;
  if(wfeHideInactive){
    renderWorkflowEditor(openState);
    return;
  }
  const body = el.closest('.wfe-wf-body');
  const wrap = body ? body.closest('.wfe-wf') : null;
  if(wrap) wrap.classList.toggle('wfe-inactive', !!el.checked);
  const toolbar = document.querySelector('#wfe-container .wfe-toolbar span');
  if(toolbar){
    const slugs = Object.keys(wfeData);
    const inactiveCount = slugs.filter(s=>!!wfeData[s]?.inactive).length;
    toolbar.innerHTML = `${slugs.length} workflows` + (inactiveCount?` &middot; ${inactiveCount} inactive`:'');
  }
}

/* ============ STEP-LEVEL MUTATIONS ============ */
function delStep(slug, path){
  collectWorkflows();
  const [container, idx] = _walkParent(wfeData[slug], path);
  if(!Array.isArray(container) || idx < 0) return;
  container.splice(idx, 1);
  renderWorkflowEditor();
}

function copyStep(slug, path){
  collectWorkflows();
  const [container, idx] = _walkParent(wfeData[slug], path);
  if(!Array.isArray(container) || idx < 0) return;
  const clone = JSON.parse(JSON.stringify(container[idx]));
  container.splice(idx+1, 0, clone);
  renderWorkflowEditor();
}

function moveStep(slug, path, dir){
  collectWorkflows();
  const [container, idx] = _walkParent(wfeData[slug], path);
  if(!Array.isArray(container) || idx < 0) return;
  const nidx = idx + dir;
  if(nidx<0 || nidx>=container.length) return;
  [container[idx], container[nidx]] = [container[nidx], container[idx]];
  renderWorkflowEditor();
}

function toggleStepDisabled(slug, path){
  collectWorkflows();
  const step = _walkStep(wfeData[slug], path);
  if(step) step._disabled = !step._disabled;
  renderWorkflowEditor();
}

function addStep(slug, containerPath, selId){
  collectWorkflows();
  const selEl = document.getElementById(selId);
  if(!selEl) return;
  const type = selEl.value;
  const step = _defaultStep(type);
  const container = _getContainerByPath(wfeData[slug], containerPath);
  if(!Array.isArray(container)) return;
  container.push(step);
  renderWorkflowEditor();
}

/* Return the array addressed by containerPath (empty string = wf.steps). */
function _getContainerByPath(wf, containerPath){
  if(!wf) return null;
  if(!containerPath) return wf.steps;
  const parts = String(containerPath).split('.');
  let cur = wf.steps;
  for(let i=0;i<parts.length;i++){
    const p = parts[i];
    if(Array.isArray(cur)){
      const idx = parseInt(p);
      if(isNaN(idx)) return null;
      cur = cur[idx];
    } else if(cur && typeof cur === 'object'){
      cur = cur[p];
    } else return null;
  }
  return cur;
}

function _defaultStep(type){
  const s = {type, _disabled:false, sleep_after:0.3};
  if(type==='tap_roi')         Object.assign(s, {roi:[0,0,100,100], jitter:4});
  if(type==='tap_xy')          Object.assign(s, {x:450, y:800, jitter:4});
  if(type==='swipe')           Object.assign(s, {direction:'up', speed:'mid', area:null});
  /* click_template intentionally starts with an empty template so the picker
     opens on a fully collapsed tree; user must pick one explicitly. */
  if(type==='click_template')  Object.assign(s, {template:'', roi:[0,0,900,1600], threshold:0.8, offset_x:0, offset_y:0, jitter:4, clicks:1, click_interval_s:0.5, optional:false, use_prev_screenshot:false});
  if(type==='click_rotating')  Object.assign(s, {template:'', roi:[0,0,900,1600], threshold:0.95, rotations:24, mask:'circle', downscale:2, offset_x:0, offset_y:0, jitter:4, clicks:1, click_interval_s:0.5, optional:false, use_prev_screenshot:false, log_mode:'both'});
  if(type==='wait')            Object.assign(s, {seconds:1.0});
  if(type==='rainbow_check')   Object.assign(s, {roi:[115,269,813,1041], sat_min:180, val_min:150, min_sat_pixels:40000, min_hue_buckets:5, min_pixels_per_bucket:200, hue_buckets:12, min_hue_entropy:1.5, optional:false, use_prev_screenshot:false});
  if(type==='call_workflow')   Object.assign(s, {target:''});
  if(type==='hold_and_wiggle') Object.assign(s, {roi:[123,247,768,1060], duration_s:5.0, step_ms:200, max_step_px:120});
  if(type==='if'){
    Object.assign(s, {
      on_missing_template: 'false',
      branches: [
        {condition:{kind:'template_visible', template:'', roi:[0,0,900,1600], threshold:0.8}, steps:[]},
      ],
      else_steps: null,
    });
  }
  return s;
}

/* ============ HELP OVERLAY (Info button) ============ */
function showWorkflowsHelp(e){
  if(e) e.stopPropagation();
  const ov = document.createElement('div');
  ov.className = 'gs-help-overlay';
  ov.onclick = function(ev){ if(ev.target === ov) ov.remove(); };
  ov.innerHTML = '<div class="gs-help-box">'
    + '<span class="gs-h-close" onclick="this.closest(\'.gs-help-overlay\').remove()">&times;</span>'
    + '<h3>\u26D3\uFE0F Workflows &mdash; Overview</h3>'

    + '<h4>What is a workflow?</h4>'
    + '<p>A <b>workflow</b> is a named sequence of <b>steps</b> executed by the bot. '
    + 'Each workflow has its own <i>interval</i> (with optional variance) and can be toggled '
    + 'individually via its <b>Auto</b> button. The master <b>Workflow</b> switch located at "CONTROLS" pauses '
    + 'the scheduler for all workflows at once.</p>'
    + '<p>A running workflow holds the in-game action lock for its entire duration &mdash; '
    + 'Freebies, Lootbug and other features wait until it finishes (dont overfeed!).</p>'

    + '<h4>Step types</h4>'
    + '<p><b>Tap (ROI / XY)</b> &mdash; tap a random point inside an ROI, or a fixed pixel. '
    + '<b>Swipe</b> &mdash; drag-scroll up/down in an area. <b>Click Template</b> &mdash; '
    + 'find a PNG template on screen and tap it (with offsets, repeats, hold-ms). '
    + '<b>Wait</b> &mdash; sleep. <b>Rainbow Check</b>, <b>Hold &amp; Wiggle</b>, '
    + '<b>Call Workflow</b> &mdash; specialised actions. <b>If / ElseIf / Else</b> &mdash; '
    + 'conditional execution (see below).</p>'
    + '<p><b>Count</b> (tap/swipe): repeat the action N times with a configurable interval '
    + '&mdash; useful for dumb-repeat loops that don\'t need their own step each time.</p>'
    + '<p><b>Comment</b> (\u{1F4DD} field on every step): free text, purely for you to keep the '
    + 'overview. Ignored by the executor.</p>'

    + '<h4>If / ElseIf / Else blocks</h4>'
    + '<p>An <b>If</b> block wraps conditional steps. It has one or more <b>branches</b> '
    + '(the first is <i>IF</i>, further ones are <i>ELSEIF</i>) and an optional <b>ELSE</b>. '
    + 'The first branch whose condition evaluates to <i>true</i> runs; if none matches and an '
    + 'ELSE exists, its steps run instead.</p>'
    + '<p>Click the \u25BE next to the block title to <b>collapse</b> long If-blocks &mdash; '
    + 'the state is remembered per block via localStorage.</p>'
    + '<p><b>Supported conditions</b>:</p>'
    + '<p style="margin-left:10px">'
    + '&bull; <b>Template visible / not visible</b> &mdash; template match in ROI<br>'
    + '&bull; <b>Level ==/&ge;/&le; value</b> &mdash; uses the <i>Detect Level</i> feature '
    + '(disabled here if the feature is off)<br>'
    + '&bull; <b>Last step OK / Last step FAILED</b> &mdash; functional result of the previous '
    + 'regular step. An <i>optional</i> click_template that missed counts as NOT OK.'
    + '</p>'
    + '<p><b>On missing template</b>: when a template-visible condition references a template '
    + 'that does not match, the default is to treat the condition as <i>false</i>. Switch to '
    + '<b>fail workflow</b> to abort the whole WF in that case.</p>'
    + '<p>Nesting depth is limited to <b>1</b>: you cannot place an If-block inside another '
    + 'If-block\'s branch. The editor hides the option in that context.</p>'

    + '<h4>Editor controls</h4>'
    + '<p>Each step has buttons for <b>disable</b> (\u25CE), <b>move</b> (\u25B2\u25BC), '
    + '<b>duplicate</b> (\u29C9), and <b>delete</b> (\u2715). You can also <b>drag &amp; drop</b> '
    + 'steps to reorder them &mdash; drop <i>onto</i> another step to place above/below, or '
    + 'drop onto an IF/ELSE branch body (highlighted blue) to move the step inside.</p>'
    + '<p>The <b>\u29C9</b> button in a workflow header <b>copies the whole workflow</b>. '
    + 'An inline rename field appears; press <i>Enter</i> to confirm.</p>'

    + '<p class="gs-h-dim" style="margin-top:10px">Changes are saved via <b>Save Workflows</b>, '
    + 'then applied via <b>\uD83D\uDD04 Reload</b> without restarting the bot.</p>'
    + '</div>';
  document.body.appendChild(ov);
}

/* Kick off the editor once every companion script has defined its globals. */
loadWorkflows();
