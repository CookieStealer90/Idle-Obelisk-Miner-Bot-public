/* ============================================================
   dashboard-gem-stats.js — Gem Statistics sidebar tile
   4-column layout: Label | Uptime | Total | avg/h
   Mobile: Uptime column hidden
   ============================================================ */

/* -- Average mode: 'wallclock' (default) or 'uptime' -- */
var _gsAvgMode = 'wallclock';

function toggleGsAvgMode() {
  _gsAvgMode = (_gsAvgMode === 'wallclock') ? 'uptime' : 'wallclock';
  /* Force re-render with last known data */
  _gsLastFingerprint = '';
  if (_gsLastData) updateGemStatsCard(_gsLastData);
}

/* Cache last bot_state data so we can re-render on mode toggle */
var _gsLastData = null;

/* -- Visibility toggle state (synced via socket.io) -- */
var _gsVisibility = { gem: true, actions: true };
var _gsVisSyncLock = false;

function toggleGsVisibility(key) {
  /* Count how many are currently ON */
  var onCount = (_gsVisibility.gem ? 1 : 0)
              + (_gsVisibility.actions ? 1 : 0);

  /* If this is the last active one, prevent turning it off */
  if (_gsVisibility[key] && onCount <= 1) return;

  _gsVisibility[key] = !_gsVisibility[key];
  applyGsVisibility();
  pushGsVisibility();
}

function applyGsVisibility() {
  /* Update button classes */
  var keys = ['gem', 'actions'];
  keys.forEach(function(k) {
    var btn = document.getElementById('gs-vis-' + k);
    if (btn) {
      btn.classList.toggle('on', _gsVisibility[k]);
      btn.classList.toggle('off', !_gsVisibility[k]);
    }
  });

  /* Show/hide gem section */
  var gemTable = document.getElementById('gs-section-gem');
  if (gemTable) gemTable.style.display = _gsVisibility.gem ? '' : 'none';

  /* Show/hide action buttons row */
  var actRow = document.querySelector('.gs-action-row');
  if (actRow) actRow.style.display = _gsVisibility.actions ? '' : 'none';
}

function pushGsVisibility() {
  if (_gsVisSyncLock) return;
  socket.emit('gs_visibility_update', _gsVisibility);
}

/* Receive sync from server */
socket.on('gs_visibility_sync', function(data) {
  if (!data || typeof data !== 'object') return;
  _gsVisSyncLock = true;
  _gsVisibility.gem      = data.gem !== false;
  _gsVisibility.actions  = data.actions !== false;
  applyGsVisibility();
  _gsVisSyncLock = false;
});

function _gsFmt(n) {
  if (n == null || n === undefined) return '\u2013';
  return Number(n).toLocaleString('de-DE');
}

/* ---- Remaining-time tooltip for hourglass icons ---- */
function _gsRemaining(sec) {
  if (!sec || sec <= 0) return null;
  sec = Math.ceil(sec);
  var d = Math.floor(sec / 86400);
  var h = Math.floor((sec % 86400) / 3600);
  var m = Math.floor((sec % 3600) / 60);
  if (d > 0) return '~' + d + 'd ' + h + 'h';
  if (h > 0) return '~' + h + 'h ' + m + 'm';
  return '~' + Math.max(1, m) + 'm';
}

function _gsVal(val, tooltip) {
  if (val == null || val === undefined) {
    var tip = tooltip ? ' title="' + tooltip + '"' : '';
    return '<span class="gs-nodata"' + tip + '>&#x23F3;</span>';
  }
  return _gsFmt(val);
}

/* ---- Uptime formatting ---- */
function _gsUptimeShort(sec) {
  /* < 24h: "H:MM", 1-99d: "Xd Yh", 100d+: "Xd" */
  if (sec == null || sec === undefined) return null;
  sec = Math.max(0, Math.floor(sec));
  var d = Math.floor(sec / 86400);
  var h = Math.floor((sec % 86400) / 3600);
  var m = Math.floor((sec % 3600) / 60);
  if (d >= 100) return d + 'd';
  if (d >= 1) return d + 'd ' + h + 'h';
  return h + ':' + ('0' + m).slice(-2);
}

function _gsUptimeFull(sec) {
  /* Always full: "Xd Yh Zm" */
  if (sec == null || sec === undefined) return '';
  sec = Math.max(0, Math.floor(sec));
  var d = Math.floor(sec / 86400);
  var h = Math.floor((sec % 86400) / 3600);
  var m = Math.floor((sec % 3600) / 60);
  var parts = [];
  if (d > 0) parts.push(d + 'd');
  if (h > 0 || d > 0) parts.push(h + 'h');
  parts.push(m + 'm');
  return parts.join(' ');
}

