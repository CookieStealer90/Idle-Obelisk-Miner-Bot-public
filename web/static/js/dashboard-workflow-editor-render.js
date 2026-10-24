/* ============================================================
   dashboard-workflow-editor-render.js — Top-level rendering
   ============================================================
   Renders the whole editor tree: workflow headers, steps, fields,
   and the add-step row. If-blocks are rendered by renderIfStep in
   dashboard-workflow-editor-if.js.
*/

function renderWorkflowEditor(preserveOpen){
  const openState = preserveOpen || _wfeGetOpenState();
  const c = document.getElementById('wfe-container');
  const slugs = Object.keys(wfeData).sort((a,b)=>{
    const oa = parseInt(wfeData[a]?.order ?? 999);
    const ob = parseInt(wfeData[b]?.order ?? 999);
    if(oa !== ob) return oa - ob;
    return a.localeCompare(b);
  });
  let h = '';
  const inactiveCount = slugs.filter(s=>!!wfeData[s]?.inactive).length;
  h += `<div class="wfe-toolbar" style="display:flex;align-items:center;gap:8px;margin-bottom:8px">`;
  h += `<button class="btn" style="font-size:.62rem;padding:3px 8px" onclick="toggleHideInactive()">`;
  h += wfeHideInactive ? `\u{1F441} Show Inactive` : `\u{1F576} Hide Inactive`;
  h += `</button>`;
  h += `<span class="wfe-info-btn" onclick="showWorkflowsHelp(event)" title="How workflows work">\u2139\uFE0F</span>`;
  h += `<span style="font-size:.6rem;color:var(--text-dim)">${slugs.length} workflows`;
  if(inactiveCount) h += ` &middot; ${inactiveCount} inactive`;
  h += `</span></div>`;
  if(slugs.length === 0){
    h += `<div class="scr-placeholder" style="padding:12px">No workflows defined. Use "+ New Workflow" below.</div>`;
  }
  const visibleSlugs = wfeHideInactive ? slugs.filter(s=>!wfeData[s]?.inactive) : slugs;
  if(slugs.length>0 && visibleSlugs.length===0){
    h += `<div class="scr-placeholder" style="padding:12px">All workflows are inactive and hidden. Click "Show Inactive" to reveal.</div>`;
  }
  for(let i=0; i<slugs.length; i++){
    const slug = slugs[i];
    const wf = wfeData[slug] || {};
    const isOpen = !!openState[slug];
    const inactive = !!wf.inactive;
    if(wfeHideInactive && inactive) continue;
    const canUp = i>0;
    const canDown = i<slugs.length-1;
    h += `<div class="wfe-wf${inactive?' wfe-inactive':''}">`;
    h += `<div class="wfe-wf-hdr${isOpen?' open':''}" onclick="this.classList.toggle('open')">`;
    h += `<div><span class="wfe-id">${esc(wf.name||slug)}</span>`;
    h += `<span class="wfe-desc">${esc(wf.description||'')}</span></div>`;
    h += `<div class="wfe-wf-hdr-ctrls" onclick="event.stopPropagation()">`;
    h += `<button class="wfe-step-btn move" ${canUp?'':'disabled style="visibility:hidden"'} onclick="moveWf(${jsArg(slug)},-1)" title="Move up">\u25B2</button>`;
    h += `<button class="wfe-step-btn move" ${canDown?'':'disabled style="visibility:hidden"'} onclick="moveWf(${jsArg(slug)},1)" title="Move down">\u25BC</button>`;
    h += `<button class="wfe-step-btn copy" onclick="copyWorkflow(${jsArg(slug)})" title="Duplicate workflow">\u29C9</button>`;
    h += `</div>`;
    h += `<span class="wp-tier-arrow">\u25B8</span></div>`;
    h += `<div class="wfe-wf-body" data-wfkey="${esc(slug)}">`;

    /* Order / inactive / delete row */
    h += `<div class="wfe-wf-controls">`;
    h += `<span style="font-size:.6rem;color:var(--text-dim)">slug: <code>${esc(slug)}</code></span>`;
    h += `<div style="flex:1"></div>`;
    h += `<label style="font-size:.6rem;display:flex;align-items:center;gap:4px">`;
    h += `<input type="checkbox" data-wfmeta="inactive" ${inactive?'checked':''} onchange="onInactiveToggle(${jsArg(slug)},this)"> inactive</label>`;
    h += `<button class="wfe-step-btn del" onclick="delWorkflow(${jsArg(slug)})" title="Delete workflow">\u2715</button>`;
    h += `</div>`;

    h += `<div id="wfe-copy-${esc(slug)}" class="wfe-copy-row" style="display:none"></div>`;

    /* Meta fields */
    h += `<div class="wfe-fields">`;
    for(const f of WF_META_FIELDS){
      h += renderField(f, wf[f.k], slug, f.k, false, /*isMeta*/true);
    }
    h += `</div>`;

    /* Steps container (drop-target) */
    h += `<div class="wfe-steps-list" data-container-path="" data-slug="${esc(slug)}">`;
    (wf.steps||[]).forEach((step,si)=>{
      h += renderStep(step, String(si), slug);
    });
    h += `</div>`;

    h += renderAddStepRow(slug, '', /*depth*/0);

    h += `</div></div>`;
  }

  /* New workflow row */
  h += `<div class="wfe-add-wf" style="display:flex;gap:6px;margin-top:8px;padding:6px;border-top:1px solid var(--border)">`;
  h += `<input id="wfe-new-slug" placeholder="new workflow name" style="flex:1;font-size:.65rem">`;
  h += `<button class="btn primary" style="font-size:.62rem;padding:3px 8px" onclick="addWorkflow()">+ New Workflow</button>`;
  h += `</div>`;

  c.innerHTML = h;
}

