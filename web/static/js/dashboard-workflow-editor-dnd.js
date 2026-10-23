/* ============================================================
   dashboard-workflow-editor-dnd.js — Drag & Drop
   ============================================================
   Step reordering via HTML5 drag. Handles step-onto-step drops
   (above/below) and step-into-container drops (if/elseif/else
   branch bodies). Also enforces the "no nested if" rule.

   Bug-fix note: the outer .wfe-if-block is itself a draggable
   step with ondrop/ondragover. When the pointer ends up inside
   its body but not over a specific child step, the OUTER handler
   used to fire and misplace the step next to the if-block.
   Guard below ("ev.target.closest('.wfe-if-body')") lets inner
   container/step handlers take those drops instead.
*/

let _dragPath = null;
let _dragSlug = null;

function onStepDragStart(ev){
  /* Stop bubbling: inner steps live inside an outer if-block that is also
     draggable. Without this, the outer handler overwrites _dragPath and the
     drop logic thinks an if-block is being dragged. */
  ev.stopPropagation();
  const el = ev.currentTarget;
  _dragPath = el.dataset.path;
  _dragSlug = el.dataset.slug;
  el.classList.add('wfe-dragging');
  ev.dataTransfer.effectAllowed = 'move';
  try { ev.dataTransfer.setData('text/plain', _dragPath); } catch(e) {}
}
function onStepDragEnd(ev){
  ev.currentTarget.classList.remove('wfe-dragging');
  document.querySelectorAll('.wfe-drop-above,.wfe-drop-below,.wfe-drop-target').forEach(el=>{
    el.classList.remove('wfe-drop-above','wfe-drop-below','wfe-drop-target');
  });
  _dragPath = null; _dragSlug = null;
}

/* True if this step-level event should be ignored because the pointer is
   inside the if-block's collapsible body (branches, options, else). Lets
   the inner step / branch-container handlers take the drop. */
function _ifBlockShouldDefer(el, ev){
  if(!el.classList.contains('wfe-if-block')) return false;
  const body = ev.target.closest('.wfe-if-body');
  return !!(body && el.contains(body));
}

function onStepDragOver(ev){
  if(!_dragPath) return;
  const el = ev.currentTarget;
  if(el.dataset.slug !== _dragSlug) return;
  if(_ifBlockShouldDefer(el, ev)){
    el.classList.remove('wfe-drop-above','wfe-drop-below');
    return;
  }
  ev.preventDefault();
  ev.dataTransfer.dropEffect = 'move';
  const rect = el.getBoundingClientRect();
  const above = (ev.clientY - rect.top) < rect.height/2;
  el.classList.toggle('wfe-drop-above', above);
  el.classList.toggle('wfe-drop-below', !above);
}
function onStepDragLeave(ev){
  ev.currentTarget.classList.remove('wfe-drop-above','wfe-drop-below');
}
function onStepDrop(ev){
  if(!_dragPath) return;
  const el = ev.currentTarget;
  if(el.dataset.slug !== _dragSlug) return;
  if(_ifBlockShouldDefer(el, ev)) return;  // let inner handler take it
  ev.preventDefault();
  ev.stopPropagation();
  const rect = el.getBoundingClientRect();
  const above = (ev.clientY - rect.top) < rect.height/2;
  const targetPath = el.dataset.path;
  _moveStepByDrag(_dragSlug, _dragPath, targetPath, above ? 'before' : 'after');
}
function onContainerDragOver(ev){
  if(!_dragPath) return;
  const el = ev.currentTarget;
  if(el.dataset.slug !== _dragSlug) return;
  ev.preventDefault();
  ev.dataTransfer.dropEffect = 'move';
  el.classList.add('wfe-drop-target');
}
function onContainerDragLeave(ev){
  ev.currentTarget.classList.remove('wfe-drop-target');
}
function onContainerDrop(ev){
  if(!_dragPath) return;
  const el = ev.currentTarget;
  if(el.dataset.slug !== _dragSlug) return;
  if(ev.target !== el){
    /* Over a child step — let step-level drop handler take it */
    return;
  }
  ev.preventDefault();
  el.classList.remove('wfe-drop-target');
  const containerPath = el.dataset.containerPath;
  _moveStepToContainer(_dragSlug, _dragPath, containerPath);
}

function _moveStepByDrag(slug, srcPath, destPath, position){
  if(srcPath === destPath) return;
  collectWorkflows();
  const wf = wfeData[slug];
  if(!wf) return;
  const [srcContainer, srcIdx] = _walkParent(wf, srcPath);
  if(!Array.isArray(srcContainer)) return;
  const destStep = _walkStep(wf, destPath);
  if(!destStep) return;
  const draggedStep = srcContainer[srcIdx];
  if(draggedStep && draggedStep.type === 'if' && _pathDepth(destPath) >= 1){
    showToast('Nested if-blocks not allowed (max depth 1)', true);
    renderWorkflowEditor();
    return;
  }
  if(destPath.startsWith(srcPath + '.')){
    showToast('Cannot move a block into itself', true);
    renderWorkflowEditor();
    return;
  }
  const [destContainer, destIdx] = _walkParent(wf, destPath);
  if(!Array.isArray(destContainer)) return;
  const [item] = srcContainer.splice(srcIdx, 1);
  let insertIdx = destIdx;
  if(srcContainer === destContainer && srcIdx < destIdx) insertIdx--;
  if(position === 'after') insertIdx++;
  destContainer.splice(insertIdx, 0, item);
  renderWorkflowEditor();
}

function _moveStepToContainer(slug, srcPath, containerPath){
  collectWorkflows();
  const wf = wfeData[slug];
  if(!wf) return;
  const [srcContainer, srcIdx] = _walkParent(wf, srcPath);
  if(!Array.isArray(srcContainer)) return;
  const destContainer = _getContainerByPath(wf, containerPath);
  if(!Array.isArray(destContainer)) return;
  const draggedStep = srcContainer[srcIdx];
  const destDepth = containerPath ? 1 : 0;
  if(draggedStep && draggedStep.type === 'if' && destDepth >= 1){
    showToast('Nested if-blocks not allowed (max depth 1)', true);
    renderWorkflowEditor();
    return;
  }
  srcContainer.splice(srcIdx, 1);
  destContainer.push(draggedStep);
  renderWorkflowEditor();
}