function _gsUptimeCell(sec, tooltip, suffix) {
  if (sec == null || sec === undefined) {
    var tip = tooltip ? ' title="' + tooltip + '"' : '';
    return '<span class="gs-nodata"' + tip + '>&#x23F3;</span>';
  }
  var short = _gsUptimeShort(sec);
  var sfx = suffix ? '<span class="gs-up-suffix">' + suffix + '</span>' : '';
  if (sec >= 86400) {
    return '<span title="' + _gsUptimeFull(sec) + '">' + short + '</span>' + sfx;
  }
  return short + sfx;
}

function _gsDate(ts) {
  if (!ts || ts <= 0) return null;
  var d = new Date(ts * 1000);
  var y = d.getFullYear();
  var m = ('0' + (d.getMonth() + 1)).slice(-2);
  var day = ('0' + d.getDate()).slice(-2);
  return y + '-' + m + '-' + day;
}

function resetGemStats() {
  if (!confirm('Reset all statistics?\n\nThis clears everything: all-time totals, 24h/7d history, uptime tracking, and session counters.\nThis cannot be undone.')) return;
  fetch('/api/gem_stats/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: 'alltime' })
  })
    .then(function(r) { return r.json(); })
    .then(function(r) {
      if (r.ok) showToast('Gem statistics reset');
      else showToast('Reset failed: ' + (r.error || '?'), true);
    })
    .catch(function(e) { showToast('Reset error: ' + e, true); });
}

function manualAddGem(type) {
  var label = 'Freebie-Gem';
  if (!confirm('Manually add one ' + label + ' claim to statistics?\n\n(This does not trigger any cooldown)')) return;
  fetch('/api/gem_stats/manual_add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: 'gem' })
  })
    .then(function(r) { return r.json(); })
    .then(function(r) {
      if (r.ok) showToast(label + ' claim added (+' + r.amount + ' \uD83D\uDC8E)');
      else showToast('Add failed: ' + (r.error || '?'), true);
    })
    .catch(function(e) { showToast('Add error: ' + e, true); });
}

function showGemStatsHelp(e) {
  if (e) e.stopPropagation();
  var ov = document.createElement('div');
  ov.className = 'gs-help-overlay';
  ov.onclick = function(ev) { if (ev.target === ov) ov.remove(); };
  ov.innerHTML = '<div class="gs-help-box">'
    + '<span class="gs-h-close" onclick="this.closest(\'.gs-help-overlay\').remove()">&times;</span>'
    + '<h3>\uD83D\uDCC8 Freebie-Gems Statistics Guide</h3>'

    + '<h4>\uD83D\uDD39 Columns</h4>'
    + '<p><b>Uptime</b> \u2014 Actual bot running time within this time window. '
    + 'If the bot was offline for part of the period, this will be less than the wall-clock duration. '
    + 'The suffix shows the reference window: <b>/24h</b> and <b>/7d</b> for the rolling windows, '
    + 'and for All-Time the suffix shows the total wall-clock time since statistics began '
    + '(e.g. <i>8d 23h/10d</i> means the bot was up 8d 23h out of 10 days total).</p>'
    + '<p><b>Total</b> \u2014 Total diamonds collected in this time window.</p>'
    + '<p><b>\u2300/h</b> \u2014 Average diamonds per hour. <b>Click the column header to toggle between two modes:</b></p>'
    + '<p style="margin-left:10px"><b>Wall-clock mode</b> (default, header shows \u2300/h) \u2014 '
    + 'Divides total by the full elapsed time window (24h, 7d, or total time since first event). '
    + 'Offline periods count against you, so the average reflects your real-world yield over time. '
    + 'Uptime suffixes (/24h, /7d, /wallclock) are shown.</p>'
    + '<p style="margin-left:10px"><b>Uptime mode</b> (header shows \u2300/h \u23F1) \u2014 '
    + 'Divides total only by the actual bot running time (uptime). '
    + 'Offline periods are excluded, so you see the true collection rate while the bot was active. '
    + 'Uptime suffixes are hidden since the uptime column already represents the denominator. '
    + 'Session row is identical in both modes (the bot was running the entire session).</p>'

    + '<h4>\uD83D\uDD39 Rows</h4>'
    + '<p><b>Session</b> \u2014 Data since the bot was last started. Resets on every restart. '
    + 'The \u2300/h here uses actual session uptime as denominator (the bot was running the entire time).</p>'
    + '<p><b>last 24h</b> \u2014 Rolling 24-hour window based on real time (wall-clock). '
    + 'Becomes available 24 hours after the first gem is ever recorded. '
    + 'Hover the \u23F3 icon to see the remaining time.</p>'
    + '<p><b>last 7 days</b> \u2014 Rolling 7-day window based on real time. '
    + 'Becomes available 7 calendar days after the first gem is recorded.</p>'
    + '<p><b>All-Time (date)</b> \u2014 Cumulative totals since the last reset (or since the very first gem). '
    + 'The row label shows the start date directly (e.g. 2026-02-26). '
    + 'The \u2300/h uses total wall-clock time since that date (in wall-clock mode).</p>'

    + '<h4>\uD83D\uDD39 Buttons</h4>'
    + '<p><b>+ add gem claim</b> \u2014 '
    + 'Manually adds one claim to the statistics, as if the bot had collected it. '
    + 'Use this when you clicked a gem yourself in-game. '
    + 'The amount added equals your configured <i>diamonds_per_claim</i> (default: 5). '
    + 'This does <b>not</b> trigger any cooldown.</p>'
    + '<p><b>Reset all Statistics</b> \u2014 '
    + 'Clears everything: all-time totals, 24h/7d rolling history, uptime tracking, '
    + 'and session counters. All data is permanently deleted. Use this for a complete fresh start.</p>'

    + '<p class="gs-h-dim" style="margin-top:10px">Data is persisted to gem_statistics.json and survives restarts. '
    + 'Hourly buckets older than 7 days are automatically pruned.</p>'
    + '</div>';
  document.body.appendChild(ov);
}

