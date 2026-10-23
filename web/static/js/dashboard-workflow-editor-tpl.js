/* ============================================================
   dashboard-workflow-editor-tpl.js — Hierarchical template picker
   ============================================================
   Companion to dashboard-workflow-editor-core.js. Provides the
   folder-tree popup for Click-Template / If-condition template
   selects, plus a few basename helpers used elsewhere.
*/

function _tplBasename(p){
  if(!p) return p;
  const i = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
  return i>=0 ? p.slice(i+1) : p;
}
function _tplExpand(sel){
  Array.from(sel.options).forEach(o=>{ if(o.dataset.full) o.textContent = o.dataset.full; });
}
function _tplCollapse(sel){
  Array.from(sel.options).forEach(o=>{
    if(!o.dataset.full) return;
    o.textContent = o.selected ? _tplBasename(o.dataset.full) : o.dataset.full;
  });
}

let _tplPickerBtn = null;
let _tplPickerPopup = null;
const _TPL_OPEN_KEY = 'wfe.tplOpenFolders';
function _tplLoadOpenFolders(){
  try { return new Set(JSON.parse(localStorage.getItem(_TPL_OPEN_KEY)||'[]')); }
  catch(e) { return new Set(); }
}
function _tplSaveOpenFolders(set){
  try { localStorage.setItem(_TPL_OPEN_KEY, JSON.stringify(Array.from(set))); } catch(e) {}
}

function _ensureTplStyles(){
  if(document.getElementById('wfe-tpl-picker-styles')) return;
  const s = document.createElement('style');
  s.id = 'wfe-tpl-picker-styles';
  s.textContent = `
    .wfe-tpl-picker{position:relative;display:block;flex:1;min-width:0}
    .wfe-tpl-btn{width:100%;text-align:left;font-size:.62rem;padding:3px 6px;background:var(--bg-2,#1a1a1a);color:var(--text,#ddd);border:1px solid var(--border,#333);border-radius:3px;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:inherit}
    .wfe-tpl-btn:hover{border-color:var(--accent,#4a9)}
    .wfe-tpl-btn.placeholder{color:var(--text-dim,#888)}
    .wfe-tpl-btn:after{content:' \\25BE';float:right;color:var(--text-dim,#888)}
    .wfe-tpl-popup{position:absolute;z-index:99999;background:var(--bg-1,#111);border:1px solid var(--border,#444);border-radius:4px;box-shadow:0 4px 16px rgba(0,0,0,.6);width:380px;max-height:440px;display:flex;flex-direction:column;font-size:.65rem}
    .wfe-tpl-search{margin:6px 6px 4px;padding:4px 6px;font-size:.65rem;background:var(--bg-2,#1a1a1a);color:var(--text,#ddd);border:1px solid var(--border,#333);border-radius:3px;outline:none}
    .wfe-tpl-search:focus{border-color:var(--accent,#4a9)}
    .wfe-tpl-tree{overflow-y:auto;flex:1;padding:0 4px 6px}
    .wfe-tpl-folder{cursor:pointer;padding:2px 4px;user-select:none;color:#6cf;font-weight:600}
    .wfe-tpl-folder:hover{background:rgba(255,255,255,.05)}
    .wfe-tpl-folder .wfe-tpl-caret{display:inline-block;width:12px;color:var(--text-dim,#888)}
    .wfe-tpl-folder-body{border-left:1px dashed var(--border,#333);margin-left:9px;padding-left:4px}
    .wfe-tpl-item{cursor:pointer;padding:2px 4px 2px 18px;color:var(--text,#ddd);user-select:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:baseline;gap:8px}
    .wfe-tpl-item:hover{background:rgba(100,170,255,.12)}
    .wfe-tpl-item.selected{background:rgba(100,170,255,.25);font-weight:600}
    .wfe-tpl-item .wfe-tpl-path{color:var(--text-dim,#888);font-size:.56rem;margin-left:auto;overflow:hidden;text-overflow:ellipsis}
    .wfe-tpl-empty{padding:10px;color:var(--text-dim,#888);font-style:italic;text-align:center}
  `;
  document.head.appendChild(s);
}

