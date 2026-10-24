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

// ── Receta (.catrecipe / .catflip.json) ──────────────────────────────
// Exportar: «Exportar receta .catrecipe» → saveRecipe() (POST
// /export_recipe → JSON con los pasos del pipeline); «Exportar .py» →
// downloadRecipe() en api.js (POST /recipe_export → script reproducible).
// Cargar: lee el archivo con FileReader y lo abre en el
// ExecutePipelineModal (F3.5), que hace dry-run en el servidor y aplica
// al llegar al 100%. Un .catrecipe arrastrado al grid sigue aquí (F3.4).
async function saveRecipe() {
  try {
    const res = await fetch('/export_recipe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: 'receta_catflip' })
    });
    if (!res.ok) { const err = await res.json(); toast(err.error || 'Error al guardar la receta', 'error'); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'receta_catflip.catrecipe'; a.click();
    URL.revokeObjectURL(url);
    toast('Receta guardada: receta_catflip.catrecipe', 'info');
  } catch (e) { toast('Error al guardar la receta', 'error'); }
}

function openRecipePicker() {
  if (!currentColumns.length) {
    toast('Carga un archivo antes de aplicar una receta', 'info');
    return;
  }
  const input = document.getElementById('recipe-file');
  if (!input) return;
  input.value = '';
  input.click();
}

function loadRecipeFile(input) {
  const file = input.files && input.files[0];
  if (file) loadRecipeFromFile(file);
}

// «Receta desde CSV…» (F3.4): la heurística csvToRecipe() de grid.js
// propone pasos a partir del CSV elegido; el modal de preview los lista
// y solo «Aplicar» los ejecuta (vía ExecutePipelineModal, con dry-run).
function openCsvRecipePicker() {
  if (!currentColumns.length) {
    toast('Carga un archivo antes de generar una receta desde CSV', 'info');
    return;
  }
  const input = document.getElementById('csv-recipe-file');
  if (!input) return;
  input.value = '';
  input.click();
}

async function loadRecipeFromFile(file) {
  let recipe;
  try {
    recipe = JSON.parse(await file.text());
  } catch (e) {
    toast('El archivo no es un JSON válido', 'error');
    return;
  }
  // F3.5: no se aplica en silencio — el modal muestra la ejecución paso
  // a paso (preview del backend + barra de progreso + consola) y llama a
  // /apply_recipe solo cuando la barra llega al 100%.
  openExecPipeline(recipe, file.name);
}

// ── ESTADO ──────────────────────────────────────────────────────────────
let currentColumns = [];
let currentDtypes = {};
let currentOp = null;
let currentSheetFile = null;
let pipelineSteps = [];
// Benchmark (GET /benchmark): [{op, ms}] alineado con pipelineSteps, el
// índice del paso más lento y el total. Lo rellena loadBenchmark() y lo
// consumen renderPipeline() (chip «N ms») y updateBench() (barra).
let benchData = [];
let benchTotal = 0;
let benchSlow = -1;
// Pasos rehacibles (popeados por undo, re-aplicados por redo). Se vacía
// siempre que el pipeline avanza (op nueva, upload, receta) — el backend
// hace lo mismo con su `redo_history`.
let redoSteps = [];
// Validación de esquema: celdas que incumplen una regla — clave
// `posición\u0000columna` → tipo de regla. La rellena refreshValidation()
// (modals.js) y la consume buildRowHtml (grid.js) para pintar .cell-viol.
let currentViolations = new Map();
// Mismos `rule` que SCHEMA_RULE_KINDS del backend, en etiqueta española
const SV_RULE_LABELS = { not_null: 'no-nulo', unique: 'único', regex: 'regex', range: 'rango' };

// Sincroniza los botones Deshacer/Rehacer con los flags del backend
// (can_undo/can_redo). Sin flags conocidos, deja el estado actual.
function updateUndoRedoButtons(canUndo, canRedo) {
  const btnUndo = document.getElementById('btn-undo');
  const btnRedo = document.getElementById('btn-redo');
  if (canUndo !== undefined && btnUndo) btnUndo.disabled = !canUndo;
  if (canRedo !== undefined && btnRedo) btnRedo.disabled = !canRedo;
}

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
  ['btn-undo','btn-csv','btn-xlsx','btn-parquet','btn-json','btn-sql','btn-script','btn-recipe','btn-recipe-py'].forEach(id => document.getElementById(id).disabled = false);
}