/**
 * Build stats table for one gem type.
 * 4 columns: Label | Uptime | Total | avg/h
 * Respects _gsAvgMode: 'wallclock' uses wall-clock averages, 'uptime' uses bot-uptime averages.
 */
function _gsSection(title, s, sinceDate, tips) {
  var isUptime = (_gsAvgMode === 'uptime');
  var avgTooltip = isUptime
    ? 'Mode: Uptime \u2014 average based on actual bot running time. Click to switch to wall-clock mode.'
    : 'Mode: Wall-clock \u2014 average based on real elapsed time (incl. offline). Click to switch to uptime mode.';
  var avgLabel = isUptime ? '\u2300/h \u23F1' : '\u2300/h';

  var h = '<table class="gs-table">';
  h += '<thead>';
  h += '<tr class="gs-th-cols">';
  h += '<td class="gs-th-title">' + title + '</td>';
  h += '<td class="gs-col-up">Uptime</td>';
  h += '<td>Total</td>';
  h += '<td class="gs-avg-toggle" onclick="toggleGsAvgMode()" title="' + avgTooltip + '">' + avgLabel + '</td>';
  h += '</tr></thead><tbody>';

  /* Session -- always uses session uptime as denominator (identical in both modes) */
  h += '<tr>';
  h += '<td class="gs-td-label">Session</td>';
  h += '<td class="gs-td-up gs-col-up">' + _gsUptimeCell(s.up_session, tips.session) + '</td>';
  h += '<td class="gs-td-val">' + _gsFmt(s.session) + '</td>';
  h += '<td class="gs-td-avg">' + _gsVal(s.avg_session, tips.session) + '</td>';
  h += '</tr>';

  /* last 24h */
  var avg24 = isUptime ? s.avg_up_24h : s.avg_24h;
  var sfx24 = (!isUptime && s.up_24h != null) ? '/24h' : null;
  h += '<tr>';
  h += '<td class="gs-td-label">last 24h</td>';
  h += '<td class="gs-td-up gs-col-up">' + _gsUptimeCell(s.up_24h, tips.h24, sfx24) + '</td>';
  h += '<td class="gs-td-val">' + _gsVal(s.last_24h, tips.h24) + '</td>';
  h += '<td class="gs-td-avg">' + _gsVal(avg24, tips.h24) + '</td>';
  h += '</tr>';

  /* last 7 days */
  var avg7 = isUptime ? s.avg_up_7d : s.avg_7d;
  var sfx7 = (!isUptime && s.up_7d != null) ? '/7d' : null;
  h += '<tr>';
  h += '<td class="gs-td-label">last 7 days</td>';
  h += '<td class="gs-td-up gs-col-up">' + _gsUptimeCell(s.up_7d, tips.d7, sfx7) + '</td>';
  h += '<td class="gs-td-val">' + _gsVal(s.last_7d, tips.d7) + '</td>';
  h += '<td class="gs-td-avg">' + _gsVal(avg7, tips.d7) + '</td>';
  h += '</tr>';

  /* All-Time -- show date directly as label */
  var atLabel = sinceDate ? sinceDate : 'All-Time';
  var avgAt = isUptime ? s.avg_up_alltime : s.avg_alltime;
  var atSuffix = null;
  if (!isUptime && s.wallclock_alltime != null && s.wallclock_alltime > 0) {
    atSuffix = '/' + _gsUptimeShort(s.wallclock_alltime);
  }
  h += '<tr>';
  h += '<td class="gs-td-label">' + atLabel + '</td>';
  h += '<td class="gs-td-up gs-col-up">' + _gsUptimeCell(s.up_alltime, null, atSuffix) + '</td>';
  h += '<td class="gs-td-val">' + _gsFmt(s.alltime) + '</td>';
  h += '<td class="gs-td-avg">' + _gsVal(avgAt, tips.alltime) + '</td>';
  h += '</tr>';

  h += '</tbody></table>';
  return h;
}