function _renderTplPicker(val, attrs){
  _ensureTplStyles();
  const disp = val ? _tplBasename(val) : '\u2014 select template \u2014';
  const cls = val ? '' : 'placeholder';
  return `<span class="wfe-tpl-picker">`
    + `<button type="button" class="wfe-tpl-btn ${cls}" onclick="_tplOpenPicker(event,this)" title="${esc(val||'')}">${esc(disp)}</button>`
    + `<input type="hidden" ${attrs} value="${esc(val||'')}">`
    + `</span>`;
}

function _tplOpenPicker(ev, btn){
  ev.stopPropagation();
  ev.preventDefault();
  if(_tplPickerBtn === btn){ _tplClosePicker(); return; }
  _tplClosePicker();
  _ensureTplStyles();
  _tplPickerBtn = btn;
  const hidden = btn.parentElement.querySelector('input[type="hidden"]');
  const cur = hidden ? hidden.value : '';
  const popup = document.createElement('div');
  popup.className = 'wfe-tpl-popup';
  popup.innerHTML = `<input class="wfe-tpl-search" placeholder="Search templates\u2026" autocomplete="off" spellcheck="false"><div class="wfe-tpl-tree"></div>`;
  document.body.appendChild(popup);
  _tplPickerPopup = popup;
  const rect = btn.getBoundingClientRect();
  popup.style.left = (rect.left + window.scrollX) + 'px';
  popup.style.top = (rect.bottom + window.scrollY + 2) + 'px';
  requestAnimationFrame(()=>{
    const pr = popup.getBoundingClientRect();
    if(pr.right > window.innerWidth - 4){
      popup.style.left = Math.max(4, window.innerWidth - pr.width - 8) + 'px';
    }
    if(pr.bottom > window.innerHeight - 4){
      const newTop = rect.top + window.scrollY - pr.height - 2;
      if(newTop > window.scrollY + 4) popup.style.top = newTop + 'px';
    }
  });
  const tree = popup.querySelector('.wfe-tpl-tree');
  const search = popup.querySelector('.wfe-tpl-search');
  _tplRenderTreeInto(tree, cur, '');
  search.addEventListener('input', ()=>_tplRenderTreeInto(tree, cur, search.value));
  search.addEventListener('keydown', ev=>{
    if(ev.key === 'Escape'){ _tplClosePicker(); }
    else if(ev.key === 'Enter'){
      const first = tree.querySelector('.wfe-tpl-item');
      if(first) first.click();
    }
  });
  setTimeout(()=>search.focus(), 0);
  setTimeout(()=>document.addEventListener('mousedown', _tplOutsideClick), 0);
}

function _tplOutsideClick(ev){
  if(_tplPickerPopup && !_tplPickerPopup.contains(ev.target) && ev.target !== _tplPickerBtn){
    _tplClosePicker();
  }
}

function _tplClosePicker(){
  if(_tplPickerPopup){ _tplPickerPopup.remove(); _tplPickerPopup = null; }
  _tplPickerBtn = null;
  document.removeEventListener('mousedown', _tplOutsideClick);
}

function _tplBuildTree(paths){
  const root = {folders:{}, files:[]};
  for(const p of paths){
    const parts = String(p).split('/');
    let node = root;
    for(let i=0;i<parts.length-1;i++){
      const seg = parts[i];
      if(!node.folders[seg]) node.folders[seg] = {folders:{}, files:[]};
      node = node.folders[seg];
    }
    node.files.push({name: parts[parts.length-1], full: p});
  }
  return root;
}

