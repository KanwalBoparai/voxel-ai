/* Shared front-end helpers: theme toggle, business-config fetch, brand injection,
   scroll reveal. Loaded by every page. */

// ── Brand mark (inline SVG so it works without external assets) ──────────────
const VOXEL_LOGO_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
  <path d="M4 10v4"/><path d="M8 6v12"/><path d="M12 3v18"/><path d="M16 6v12"/><path d="M20 10v4"/>
</svg>`;

function brandMark(label = 'Voxel AI') {
  return `<span class="brand-logo">${VOXEL_LOGO_SVG}</span><span>${label}</span>`;
}

// ── Theme ────────────────────────────────────────────────────────────────────
function initTheme() {
  const stored = localStorage.getItem('voxel-theme');
  if (stored) document.documentElement.setAttribute('data-theme', stored);
  document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
    btn.addEventListener('click', () => {
      const cur = document.documentElement.getAttribute('data-theme');
      const isDark = cur ? cur === 'dark'
        : window.matchMedia('(prefers-color-scheme: dark)').matches;
      const next = isDark ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('voxel-theme', next);
    });
  });
}

const THEME_ICONS = `
  <svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
  <svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>`;

// ── Business config ──────────────────────────────────────────────────────────
let _bizCache = null;
async function getBusinessConfig() {
  if (_bizCache) return _bizCache;
  try {
    const res = await fetch('/api/business-config');
    if (res.ok) _bizCache = await res.json();
  } catch (_) { /* offline / not wired — fall back below */ }
  _bizCache = _bizCache || {
    business_name: 'Your Business', industry: 'general business', agent_name: 'Ava',
    booking: { appointment_label: 'appointment' }, promotion: { active: false },
    services: [], faqs: [], hours: {},
  };
  return _bizCache;
}

async function saveBusinessConfig(config) {
  const res = await fetch('/api/business-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error('Save failed');
  _bizCache = await res.json();
  return _bizCache;
}

// ── Scroll reveal ────────────────────────────────────────────────────────────
function initReveal() {
  const els = document.querySelectorAll('.reveal');
  if (!('IntersectionObserver' in window) || !els.length) {
    els.forEach(el => el.classList.add('in')); return;
  }
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
  }, { threshold: 0.12 });
  els.forEach(el => io.observe(el));
}

function initials(name = '') {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || 'AI';
}

document.addEventListener('DOMContentLoaded', () => { initTheme(); initReveal(); });
