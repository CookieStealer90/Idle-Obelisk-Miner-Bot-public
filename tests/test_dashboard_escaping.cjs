const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

function context() {
  const container = {innerHTML:''};
  const ctx = vm.createContext({container, localStorage:{getItem:()=>null},
    document:{getElementById:()=>container, querySelectorAll:()=>[]}});
  const core = readFileSync(join(__dirname,'../web/static/js/dashboard-core.js'),'utf8');
  vm.runInContext(core.split('\n').filter(line=>/^function (esc|jsArg)\(/.test(line)).join('\n'),ctx);
  return ctx;
}
function load(ctx,name) {
  vm.runInContext(readFileSync(join(__dirname,'../web/static/js/'+name),'utf8'),ctx);
}
function decode(value) {
  return value.replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<')
    .replace(/&gt;/g,'>').replace(/&amp;/g,'&');
}

test('workflow names and comments preserve quotes and literal entities in attributes',()=>{
  const ctx=context();
  load(ctx,'dashboard-workflow-editor-core.js');
  load(ctx,'dashboard-workflow-editor-render.js');
  ctx.value='Use "Bomb" & \'Close\' <now> &quot;';
  const html=vm.runInContext("renderField({k:'name',label:'Name',type:'text'},value,'wf','name',false,true)",ctx);
  assert.equal(decode(html.match(/ value="([^"]*)"/)[1]),ctx.value);
  const note=vm.runInContext("_renderStepNote({note:value},'0')",ctx);
  assert.equal(decode(note.match(/ value="([^"]*)"/)[1]),ctx.value);
});

test('HTML-decoded inline handlers pass arbitrary slugs as one inert argument',()=>{
  const ctx=context();
  load(ctx,'dashboard-workflow-editor-core.js');
  load(ctx,'dashboard-workflow-editor-render.js');
  const slug=`wf');globalThis.injected=true;//"`;
  ctx.payload={[slug]:{name:'Example',steps:[]}};
  vm.runInContext('wfeData=payload;renderWorkflowEditor({})',ctx);
  let deleted;
  ctx.delWorkflow=value=>{deleted=value;};
  const handler=ctx.container.innerHTML.match(/onclick="(delWorkflow\([^\n]*?)"/)[1];
  vm.runInContext(decode(handler),ctx);
  assert.equal(deleted,slug);
  assert.equal(ctx.injected,undefined);
});

test('settings strings cannot introduce attributes and roundtrip literal quotes',()=>{
  const ctx=context();
  const source=readFileSync(join(__dirname,'../web/static/js/dashboard-settings.js'),'utf8');
  vm.runInContext(source.replace(/\nloadSettings\(\);\s*$/,''),ctx);
  ctx.value='device" autofocus onfocus="injected()';
  vm.runInContext('renderSettings({adb:{DEVICE:value}})',ctx);
  const html=ctx.container.innerHTML;
  assert.equal(decode(html.match(/ value="([^"]*)"/)[1]),ctx.value);
  assert.doesNotMatch(html,/" autofocus/);
});
