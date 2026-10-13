/* ================================================================
   ARPS v3 — Portal JavaScript
   IBB University Academic Result Processing System
   Includes: Dark Mode · Toasts · Score Preview · Modals · Search
   ================================================================ */
'use strict';

/* ── Dark mode ──────────────────────────────────────────────── */
function toggleDark() {
  var html  = document.documentElement;
  var isDark = html.getAttribute('data-theme') === 'dark';
  var next  = isDark ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('arps-theme', next);
  _updateDarkIcon(next);
}

function _updateDarkIcon(theme) {
  document.querySelectorAll('#darkIcon').forEach(function(el) {
    el.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
  });
}

/* Apply saved theme immediately (also done inline in <head>) */
(function () {
  var t = localStorage.getItem('arps-theme') || 'light';
  document.documentElement.setAttribute('data-theme', t);
  document.addEventListener('DOMContentLoaded', function () {
    _updateDarkIcon(t);
    // Wire up toggle buttons
    document.querySelectorAll('#darkToggle').forEach(function (btn) {
      btn.addEventListener('click', toggleDark);
    });
  });
})();

/* ── DOM ready ──────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
  initToasts();
  initSearch();
  initScorePreview();
  addLoadingToForms();
  animateStats();
});

/* ── Flash toasts ───────────────────────────────────────────── */
function initToasts() {
  document.querySelectorAll('.flash-toast').forEach(function (el, i) {
    el.style.animationDelay = (i * 80) + 'ms';
    setTimeout(function () { dismissToast(el); }, 5200 + i * 80);
    var btn = el.querySelector('.toast-close');
    if (btn) btn.addEventListener('click', function () { dismissToast(el); });
  });
}

function dismissToast(el) {
  el.style.transition = 'opacity .25s, transform .25s';
  el.style.opacity = '0';
  el.style.transform = 'translateX(14px)';
  setTimeout(function () { el.remove(); }, 280);
}

/* ── Table search ───────────────────────────────────────────── */
function initSearch() {
  var input = document.getElementById('globalSearch');
  if (!input) return;
  input.addEventListener('input', function () {
    var q = this.value.trim().toLowerCase();
    document.querySelectorAll('.searchable-row').forEach(function (row) {
      row.style.display = (!q || row.textContent.toLowerCase().includes(q)) ? '' : 'none';
    });
  });
}

/* ── Score preview ──────────────────────────────────────────── */
function initScorePreview() {
  ['ca_score', 'exam_score'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('input', renderScorePreview);
  });
}

function renderScorePreview() {
  var caEl   = document.getElementById('ca_score');
  var exEl   = document.getElementById('exam_score');
  var box    = document.getElementById('score_preview');
  if (!box || !caEl || !exEl) return;

  var ca    = Math.min(30, Math.max(0, parseFloat(caEl.value) || 0));
  var exam  = Math.min(70, Math.max(0, parseFloat(exEl.value) || 0));
  var total = ca + exam;

  var grades = [
    { min: 70, grade: 'A', gp: 5.0, cls: 'g-A', label: 'First Class Honours' },
    { min: 60, grade: 'B', gp: 4.0, cls: 'g-B', label: '2nd Class Upper' },
    { min: 50, grade: 'C', gp: 3.0, cls: 'g-C', label: '2nd Class Lower' },
    { min: 45, grade: 'D', gp: 2.0, cls: 'g-D', label: 'Third Class' },
    { min: 40, grade: 'E', gp: 1.0, cls: 'g-E', label: 'Pass' },
    { min: 0,  grade: 'F', gp: 0.0, cls: 'g-F', label: 'Fail' },
  ];
  var g = grades.find(function (r) { return total >= r.min; }) || grades[grades.length - 1];

  box.innerHTML = [
    '<div style="display:flex;align-items:center;gap:.55rem;flex-wrap:wrap;margin-top:.5rem;',
    'background:var(--surface-2);border:1px solid var(--border);border-radius:var(--r-sm);',
    'padding:.45rem .85rem;">',
    '<span style="font-size:.68rem;font-weight:700;color:var(--tx-faint);text-transform:uppercase;letter-spacing:.6px;">Preview</span>',
    '<span style="font-size:.82rem;font-weight:700;color:var(--tx-primary);">Total: ' + total.toFixed(1) + '/100</span>',
    '<span class="grade-chip ' + g.cls + '">' + g.grade + '</span>',
    '<span class="badge badge-green" style="font-size:.68rem;">GP ' + g.gp.toFixed(1) + '</span>',
    '<span style="font-size:.76rem;color:var(--tx-muted);">' + g.label + '</span>',
    '</div>'
  ].join('');
}

