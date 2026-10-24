/* Persistent notice inbox. Keyed updates preserve focus and animate removals. */
(function(){
  const list=document.getElementById('notices-list');
  const error=document.getElementById('notices-error');
  const nodes=new Map();
  const acknowledged=new Set();
  let entries=[], limit=30, loading=false, workerError='';
  let enabled=null;

  function renderStatusValue(){
    const value=document.getElementById('s-notices-val');
    value.className='stat-value'+(enabled===false?' red':enabled?' green':'');
    value.textContent=enabled===false?'OFF':entries.length;
  }

  function report(message){error.textContent=message||'';error.hidden=!message;}
  async function request(url,options){
    const response=await fetch(url,options);
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||'Request failed');
    return data;
  }
  function removeEntry(id){
    const node=nodes.get(id);
    if(!node || node.classList.contains('notice-removing'))return;
    node.classList.add('notice-removing');
    node.setAttribute('aria-hidden','true');
    setTimeout(()=>{node.remove();if(nodes.get(id)===node)nodes.delete(id);},320);
  }
  function createEntry(entry){
    const node=document.createElement('article');node.className='notice-entry';
    const inner=document.createElement('div');inner.className='notice-inner';
    const card=document.createElement('div');card.className='notice-card';
    const time=document.createElement('time');
    const date=new Date(entry.created_ts*1000);time.dateTime=date.toISOString();time.textContent=date.toLocaleString();
    const media=document.createElement('div');media.className='notice-media';
    const img=document.createElement('img');img.src='/api/notices/'+entry.id+'/image';
    img.alt='Saved '+entry.variant+' notice';img.loading='lazy';img.width=entry.width;img.height=entry.height;
    const acknowledge=document.createElement('button');acknowledge.className='notice-delete';acknowledge.type='button';
    acknowledge.textContent='Tap to delete';acknowledge.setAttribute('aria-label','Acknowledge and delete notice from '+time.textContent);
    acknowledge.addEventListener('click',async()=>{
      acknowledge.disabled=true;
      try{
        await request('/api/notices/'+entry.id,{method:'DELETE',headers:{'Content-Type':'application/json'},body:'{}'});
        acknowledged.add(entry.id);
        entries=entries.filter(item=>item.id!==entry.id);render();report('');
        const next=list.querySelector('.notice-entry:not(.notice-removing) .notice-delete');
        (next||document.getElementById('notices-test')).focus();
      }catch(e){acknowledge.disabled=false;report(e.message);}
    });
    const preview=document.createElement('button');preview.className='notice-preview-btn';preview.type='button';preview.textContent='Enlarge';
    preview.addEventListener('click',()=>{
      document.getElementById('notice-preview-image').src=img.src;
      document.getElementById('notice-preview').showModal();
    });
    media.append(img,acknowledge);card.append(time,media,preview);inner.append(card);node.append(inner);
    return node;
  }
  function render(){
    const visible=entries.slice(0,limit), ids=new Set(visible.map(entry=>entry.id));
    for(const id of nodes.keys())if(!ids.has(id))removeEntry(id);
    for(const entry of visible){
      if(!nodes.has(entry.id)){const node=createEntry(entry);nodes.set(entry.id,node);list.append(node);}
    }
    document.getElementById('notices-count').textContent=entries.length;
    renderStatusValue();
    document.getElementById('notices-empty').hidden=entries.length>0;
    document.getElementById('notices-more').hidden=entries.length<=limit;
  }
  async function refresh(){
    if(loading)return;loading=true;
    try{const data=await request('/api/notices');entries=data.entries.filter(entry=>!acknowledged.has(entry.id));render();report(workerError||(data.unreadable?data.unreadable+' unreadable archive file(s); files have been preserved.':''));}
    catch(e){report(e.message);}finally{loading=false;}
  }
  socket.on('bot_state',data=>{
    const n=data.notices||{};
    setBtn('btn-notices',n.enabled,'\uD83D\uDCE5 Notices');
    enabled=!!n.enabled;
    renderStatusValue();
    const last=typeof n.last_scan_age==='number'?'Last scan: '+fmtSec(n.last_scan_age)+' ago':'Never scanned';
    updateScanCountdown('s-notices-next',n,{detail:[last,n.error||n.status].filter(Boolean).join(' \u00b7 ')});
    document.getElementById('notices-status').textContent=n.enabled
      ? (n.status||'Ready')+(n.next_check_remaining>0?' · next '+fmtSec(n.next_check_remaining):'')
      : 'Off · saved notices remain available';
    workerError=n.error||'';
    if(workerError)report(workerError);
  });
  socket.on('connect',refresh);
  document.getElementById('notices-more').addEventListener('click',()=>{limit+=30;render();});
  document.getElementById('notices-test').addEventListener('click',async function(){
    this.disabled=true;
    const result=document.getElementById('notices-test-result');
    try{
      const data=await request('/api/notices/test',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      result.textContent=(data.found?'Detected: '+data.variant:'No notice detected')+' · score '+data.score.toFixed(3)+' · no tap sent';
    }catch(e){result.textContent=e.message;}finally{this.disabled=false;}
  });
  document.getElementById('notice-preview-close').addEventListener('click',()=>document.getElementById('notice-preview').close());
  setInterval(()=>{if(!document.hidden)refresh();},5000);
  refresh();
})();