function switchTab(name) {
  const names = ['data','stats','schema','lineage','code'];
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', names[i]===name));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  if (name === 'stats') { loadStats(); loadCorrelations(); }
  if (name === 'schema') loadSchema();
  if (name === 'lineage') loadLineage();
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
    // El detalle puede traer params de una receta ajena → escapar (F: diff)
    const detailSafe = escapeHtml(detail);
    const ms = benchData[i] !== undefined ? benchData[i].ms : null;
    const msChip = (ms !== null)
      ? `<span class="step-ms${i === benchSlow ? ' step-ms-slow' : ''}" title="Tiempo del paso: ${ms} ms">${ms} ms</span>`
      : '';
    card.innerHTML = `<div class="step-num">${i+1}</div><div class="step-info"><div class="step-name">${escapeHtml(s.op.replace(/_/g,' '))}</div><div class="step-detail" title="${detailSafe}">${detailSafe}</div></div>`
      + msChip
      + `<button type="button" class="step-diff-btn" onclick="openStepDiff(${i})" aria-label="Ver qué cambió el paso ${i+1}" title="¿Qué cambió este paso?">${icon('git-compare')}</button>`;
    list.appendChild(card);
  });
}

// ── BARRA DE BENCHMARK — tiempo por paso (roadmap) ──────────────────────
// `GET /benchmark` devuelve [{op, ms}] alineado con el pipeline (el
// backend lo rebana con op_history, así que undo/redo solo cambian la
// vista y un redo recupera el MISMO ms). Se refresca junto a loadStats.
async function loadBenchmark() {
  const clear = () => { benchData = []; benchTotal = 0; benchSlow = -1; updateBench(); };
  if (!currentColumns.length) { clear(); return; }
  try {
    const res = await fetch('/benchmark');
    const data = await res.json();
    if (data.error) { clear(); return; }
    benchData = data.steps || [];
    benchTotal = data.total_ms || 0;
    benchSlow = -1;
    let max = -1;
    benchData.forEach((s, i) => { if (s.ms > max) { max = s.ms; benchSlow = i; } });
    updateBench();
  } catch (e) { /* refresco en segundo plano */ }
}

function updateBench() {
  const block = document.getElementById('bench-block');
  if (!block) return;
  renderPipeline(); // actualiza los chips «N ms» de las tarjetas
  if (!benchData.length) { block.hidden = true; return; }
  block.hidden = false;
  const share = i => (benchTotal > 0
    ? benchData[i].ms / benchTotal
    : 1 / benchData.length);
  const bar = document.getElementById('bench-bar');
  bar.innerHTML = benchData.map((s, i) => {
    const pct = Math.round(share(i) * 100);
    // Color por tokens (color-mix, sin hex): teal proporcional al peso,
    // naranja para el paso más lento — el cuello de botella.
    const bg = i === benchSlow
      ? 'color-mix(in srgb, var(--orange) 55%, var(--surface))'
      : 'color-mix(in srgb, var(--teal-400) '
        + Math.round(35 + Math.min(share(i), 1) * 45) + '%, var(--surface))';
    return '<span class="bench-seg' + (i === benchSlow ? ' bench-seg-slow' : '') + '"'
      + ' style="flex:' + Math.max(s.ms, 0.001) + ' 1 0;background:' + bg + '"'
      + ' title="' + escapeHtml(s.op) + ': ' + s.ms + ' ms (' + pct + '%)"></span>';
  }).join('');
  const legend = document.getElementById('bench-legend');
  if (!legend) return;
  if (benchSlow >= 0) {
    const slow = benchData[benchSlow];
    const pct = Math.round(share(benchSlow) * 100);
    legend.textContent = 'Benchmark: ' + benchData.length + ' paso(s) · ' + benchTotal
      + ' ms — más lento: ' + slow.op.replace(/_/g, ' ')
      + ' (' + slow.ms + ' ms, ' + pct + '%)';
  } else {
    legend.textContent = 'Benchmark: ' + benchData.length + ' paso(s) · ' + benchTotal + ' ms';
  }
}
