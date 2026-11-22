/* IshtirafAI portal UI layer: theme, navigation drawer, motion, toasts, chart theming.
   Motion One (vendor/motion-*.js) is optional: every effect degrades to CSS or no-op. */
(function () {
  'use strict';
  var root = document.documentElement;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  var M = window.Motion || null;
  var EASE = [0.22, 1, 0.36, 1];

  /* ---------- Theme ---------- */
  window.toggleTheme = function () {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    var apply = function () {
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('ishtirafai-theme', next); } catch (e) { /* private mode */ }
      document.dispatchEvent(new CustomEvent('themechange', { detail: next }));
    };
    if (document.startViewTransition && !reduce.matches) document.startViewTransition(apply); else apply();
  };

  /* ---------- Tokens -> JS (charts, canvas) ---------- */
  window.ishtirafColor = function (token, alpha) {
    var v = getComputedStyle(root).getPropertyValue('--' + token).trim();
    if (!v) return '#888';
    return alpha == null ? 'rgb(' + v + ')' : 'rgb(' + v + ' / ' + alpha + ')';
  };

  /* ---------- Drawer (mobile nav) ---------- */
  window.toggleNav = function (open) {
    var b = document.body;
    var willOpen = open == null ? !b.classList.contains('nav-open') : open;
    b.classList.toggle('nav-open', willOpen);
    var btn = document.getElementById('navToggle');
    if (btn) btn.setAttribute('aria-expanded', String(willOpen));
  };
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') window.toggleNav(false); });

  /* ---------- Notifications popover ---------- */
  window.toggleNotifications = function () {
    var d = document.getElementById('notifDropdown');
    if (d) d.classList.toggle('show');
  };
  document.addEventListener('click', function (e) {
    var bell = document.querySelector('.notification-bell');
    var d = document.getElementById('notifDropdown');
    if (bell && d && !bell.contains(e.target)) d.classList.remove('show');
  });

  /* ---------- Toasts ---------- */
  var ICON = { success: 'fa-circle-check', error: 'fa-circle-exclamation', danger: 'fa-circle-exclamation', warning: 'fa-triangle-exclamation', info: 'fa-circle-info', message: 'fa-circle-info' };
  var TONE = { success: 'tone-clear', error: 'tone-refer', danger: 'tone-refer', warning: 'tone-unsure', info: 'tone-brand', message: 'tone-brand' };
  function dismiss(t) { t.classList.add('is-leaving'); setTimeout(function () { t.remove(); }, 280); }
  window.ishtirafToast = function (msg, kind) {
    kind = kind || 'info';
    var region = document.getElementById('toastRegion');
    if (!region) return;
    var t = document.createElement('div');
    t.className = 'toast ' + (TONE[kind] || 'tone-brand');
    t.setAttribute('role', kind === 'error' || kind === 'danger' ? 'alert' : 'status');
    var i = document.createElement('i'); i.className = 'fas ' + (ICON[kind] || ICON.info);
    var p = document.createElement('div'); p.className = 'flex-1'; p.textContent = msg;
    var x = document.createElement('button'); x.className = 'icon-btn -m-2'; x.setAttribute('aria-label', 'Dismiss');
    x.innerHTML = '<i class="fas fa-xmark text-sm"></i>'; x.onclick = function () { dismiss(t); };
    t.append(i, p, x); region.appendChild(t);
    setTimeout(function () { if (t.isConnected) dismiss(t); }, kind === 'error' || kind === 'danger' ? 9000 : 5000);
  };

  /* ---------- Count-up numbers ---------- */
  function countUp(el) {
    var target = parseFloat(el.getAttribute('data-count'));
    if (isNaN(target)) return;
    var dec = (el.getAttribute('data-count').split('.')[1] || '').length;
    if (reduce.matches || !M) { el.textContent = target.toFixed(dec); return; }
    M.animate(0, target, { duration: Math.min(1.4, 0.5 + target / 60), ease: EASE, onUpdate: function (v) { el.textContent = v.toFixed(dec); } });
  }

  /* ---------- Reveal choreography ---------- */
  function reveal() {
    var els = Array.prototype.slice.call(document.querySelectorAll('[data-reveal]'));
    if (!('IntersectionObserver' in window) || reduce.matches) {
      els.forEach(function (el) { el.classList.add('is-in'); });
      return;
    }
    var n = 0;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        en.target.style.setProperty('--i', String(Math.min(n++, 8)));
        en.target.classList.add('is-in');
        io.unobserve(en.target);
      });
      n = 0;
    }, { rootMargin: '0px 0px -6% 0px' });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------- Topbar hairline on scroll ---------- */
  function topbarShadow() {
    var bar = document.querySelector('.topbar');
    if (!bar) return;
    var on = function () { bar.classList.toggle('is-scrolled', window.scrollY > 4); };
    window.addEventListener('scroll', on, { passive: true }); on();
  }

  /* ---------- Flash messages rendered by the server ---------- */
  function flashes() {
    var data = document.getElementById('flashData');
    if (!data) return;
    try { JSON.parse(data.textContent).forEach(function (f, k) { setTimeout(function () { window.ishtirafToast(f[1], f[0]); }, 250 + k * 120); }); } catch (e) { /* ignore */ }
  }

  /* ---------- Buttons with data-loading show a spinner on submit ---------- */
  document.addEventListener('submit', function (e) {
    var b = e.target.querySelector('button[type=submit][data-loading]');
    if (b && !e.defaultPrevented) setTimeout(function () { b.classList.add('is-loading'); b.setAttribute('aria-busy', 'true'); }, 0);
  });

  document.addEventListener('DOMContentLoaded', function () {
    reveal(); topbarShadow(); flashes();
    document.querySelectorAll('[data-count]').forEach(countUp);
  });

  /* ---------- Chart.js defaults from tokens ---------- */
  window.ishtirafChartDefaults = function () {
    if (!window.Chart) return;
    var C = window.Chart.defaults;
    C.font.family = '"Instrument Sans", system-ui, sans-serif';
    C.font.size = 12;
    C.color = window.ishtirafColor('g-500');
    C.borderColor = window.ishtirafColor('g-200');
    C.plugins.legend.display = false;
    C.plugins.tooltip.backgroundColor = window.ishtirafColor('g-900');
    C.plugins.tooltip.titleColor = window.ishtirafColor('g-50');
    C.plugins.tooltip.bodyColor = window.ishtirafColor('g-100');
    C.plugins.tooltip.padding = 10;
    C.plugins.tooltip.cornerRadius = 10;
    C.plugins.tooltip.boxPadding = 4;
    C.animation.duration = reduce.matches ? 0 : 900;
    C.animation.easing = 'easeOutQuart';
  };

  /* Legacy chart helpers kept for pages that call them (analytics, reports). */
  window.createLineChart = function (canvasId, labels, datasets, options) {
    var ctx = document.getElementById(canvasId);
    if (!ctx || !window.Chart) return null;
    window.ishtirafChartDefaults();
    return new window.Chart(ctx, Object.assign({ type: 'line', data: { labels: labels, datasets: datasets },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true } } } }, options ? { options: options } : {}));
  };
  window.createDoughnutChart = function (canvasId, labels, data, colors) {
    var ctx = document.getElementById(canvasId);
    if (!ctx || !window.Chart) return null;
    window.ishtirafChartDefaults();
    return new window.Chart(ctx, { type: 'doughnut', data: { labels: labels, datasets: [{ data: data, backgroundColor: colors, borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '72%', plugins: { legend: { display: true, position: 'bottom' } } } });
  };
  window.initWaveform = function () { return null; };
})();
