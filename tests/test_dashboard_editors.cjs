// Run with: node --test tests/test_dashboard_editors.cjs
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

test('Founders priority, chain limit and bounded Buy retries render and save', () => {
  const container = {innerHTML:''};
  const inputs = [
    ['lootbug','LOOTBUG_BUY_MAX_ATTEMPTS','4'],
    ['lootbug','LOOTBUG_FOUNDERS_LOOKAHEAD_S','0'],
    ['founders','FOUNDERS_MAX_CLAIMS_PER_CYCLE','2'],
  ].map(([section,key,value])=>({dataset:{section,key},value}));
  let saved;
  const context = vm.createContext({
    document:{getElementById(){return container;},querySelectorAll(){return inputs;}},
    fetch(url,options){saved=JSON.parse(options.body);return Promise.resolve({json:()=>({ok:true})});},
    showToast(){},
  });
  const source=readFileSync(join(__dirname,'../web/static/js/dashboard-settings.js'),'utf8');
  vm.runInContext(source.replace(/\nloadSettings\(\);\s*$/, ''),context);
  vm.runInContext(`settingsData={lootbug:{LOOTBUG_BUY_MAX_ATTEMPTS:5,LOOTBUG_FOUNDERS_LOOKAHEAD_S:5},
    founders:{FOUNDERS_MAX_CLAIMS_PER_CYCLE:3}};renderSettings(settingsData);saveSettings();`,context);
  for (const field of inputs) {
    assert.ok(container.innerHTML.includes(`cfg-${field.dataset.section}-${field.dataset.key}`));
  }
  assert.match(container.innerHTML,/fresh recheck after every tap/);
  assert.match(container.innerHTML,/release the action lock/);
  assert.match(container.innerHTML,/0 still yields for due checks/);
  assert.deepEqual(saved,{lootbug:{LOOTBUG_BUY_MAX_ATTEMPTS:4,LOOTBUG_FOUNDERS_LOOKAHEAD_S:0},
    founders:{FOUNDERS_MAX_CLAIMS_PER_CYCLE:2}});
});

test('Freebie-Gems FIRST and SLOW controls explain phases and save numeric seconds', () => {
  const container = {innerHTML:''};
  const inputs = [
    ['FREEBIES_CHECK_INTERVAL_S_FIRST','90'], ['FREEBIES_CHECK_INTERVAL_S_SLOW','2700'],
  ].map(([key,value])=>({dataset:{section:'freebies',key},value}));
  let saved;
  const context = vm.createContext({
    document:{getElementById(){return container;},querySelectorAll(){return inputs;}},
    fetch(url,options){saved=JSON.parse(options.body);return Promise.resolve({json:()=>({ok:true})});},
    showToast(){},
  });
  const source=readFileSync(join(__dirname,'../web/static/js/dashboard-settings.js'),'utf8');
  vm.runInContext(source.replace(/\nloadSettings\(\);\s*$/, ''),context);
  vm.runInContext(`settingsData={freebies:{FREEBIES_CHECK_INTERVAL_S_FIRST:300,
    FREEBIES_CHECK_INTERVAL_S_SLOW:2700}};renderSettings(settingsData);saveSettings();`,context);
  assert.match(container.innerHTML,/cfg-freebies-FREEBIES_CHECK_INTERVAL_S_FIRST/);
  assert.match(container.innerHTML,/cfg-freebies-FREEBIES_CHECK_INTERVAL_S_SLOW/);
  assert.match(container.innerHTML,/startup or activation/);
  assert.match(container.innerHTML,/slow mode until restart or reactivation/);
  assert.match(container.innerHTML,/2700 s \(45 minutes\)/);
  assert.deepEqual(saved.freebies,{FREEBIES_CHECK_INTERVAL_S_FIRST:90,
    FREEBIES_CHECK_INTERVAL_S_SLOW:2700});
});

test('Founders FIRST and SLOW intervals render with descriptions and save as numbers', () => {
  const container = {innerHTML:''};
  const inputs = [
    ['FOUNDERS_CHECK_INTERVAL_S_FIRST','45'], ['FOUNDERS_CHECK_INTERVAL_S_SLOW','7200'],
  ].map(([key,value])=>({dataset:{section:'founders',key},value}));
  let saved;
  const context = vm.createContext({
    document:{getElementById(){return container;},querySelectorAll(){return inputs;}},
    fetch(url,options){saved=JSON.parse(options.body);return Promise.resolve({json:()=>({ok:true})});},
    showToast(){},
  });
  const source=readFileSync(join(__dirname,'../web/static/js/dashboard-settings.js'),'utf8');
  vm.runInContext(source.replace(/\nloadSettings\(\);\s*$/, ''),context);
  vm.runInContext(`settingsData={founders:{FOUNDERS_CHECK_INTERVAL_S_FIRST:180,
    FOUNDERS_CHECK_INTERVAL_S_SLOW:3600}};renderSettings(settingsData);saveSettings();`,context);
  assert.match(container.innerHTML,/cfg-founders-FOUNDERS_CHECK_INTERVAL_S_FIRST/);
  assert.match(container.innerHTML,/cfg-founders-FOUNDERS_CHECK_INTERVAL_S_SLOW/);
  assert.match(container.innerHTML,/fast scans after startup, activation or a regular scan without a bundle/);
  assert.match(container.innerHTML,/returns to FIRST \(fast checks\)/);
  assert.match(container.innerHTML,/Immediate fresh rechecks after taps do not reset SLOW/);
  assert.deepEqual(saved.founders,{FOUNDERS_CHECK_INTERVAL_S_FIRST:45,
    FOUNDERS_CHECK_INTERVAL_S_SLOW:7200});
});