/* ── Form loading state ─────────────────────────────────────── */
function addLoadingToForms() {
  /* Inject keyframe only once */
  if (!document.getElementById('spin-style')) {
    var s = document.createElement('style');
    s.id = 'spin-style';
    s.textContent = '@keyframes _spin{to{transform:rotate(360deg)}}';
    document.head.appendChild(s);
  }

  document.querySelectorAll('form').forEach(function (form) {
    form.addEventListener('submit', function () {
      var btn = this.querySelector('button[type="submit"]:not([data-no-loader])');
      if (!btn) return;
      var orig = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<span style="display:inline-block;width:13px;height:13px;' +
        'border:2px solid rgba(255,255,255,.35);border-top-color:#fff;border-radius:50%;' +
        'animation:_spin .6s linear infinite;vertical-align:middle;margin-right:.3rem;"></span>' +
        'Processing…';
      setTimeout(function () { btn.disabled = false; btn.innerHTML = orig; }, 8000);
    });
  });
}

/* ── Animated stat counters ─────────────────────────────────── */
function animateStats() {
  document.querySelectorAll('.stat-value').forEach(function (el) {
    var raw = el.textContent.replace(/,/g, '').trim();
    var target = parseInt(raw, 10);
    if (isNaN(target) || target < 2 || raw.length > 5) return; /* skip CGPA / long strings */
    var start = null;
    var duration = 700;
    function step(ts) {
      if (!start) start = ts;
      var progress = Math.min((ts - start) / duration, 1);
      var ease = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.round(ease * target).toLocaleString();
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });
}

/* ── Password toggle ────────────────────────────────────────── */
function togglePassword(inputId, iconId) {
  var inp  = document.getElementById(inputId);
  var icon = document.getElementById(iconId);
  if (!inp) return;
  inp.type = inp.type === 'password' ? 'text' : 'password';
  if (icon) icon.className = inp.type === 'password' ? 'bi bi-eye' : 'bi bi-eye-slash';
}

/* ── Confirm dialog ─────────────────────────────────────────── */
function confirmAction(msg) {
  return confirm(msg || 'Are you sure? This action cannot be undone.');
}

/* ── Modals ─────────────────────────────────────────────────── */
function openModal(id) {
  var m = document.getElementById(id);
  if (!m) return;
  m.classList.add('show');
  var first = m.querySelector('input:not([type=hidden]),select,textarea,button');
  if (first) setTimeout(function () { first.focus(); }, 50);
}
function closeModal(id) {
  var m = document.getElementById(id);
  if (m) m.classList.remove('show');
}
document.addEventListener('click', function (e) {
  if (e.target.classList.contains('modal-overlay')) closeModal(e.target.id);
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape')
    document.querySelectorAll('.modal-overlay.show').forEach(function (m) { m.classList.remove('show'); });
});

/* ── Course edit modal ──────────────────────────────────────── */
function openEditCourseModal(id, code, title, units, semester, level, lecId) {
  var form = document.getElementById('editCourseForm');
  if (form) form.action = '/admin/courses/' + id + '/edit';
  _setVal('edit_code', code); _setVal('edit_title', title);
  _setVal('edit_units', units); _setVal('edit_semester', semester);
  _setVal('edit_level', level);
  var sel = document.getElementById('edit_lecturer');
  if (sel) Array.from(sel.options).forEach(function (o) { o.selected = +o.value === +lecId; });
  openModal('editCourseModal');
}

/* ── Edit student modal ─────────────────────────────────────── */
function openEditStudentModal(id, matric, fn, ln, mn, level, year, dob, email, dept) {
  var el = document.getElementById('editStudentMatric');
  if (el) el.textContent = matric;
  var form = document.getElementById('editStudentForm');
  if (form) form.action = '/admin/students/' + id + '/edit';
  _setVal('es_first', fn); _setVal('es_last', ln); _setVal('es_middle', mn);
  _setVal('es_level', level); _setVal('es_year', year);
  _setVal('es_dob', dob); _setVal('es_email', email); _setVal('es_dept', dept);
  openModal('editStudentModal');
}

/* ── Email modal ────────────────────────────────────────────── */
function openEmailModal(studentId, matricNo, currentEmail) {
  var n = document.getElementById('emailModalName');
  var i = document.getElementById('emailInput');
  var f = document.getElementById('emailModalForm');
  if (n) n.textContent = matricNo;
  if (i) i.value = currentEmail || '';
  if (f) f.action = '/admin/students/' + studentId + '/update-email';
  openModal('emailModal');
}

/* ── Spillover modals ───────────────────────────────────────── */
function updateSpilloverForm(studentId) {
  var f = document.getElementById('markSpilloverForm');
  if (f && studentId) f.action = '/admin/spillover/mark/' + studentId;
}
function openAutoMarkModal(id, matric, name, reasons, outstanding) {
  var f = document.getElementById('markSpilloverForm');
  if (f) f.action = '/admin/spillover/mark/' + id;
  var r = document.querySelector('#markSpilloverModal textarea[name="reason"]');
  var o = document.querySelector('#markSpilloverModal input[name="outstanding_courses"]');
  if (r) r.value = reasons;
  if (o) o.value = outstanding;
  var t = document.querySelector('#markSpilloverModal .modal-title');
  if (t) t.innerHTML = '<i class="bi bi-hourglass-split"></i> Mark Spillover — ' + matric;
  openModal('markSpilloverModal');
}
function openClearModal(studentId, matricNo) {
  var n = document.getElementById('clearStudentName');
  var f = document.getElementById('clearSpilloverForm');
  if (n) n.textContent = matricNo;
  if (f) f.action = '/admin/spillover/clear/' + studentId;
  openModal('clearSpilloverModal');
}

/* ── Restore modal ──────────────────────────────────────────── */
function openRestoreModal(filename) {
  _setVal('restoreFilename', filename, true);
  var form = document.getElementById('restoreForm');
  if (form) form.action = '/admin/backup/restore/' + filename;
  var inp = document.getElementById('restoreConfirmInput');
  if (inp) inp.value = '';
  var btn = document.getElementById('restoreSubmitBtn');
  if (btn) btn.disabled = true;
  openModal('restoreModal');
}
document.addEventListener('input', function (e) {
  if (e.target.id === 'restoreConfirmInput') {
    var btn = document.getElementById('restoreSubmitBtn');
    if (btn) btn.disabled = e.target.value.trim() !== 'RESTORE';
  }
});

/* ── Register role toggle ───────────────────────────────────── */
function togglePasskey() {
  var role   = (document.querySelector('input[name="role"]:checked') || {}).value;
  var block  = document.getElementById('passkey_block');
  var pk     = document.getElementById('passkey');
  var stuFld = document.getElementById('student_fields');
  if (block) {
    if (role === 'admin') { block.classList.remove('d-none'); if (pk) pk.required = true; }
    else                  { block.classList.add('d-none');    if (pk) pk.required = false; }
  }
  if (stuFld) stuFld.style.display = (role === 'student') ? 'block' : 'none';
}
document.addEventListener('DOMContentLoaded', function () {
  if (document.querySelector('input[name="role"]')) togglePasskey();
});

/* ── Level filter ───────────────────────────────────────────── */
function filterLevel(level, el) {
  document.querySelectorAll('.level-tab').forEach(function (t) { t.classList.remove('active'); });
  if (el) el.classList.add('active');
  document.querySelectorAll('[data-level]').forEach(function (row) {
    row.style.display = (level === 'all' || row.dataset.level === level) ? '' : 'none';
  });
  return false;
}

/* ── Print ──────────────────────────────────────────────────── */
function printPage() { window.print(); }

/* ── Helper ─────────────────────────────────────────────────── */
function _setVal(id, val, isText) {
  var el = document.getElementById(id);
  if (!el) return;
  if (isText) el.textContent = val || '';
  else el.value = val || '';
}

/* ── Passport photo live preview (student profile upload) ─────── */
function previewPassportPhoto(input) {
  if (!input.files || !input.files[0]) return;
  var file = input.files[0];

  var validTypes = ['image/jpeg', 'image/png', 'image/webp'];
  if (validTypes.indexOf(file.type) === -1) {
    alert('Please choose a JPG, PNG, or WEBP image.');
    input.value = '';
    return;
  }
  if (file.size > 3 * 1024 * 1024) {
    alert('That photo is larger than 3 MB. Please choose a smaller file.');
    input.value = '';
    return;
  }

  var reader = new FileReader();
  reader.onload = function (e) {
    var img = document.getElementById('photoPreview');
    var placeholder = document.getElementById('photoPlaceholder');
    if (img) {
      img.src = e.target.result;
      img.style.display = 'block';
    }
    if (placeholder) placeholder.style.display = 'none';
  };
  reader.readAsDataURL(file);
}


/* ── Responsive helpers ─────────────────────────────────────── */
(function () {
  /* Off-canvas sidebar (tablets / phones) */
  function setNav(open) {
    document.body.classList.toggle('sidebar-open', open);
    var t = document.getElementById('navToggle');
    if (t) {
      t.setAttribute('aria-expanded', open ? 'true' : 'false');
      var i = t.querySelector('i');
      if (i) i.className = open ? 'bi bi-x-lg' : 'bi bi-list';
    }
  }

  /* Wrap every table in a horizontal scroller so wide tables swipe
     instead of being clipped or stretching the whole page. */
  function wrapTables() {
    document.querySelectorAll('table').forEach(function (tbl) {
      if (tbl.closest('.table-scroll') || tbl.closest('.no-scroll-wrap')) return;
      var p = tbl.parentElement;
      if (p && p.style && /auto|scroll/.test(p.style.overflowX || p.style.overflow || '')) {
        p.classList.add('table-scroll');
      } else {
        var w = document.createElement('div');
        w.className = 'table-scroll';
        tbl.parentNode.insertBefore(w, tbl);
        w.appendChild(tbl);
      }
      /* give multi-column tables a sensible minimum so they scroll, not crush */
      var row = tbl.querySelector('thead tr') || tbl.querySelector('tr');
      var cols = row ? row.children.length : 0;
      if (cols >= 4) tbl.style.minWidth = Math.min(cols * 105, 1100) + 'px';
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    wrapTables();

    var toggle   = document.getElementById('navToggle');
    var backdrop = document.getElementById('sidebarBackdrop');
    if (toggle) {
      toggle.addEventListener('click', function () {
        setNav(!document.body.classList.contains('sidebar-open'));
      });
    }
    if (backdrop) backdrop.addEventListener('click', function () { setNav(false); });

    /* Close the drawer after choosing a page */
    document.querySelectorAll('.sidebar a').forEach(function (a) {
      a.addEventListener('click', function () { setNav(false); });
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') setNav(false);
    });
    /* Reset when growing back to desktop width */
    window.addEventListener('resize', function () {
      if (window.innerWidth > 1024) setNav(false);
    });
  });
})();