function renderAddStepRow(slug, containerPath, depth){
  const selId = `wfe-newtype-${slug}-${containerPath||'root'}`;
  let h = `<div class="wfe-add-step" data-container-path="${esc(containerPath)}" data-slug="${esc(slug)}">`;
  h += `<select id="${esc(selId)}">`;
  STEP_TYPES.forEach(t=>{
    if(t.value === 'if' && depth >= 1) return;  // No nested if
    h += `<option value="${t.value}">${t.label}</option>`;
  });
  h += `</select>`;
  h += `<button class="btn" style="font-size:.62rem;padding:3px 8px" onclick="addStep(${jsArg(slug)},${jsArg(containerPath)},${jsArg(selId)})">+ Add Step</button>`;
  h += `</div>`;
  return h;
}

/* Render one non-if step. `path` is the dot-path addressing this step inside wf. */
function renderStep(step, path, slug){
  if(!step) return '';
  const t = step.type||'?';
  if(t === 'if') return renderIfStep(step, path, slug);

  const label = STEP_TYPES.find(s=>s.value===t)?.label || t;
  const isDis = !!step._disabled;
  const depth = _pathDepth(path);
  let h = `<div class="wfe-step${isDis?' disabled':''}" draggable="true" data-path="${esc(path)}" data-slug="${esc(slug)}" ondragstart="onStepDragStart(event)" ondragend="onStepDragEnd(event)" ondragover="onStepDragOver(event)" ondrop="onStepDrop(event)" ondragleave="onStepDragLeave(event)">`;
  h += `<div class="wfe-step-hdr">`;
  h += `<span class="wfe-step-drag" title="Drag to reorder">\u2630</span>`;
  h += `<span class="wfe-step-num">${_pathDisplayNum(path)}</span>`;
  h += `<span class="wfe-step-type">${esc(label)}</span>`;
  h += `<div class="wfe-step-controls">`;
  h += `<button class="wfe-step-btn toggle-dis" onclick="toggleStepDisabled(${jsArg(slug)},${jsArg(path)})" title="${isDis?'Enable':'Disable'} step">${isDis?'\u25C9':'\u25CE'}</button>`;
  h += `<button class="wfe-step-btn move" onclick="moveStep(${jsArg(slug)},${jsArg(path)},-1)" title="Move up">\u25B2</button>`;
  h += `<button class="wfe-step-btn move" onclick="moveStep(${jsArg(slug)},${jsArg(path)},1)" title="Move down">\u25BC</button>`;
  h += `<button class="wfe-step-btn copy" onclick="copyStep(${jsArg(slug)},${jsArg(path)})" title="Duplicate step">\u29C9</button>`;
  h += `<button class="wfe-step-btn del" onclick="delStep(${jsArg(slug)},${jsArg(path)})" title="Delete">\u2715</button>`;
  h += `</div></div>`;
  h += _renderStepNote(step, path);
  h += `<div class="wfe-fields">`;
  const fields = STEP_FIELDS[t]||[];
  for(const f of fields){
    h += renderField(f, step[f.k], slug, `${path}.${f.k}`, false, /*isMeta*/false, /*stepPath*/path);
  }
  h += `</div></div>`;
  return h;
}

