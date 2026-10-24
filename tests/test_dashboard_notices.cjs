// Notice inbox behavior without a browser dependency or live backend.
const assert=require('node:assert/strict');
const {test}=require('node:test');
const vm=require('node:vm');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('inbox supplies touch, keyboard, reduced motion and explicit hidden styles',()=>{
  const css=readFileSync(join(__dirname,'../web/static/css/dashboard.css'),'utf8');
  assert.match(css,/#card-notices \[hidden\]\{display:none!important\}/);
  assert.match(css,/@media\(hover:none\)/);
  assert.match(css,/notice-delete:focus-visible/);
  assert.match(css,/@media\(prefers-reduced-motion:reduce\)/);
});

function harness(){
  const timers=[],handlers={},elements=new Map();
  let focused=null,entries=[{id:'a'.repeat(32),created_ts:100,variant:'level',width:372,height:123}],failDelete=false;
  class Element{
    constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.hidden=false;this.disabled=false;this.textContent='';this.className='';}
    get classList(){return {contains:name=>this.className.split(' ').includes(name),add:name=>{this.className+=' '+name;}};}
    append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);}}
    remove(){this.parent.children=this.parent.children.filter(n=>n!==this);}
    setAttribute(key,value){this[key]=value;}
    addEventListener(name,callback){this.listeners[name]=callback;}
    focus(){focused=this;}
    showModal(){this.open=true;}
    close(){this.open=false;}
    querySelector(){
      const entry=this.children.find(n=>n.className.includes('notice-entry')&&!n.classList.contains('notice-removing'));
      return entry?.children[0].children[0].children[1].children[1]||null;
    }
  }
  const calls=[],countdowns=[];
  const context=vm.createContext({
    document:{hidden:false,createElement:tag=>new Element(tag),getElementById(id){if(!elements.has(id))elements.set(id,new Element('div'));return elements.get(id);}},
    socket:{on:(name,callback)=>{handlers[name]=callback;}},
    updateScanCountdown(...args){countdowns.push(args);},setBtn(){},fmtSec:s=>s+'s',setTimeout:callback=>{timers.push(callback);},setInterval:callback=>{handlers.poll=callback;},
    async fetch(url,options){
      calls.push({url,options});
      if(options?.method==='DELETE'){
        if(failDelete)return {ok:false,json:async()=>({error:'Disk error'})};
        entries=[];return {ok:true,json:async()=>({ok:true})};
      }
      if(url.endsWith('/test'))return {ok:true,json:async()=>({found:true,variant:'shard',score:1})};
      return {ok:true,json:async()=>({entries,unreadable:0})};
    },
  });
  vm.runInContext(readFileSync(join(__dirname,'../web/static/js/dashboard-notices.js'),'utf8'),context);
  return {elements,handlers,timers,calls,countdowns,get focused(){return focused;},setFail:value=>{failDelete=value;},setEntries:value=>{entries=value;}};
}

test('persistent inbox preserves nodes across polls, previews and tests without game commands',async()=>{
  const h=harness();await flush();
  const list=h.elements.get('notices-list'), entry=list.children[0];
  assert.equal(h.elements.get('notices-count').textContent,1);
  assert.equal(h.elements.get('s-notices-val').textContent,1);
  assert.equal(h.elements.get('notices-more').hidden,true);
  h.handlers.poll();await flush();assert.equal(list.children[0],entry);
  const card=entry.children[0].children[0];
  card.children[2].listeners.click();assert.equal(h.elements.get('notice-preview').open,true);
  h.elements.get('notice-preview-close').listeners.click();assert.equal(h.elements.get('notice-preview').open,false);
  await h.elements.get('notices-test').listeners.click();
  assert.match(h.elements.get('notices-test-result').textContent,/Detected: shard.*no tap sent/);
  assert(h.calls.every(call=>!call.url.includes('/command')));
});

