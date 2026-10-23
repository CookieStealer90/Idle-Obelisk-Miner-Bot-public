/* ============================================================
   dashboard-workflow-editor-if.js — If / ElseIf / Else blocks
   ============================================================
   Rendering + mutations for the `if` block-step, condition editor,
   and the collapse/expand UI (state persisted in localStorage).
*/

/* ---- Collapse state ---- */
let _ifCollapsedSet = null;
function _loadIfCollapsed(){
  if(_ifCollapsedSet) return _ifCollapsedSet;
  try { _ifCollapsedSet = new Set(JSON.parse(localStorage.getItem(WFE_IF_COLLAPSED_KEY)||'[]')); }
  catch(e){ _ifCollapsedSet = new Set(); }
  return _ifCollapsedSet;
}
function _saveIfCollapsed(){
  try { localStorage.setItem(WFE_IF_COLLAPSED_KEY, JSON.stringify(Array.from(_ifCollapsedSet||[]))); } catch(e){}
}
function _isIfCollapsed(slug, path){ return _loadIfCollapsed().has(slug+':'+path); }

function toggleIfCollapse(slug, path, btn, ev){
  if(ev){ ev.stopPropagation(); ev.preventDefault(); }
  const set = _loadIfCollapsed();
  const key = slug+':'+path;
  const block = btn.closest('.wfe-if-block');
  if(!block) return;
  if(set.has(key)){
    set.delete(key);
    block.classList.remove('wfe-collapsed');
    btn.textContent = '\u25BE';
    btn.title = 'Collapse block';
  } else {
    set.add(key);
    block.classList.add('wfe-collapsed');
    btn.textContent = '\u25B8';
    btn.title = 'Expand block';
  }
  _saveIfCollapsed();
}

function _ensureIfStyles(){
  if(document.getElementById('wfe-if-collapse-styles')) return;
  const s = document.createElement('style');
  s.id = 'wfe-if-collapse-styles';
  s.textContent = `
    .wfe-if-block.wfe-collapsed > .wfe-if-body { display:none; }
    .wfe-if-collapse-btn {
      cursor:pointer; background:none; border:1px solid transparent;
      color:var(--text-dim,#888); font-size:.7rem; padding:0 4px;
      margin-right:4px; border-radius:3px; line-height:1;
    }
    .wfe-if-collapse-btn:hover { color:var(--accent,#4a9); border-color:var(--border,#333); }
  `;
  document.head.appendChild(s);
}