function _pathDisplayNum(path){
  const parts = String(path).split('.');
  const last = parts[parts.length-1];
  return `#${parseInt(last)+1}`;
}

/* Small single-line comment field shown on every step (incl. if-blocks).
   Stored on the step object under `note`. */
function _renderStepNote(step, path){
  const note = step.note == null ? '' : String(step.note);
  const id = `wfe-note-${String(path).replace(/[^a-z0-9]/gi,'_')}`;
  return `<div class="wfe-step-note" style="padding:2px 8px 4px;display:flex;gap:6px;align-items:center">`
    + `<span style="font-size:.6rem;color:var(--text-dim)" title="Free-form comment for this step">\u{1F4DD}</span>`
    + `<input id="${id}" data-path="${path}.note" placeholder="comment\u2026" value="${esc(note)}" style="flex:1;font-size:.62rem;padding:2px 6px;background:transparent;border:1px dashed var(--border);color:var(--text);border-radius:3px;font-family:inherit">`
    + `</div>`;
}

function renderField(f, val, slug, path, ro, isMeta, stepPath){
  const id = `wfe-${esc(slug)}-${esc(path).replace(/[^a-z0-9_-]/gi,'_')}`;
  const dis = ro?'disabled':'';
  const dataAttr = isMeta ? `data-wfmeta="${path}"` : `data-path="${path}"`;
  let h = `<div class="wfe-field">`;
  const tip = f.hint ? `${f.hint}\n(${f.k})` : f.k;
  const hintMark = f.hint ? ' <span class="wfe-hint" title="'+esc(f.hint)+'">&#9432;</span>' : '';
  h += `<label title="${esc(tip)}">${esc(f.label)}${hintMark}</label>`;
  if(f.type==='tpl'){
    h += _renderTplPicker(val, `id="${id}" ${dataAttr} ${dis}`);
  } else if(f.type==='bool'){
    h += `<select id="${id}" ${dataAttr} ${dis}>`;
    h += `<option value="true" ${val===true?'selected':''}>Yes</option>`;
    h += `<option value="false" ${val===false||val==null?'selected':''}>No</option>`;
    h += `</select>`;
  } else if(f.type==='select'){
    h += `<select id="${id}" ${dataAttr} ${dis}>`;
    (f.options||[]).forEach(o=>{
      const sel = (val===o)?'selected':'';
      h += `<option value="${esc(o)}" ${sel}>${esc(o)}</option>`;
    });
    h += `</select>`;
  } else if(f.type==='loglevel'){
    h += `<select id="${id}" ${dataAttr} ${dis}>`;
    LOG_LEVELS.forEach(o=>{
      const lbl = o===''?'(use global)':o;
      const sel = ((val||'')===o)?'selected':'';
      h += `<option value="${o}" ${sel}>${lbl}</option>`;
    });
    h += `</select>`;
  } else if(f.type==='wf'){
    h += `<select id="${id}" ${dataAttr} ${dis}>`;
    h += `<option value="">\u2014 select workflow \u2014</option>`;
    const targets = Object.keys(wfeData).sort((a,b)=>{
      const oa = parseInt(wfeData[a]?.order ?? 999);
      const ob = parseInt(wfeData[b]?.order ?? 999);
      if(oa !== ob) return oa - ob;
      return a.localeCompare(b);
    });
    const curSlug = slug;
    let hasVal = false;
    for(const t of targets){
      if(t === curSlug) continue;
      const tw = wfeData[t] || {};
      const lbl = (tw.name ? tw.name : t) + (tw.inactive?' (inactive)':'');
      const sel = (val===t)?'selected':'';
      if(val===t) hasVal = true;
      h += `<option value="${esc(t)}" ${sel}>${esc(lbl)} [${esc(t)}]</option>`;
    }
    if(val && !hasVal){
      h += `<option value="${esc(val)}" selected style="color:#f55">\u26A0 missing: ${esc(val)}</option>`;
    }
    h += `</select>`;
  } else if(f.type==='roi'){
    const v = Array.isArray(val)?val.join(', '):(val||'');
    h += `<input id="${id}" ${dataAttr} data-ftype="roi" value="${esc(v)}" placeholder="x1, y1, x2, y2" ${dis}>`;
  } else if(f.type==='num'){
    h += `<input id="${id}" type="number" ${dataAttr} data-ftype="num" value="${val!=null?val:''}" step="${f.step||1}" ${dis}>`;
  } else {
    h += `<input id="${id}" ${dataAttr} value="${esc(String(val==null?'':val))}" ${dis}>`;
  }
  h += `</div>`;
  return h;
}
