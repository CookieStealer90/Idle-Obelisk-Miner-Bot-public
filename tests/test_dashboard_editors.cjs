// Run with: node --test tests/test_dashboard_editors.cjs
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

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