/* ---- Render ---- */
function renderIfStep(step, path, slug){
  _ensureIfStyles();
  const isDis = !!step._disabled;
  const depth = _pathDepth(path);
  const branches = Array.isArray(step.branches) ? step.branches : [];
  const elseSteps = Array.isArray(step.else_steps) ? step.else_steps : null;
  const onMissing = step.on_missing_template || 'false';
  const collapsed = _isIfCollapsed(slug, path);

  let h = `<div class="wfe-step wfe-if-block${isDis?' disabled':''}${collapsed?' wfe-collapsed':''}" draggable="true" data-path="${esc(path)}" data-slug="${esc(slug)}" ondragstart="onStepDragStart(event)" ondragend="onStepDragEnd(event)" ondragover="onStepDragOver(event)" ondrop="onStepDrop(event)" ondragleave="onStepDragLeave(event)">`;
  /* Header */
  h += `<div class="wfe-step-hdr">`;
  h += `<span class="wfe-step-drag" title="Drag to reorder">\u2630</span>`;
  h += `<button class="wfe-if-collapse-btn" onclick="toggleIfCollapse('${esc(slug)}','${esc(path)}',this,event)" title="${collapsed?'Expand':'Collapse'} block">${collapsed?'\u25B8':'\u25BE'}</button>`;
  h += `<span class="wfe-step-num">${_pathDisplayNum(path)}</span>`;
  h += `<span class="wfe-step-type wfe-if-label">\u2756 If / ElseIf / Else</span>`;
  h += `<div class="wfe-step-controls">`;
  h += `<button class="wfe-step-btn toggle-dis" onclick="toggleStepDisabled('${esc(slug)}','${esc(path)}')" title="${isDis?'Enable':'Disable'} block">${isDis?'\u25C9':'\u25CE'}</button>`;
  h += `<button class="wfe-step-btn move" onclick="moveStep('${esc(slug)}','${esc(path)}',-1)" title="Move up">\u25B2</button>`;
  h += `<button class="wfe-step-btn move" onclick="moveStep('${esc(slug)}','${esc(path)}',1)" title="Move down">\u25BC</button>`;
  h += `<button class="wfe-step-btn copy" onclick="copyStep('${esc(slug)}','${esc(path)}')" title="Duplicate block">\u29C9</button>`;
  h += `<button class="wfe-step-btn del" onclick="delStep('${esc(slug)}','${esc(path)}')" title="Delete">\u2715</button>`;
  h += `</div></div>`;

  /* Note field (always visible, also when collapsed) */
  h += _renderStepNote(step, path);

  /* Collapsible body */
  h += `<div class="wfe-if-body">`;

  /* Block-level options */
  h += `<div class="wfe-if-options">`;
  h += `<label>On missing template:</label>`;
  h += `<select data-ifopt="on_missing_template" data-step-path="${esc(path)}">`;
  h += `<option value="false" ${onMissing==='false'?'selected':''}>condition = false (continue)</option>`;
  h += `<option value="fail_wf" ${onMissing==='fail_wf'?'selected':''}>fail workflow (abort)</option>`;
  h += `</select>`;
  h += `<button class="btn wfe-mini" onclick="addElseIf('${esc(slug)}','${esc(path)}')" title="Add an ElseIf branch">+ ElseIf</button>`;
  if(elseSteps===null){
    h += `<button class="btn wfe-mini" onclick="addElseBranch('${esc(slug)}','${esc(path)}')" title="Add Else branch">+ Else</button>`;
  }
  h += `</div>`;

  /* Ensure at least one branch exists visually */
  const shownBranches = branches.length > 0 ? branches : [{condition:{kind:'template_visible',template:'',roi:[0,0,900,1600],threshold:0.8}, steps:[]}];

  shownBranches.forEach((br, bi)=>{
    const brPath = `${path}.branches.${bi}`;
    const cond = br.condition || {};
    const label = bi === 0 ? 'IF' : `ELSEIF #${bi}`;
    h += `<div class="wfe-if-branch">`;
    h += `<div class="wfe-if-branch-hdr"><span class="wfe-if-branch-label">${label}</span>`;
    if(bi > 0){
      h += `<button class="wfe-step-btn del" style="margin-left:auto" onclick="delBranch('${esc(slug)}','${esc(path)}',${bi})" title="Remove this ElseIf">\u2715</button>`;
    } else {
      h += `<div style="flex:1"></div>`;
    }
    h += `</div>`;
    h += renderConditionEditor(cond, `${brPath}.condition`);
    const brStepsPath = `${brPath}.steps`;
    h += `<div class="wfe-branch-steps wfe-steps-list" data-container-path="${esc(brStepsPath)}" data-slug="${esc(slug)}" ondragover="onContainerDragOver(event)" ondrop="onContainerDrop(event)" ondragleave="onContainerDragLeave(event)">`;
    (br.steps||[]).forEach((s, si)=>{
      h += renderStep(s, `${brStepsPath}.${si}`, slug);
    });
    h += `</div>`;
    h += renderAddStepRow(slug, brStepsPath, depth+1);
    h += `</div>`;
  });

  if(elseSteps !== null){
    const elsePath = `${path}.else_steps`;
    h += `<div class="wfe-if-branch wfe-if-else">`;
    h += `<div class="wfe-if-branch-hdr"><span class="wfe-if-branch-label">ELSE</span>`;
    h += `<button class="wfe-step-btn del" style="margin-left:auto" onclick="delElseBranch('${esc(slug)}','${esc(path)}')" title="Remove Else">\u2715</button>`;
    h += `</div>`;
    h += `<div class="wfe-branch-steps wfe-steps-list" data-container-path="${esc(elsePath)}" data-slug="${esc(slug)}" ondragover="onContainerDragOver(event)" ondrop="onContainerDrop(event)" ondragleave="onContainerDragLeave(event)">`;
    (elseSteps||[]).forEach((s, si)=>{
      h += renderStep(s, `${elsePath}.${si}`, slug);
    });
    h += `</div>`;
    h += renderAddStepRow(slug, elsePath, depth+1);
    h += `</div>`;
  }

  /* Sleep after block */
  h += `<div class="wfe-fields" style="margin-top:6px">`;
  h += renderField({k:'sleep_after', label:'Sleep After (s)', type:'num', step:0.05}, step.sleep_after, slug, `${path}.sleep_after`, false, false, path);
  h += `</div>`;

  h += `</div>`; /* /.wfe-if-body */
  h += `</div>`;
  return h;
}

