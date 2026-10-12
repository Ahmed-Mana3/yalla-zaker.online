/* yalla zaker — study room page: live presence, ticking clocks, invite sharing. */
(function () {
  'use strict';

  var POLL_MS = 15000;

  /* ---------- helpers ---------- */
  function fmt(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    var h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
    if (h) return h + 'h ' + m + 'm';
    if (m) return s ? m + 'm ' + s + 's' : m + 'm';
    return s + 's';
  }
  function clock(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    var h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
    var mm = (m < 10 ? '0' : '') + m, ss = (s < 10 ? '0' : '') + s;
    return h ? h + ':' + mm + ':' + ss : mm + ':' + ss;
  }
  function field(row, name) { return row.querySelector('[data-f="' + name + '"]'); }

  /* ---------- invite: copy + native share ---------- */
  (function () {
    var input = document.getElementById('sr-invite-url');
    var copyBtn = document.getElementById('sr-copy');
    var shareBtn = document.getElementById('sr-share');
    var dockBtns = Array.prototype.slice.call(document.querySelectorAll('.sr-copy-btn'));
    var status = document.getElementById('sr-copy-status');
    if (!input || !copyBtn) return;
    var original = status ? status.textContent : '';
    var resetTimer;

    function share() {
      return navigator.share({
        title: document.title.split(' · ')[0],
        text: 'Study with me on yalla zaker',
        url: input.value
      }).catch(function () { /* dismissed */ });
    }
    function label(btn, text) { if (!btn.getAttribute('data-label')) btn.setAttribute('data-label', btn.textContent); btn.textContent = text; }
    function done(ok) {
      [copyBtn].concat(dockBtns).forEach(function (b) { label(b, ok ? 'Copied ✓' : 'Copy failed'); });
      if (status) status.textContent = ok ? 'Link copied. Paste it anywhere to invite people.' : 'Select the link and copy it.';
      clearTimeout(resetTimer);
      resetTimer = setTimeout(function () {
        [copyBtn].concat(dockBtns).forEach(function (b) { b.textContent = b.getAttribute('data-label'); });
        if (status) status.textContent = original;
      }, 2500);
    }
    function fallback() {
      input.focus({ preventScroll: true });
      input.select();
      input.setSelectionRange(0, input.value.length);   // iOS ignores select() alone
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      done(ok);
    }
    function copy() {
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(input.value).then(function () { done(true); }, fallback);
      } else {
        fallback();
      }
    }
    copyBtn.addEventListener('click', copy);
    // On phones the share sheet (WhatsApp, Messages…) beats copy-and-paste.
    dockBtns.forEach(function (b) { b.addEventListener('click', navigator.share ? share : copy); });
    if (shareBtn && navigator.share) {
      shareBtn.hidden = false;
      shareBtn.addEventListener('click', share);
    }
  })();

  /* ---------- status line without a page reload ---------- */
  (function () {
    var form = document.getElementById('sr-goal-form');
    var saved = document.getElementById('sr-saved');
    if (!form || !window.fetch) return;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'fetch' },
        credentials: 'same-origin'
      }).then(function (r) {
        if (!r.ok) throw new Error('bad status');
        if (saved) saved.textContent = 'Saved ✓';
        poll();
      }).catch(function () {
        form.submit();   // fall back to a normal post so nothing is lost
      });
    });
  })();

  /* ---------- live presence ---------- */
  var live = document.getElementById('room-live');
  if (!live) return;
  var list = document.getElementById('sr-list');
  var syncEl = document.getElementById('sr-sync');
  var syncText = document.getElementById('sr-sync-text');
  var stateUrl = live.getAttribute('data-state-url');
  var range = live.getAttribute('data-range');
  var snapshotAt = Date.now();
  var inFlight = false;

  function setSync(ok) {
    if (!syncEl) return;
    syncEl.classList.toggle('is-error', !ok);
    syncText.textContent = ok ? 'Live' : 'Reconnecting…';
    var dot = syncEl.querySelector('.status-dot');
    if (dot) dot.className = 'status-dot ' + (ok ? 'status-live' : 'status-paused');
  }

  function applyRow(row, data) {
    row.setAttribute('data-status', data.status);
    row.setAttribute('data-seconds', data.seconds);
    if (data.elapsed === null) row.removeAttribute('data-elapsed');
    else row.setAttribute('data-elapsed', data.elapsed);
    field(row, 'dot').className = 'status-dot status-' + data.status;
    field(row, 'label').textContent = data.label;
    field(row, 'goal').textContent = data.goal;
    field(row, 'rank').textContent = data.rank;
  }

  function apply(payload) {
    var byName = {};
    payload.rows.forEach(function (d) { byName[d.username] = d; });
    var rows = Array.prototype.slice.call(list.children);

    // Someone joined or left: rebuild from the server so every control
    // (remove buttons, badges) is right, instead of faking it in JS.
    var same = rows.length === payload.rows.length && rows.every(function (r) {
      return byName[r.getAttribute('data-username')];
    });
    if (!same) { window.location.reload(); return; }

    snapshotAt = Date.now();
    rows.forEach(function (r) { applyRow(r, byName[r.getAttribute('data-username')]); });
    rows.sort(function (a, b) {
      return byName[a.getAttribute('data-username')].rank - byName[b.getAttribute('data-username')].rank;
    }).forEach(function (r) { list.appendChild(r); });

    var s = payload.summary;
    var set = function (k, v) { var el = live.querySelector('[data-sum="' + k + '"]'); if (el) el.textContent = v; };
    set('studying', s.studying);
    set('total', fmt(s.total_seconds));
    set('members', s.members + '/' + live.querySelector('[data-sum="members"]').textContent.split('/')[1]);
    tick();
  }

  function poll() {
    if (inFlight || document.hidden) return;
    inFlight = true;
    fetch(stateUrl + '?range=' + encodeURIComponent(range), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) {
        if (r.status === 404 || r.status === 403) { window.location.href = '/rooms/'; return null; }  // removed or room deleted
        if (!r.ok) throw new Error('bad status');
        return r.json();
      })
      .then(function (payload) { if (payload) { apply(payload); setSync(true); } })
      .catch(function () { setSync(false); })
      .then(function () { inFlight = false; });
  }

  // Clocks tick locally between polls so the page feels alive without extra requests.
  function tick() {
    var delta = (Date.now() - snapshotAt) / 1000;
    Array.prototype.forEach.call(list.children, function (row) {
      var elapsed = row.getAttribute('data-elapsed');
      var isLive = row.getAttribute('data-status') === 'live' && elapsed !== null;
      var total = parseInt(row.getAttribute('data-seconds'), 10) || 0;
      field(row, 'total').textContent = fmt(isLive ? total + delta : total);
      field(row, 'clock').textContent = isLive ? clock(parseInt(elapsed, 10) + delta) : '';
    });
  }

  tick();
  setInterval(tick, 1000);
  setInterval(poll, POLL_MS);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });
  window.addEventListener('online', poll);
  window.addEventListener('offline', function () { setSync(false); });
})();
