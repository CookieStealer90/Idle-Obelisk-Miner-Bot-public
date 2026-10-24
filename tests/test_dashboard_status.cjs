const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
function harness(){
  const elements=new Map();
  function element(){return {textContent:'',style:{},dataset:{},title:'',writes:0,
    classList:{add(){}},setAttribute(k,v){this[k]=v;},
    querySelector(s){return this.nodes?.[s]||null;},
    set innerHTML(v){this.writes++;this.nodes={'.scan-time':element(),'.scan-fill':element()};}};}
  const context=vm.createContext({fmtSec:s=>s+'s',document:{getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);}}});
  vm.runInContext(readFileSync(join(__dirname,'../web/static/js/dashboard-status.js'),'utf8'),context);
  return {elements,status:data=>context.updateStatus(data),update:(data,options)=>context.updateScanCountdown('timer',data,options)};
}
test('countdown preserves DOM nodes while time and progress change',()=>{
  const h=harness();
  h.update({enabled:true,next_check_ts:500,next_check_remaining:120});
  const host=h.elements.get('timer'), time=host.querySelector('.scan-time'),fill=host.querySelector('.scan-fill');
  assert.equal(time.textContent,'2:00');
  h.update({enabled:true,next_check_ts:500,next_check_remaining:60});
  assert.equal(time.textContent,'1:00');
  assert.equal(fill.style.transform,'scaleX(0.5000)');
  assert.equal(host.writes,1);
  assert.equal(host.querySelector('.scan-time'),time);
  h.update({enabled:true,next_check_ts:500,next_check_remaining:0});
  assert.equal(time.textContent,'Ready');assert.equal(host.dataset.mode,'ready');
});
test('new deadlines and reactivation reset progress; disabled scans stay empty',()=>{
  const h=harness();
  h.update({enabled:true,next_check_ts:500,next_check_remaining:120});
  h.update({enabled:true,next_check_ts:500,next_check_remaining:60});
  h.update({enabled:true,next_check_ts:600,next_check_remaining:15});
  const host=h.elements.get('timer'),fill=host.querySelector('.scan-fill');
  assert.equal(fill.style.transform,'scaleX(0.0000)');
  h.update({enabled:false,next_check_remaining:10});
  assert.equal(host.querySelector('.scan-time').textContent,'Off');assert.equal(host.dataset.mode,'off');
  h.update({enabled:true,next_check_ts:600,next_check_remaining:5});
  assert.equal(fill.style.transform,'scaleX(0.0000)');assert.equal(host.writes,1);
});
test('long countdowns stay compact and error details remain accessible as plain text',()=>{
  const h=harness();
  h.update({enabled:true,next_check_remaining:3661},{detail:'Last scan: 42s ago; <capture failed>'});
  const host=h.elements.get('timer');
  assert.equal(host.querySelector('.scan-time').textContent,'1:01:01');
  assert.match(host.title,/Last scan: 42s ago; <capture failed>/);
  assert.equal(host['aria-label'],host.title);
  h.update({enabled:true},{blocked:'Setup'});
  assert.equal(host.querySelector('.scan-time').textContent,'Setup');
  assert.equal(host.querySelector('.scan-fill').style.transform,'scaleX(0.0000)');
});

test('status updates retain unchanged value markup and countdown nodes across all scan tiles',()=>{
  const h=harness(),scan={enabled:true,next_check_ts:500,next_check_remaining:60};
  const state={game_running:true,freebies:{...scan,claimed:3,diamonds:84},
    lootbug:{...scan,clicked:12},founders:{...scan,clicked:2},
    detect_level:{...scan,armed:true,current:226,last_age:8}};
  h.status(state);
  const value=h.elements.get('s-gem-val'),countdown=h.elements.get('s-gem-next');
  assert.equal(value.writes,1);assert.equal(countdown.writes,1);
  state.freebies.next_check_remaining=30;h.status(state);
  assert.equal(value.writes,1);assert.equal(countdown.writes,1);
  assert.equal(countdown.querySelector('.scan-time').textContent,'0:30');
  state.detect_level.armed=false;h.status(state);
  assert.equal(h.elements.get('s-level-next').querySelector('.scan-time').textContent,'Setup');
});
