// Run with: node --test tests/test_dashboard_gem_stats.cjs
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, '../web/static/js/dashboard-gem-stats.js'), 'utf8');

function dashboard() {
  const elements = {};
  for (const id of ['card-gem-stats', 'gs-content', 'gs-inactive', 'gs-add', 'gs-legacy']) {
    const classes = new Set();
    elements[id] = {innerHTML: '', hidden: true, disabled: false, style: {},
      classList: {toggle(key, on) {on ? classes.add(key) : classes.delete(key);},
        contains(key) {return classes.has(key);}}};
  }
  let requests = 0;
  const context = vm.createContext({
    socket: {on() {}, emit() {}},
    document: {getElementById(id) {return elements[id] || null;}, querySelector() {return null;}},
    confirm() {return true;},
    fetch() {requests++; return Promise.resolve({json: () => Promise.resolve({ok: true, amount: 28})});},
    showToast() {},
  });
  vm.runInContext(source, context);
  const stats = {active: true, stats_start_ts: 1790841600, first_event_ts: 0,
    alltime_uptime_complete: true, uptime_session_s: 7200, uptime_24h_s: null,
    uptime_7d_s: null, uptime_alltime_s: 7200, wallclock_alltime_s: 14400,
    gem_since_startup: 28, gem_last_24h: null, gem_last_7d: null, gem_alltime: 28,
    gem_avg_per_hour_session: 14, gem_avg_per_hour_alltime: 7,
    gem_avg_per_hour_uptime_alltime: 14,
    wallclock_remaining_24h_s: 72000, wallclock_remaining_7d_s: 590400};
  const update = (patch = {}) => {
    Object.assign(stats, patch);
    context.updateGemStatsCard({gem_statistics: {...stats}});
  };
  return {context, elements, stats, update, requests: () => requests};
}

test('pause greys values, shows inactive label and disables manual additions; resume restores', () => {
  const d = dashboard();
  d.update();
  assert.equal(d.elements['gs-inactive'].hidden, true);
  d.update({active: false});
  assert.equal(d.elements['gs-inactive'].hidden, false);
  assert.equal(d.elements['card-gem-stats'].classList.contains('gs-paused'), true);
  assert.equal(d.elements['gs-add'].disabled, true);
  d.context.manualAddGem('gem');
  assert.equal(d.requests(), 0);
  assert.match(d.elements['gs-content'].innerHTML, />28</);
  d.update({active: true});
  assert.equal(d.elements['gs-inactive'].hidden, true);
  assert.equal(d.elements['card-gem-stats'].classList.contains('gs-paused'), false);
  assert.equal(d.elements['gs-add'].disabled, false);
  d.context.manualAddGem('gem');
  assert.equal(d.requests(), 1);
});

test('date and availability use statistics start even with no claims', () => {
  const d = dashboard();
  d.update();
  assert.match(d.elements['gs-content'].innerHTML, /since statistics started/);
  assert.doesNotMatch(d.elements['gs-content'].innerHTML, /no events|first event/);
  assert.match(d.elements['gs-content'].innerHTML, new RegExp(d.context._gsDate(d.stats.stats_start_ts)));
  d.update({stats_start_ts: 0, last_reset_ts: 1790841600, active: false});
  assert.match(d.elements['gs-content'].innerHTML, />All-Time</);
  assert.doesNotMatch(d.elements['gs-content'].innerHTML, />2026-/);
});

test('both modes render correct average and uptime-only changes refresh immediately', () => {
  const d = dashboard();
  d.update();
  assert.match(d.elements['gs-content'].innerHTML, />7</);
  d.context.toggleGsAvgMode();
  d.update({gem_avg_per_hour_uptime_alltime: 19.5});
  assert.match(d.elements['gs-content'].innerHTML, />19,5</);
  d.context.toggleGsAvgMode();
  assert.doesNotMatch(d.elements['gs-content'].innerHTML, />19,5</);
});

test('legacy uptime is unavailable rather than a misleading exact value or endless countdown', () => {
  const d = dashboard();
  d.update({alltime_uptime_complete: false, uptime_alltime_s: null,
    gem_avg_per_hour_uptime_alltime: null});
  assert.equal(d.elements['gs-legacy'].hidden, false);
  d.context.toggleGsAvgMode();
  assert.match(d.elements['gs-content'].innerHTML, /Historical uptime unavailable/);
  d.update({alltime_uptime_complete: true, uptime_alltime_s: 0});
  assert.equal(d.elements['gs-legacy'].hidden, true);
});

test('paused styling and accessible inactive status exist in the shipped dashboard', () => {
  const css = readFileSync(join(__dirname, '../web/static/css/dashboard.css'), 'utf8');
  const html = readFileSync(join(__dirname, '../web/templates/index.html'), 'utf8');
  assert.match(css, /\.gs-paused \.gs-table\{[^}]*opacity:\.5;[^}]*grayscale\(1\)/);
  assert.match(html, /id="gs-inactive"[^>]*role="status"[^>]*>Freebies inactive</);
});