test('humanized tap controls render and save typed settings', () => {
  const container = {innerHTML:''};
  const inputs = [
    ['TAP_HUMANIZE_ENABLED','false'], ['TAP_HOLD_MS','120'],
    ['TAP_HOLD_VARIANCE_PCT','25,5'], ['TAP_JITTER_PX','6'],
  ].map(([key,value])=>({dataset:{section:'tapping',key},value}));
  let saved;
  const context = vm.createContext({
    document:{getElementById(){return container;},querySelectorAll(){return inputs;}},
    fetch(url,options){saved=JSON.parse(options.body);return Promise.resolve({json:()=>({ok:true})});},
    showToast(){},
  });
  const source=readFileSync(join(__dirname,'../web/static/js/dashboard-settings.js'),'utf8');
  vm.runInContext(source.replace(/\nloadSettings\(\);\s*$/, ''),context);
  vm.runInContext(`settingsData={tapping:{TAP_HUMANIZE_ENABLED:true,TAP_HOLD_MS:100,
    TAP_HOLD_VARIANCE_PCT:30,TAP_JITTER_PX:4}};renderSettings(settingsData);saveSettings();`,context);
  assert.match(container.innerHTML,/Humanized Taps/);
  assert.match(container.innerHTML,/cfg-tapping-TAP_HUMANIZE_ENABLED/);
  assert.match(container.innerHTML,/cfg-tapping-TAP_HOLD_VARIANCE_PCT/);
  assert.deepEqual(saved.tapping,{TAP_HUMANIZE_ENABLED:false,TAP_HOLD_MS:120,
    TAP_HOLD_VARIANCE_PCT:25.5,TAP_JITTER_PX:6});
});

test('settings preserve strings and arrays, accept decimal commas and do not truncate invalid numbers', () => {
  const inputs = [
    ['adb', 'DEVICE', '12345'],
    ['adb', 'ADB_CONNECT_TIMEOUT', '1,25'],
    ['adb', 'ADB_AUTO_CONNECT', 'false'],
    ['adb', 'ADB_SCAN_PORTS', '21503, 7555', 'array'],
    ['screenshot_viewer', 'SCREENSHOT_VIEWER_FILES', '123.png, game_scr.png', 'array'],
    ['freebies', 'FREEBIES_SCROLL_ATTEMPTS', '3oops'],
  ].map(([section, key, value, ftype]) => ({dataset:{section,key,ftype},value}));
  let saved;
  const context = vm.createContext({
    document:{querySelectorAll(){return inputs;}},
    fetch(url, options){saved=JSON.parse(options.body);return Promise.resolve({json:()=>({ok:true})});},
    showToast(){},
  });
  const source=readFileSync(join(__dirname, '../web/static/js/dashboard-settings.js'),'utf8');
  vm.runInContext(source.replace(/\nloadSettings\(\);\s*$/, ''), context);
  vm.runInContext(`settingsData={
    adb:{DEVICE:'old',ADB_CONNECT_TIMEOUT:1,ADB_AUTO_CONNECT:true,ADB_SCAN_PORTS:[1]},
    screenshot_viewer:{SCREENSHOT_VIEWER_FILES:['game_scr.png']},
    freebies:{FREEBIES_SCROLL_ATTEMPTS:4}
  }; saveSettings();`, context);
  assert.equal(saved.adb.DEVICE, '12345');
  assert.equal(saved.adb.ADB_CONNECT_TIMEOUT, 1.25);
  assert.equal(saved.adb.ADB_AUTO_CONNECT, false);
  assert.deepEqual(saved.adb.ADB_SCAN_PORTS, [21503,7555]);
  assert.deepEqual(saved.screenshot_viewer.SCREENSHOT_VIEWER_FILES, ['123.png','game_scr.png']);
  assert.equal(saved.freebies.FREEBIES_SCROLL_ATTEMPTS, null); // server rejects, never silently becomes 3
});

test('workflow editor saves blank areas as empty arrays and preserves valid coordinates', () => {
  const area = {dataset:{path:'0.area',ftype:'roi'},value:'',tagName:'INPUT'};
  const body = {dataset:{wfkey:'wf'},querySelectorAll(selector){
    return selector.startsWith('input[data-path]') ? [area] : [];
  }};
  const context = vm.createContext({
    localStorage:{getItem(){return null;}},
    document:{querySelectorAll(){return [body];}},
  });
  const source=readFileSync(join(__dirname, '../web/static/js/dashboard-workflow-editor-core.js'),'utf8');
  vm.runInContext(source,context);
  vm.runInContext("wfeData={wf:{steps:[{type:'swipe',area:null}]}}",context);
  const collect=()=>JSON.parse(vm.runInContext('JSON.stringify(collectWorkflows())',context));
  assert.deepEqual(collect().wf.steps[0].area, []);
  area.value='0, 102, 900, 1457';
  assert.deepEqual(collect().wf.steps[0].area, [0,102,900,1457]);
  area.value='0, invalid, 900, 1457';
  assert.deepEqual(collect().wf.steps[0].area, [0,null,900,1457]);
});
