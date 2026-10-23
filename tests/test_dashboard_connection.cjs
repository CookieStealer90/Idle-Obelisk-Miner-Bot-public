// Run with: node --test tests/test_dashboard_connection.cjs
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, '../web/static/js/dashboard-core.js'), 'utf8');

function dashboard() {
  const handlers = {};
  const listeners = {};
  const elements = new Map();
  const socket = {
    connectCalls: 0,
    on(event, handler) { handlers[event] = handler; },
    connect() { this.connectCalls++; if (this.onConnect) this.onConnect(); },
  };
  let options;
  const context = vm.createContext({
    io(config) { options = config; return socket; },
    document: {
      addEventListener(event, handler) { listeners[event] = handler; },
      querySelector() { return null; },
      getElementById(id) {
        if (!elements.has(id)) {
          const classes = new Set();
          elements.set(id, {
            textContent: id === 'conn-text' ? 'connecting…' : '',
            style: {},
            classList: {
              toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); },
              contains(name) { return classes.has(name); },
            },
          });
        }
        return elements.get(id);
      },
    },
    localStorage: {getItem() { return null; }},
    setTimeout() { return 1; },
    clearTimeout() {},
  });
  vm.runInContext(source, context);
  function badge(expected) {
    assert.equal(elements.get('conn-text').textContent, expected ? 'connected' : 'disconnected');
    assert.equal(elements.get('conn-dot').classList.contains('on'), expected);
    assert.equal(vm.runInContext('connected', context), expected);
  }
  return {socket, handlers, listeners, context, badge, options};
}

test('waits for dashboard modules before connecting, including early server state', () => {
  const d = dashboard();
  assert.equal(d.options.autoConnect, false);
  assert.equal(d.options.reconnection, true);
  assert.equal(d.socket.connectCalls, 0);
  const updates = [];
  // These renderers are supplied by scripts loaded after dashboard-core.js.
  for (const name of ['updateStatus', 'updateButtons', 'updateWorkflows', 'updateGemStatsCard']) {
    d.context[name] = () => updates.push(name);
  }
  d.socket.onConnect = () => {
    // Flask's connect handler sends state before the Socket.IO connect event.
    d.handlers.bot_state({started: true});
    d.handlers.connect();
  };
  d.listeners.DOMContentLoaded();
  assert.equal(d.socket.connectCalls, 1);
  assert.equal(updates.length, 4);
  d.badge(true);
});

test('live state repairs stale connection badge even before the bot starts', () => {
  const d = dashboard();
  d.handlers.bot_state({started: false});
  d.badge(true);
  d.handlers.disconnect();
  d.badge(false);
  d.handlers.bot_state({started: false});
  d.badge(true);
});

test('connection errors and repeated disconnect/reconnect cycles update the badge', () => {
  const d = dashboard();
  for (let i = 0; i < 3; i++) {
    d.handlers.connect_error(new Error('server unavailable'));
    d.badge(false);
    d.handlers.connect();
    d.badge(true);
    d.handlers.disconnect();
    d.badge(false);
    d.handlers.connect();
    d.badge(true);
  }
});