function _tplRenderTreeInto(container, selectedVal, query){
  const q = (query||'').trim().toLowerCase();
  if(q){
    const matches = wfeTpls.filter(p=>p.toLowerCase().includes(q));
    if(matches.length === 0){
      container.innerHTML = '<div class="wfe-tpl-empty">No templates match.</div>';
      return;
    }
    let h = '';
    for(const p of matches){
      const sel = p === selectedVal ? ' selected' : '';
      const dir = p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '';
      h += `<div class="wfe-tpl-item${sel}" data-full="${esc(p)}" onclick="_tplPickItem(event)" title="${esc(p)}">`
         + `<span>${esc(_tplBasename(p))}</span>`;
      if(dir) h += `<span class="wfe-tpl-path">${esc(dir)}</span>`;
      h += `</div>`;
    }
    container.innerHTML = h;
    return;
  }
  const tree = _tplBuildTree(wfeTpls);
  const openSet = _tplLoadOpenFolders();
  /* Only auto-expand folders containing the currently selected template.
     An empty selectedVal leaves the tree fully collapsed on open. */
  if(selectedVal){
    const parts = String(selectedVal).split('/');
    for(let i=0;i<parts.length-1;i++) openSet.add(parts.slice(0, i+1).join('/'));
  }
  container.innerHTML = _tplRenderNode(tree, '', selectedVal, openSet);
  const selEl = container.querySelector('.wfe-tpl-item.selected');
  if(selEl) selEl.scrollIntoView({block:'nearest'});
}

function _tplRenderNode(node, prefix, selectedVal, openSet){
  let h = '';
  const folderNames = Object.keys(node.folders).sort();
  for(const fn of folderNames){
    const fp = prefix ? (prefix + '/' + fn) : fn;
    const open = openSet.has(fp);
    h += `<div class="wfe-tpl-folder" data-path="${esc(fp)}" onclick="_tplToggleFolder(event)">`
       + `<span class="wfe-tpl-caret">${open?'\u25BE':'\u25B8'}</span> ${esc(fn)}</div>`;
    h += `<div class="wfe-tpl-folder-body" style="${open?'':'display:none'}">`;
    h += _tplRenderNode(node.folders[fn], fp, selectedVal, openSet);
    h += `</div>`;
  }
  const files = node.files.slice().sort((a,b)=>a.name.localeCompare(b.name));
  for(const f of files){
    const sel = f.full === selectedVal ? ' selected' : '';
    h += `<div class="wfe-tpl-item${sel}" data-full="${esc(f.full)}" onclick="_tplPickItem(event)" title="${esc(f.full)}">`
       + `<span>${esc(f.name)}</span></div>`;
  }
  return h;
}

function _tplToggleFolder(ev){
  ev.stopPropagation();
  const folder = ev.currentTarget;
  const body = folder.nextElementSibling;
  const isOpen = body && body.style.display !== 'none';
  const newOpen = !isOpen;
  if(body) body.style.display = newOpen ? '' : 'none';
  const caret = folder.querySelector('.wfe-tpl-caret');
  if(caret) caret.textContent = newOpen ? '\u25BE' : '\u25B8';
  const fp = folder.dataset.path;
  if(fp){
    const openSet = _tplLoadOpenFolders();
    if(newOpen) openSet.add(fp); else openSet.delete(fp);
    _tplSaveOpenFolders(openSet);
  }
}

function _tplPickItem(ev){
  ev.stopPropagation();
  const item = ev.currentTarget;
  const full = item.dataset.full || '';
  if(!_tplPickerBtn) return;
  const wrap = _tplPickerBtn.parentElement;
  const hidden = wrap.querySelector('input[type="hidden"]');
  if(hidden){
    hidden.value = full;
    hidden.dispatchEvent(new Event('change', {bubbles:true}));
  }
  _tplPickerBtn.textContent = full ? _tplBasename(full) : '\u2014 select template \u2014';
  _tplPickerBtn.title = full;
  _tplPickerBtn.classList.toggle('placeholder', !full);
  _tplClosePicker();
}