/* -- Fingerprint to skip redundant re-renders -- */
var _gsLastFingerprint = '';

function _gsFingerprint(gs) {
  return [
    Math.floor((gs.uptime_session_s || 0) / 60),
    gs.uptime_24h_s, gs.uptime_7d_s,
    Math.floor((gs.uptime_alltime_s || 0) / 60),
    Math.floor((gs.wallclock_alltime_s || 0) / 60),
    gs.gem_since_startup, gs.gem_last_24h, gs.gem_last_7d, gs.gem_alltime,
    gs.gem_avg_per_hour_session, gs.gem_avg_per_hour_24h, gs.gem_avg_per_hour_7d, gs.gem_avg_per_hour_alltime,
    gs.first_event_ts, gs.last_reset_ts
  ].join('|');
}

function updateGemStatsCard(d) {
  var gs = d.gem_statistics;
  if (!gs) return;

  _gsLastData = d;

  /* Skip re-render if nothing visible changed */
  var fp = _gsFingerprint(gs);
  if (fp === _gsLastFingerprint) return;
  _gsLastFingerprint = fp;

  var container = document.getElementById('gs-content');
  if (!container) return;

  var sinceTs = (gs.last_reset_ts && gs.last_reset_ts > 0) ? gs.last_reset_ts : gs.first_event_ts;
  var sinceDate = _gsDate(sinceTs);

  /* Remaining-time tooltips */
  var uptime = gs.uptime_session_s || 0;
  var up24h = gs.uptime_24h_s;
  var up7d = gs.uptime_7d_s;
  var upAll = gs.uptime_alltime_s || 0;
  var wc24h = gs.wallclock_remaining_24h_s;
  var wc7d = gs.wallclock_remaining_7d_s;
  var firstTs = gs.first_event_ts || 0;
  var tips = { session: null, h24: null, d7: null, alltime: null };

  if (uptime < 3600)
    tips.session = 'available after 1h session uptime (' + _gsRemaining(3600 - uptime) + ' remaining)';
  if (firstTs <= 0)
    tips.h24 = 'available after 24h \u2014 no events recorded yet';
  else if (up24h == null)
    tips.h24 = 'available after 24h since first event (' + _gsRemaining(wc24h) + ' remaining)';
  if (firstTs <= 0)
    tips.d7 = 'available after 7 days \u2014 no events recorded yet';
  else if (up7d == null)
    tips.d7 = 'available after 7 days since first event (' + _gsRemaining(wc7d) + ' remaining)';
  if (firstTs <= 0)
    tips.alltime = 'available after 1h session uptime \u2014 no events recorded yet';
  else if (upAll < 3600)
    tips.alltime = 'available after 1h session uptime (' + _gsRemaining(3600 - upAll) + ' remaining)';

  var wcAlltime = gs.wallclock_alltime_s || 0;

  var html = '<div id="gs-section-gem">';
  html += _gsSection('Freebie-Gems &#x1F48E;', {
    session:     gs.gem_since_startup,
    last_24h:    gs.gem_last_24h,
    last_7d:     gs.gem_last_7d,
    alltime:     gs.gem_alltime,
    avg_session: gs.gem_avg_per_hour_session,
    avg_24h:     gs.gem_avg_per_hour_24h,
    avg_7d:      gs.gem_avg_per_hour_7d,
    avg_alltime: gs.gem_avg_per_hour_alltime,
    avg_up_24h:      gs.gem_avg_per_hour_uptime_24h,
    avg_up_7d:       gs.gem_avg_per_hour_uptime_7d,
    avg_up_alltime:  gs.gem_avg_per_hour_uptime_alltime,
    up_session:  gs.uptime_session_s,
    up_24h:      gs.uptime_24h_s,
    up_7d:       gs.uptime_7d_s,
    up_alltime:  gs.uptime_alltime_s,
    wallclock_alltime: wcAlltime
  }, sinceDate, tips);
  html += '</div>';

  container.innerHTML = html;

  /* Re-apply visibility after re-rendering content */
  applyGsVisibility();
}
