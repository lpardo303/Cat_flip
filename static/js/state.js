// Cat_flip — estado global, columnas ocultas, toast, tabs, pipeline
// ── VISIBILIDAD DE COLUMNAS (F2.6) ──────────────────────────────────────
let hiddenColumns = new Set();
try {
  const savedHidden = JSON.parse(localStorage.getItem('catflip-hidden-cols') || '[]');
  hiddenColumns = new Set(savedHidden);
} catch(e) {}

function updateColVisBadge() {
  const badge = document.getElementById('col-vis-badge');
  if (!badge) return;
  const hiddenCount = currentColumns.filter(c => hiddenColumns.has(c)).length;
  if (hiddenCount > 0) {
    badge.textContent = hiddenCount;
    badge.classList.add('visible');
    badge.title = `${hiddenCount} columna(s) oculta(s)`;
  } else {
    badge.textContent = '';
    badge.classList.remove('visible');
  }
}

function openColVisModal() {
  if (!currentColumns.length) {
    toast('Carga un archivo para gestionar la visibilidad de columnas', 'info');
    return;
  }
  const list = document.getElementById('colvis-list');
  list.innerHTML = currentColumns.map(c => {
    const isChecked = !hiddenColumns.has(c);
    const escaped = c.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return `<label><input type="checkbox" value="${escaped}" ${isChecked ? 'checked' : ''}> ${escaped}</label>`;
  }).join('');
  document.getElementById('colvis-overlay').classList.add('open');
}

function closeColVisModal() {
  const overlay = document.getElementById('colvis-overlay');
  if (overlay) overlay.classList.remove('open');
}

function setAllColVis(showAll) {
  document.querySelectorAll('#colvis-list input[type="checkbox"]').forEach(cb => cb.checked = showAll);
}

function applyColVis() {
  const checkboxes = document.querySelectorAll('#colvis-list input[type="checkbox"]');
  checkboxes.forEach(cb => {
    if (cb.checked) {
      hiddenColumns.delete(cb.value);
    } else {
      hiddenColumns.add(cb.value);
    }
  });
  localStorage.setItem('catflip-hidden-cols', JSON.stringify([...hiddenColumns]));
  closeColVisModal();
  updateColVisBadge();
  if (currentRawData) renderTable(currentRawData);
  toast('Visibilidad de columnas actualizada');
}

// ── ESTADO ──────────────────────────────────────────────────────────────
let currentColumns = [];
let currentDtypes = {};
let currentOp = null;
let currentSheetFile = null;
let pipelineSteps = [];

function showLoading() { document.getElementById('loading').classList.add('open'); }
function hideLoading() { document.getElementById('loading').classList.remove('open'); }

function toast(msg, type='success') {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  const icons = {success:'check',error:'x',info:'info'};
  t.innerHTML = '<span>' + icon(icons[type]||'info') + '</span><span>' + msg + '</span>';
  document.getElementById('toast-container').appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

function enableOps() {
  document.querySelectorAll('.op-btn').forEach(b => b.disabled = false);
  ['btn-undo','btn-csv','btn-xlsx','btn-script'].forEach(id => document.getElementById(id).disabled = false);
}

function switchTab(name) {
  const names = ['data','stats','schema','code'];
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', names[i]===name));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  if (name === 'stats') loadStats();
  if (name === 'schema') loadSchema();
}

// ── Pipeline recipe ─────────────────────────────────────────────────────
function addPipelineStep(op, params) {
  pipelineSteps.push({ op, params });
  renderPipeline();
}

function renderPipeline() {
  const list = document.getElementById('pipeline-list');
  const empty = document.getElementById('pipeline-empty');
  // Remove existing step cards (keep empty div) — also on empty, Bug 5
  [...list.querySelectorAll('.pipeline-step')].forEach(el => el.remove());
  if (pipelineSteps.length === 0) {
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';
  pipelineSteps.forEach((s, i) => {
    const card = document.createElement('div');
    card.className = 'pipeline-step';
    const detail = Object.entries(s.params).map(([k,v]) => `${k}: ${Array.isArray(v)?v.join(','):v}`).join(' · ');
    card.innerHTML = `<div class="step-num">${i+1}</div><div class="step-info"><div class="step-name">${s.op.replace(/_/g,' ')}</div><div class="step-detail" title="${detail}">${detail}</div></div>`;
    list.appendChild(card);
  });
}
