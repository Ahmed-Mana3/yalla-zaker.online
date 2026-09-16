/* yalla zaker — shared UI, the study lamp timer, and the post-session log. */
(function () {
  'use strict';

  /* ---------- toasts ---------- */
  document.querySelectorAll('.toast').forEach(function (toast) {
    var close = toast.querySelector('.toast-close');
    var dismiss = function () {
      toast.classList.add('leaving');
      setTimeout(function () { toast.remove(); }, 320);
    };
    if (close) close.addEventListener('click', dismiss);
    setTimeout(dismiss, 6000);
  });

  /* ---------- helpers ---------- */
  function pad(n) { return String(n).padStart(2, '0'); }

  function fmt(totalSeconds) {
    var s = Math.max(0, Math.floor(totalSeconds));
    var h = Math.floor(s / 3600);
    var m = Math.floor((s % 3600) / 60);
    var sec = s % 60;
    if (h > 0) return pad(h) + ':' + pad(m) + ':' + pad(sec);
    return pad(m) + ':' + pad(sec);
  }

  /* ---------- copy buttons ---------- */
  function fallbackCopy(text, label) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
      return true;
    } catch (e) {
      return false;
    } finally {
      document.body.removeChild(ta);
    }
  }

  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var text = btn.getAttribute('data-copy') || '';
      var label = btn.querySelector('.copy-label');
      var copiedLabel = btn.getAttribute('data-copied-label') || 'Copied';
      var baseLabel = btn.getAttribute('data-label') || 'Copy';
      var done = function () {
        btn.classList.add('is-copied');
        if (label) label.textContent = copiedLabel;
      };
      var revert = function () {
        setTimeout(function () {
          btn.classList.remove('is-copied');
          if (label) label.textContent = baseLabel;
        }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(function () {
          if (fallbackCopy(text, label)) done(); else if (label) label.textContent = 'Press Ctrl+C';
          revert();
        });
      } else if (fallbackCopy(text, label)) {
        done();
        revert();
      }
    });
  });

  /* ---------- Web Audio Chime ---------- */
  function playChime() {
    if (localStorage.getItem('yz_chime_muted') === 'true') return;
    try {
      var AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      var ctx = new AudioCtx();
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.18); // A5
      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 1.2);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 1.2);
    } catch (e) {}
  }

  /* ---------- setup: pick a timer + a course ---------- */
  function initSetup() {
    var hidden = document.getElementById('target-input');
    if (!hidden) return;
    var summary = document.getElementById('setup-summary');
    var otherRow = document.getElementById('other-row');
    var otherInput = document.getElementById('other-minutes');
    var startBtn = document.getElementById('btn-start');
    var chips = Array.prototype.slice.call(document.querySelectorAll('.chip, .d-chip'));
    var courseRadios = document.querySelectorAll('#setup-form input[name="course"]');
    var courseOptions = document.querySelectorAll('.course-option');

    function minutesFromInput() {
      var other = otherInput ? parseInt(otherInput.value, 10) : 0;
      return (other && other > 0) ? Math.min(720, other) : 0;
    }
    function refresh() {
      var preset = null;
      chips.forEach(function (c) {
        if (c.dataset.min && c.classList.contains('is-selected')) preset = parseInt(c.dataset.min, 10);
      });
      var minutes = preset !== null ? preset : minutesFromInput();
      hidden.value = minutes || '';
      var durationTxt = minutes ? minutes + ' min' : 'free flow';
      var courseTxt = 'Free focus';
      courseRadios.forEach(function (r) {
        if (r.checked) {
          courseTxt = r.dataset.title || 'Free focus';
        }
      });
      if (summary) {
        summary.innerHTML = "Ready to focus for <b>" + durationTxt + "</b> · <b>" + courseTxt + "</b>";
      }
      if (startBtn) startBtn.classList.toggle('is-armed', true);
    }

    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        chips.forEach(function (c) {
          c.classList.remove('is-selected');
          c.setAttribute('aria-pressed', 'false');
        });
        if (chip.dataset.other !== undefined) {
          chip.classList.add('is-selected');
          chip.setAttribute('aria-pressed', 'true');
          if (otherRow) otherRow.hidden = false;
          if (otherInput) { otherInput.value = ''; otherInput.focus(); }
        } else if (chip.dataset.free !== undefined) {
          chip.classList.add('is-selected');
          chip.setAttribute('aria-pressed', 'true');
          if (otherRow) otherRow.hidden = true;
          if (otherInput) otherInput.value = '';
        } else {
          chip.classList.add('is-selected');
          chip.setAttribute('aria-pressed', 'true');
          if (otherRow) otherRow.hidden = true;
        }
        refresh();
      });
    });
    if (otherInput) otherInput.addEventListener('input', refresh);

    courseRadios.forEach(function (r) {
      r.addEventListener('change', function () {
        courseOptions.forEach(function (opt) {
          var input = opt.querySelector('input[type="radio"]');
          opt.classList.toggle('is-active', input && input.checked);
        });
        refresh();
      });
    });
    refresh();
  }
  initSetup();

  /* ---------- the lamp ---------- */
  function startLamp(lamp) {
    var status = lamp.dataset.status;
    if (!status || status === 'none') return;

    var pausedAt = lamp.dataset.pausedAt ? new Date(lamp.dataset.pausedAt).getTime() : null;
    var maxBreak = parseInt(lamp.dataset.maxBreak || '1800', 10);
    var targetMin = parseInt(lamp.dataset.target || '0', 10) || 0;
    var elapsedEl = lamp.querySelector('.lamp-timer');
    var labelEl = lamp.querySelector('.lamp-label');
    var fgCircle = null;
    var circumference = 0;
    var hasChimed = false;

    /* server-measured study seconds at load; we tick forward locally from here. */
    var baseElapsed = parseInt(lamp.dataset.elapsed || '0', 10);
    var baseAt = Date.now();

    var ring = lamp.querySelector('svg.ring circle.fg');
    if (ring) {
      circumference = 2 * Math.PI * ring.r.baseVal.value;
      ring.style.strokeDasharray = circumference;
      fgCircle = ring;
    }
    function setArc(frac) {
      if (!fgCircle) return;
      fgCircle.style.strokeDashoffset = circumference * Math.max(0, Math.min(1, frac));
    }

    var endForm = document.getElementById('form-end');

    function render() {
      var now = Date.now();
      if (status === 'active') {
        var elapsed = baseElapsed + (now - baseAt) / 1000;
        if (targetMin) {
          var remaining = targetMin * 60 - elapsed;
          if (remaining <= 0) {
            elapsedEl.textContent = '00:00';
            if (!hasChimed) {
              hasChimed = true;
              playChime();
            }
            if (endForm) endForm.submit();
            return;
          }
          elapsedEl.textContent = fmt(Math.ceil(remaining));
          if (labelEl) labelEl.textContent = 'Time left · ' + (lamp.dataset.course || 'the grind');
          setArc(remaining / (targetMin * 60));
          lamp.classList.toggle('is-tight', remaining <= 120);
        } else {
          elapsedEl.textContent = fmt(elapsed);
          if (labelEl) labelEl.textContent = 'Free focus · ' + (lamp.dataset.course || 'the grind');
          setArc(0);
        }
      } else if (status === 'paused') {
        var leftSec = Math.max(0, (maxBreak * 1000 - (now - pausedAt)) / 1000);
        elapsedEl.textContent = fmt(leftSec);
        if (labelEl) labelEl.textContent = 'Break · ' + Math.ceil(leftSec / 60) + 'm budget left';
        setArc(leftSec / maxBreak);
        lamp.classList.toggle('is-tight', leftSec <= 300);
        if (leftSec <= 0) {
          if (endForm) endForm.submit();
          return;
        }
      }
    }

    render();
    var ticker = setInterval(render, 1000);

    /* ---------- sync with the server every 4s ---------- */
    var api = lamp.dataset.api;
    if (api) {
      setInterval(function () {
        fetch(api, { headers: { 'Accept': 'application/json' } })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (!data.session) {
              window.location.reload();
              return;
            }
            var s = data.session;
            if (s.id !== lamp.dataset.id) window.location.reload();
            if (s.status === 'paused' && (!pausedAt || new Date(s.paused_at).getTime() !== pausedAt)) {
              window.location.reload();
            }
            if (s.status === 'finished') window.location.reload();
            if (s.status !== status) window.location.reload();
            if (status === 'active' && typeof s.elapsed === 'number') {
              baseAt = Date.now();
              baseElapsed = s.elapsed;
            }
          })
          .catch(function () { /* offline */ });
      }, 4000);
    }
  }

  var lamps = document.querySelectorAll('.lamp');
  Array.prototype.forEach.call(lamps, startLamp);

  /* ---------- Focus Toolbar & Shortcuts ---------- */
  var zenBtn = document.getElementById('btn-zen');
  if (zenBtn) {
    function isFullscreen() {
      return !!(document.fullscreenElement ||
                document.webkitFullscreenElement ||
                document.msFullscreenElement);
    }
    function requestZenFullscreen() {
      var el = document.documentElement;
      var req = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
      if (req) {
        var p = req.call(el);
        if (p && p.catch) {
          p.catch(function () { document.body.classList.remove('is-zen'); });
        }
      } else {
        document.body.classList.add('is-zen');
      }
    }
    function exitZenFullscreen() {
      var ex = document.exitFullscreen || document.webkitExitFullscreen || document.msExitFullscreen;
      if (ex) ex.call(document);
      document.body.classList.remove('is-zen');
    }
    var onFullscreenChange = function () {
      document.body.classList.toggle('is-zen', isFullscreen());
    };
    zenBtn.addEventListener('click', function () {
      if (isFullscreen()) exitZenFullscreen();
      else requestZenFullscreen();
    });
    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('webkitfullscreenchange', onFullscreenChange);
    document.addEventListener('msfullscreenchange', onFullscreenChange);
  }

  var soundBtn = document.getElementById('btn-sound');
  var soundLabel = document.getElementById('sound-label');
  if (soundBtn) {
    var refreshSoundUi = function () {
      var muted = localStorage.getItem('yz_chime_muted') === 'true';
      if (soundLabel) soundLabel.textContent = muted ? 'Chime off' : 'Chime on';
      soundBtn.classList.toggle('is-muted', muted);
    };
    refreshSoundUi();
    soundBtn.addEventListener('click', function () {
      var muted = localStorage.getItem('yz_chime_muted') === 'true';
      localStorage.setItem('yz_chime_muted', (!muted).toString());
      refreshSoundUi();
      if (muted) playChime();
    });
  }

  /* Global focus hotkeys */
  document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;
    if (e.key === ' ' || e.code === 'Space') {
      var pauseBtn = document.getElementById('btn-pause');
      var resumeBtn = document.getElementById('btn-resume');
      if (pauseBtn) { e.preventDefault(); pauseBtn.click(); }
      else if (resumeBtn) { e.preventDefault(); resumeBtn.click(); }
    } else if (e.key === 'Escape') {
      var endBtn = document.getElementById('btn-end');
      if (endBtn) {
        if (confirm('End this study session and record your progress?')) {
          endBtn.click();
        }
      }
    } else if (e.key === 'f' || e.key === 'F') {
      if (zenBtn) zenBtn.click();
    }
  });

  /* ---------- Check-in: simple minutes input with live course impact ---------- */
  function initCheckin() {
    var minInput = document.getElementById('log-minutes');
    if (!minInput) return;

    var quickPills = document.querySelectorAll('.quick-pill[data-add]');
    var asMeasuredBtn = document.querySelector('.quick-pill[data-as-measured]');
    var skipBtn = document.getElementById('skip-log');

    var credits = parseFloat(minInput.dataset.credits || '0') || 0;
    var total = parseFloat(minInput.dataset.total || '0') || 0;

    var convHours = document.getElementById('conv-hours');
    var btnMinText = document.getElementById('btn-min-text');
    var scbDone = document.getElementById('scb-done');
    var scbPct = document.getElementById('scb-pct');
    var scbBarFill = document.getElementById('scb-bar-fill');
    var scbRemain = document.getElementById('scb-remain');

    function updatePreview(valMins) {
      var m = Math.max(0, parseInt(valMins, 10) || 0);
      var addedHours = Math.round((m / 60.0) * 100) / 100;
      var newCredits = Math.round((credits + addedHours) * 100) / 100;
      var newPct = total > 0 ? Math.min(100, Math.round((newCredits / total) * 100)) : 0;
      var remaining = Math.max(0, Math.round((total - newCredits) * 100) / 100);

      if (convHours) convHours.textContent = addedHours.toFixed(2).replace(/\.00$/, '');
      if (btnMinText) btnMinText.textContent = m + ' min';
      if (scbDone) scbDone.textContent = newCredits.toFixed(1) + 'h';
      if (scbPct) scbPct.textContent = newPct + '%';
      if (scbBarFill) scbBarFill.style.width = newPct + '%';
      if (scbRemain) {
        if (total > 0 && newCredits >= total) {
          scbRemain.innerHTML = '🎉 <strong style="color:var(--amber)">Will complete this course!</strong>';
        } else {
          scbRemain.textContent = remaining.toFixed(1) + 'h remaining';
        }
      }
    }

    minInput.addEventListener('input', function () {
      updatePreview(minInput.value);
    });

    quickPills.forEach(function (pill) {
      pill.addEventListener('click', function () {
        var add = parseInt(pill.dataset.add, 10) || 0;
        var current = parseInt(minInput.value, 10) || 0;
        var next = Math.max(0, current + add);
        minInput.value = next;
        updatePreview(next);
      });
    });

    if (asMeasuredBtn) {
      asMeasuredBtn.addEventListener('click', function () {
        var base = asMeasuredBtn.dataset.asMeasured || '1';
        minInput.value = base;
        updatePreview(base);
      });
    }

    if (skipBtn) {
      skipBtn.addEventListener('click', function () {
        minInput.value = '0';
      });
    }

    // Initial render
    updatePreview(minInput.value);
  }
  initCheckin();

  /* ---------- roadmap: steps builder (reorder, edit, add) ---------- */
  function uiToast(msg, kind) {
    var box = document.querySelector('.toasts');
    if (!box) {
      box = document.createElement('div');
      box.className = 'toasts';
      document.body.appendChild(box);
    }
    var toast = document.createElement('div');
    toast.className = 'toast' + (kind ? ' toast-' + kind : '');
    var label = document.createElement('span');
    label.textContent = msg;
    var close = document.createElement('button');
    close.className = 'toast-close';
    close.setAttribute('aria-label', 'Dismiss');
    close.textContent = '\u00d7';
    toast.appendChild(label);
    toast.appendChild(close);
    box.appendChild(toast);
    var dismiss = function () {
      toast.classList.add('leaving');
      setTimeout(function () { toast.remove(); }, 320);
    };
    close.addEventListener('click', dismiss);
    setTimeout(dismiss, 2800);
  }

  function initRoadmapBuilder() {
    var list = document.querySelector('.roadmap-steps[data-reorder-url]');
    if (!list) return;
    var reorderUrl = list.getAttribute('data-reorder-url');
    var dragged = null;

    function items() {
      return Array.prototype.slice.call(list.querySelectorAll('.roadmap-step'));
    }
    function renumber() {
      items().forEach(function (item, index) {
        var badge = item.querySelector('.rm-index');
        if (badge) badge.textContent = index + 1;
      });
    }
    function clearOver() {
      items().forEach(function (item) { item.classList.remove('is-over'); });
    }
    function getDragAfterElement(y) {
      var rows = list.querySelectorAll('.roadmap-step:not(.is-dragging)');
      var closest = { offset: Number.NEGATIVE_INFINITY, element: null };
      Array.prototype.forEach.call(rows, function (el) {
        var box = el.getBoundingClientRect();
        var offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) {
          closest = { offset: offset, element: el };
        }
      });
      return closest.element;
    }
    function getCsrf() {
      var el = document.querySelector('input[name="csrfmiddlewaretoken"]');
      return el ? el.value : '';
    }
    function saveOrder(confirmOnOk) {
      var ids = items().map(function (item) { return item.getAttribute('data-step-id'); });
      var body = new URLSearchParams();
      body.set('order', ids.join(','));
      return fetch(reorderUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
          'X-Requested-With': 'XMLHttpRequest',
          'X-CSRFToken': getCsrf()
        },
        body: body.toString()
      }).then(function (r) {
        if (confirmOnOk && r.ok) uiToast('Order saved.');
        else if (confirmOnOk) uiToast("Couldn't save this order.", 'error');
      }).catch(function () {
        if (confirmOnOk) uiToast('Connection trouble — order will revert on reload.', 'error');
      });
    }

    /* drag to reorder */
    list.addEventListener('dragstart', function (e) {
      var handle = e.target.closest('.rm-drag');
      var item = e.target.closest('.roadmap-step');
      if (!handle || !item) {
        e.preventDefault();
        return;
      }
      dragged = item;
      item.classList.add('is-dragging');
      e.dataTransfer.effectAllowed = 'move';
      try { e.dataTransfer.setData('text/plain', 'reorder'); } catch (err) {}
    });
    list.addEventListener('dragover', function (e) {
      e.preventDefault();
      clearOver();
      if (!dragged) return;
      var after = getDragAfterElement(e.clientY);
      if (after) after.classList.add('is-over');
    });
    list.addEventListener('drop', function (e) {
      e.preventDefault();
      clearOver();
      if (!dragged) return;
      var after = getDragAfterElement(e.clientY);
      if (after == null) list.appendChild(dragged);
      else list.insertBefore(dragged, after);
    });
    list.addEventListener('dragend', function () {
      if (!dragged) return;
      dragged.classList.remove('is-dragging');
      clearOver();
      renumber();
      saveOrder(true);
      dragged = null;
    });

    /* arrow moves + step editor expand */
    list.addEventListener('click', function (e) {
      var up = e.target.closest('.rm-move-up');
      var down = e.target.closest('.rm-move-down');
      var edit = e.target.closest('.rm-edit-btn');
      var item = e.target.closest('.roadmap-step');
      if (up || down) {
        if (!item) return;
        var target = up ? item.previousElementSibling : item.nextElementSibling;
        if (!target || target === list) return;
        if (up) list.insertBefore(item, target);
        else list.insertBefore(target, item);
        renumber();
        saveOrder(false);
      } else if (edit) {
        var editor = document.getElementById(edit.getAttribute('data-editor-target'));
        var open = item.classList.toggle('is-open');
        edit.classList.toggle('is-armed', open);
        edit.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open && editor) {
          var first = editor.querySelector('input, select');
          if (first) first.focus();
        }
      }
    });
  }
  initRoadmapBuilder();

  /* ---------- roadmap: edit-mode toggle (steps are read-only by default) ---------- */
  function initRoadmapEditToggle() {
    var btn = document.getElementById('btn-edit-steps');
    if (!btn) return;
    var panel = document.querySelector('.rm-steps-panel');
    if (!panel) return;
    btn.addEventListener('click', function () {
      var editing = panel.classList.toggle('is-editing');
      btn.textContent = editing ? 'Done editing' : 'Edit steps';
      btn.setAttribute('aria-expanded', editing ? 'true' : 'false');
      if (!editing) {
        panel.querySelectorAll('.roadmap-step.is-open').forEach(function (item) {
          item.classList.remove('is-open');
          var edit = item.querySelector('.rm-edit-btn');
          if (edit) {
            edit.classList.remove('is-armed');
            edit.setAttribute('aria-expanded', 'false');
          }
        });
      }
    });
  }
  initRoadmapEditToggle();

  /* ---------- roadmap: add-step composer tabs + counter ---------- */
  function initRoadmapComposer() {
    var tabs = document.querySelectorAll('.rm-tab');
    var panels = document.querySelectorAll('.rm-tab-panel');
    if (!tabs.length) return;
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        tabs.forEach(function (t) {
          t.classList.remove('is-active');
          t.setAttribute('aria-selected', 'false');
        });
        panels.forEach(function (p) { p.classList.remove('is-active'); });
        tab.classList.add('is-active');
        tab.setAttribute('aria-selected', 'true');
        var panel = document.querySelector('.rm-tab-panel[data-panel="' + tab.getAttribute('data-tab') + '"]');
        if (panel) panel.classList.add('is-active');
      });
    });

    var submit = document.querySelector('.rm-composer-submit');
    var boxes = document.querySelectorAll('.rm-desk-row input[type="checkbox"]');
    if (submit && boxes.length) {
      var update = function () {
        var n = 0;
        boxes.forEach(function (b) { if (b.checked) n += 1; });
        submit.textContent = n ? 'Add ' + n + ' to roadmap' : 'Add to roadmap';
      };
      boxes.forEach(function (b) { b.addEventListener('change', update); });
    }
  }
  initRoadmapComposer();

  /* ============================================================
     ROADMAP STUDIO (Edit Roadmap Steps Page)
     ============================================================ */
  function initRoadmapStudio() {
    var studio = document.querySelector('.rm-studio-wrap');
    if (!studio) return;

    var list = document.getElementById('roadmap-steps-list');
    var saveStatus = document.getElementById('save-status');
    var statusDot = saveStatus ? saveStatus.querySelector('.rm-save-dot') : null;
    var statusText = saveStatus ? saveStatus.querySelector('.rm-save-text') : null;

    function getCsrf() {
      var el = document.querySelector('input[name="csrfmiddlewaretoken"]');
      return el ? el.value : '';
    }

    function setStatus(state, msg) {
      if (!saveStatus) return;
      if (statusDot) {
        statusDot.className = 'rm-save-dot' + (state === 'saving' ? ' is-saving' : state === 'error' ? ' is-error' : '');
      }
      if (statusText) {
        statusText.textContent = msg || (state === 'saving' ? 'Saving changes…' : state === 'error' ? 'Trouble saving' : 'All changes saved');
      }
    }

    function stepItems() {
      if (!list) return [];
      return Array.prototype.slice.call(list.querySelectorAll('.rm-studio-step'));
    }

    function renumber() {
      var items = stepItems();
      items.forEach(function (item, idx) {
        var badge = item.querySelector('.rm-index');
        if (badge) badge.textContent = idx + 1;
      });
      var counter = document.getElementById('canvas-step-counter');
      var statStep = document.getElementById('stat-step-count');
      if (counter) counter.textContent = items.length + ' step' + (items.length === 1 ? '' : 's');
      if (statStep) statStep.textContent = items.length;

      var emptyCanvas = document.getElementById('rm-empty-canvas');
      if (emptyCanvas) {
        emptyCanvas.style.display = items.length ? 'none' : 'flex';
      }
    }

    function clearDragOver() {
      stepItems().forEach(function (item) { item.classList.remove('is-over'); });
    }

    function getDragAfter(y) {
      var rows = list.querySelectorAll('.rm-studio-step:not(.is-dragging)');
      var closest = { offset: Number.NEGATIVE_INFINITY, element: null };
      Array.prototype.forEach.call(rows, function (el) {
        var box = el.getBoundingClientRect();
        var offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) {
          closest = { offset: offset, element: el };
        }
      });
      return closest.element;
    }

    function saveOrder(showToast) {
      if (!list) return Promise.resolve();
      var reorderUrl = list.getAttribute('data-reorder-url');
      if (!reorderUrl) return Promise.resolve();

      var ids = stepItems().map(function (item) { return item.getAttribute('data-step-id'); });
      var body = new URLSearchParams();
      body.set('order', ids.join(','));

      setStatus('saving');
      return fetch(reorderUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
          'X-Requested-With': 'XMLHttpRequest',
          'X-CSRFToken': getCsrf()
        },
        body: body.toString()
      }).then(function (res) {
        if (res.ok) {
          setStatus('saved', 'Order updated');
          if (showToast) uiToast('Step order saved.');
        } else {
          setStatus('error', "Couldn't save order");
          uiToast("Couldn't save step order.", 'error');
        }
      }).catch(function () {
        setStatus('error', 'Connection issue');
        uiToast('Connection issue saving step order.', 'error');
      });
    }

    /* Drag and Drop reordering */
    var dragged = null;
    if (list) {
      list.addEventListener('dragstart', function (e) {
        var handle = e.target.closest('.rm-drag-handle');
        var item = e.target.closest('.rm-studio-step');
        if (!handle || !item) {
          e.preventDefault();
          return;
        }
        dragged = item;
        item.classList.add('is-dragging');
        e.dataTransfer.effectAllowed = 'move';
        try { e.dataTransfer.setData('text/plain', 'reorder'); } catch (err) {}
      });

      list.addEventListener('dragover', function (e) {
        e.preventDefault();
        clearDragOver();
        if (!dragged) return;
        var after = getDragAfter(e.clientY);
        if (after) after.classList.add('is-over');
      });

      list.addEventListener('drop', function (e) {
        e.preventDefault();
        clearDragOver();
        if (!dragged) return;
        var after = getDragAfter(e.clientY);
        if (after == null) list.appendChild(dragged);
        else list.insertBefore(dragged, after);
      });

      list.addEventListener('dragend', function () {
        if (!dragged) return;
        dragged.classList.remove('is-dragging');
        clearDragOver();
        renumber();
        saveOrder(true);
        dragged = null;
      });
    }

    /* List Click Delegations (Arrows, Edit toggle, Delete trigger) */
    if (list) {
      list.addEventListener('click', function (e) {
        var upBtn = e.target.closest('.rm-move-up-btn');
        var downBtn = e.target.closest('.rm-move-down-btn');
        var editBtn = e.target.closest('.rm-toggle-edit-btn');
        var closeEditBtn = e.target.closest('.rm-close-editor-btn');
        var removeTrigger = e.target.closest('.rm-remove-trigger');
        var cancelDelBtn = e.target.closest('.rm-cancel-del-btn');
        var item = e.target.closest('.rm-studio-step');

        if (upBtn || downBtn) {
          if (!item) return;
          var target = upBtn ? item.previousElementSibling : item.nextElementSibling;
          if (!target || !target.classList.contains('rm-studio-step')) return;
          if (upBtn) list.insertBefore(item, target);
          else list.insertBefore(target, item);
          renumber();
          saveOrder(false);
        } else if (editBtn) {
          var targetId = editBtn.getAttribute('data-target');
          var drawer = document.getElementById(targetId);
          if (drawer) {
            var isHidden = drawer.style.display === 'none' || !drawer.style.display;
            drawer.style.display = isHidden ? 'block' : 'none';
            editBtn.classList.toggle('is-active', isHidden);
            editBtn.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
            if (isHidden) {
              var input = drawer.querySelector('input');
              if (input) input.focus();
            }
          }
        } else if (closeEditBtn) {
          var drawerId = closeEditBtn.getAttribute('data-target');
          var d = document.getElementById(drawerId);
          if (d) d.style.display = 'none';
          if (item) {
            var tb = item.querySelector('.rm-toggle-edit-btn');
            if (tb) {
              tb.classList.remove('is-active');
              tb.setAttribute('aria-expanded', 'false');
            }
          }
        } else if (removeTrigger) {
          var popId = removeTrigger.getAttribute('data-target');
          var pop = document.getElementById(popId);
          if (pop) {
            pop.style.display = pop.style.display === 'none' ? 'flex' : 'none';
          }
        } else if (cancelDelBtn) {
          var cId = cancelDelBtn.getAttribute('data-target');
          var p = document.getElementById(cId);
          if (p) p.style.display = 'none';
        }
      });

      /* Inline Edit Step Form AJAX Submission */
      list.addEventListener('submit', function (e) {
        var editForm = e.target.closest('.rm-edit-step-form');
        var deleteForm = e.target.closest('.rm-delete-step-form');
        var detachForm = e.target.closest('.rm-detach-form');
        var item = e.target.closest('.rm-studio-step');

        if (editForm) {
          e.preventDefault();
          setStatus('saving');
          var submitBtn = editForm.querySelector('button[type="submit"]');
          if (submitBtn) submitBtn.disabled = true;

          var formData = new FormData(editForm);
          fetch(editForm.action, {
            method: 'POST',
            headers: {
              'X-Requested-With': 'XMLHttpRequest',
              'X-CSRFToken': getCsrf()
            },
            body: formData
          }).then(function (res) { return res.json(); }).then(function (data) {
            if (submitBtn) submitBtn.disabled = false;
            if (data.ok && data.step) {
              setStatus('saved', 'Step updated');
              uiToast('Step details saved.');
              // Update card title
              var titleEl = item.querySelector('.rm-title');
              if (titleEl) titleEl.textContent = data.step.title;
              // Close editor
              var drawer = editForm.closest('.rm-inline-editor');
              if (drawer) drawer.style.display = 'none';
              var editToggle = item.querySelector('.rm-toggle-edit-btn');
              if (editToggle) {
                editToggle.classList.remove('is-active');
                editToggle.setAttribute('aria-expanded', 'false');
              }
            } else {
              setStatus('error', "Couldn't update step");
              uiToast(data.error || 'Failed to update step.', 'error');
            }
          }).catch(function () {
            if (submitBtn) submitBtn.disabled = false;
            setStatus('error', 'Connection error');
            uiToast('Connection error updating step.', 'error');
          });
        } else if (deleteForm) {
          e.preventDefault();
          setStatus('saving');
          var delBtn = deleteForm.querySelector('button[type="submit"]');
          if (delBtn) delBtn.disabled = true;

          fetch(deleteForm.action, {
            method: 'POST',
            headers: {
              'X-Requested-With': 'XMLHttpRequest',
              'X-CSRFToken': getCsrf()
            },
            body: new URLSearchParams(new FormData(deleteForm)).toString()
          }).then(function (res) { return res.json(); }).then(function (data) {
            if (data.ok) {
              setStatus('saved', 'Step removed');
              uiToast('Step removed from roadmap.');
              item.style.opacity = '0';
              item.style.transform = 'translateY(-10px)';
              setTimeout(function () {
                item.remove();
                renumber();
              }, 220);
            } else {
              setStatus('error', "Couldn't remove step");
              uiToast('Could not remove step.', 'error');
              if (delBtn) delBtn.disabled = false;
            }
          }).catch(function () {
            setStatus('error', 'Connection error');
            uiToast('Connection error removing step.', 'error');
            if (delBtn) delBtn.disabled = false;
          });
        }
      });
    }

    /* Add Course Form AJAX Submission */
    var customForm = document.getElementById('rm-add-custom-form');
    if (customForm) {
      customForm.addEventListener('submit', function (e) {
        e.preventDefault();
        var titleIn = document.getElementById('custom-title');
        var linkIn = document.getElementById('custom-link');
        if (!titleIn || !titleIn.value.trim() || !linkIn || !linkIn.value.trim()) {
          uiToast('Course title and link are required.', 'error');
          return;
        }

        var submitBtn = customForm.querySelector('button[type="submit"]');
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.textContent = 'Adding course…';
        }
        setStatus('saving');

        var formData = new FormData(customForm);
        fetch(customForm.action, {
          method: 'POST',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': getCsrf()
          },
          body: formData
        }).then(function (res) { return res.json(); }).then(function (data) {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = '+ Add course to roadmap';
          }
          if (data.ok && data.step) {
            setStatus('saved', 'Course added');
            uiToast(data.step.title + ' added to roadmap.');
            customForm.reset();
            window.location.reload();
          } else {
            setStatus('error', data.error || "Couldn't add course");
            uiToast(data.error || 'Failed to add course.', 'error');
          }
        }).catch(function () {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = '+ Add course to roadmap';
          }
          setStatus('error', 'Connection error');
          uiToast('Connection error adding course.', 'error');
        });
      });
    }
  }
  initRoadmapStudio();
})();