function renderConditionEditor(cond, condPath){
  cond = cond || {};
  const kind = cond.kind || 'template_visible';
  const lvlEnabled = _detectLevelEnabled();
  let h = `<div class="wfe-cond" data-cond-path="${esc(condPath)}">`;
  h += `<div class="wfe-cond-row">`;
  h += `<label>Condition</label>`;
  h += `<select data-cond-field="kind" onchange="onConditionKindChange(this)">`;
  CONDITION_KINDS.forEach(k=>{
    const disabled = k.needsLevel && !lvlEnabled ? 'disabled' : '';
    const tip = (k.needsLevel && !lvlEnabled) ? ' title="Detect Level feature is disabled — enable it in Settings"' : '';
    const sel = (kind === k.value) ? 'selected' : '';
    h += `<option value="${k.value}" ${disabled} ${sel}${tip}>${esc(k.label)}${k.needsLevel && !lvlEnabled ? ' (disabled)' : ''}</option>`;
  });
  h += `</select></div>`;

  if(kind === 'template_visible' || kind === 'template_not_visible'){
    h += `<div class="wfe-cond-row"><label>Template</label>`;
    h += _renderTplPicker(cond.template, `data-cond-field="template"`);
    h += `</div>`;
    const roiStr = Array.isArray(cond.roi) ? cond.roi.join(', ') : (cond.roi || '');
    h += `<div class="wfe-cond-row"><label>ROI</label><input data-cond-field="roi" data-ftype="roi" value="${esc(roiStr)}" placeholder="x1, y1, x2, y2"></div>`;
    h += `<div class="wfe-cond-row"><label>Threshold</label><input type="number" data-cond-field="threshold" data-ftype="num" step="0.01" value="${cond.threshold!=null?cond.threshold:0.8}"></div>`;
  } else if(kind === 'level_eq' || kind === 'level_gte' || kind === 'level_lte'){
    h += `<div class="wfe-cond-row"><label>Value</label><input type="number" data-cond-field="value" data-ftype="num" step="1" value="${cond.value!=null?cond.value:1}"></div>`;
    if(!lvlEnabled){
      h += `<div class="wfe-cond-warn">\u26A0 Detect Level is disabled — this condition will always be false at runtime.</div>`;
    }
  }

  h += `</div>`;
  return h;
}

/* ---- Mutations ---- */
function addElseIf(slug, ifPath){
  collectWorkflows();
  const step = _walkStep(wfeData[slug], ifPath);
  if(!step || step.type !== 'if') return;
  if(!Array.isArray(step.branches)) step.branches = [];
  step.branches.push({condition:{kind:'template_visible', template:'', roi:[0,0,900,1600], threshold:0.8}, steps:[]});
  renderWorkflowEditor();
}
function delBranch(slug, ifPath, branchIdx){
  collectWorkflows();
  const step = _walkStep(wfeData[slug], ifPath);
  if(!step || step.type !== 'if') return;
  if(!Array.isArray(step.branches) || branchIdx<=0 || branchIdx>=step.branches.length) return;
  step.branches.splice(branchIdx, 1);
  renderWorkflowEditor();
}
function addElseBranch(slug, ifPath){
  collectWorkflows();
  const step = _walkStep(wfeData[slug], ifPath);
  if(!step || step.type !== 'if') return;
  step.else_steps = [];
  renderWorkflowEditor();
}
function delElseBranch(slug, ifPath){
  collectWorkflows();
  const step = _walkStep(wfeData[slug], ifPath);
  if(!step || step.type !== 'if') return;
  step.else_steps = null;
  renderWorkflowEditor();
}

function onConditionKindChange(sel){
  /* Collect first so the kind change persists into wfeData, then re-render
     to swap dynamic fields. */
  collectWorkflows();
  const condBox = sel.closest('.wfe-cond');
  if(!condBox) return;
  const condPath = condBox.dataset.condPath;
  const slug = condBox.closest('.wfe-wf-body')?.dataset.wfkey;
  if(!slug || !condPath) return;
  const obj = _resolveFromSteps(wfeData[slug], condPath);
  if(obj && typeof obj === 'object'){
    obj.kind = sel.value;
    if(obj.kind === 'template_visible' || obj.kind === 'template_not_visible'){
      if(obj.template == null) obj.template = '';
      if(!Array.isArray(obj.roi)) obj.roi = [0,0,900,1600];
      if(obj.threshold == null) obj.threshold = 0.8;
    } else if(obj.kind === 'level_eq' || obj.kind === 'level_gte' || obj.kind === 'level_lte'){
      if(obj.value == null) obj.value = 1;
    }
  }
  renderWorkflowEditor();
}