test('failed delete preserves entry; successful acknowledgement animates and updates count',async()=>{
  const h=harness();await flush();
  const list=h.elements.get('notices-list'), entry=list.children[0];
  const button=entry.children[0].children[0].children[1].children[1];
  h.setFail(true);await button.listeners.click();
  assert.equal(button.disabled,false);assert.equal(list.children.length,1);
  assert.match(h.elements.get('notices-error').textContent,/Disk error/);
  h.setFail(false);await button.listeners.click();
  assert(entry.classList.contains('notice-removing'));
  assert.equal(h.elements.get('notices-count').textContent,0);
  assert.equal(h.elements.get('s-notices-val').textContent,0);
  assert.equal(h.elements.get('notices-empty').hidden,false);
  assert.equal(h.focused,h.elements.get('notices-test'));
  h.timers.forEach(callback=>callback());assert.equal(list.children.length,0);
  assert.equal(h.calls.find(call=>call.options?.method==='DELETE').options.headers['Content-Type'],'application/json');
  // A stale list response cannot resurrect an acknowledged image.
  h.setEntries([{id:'a'.repeat(32),created_ts:100,variant:'level',width:372,height:123}]);
  h.handlers.poll();await flush();assert.equal(list.children.length,0);
});

test('compact notice status keeps last-scan details in countdown tooltip data',async()=>{
  const h=harness();await flush();
  h.handlers.bot_state({notices:{enabled:true,last_scan_ts:100,last_scan_age:42,next_check_remaining:2700}});
  assert.equal(h.elements.get('s-notices-val').textContent,1);
  assert.equal(h.countdowns.at(-1)[0],'s-notices-next');
  assert.equal(h.countdowns.at(-1)[1].next_check_remaining,2700);
  assert.match(h.countdowns.at(-1)[2].detail,/Last scan: 42s ago/);
  h.handlers.bot_state({notices:{enabled:false,last_scan_age:50}});
  assert.equal(h.elements.get('s-notices-val').textContent,'OFF');
  assert.equal(h.elements.get('s-notices-val').className,'stat-value red');
  h.handlers.poll();await flush();
  assert.equal(h.elements.get('s-notices-val').textContent,'OFF');
  assert.equal(h.elements.get('notices-count').textContent,1);
  assert.equal(h.countdowns.at(-1)[1].enabled,false);
  assert.match(h.countdowns.at(-1)[2].detail,/50s ago/);
  h.handlers.bot_state({notices:{enabled:true,last_scan_age:null,error:'Capture failed'}});
  assert.equal(h.elements.get('s-notices-val').textContent,1);
  assert.equal(h.elements.get('s-notices-val').className,'stat-value green');
  assert.match(h.countdowns.at(-1)[2].detail,/Never scanned.*Capture failed/);
});

test('Notices settings render and save numbers, ROI, paths and startup independently',()=>{
  const container={innerHTML:''};
  const inputs=[
    {dataset:{section:'notices',key:'NOTICES_CHECK_INTERVAL_S'},value:'2700'},
    {dataset:{section:'notices',key:'NOTICES_INTERVAL_VARIANCE_PCT'},value:'15,5'},
    {dataset:{section:'notices',key:'NOTICES_DETECT_ROI',ftype:'array'},value:'0, 740, 390, 925'},
    {dataset:{section:'notices',key:'NOTICES_TEMPLATE_GLOB'},value:'Notices/*_frame.png'},
    {dataset:{section:'startup_defaults',key:'NOTICES_ENABLED'},value:'true'},
  ];
  let saved;
  const context=vm.createContext({esc:String,document:{getElementById:()=>container,querySelectorAll:()=>inputs},
    fetch:(url,options)=>{saved=JSON.parse(options.body);return Promise.resolve({json:()=>({ok:true})});},showToast(){}});
  vm.runInContext(readFileSync(join(__dirname,'../web/static/js/dashboard-settings.js'),'utf8').replace(/\nloadSettings\(\);\s*$/,''),context);
  vm.runInContext(`settingsData={notices:{NOTICES_CHECK_INTERVAL_S:2700,NOTICES_INTERVAL_VARIANCE_PCT:15,
    NOTICES_DETECT_ROI:[0,740,390,925],NOTICES_TEMPLATE_GLOB:'Notices/*_frame.png'},startup_defaults:{NOTICES_ENABLED:false}};
    renderSettings(settingsData);saveSettings();`,context);
  assert.match(container.innerHTML,/cfg-notices-NOTICES_CHECK_INTERVAL_S/);
  assert.match(container.innerHTML,/multiple masked frame variants/);
  assert.deepEqual(saved,{notices:{NOTICES_CHECK_INTERVAL_S:2700,NOTICES_INTERVAL_VARIANCE_PCT:15.5,
    NOTICES_DETECT_ROI:[0,740,390,925],NOTICES_TEMPLATE_GLOB:'Notices/*_frame.png'},startup_defaults:{NOTICES_ENABLED:true}});
});
