/* ============================================================
   dashboard-core.js — Socket, state, helpers, tabs
   ============================================================ */

// Connect only after all dashboard modules have registered their handlers.
// The server can send bot_state before the client's connect event.
const socket = io({autoConnect:false,reconnection:true,reconnectionDelay:1000});
let botState = {};
let connected = false;

/* Safari HTTPS-Only detection: if we can't connect after 4s, show hint */
let _safariHintTimer = setTimeout(()=>{
  const hint = document.getElementById('safari-hint');
  if(hint && !connected) hint.style.display = '';
}, 4000);

function updateConnectionStatus(isConnected){
  connected=isConnected;
  if(isConnected) clearTimeout(_safariHintTimer);
  const hint = document.getElementById('safari-hint');
  if(hint && isConnected) hint.style.display = 'none';
  document.getElementById('conn-dot').classList.toggle('on',isConnected);
  document.getElementById('conn-text').textContent=isConnected?'connected':'disconnected';
}
socket.on('connect',()=>updateConnectionStatus(true));
socket.on('disconnect',()=>updateConnectionStatus(false));
socket.on('connect_error',()=>updateConnectionStatus(false));
socket.on('toast',(d)=>{if(d&&d.msg)showToast(d.msg,!!d.error);});

function cmd(c){socket.emit('command',{cmd:c})}

/* ============ COLLAPSE CARDS ============ */
const CARD_STORAGE_KEY = 'obeliskbot_card_states';
const cardStates = {};

function loadCardStates() {
  try {
    const saved = localStorage.getItem(CARD_STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      Object.assign(cardStates, parsed);
      for (const [id, collapsed] of Object.entries(cardStates)) {
        const body = document.getElementById('body-'+id);
        const tog = document.getElementById('tog-'+id);
        if (body && tog) {
          body.classList.toggle('collapsed', collapsed);
          tog.textContent = collapsed ? '+' : '−';
        }
        const card = document.getElementById('card-'+id);
        if(card && collapsed) card.classList.add('log-collapsed');
      }
    }
  } catch(e) { /* localStorage not available or corrupted – ignore */ }
}

function saveCardStates() {
  try { localStorage.setItem(CARD_STORAGE_KEY, JSON.stringify(cardStates)); } catch(e) {}
}

function toggleCard(id) {
  const body = document.getElementById('body-'+id);
  const tog = document.getElementById('tog-'+id);
  const collapsed = !body.classList.contains('collapsed');
  body.classList.toggle('collapsed', collapsed);
  tog.textContent = collapsed ? '+' : '−';
  cardStates[id] = collapsed;
  saveCardStates();
  // sync collapsed class on card element (used by log-filter hide)
  const card = document.getElementById('card-'+id);
  if(card) card.classList.toggle('log-collapsed', collapsed);
  /* Adjust sidebar width when Configuration opens or closes. */
  if(id==='config'){
    var grid=document.querySelector('.grid-main');
    if(grid) grid.classList.toggle('config-open',!collapsed);
  }
}

/* Restore card states on page load */
document.addEventListener('DOMContentLoaded', function(){
  loadCardStates();
  /* Apply initial visibility for gs-info-btn and vis toggles */
  if(cardStates['gem-stats']){
    var ib=document.getElementById('gs-info-btn');if(ib)ib.style.display='none';
    var vt=document.getElementById('gs-vis-toggles');if(vt)vt.style.display='none';
  }
  /* Restore the wider sidebar when Configuration starts open. */
  var grid=document.querySelector('.grid-main');
  if(grid && !cardStates['config']) grid.classList.add('config-open');
  socket.connect();
});

/* ============ STATE UPDATE ============ */
socket.on('bot_state', (data) => {
  // Live state also repairs a stale badge if a connect notification was missed.
  updateConnectionStatus(true);
  botState = data;
  if (!data.started) return;
  updateStatus(data);
  updateButtons(data);
  updateWorkflows(data);
  if(typeof updateGemStatsCard==='function') updateGemStatsCard(data);
  /* Hide/show sidebar cards based on startup_defaults visibility flags */
  var gsCard = document.getElementById('card-gem-stats');
  if(gsCard) gsCard.style.display = data.gem_statistics_enabled === false ? 'none' : '';
  var scrCard = document.getElementById('card-screenshot');
  if(scrCard) scrCard.style.display = data.screenshot_visible === false ? 'none' : '';
});

/* ============ TABS ============ */
function switchTab(tab,btnEl){
  /* ── Mobile scroll-anchor: keep card header pinned ── */
  const cardHdr = document.querySelector('#card-config .card-hdr');
  const hdrTop  = cardHdr ? cardHdr.getBoundingClientRect().top : null;

  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));
  document.getElementById('tab-'+tab).classList.add('active');
  if(btnEl) btnEl.classList.add('active');

  /* ── After DOM reflow: restore scroll so card header stays put ── */
  if(cardHdr && hdrTop !== null){
    requestAnimationFrame(()=>{
      const newTop = cardHdr.getBoundingClientRect().top;
      const drift  = newTop - hdrTop;
      if(Math.abs(drift) > 2) window.scrollBy({top: drift, behavior:'instant'});
    });
  }
}

/* ============ HELPERS ============ */
function fmtSec(s){s=Math.max(0,Math.round(s));const m=Math.floor(s/60);const sec=s%60;return`${m}m${String(sec).padStart(2,'0')}s`}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
// HTML encoding alone cannot protect a JavaScript string inside an event attribute.
function jsArg(value){return esc(JSON.stringify(String(value)))}

/* ============ RESTART ============ */
function restartBot(){
  if(!confirm('Are you sure you want to restart the bot?'))return;
  fetch('/api/restart',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.json()).then(r=>{
    if(r.ok){
      showToast('Restarting… page will reconnect automatically');
      document.getElementById('conn-text').textContent='restarting…';
      document.getElementById('conn-dot').classList.remove('on');
    }else showToast('Restart failed',true);
  }).catch(e=>showToast('Restart error: '+e,true));
}

function showToast(msg,isErr){const el=document.createElement('div');el.style.cssText=`position:fixed;bottom:20px;right:20px;padding:10px 18px;border-radius:8px;font-family:var(--font);font-size:.8rem;z-index:9999;color:#fff;background:${isErr?'var(--red)':'var(--green)'};box-shadow:0 4px 20px rgba(0,0,0,.4);animation:slideIn .2s ease-out`;el.textContent=msg;document.body.appendChild(el);setTimeout(()=>el.remove(),3500)}
