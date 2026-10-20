// Cat_flip — carga de archivos y llamadas fetch al backend
// ── FILE UPLOAD ─────────────────────────────────────────────────────────
const uploadArea = document.getElementById('upload-area');
uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('drag-over'); });
uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('drag-over'));
uploadArea.addEventListener('drop', e => {
  e.preventDefault(); uploadArea.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
});
document.getElementById('file-input').addEventListener('change', e => {
  if (e.target.files[0]) handleFile(e.target.files[0]);
});

async function handleFile(file) {
  closeDatasetPicker();
  const name = file.name.toLowerCase();
  if (name.endsWith('.xlsx') || name.endsWith('.xls')) {
    showLoading();
    const fd = new FormData(); fd.append('file', file);
    currentSheetFile = file;
    const res = await fetch('/get_sheets', {method:'POST', body:fd});
    hideLoading();
    const data = await res.json();
    if (data.sheets && data.sheets.length > 1) {
      const sel = document.getElementById('sheet-select');
      sel.innerHTML = data.sheets.map((s,i) => '<option value="'+i+'">'+s+'</option>').join('');
      document.getElementById('sheet-selector').style.display = 'block';
      return;
    }
  }
  document.getElementById('sheet-selector').style.display = 'none';
  uploadFile(file, 0);
}

async function loadSheet() {
  uploadFile(currentSheetFile, document.getElementById('sheet-select').value);
}

async function uploadFile(file, sheet) {
  showLoading();
  const fd = new FormData(); fd.append('file', file); fd.append('sheet', sheet);
  try {
    const res = await fetch('/upload', {method:'POST', body:fd});
    const data = await res.json();
    hideLoading();
    if (data.error) { toast(data.error, 'error'); return; }

    currentSearchQuery = '';
    const searchInput = document.getElementById('ribbon-search');
    if (searchInput) searchInput.value = '';
    const clearBtn = document.getElementById('search-clear');
    if (clearBtn) clearBtn.classList.remove('visible');

    renderTable(data.data);
    updateCode(data.code);
    showTypeSuggestions(data.type_suggestions || []);
    showPiiSuggestions(data.pii_suggestions || []);
    pipelineSteps = [];
    redoSteps = [];
    const btnRedo0 = document.getElementById('btn-redo');
    if (btnRedo0) btnRedo0.disabled = true;
    renderPipeline();

    // Top ribbon breadcrumb & Active Buffer badge (F2.1)
    const breadcrumb = document.getElementById('ribbon-breadcrumb');
    if (breadcrumb) {
      document.getElementById('ribbon-filename').textContent = file.name;
      breadcrumb.classList.add('visible');
    }
    const badgeActive = document.getElementById('badge-active');
    if (badgeActive) badgeActive.classList.add('visible');

    const badge = document.getElementById('filename-badge');
    if (badge) {
      document.getElementById('filename-text').textContent = file.name;
      badge.style.display = 'none';
    }
    document.getElementById('header-metrics').style.display = 'flex';
    document.getElementById('empty-state').style.display = 'none';
    enableOps();
    loadStats(); // refrescar diagnóstico en segundo plano
    toast('Archivo cargado: ' + data.data.shape[0] + ' filas × ' + data.data.shape[1] + ' columnas');
    // Codificación no-utf8 detectada (latin-1/cp1252): solo entonces hay campo
    if (data.detected_encoding) {
      toast('Codificación detectada: ' + data.detected_encoding, 'info');
    }
  } catch(e) { hideLoading(); toast('Error al cargar el archivo', 'error'); }
}

// ── AUTO-MAPEO DE TIPOS AL CARGAR (heurística de esquema completo) ─────
// El backend solo sugiere (campo `type_suggestions` de /upload); aquí se
// muestran en una barra con chips y la conversión se aplica como pasos
// `change_type` (uno por columna → receta visible y deshacible con undo).
let pendingTypeSuggestions = [];

// Mismos nombres que los badges de tipo del Data Grid (STR/INT/FLOAT/DATE/BOOL)
const TYPE_LABELS = { datetime: 'DATE', int: 'INT', float: 'FLOAT' };

function showTypeSuggestions(list) {
  pendingTypeSuggestions = Array.isArray(list) ? list : [];
  const bar = document.getElementById('type-suggest-bar');
  if (!bar) return;
  if (pendingTypeSuggestions.length === 0) { bar.hidden = true; return; }
  const chips = document.getElementById('type-suggest-chips');
  chips.innerHTML = pendingTypeSuggestions.map(s => {
    const target = TYPE_LABELS[s.suggested_dtype] || escapeHtml(s.suggested_dtype);
    return `<span class="type-chip" title="Ej.: ${escapeHtml(s.sample)} — ${s.pct}% de los valores se convierten a ${target}">` +
      `${escapeHtml(s.column)} → ${target} <span class="type-chip-pct">${s.pct}%</span></span>`;
  }).join('');
  const applyBtn = document.getElementById('type-suggest-apply');
  if (applyBtn) {
    const n = pendingTypeSuggestions.length;
    applyBtn.textContent = n === 1 ? 'Aplicar' : `Aplicar (${n})`;
  }
  bar.hidden = false;
}

async function applyTypeSuggestions() {
  const suggs = pendingTypeSuggestions.slice();
  if (suggs.length === 0) return;
  showLoading();
  let applied = 0;
  for (const s of suggs) {
    const params = { column: s.column, dtype: s.suggested_dtype };
    try {
      const res = await fetch('/operation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operation: 'change_type', params })
      });
      const data = await res.json();
      if (data.error) { toast(data.error, 'error'); break; }
      handleOpResponse('change_type', params, data, false);
      applied++;
    } catch(e) {
      toast('Error al aplicar el tipado sugerido', 'error');
      break;
    }
  }
  hideLoading();
  if (applied > 0 && applied === suggs.length) {
    dismissTypeSuggestions();
    toast(applied === 1 ? '1 columna ajustada a su tipo sugerido' : applied + ' columnas ajustadas a su tipo sugerido');
  }
}

function dismissTypeSuggestions() {
  pendingTypeSuggestions = [];
  const bar = document.getElementById('type-suggest-bar');
  if (bar) bar.hidden = true;
}

// ── ESCANEO DE PII AL CARGAR (heurística sobre los presets de regex_mask) ──
// El backend solo sugiere (campo `pii_suggestions` de /upload). Enmascarar
// dispara `regex_mask` en modo mask — un paso de receta por columna, visible
// en el pipeline y deshacible con Deshacer, igual que Aplicar de tipos.
let pendingPiiSuggestions = [];

// Mismos `kind` que las claves de _MASK_PATTERNS del backend
const PII_LABELS = { email: 'EMAIL', phone: 'TELÉFONO', id: 'ID/TARJETA' };

function showPiiSuggestions(list) {
  pendingPiiSuggestions = Array.isArray(list) ? list : [];
  const bar = document.getElementById('pii-suggest-bar');
  if (!bar) return;
  if (pendingPiiSuggestions.length === 0) { bar.hidden = true; return; }
  document.getElementById('pii-suggest-chips').innerHTML = pendingPiiSuggestions.map(s => {
    const kind = PII_LABELS[s.kind] || escapeHtml(s.kind);
    return `<span class="type-chip" title="Ej.: ${escapeHtml(s.sample)} — ${s.pct}% de los valores casan el patrón de ${kind}">` +
      `${escapeHtml(s.column)} → ${kind} <span class="type-chip-pct">${s.pct}%</span></span>`;
  }).join('');
  const applyBtn = document.getElementById('pii-suggest-apply');
  if (applyBtn) {
    const n = pendingPiiSuggestions.length;
    applyBtn.textContent = n === 1 ? 'Enmascarar' : `Enmascarar (${n})`;
  }
  bar.hidden = false;
}

function dismissPiiSuggestions() {
  pendingPiiSuggestions = [];
  const bar = document.getElementById('pii-suggest-bar');
  if (bar) bar.hidden = true;
}

async function applyPiiSuggestions() {
  const suggs = pendingPiiSuggestions.slice();
  if (suggs.length === 0) return;
  showLoading();
  let applied = 0;
  for (const s of suggs) {
    const params = { column: s.column, pattern: s.kind, mode: 'mask' };
    try {
      const res = await fetch('/operation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operation: 'regex_mask', params })
      });
      const data = await res.json();
      if (data.error) { toast(data.error, 'error'); break; }
      handleOpResponse('regex_mask', params, data, false);
      applied++;
    } catch(e) {
      toast('Error al enmascarar el PII detectado', 'error');
      break;
    }
  }
  hideLoading();
  if (applied > 0 && applied === suggs.length) {
    dismissPiiSuggestions();
    toast(applied === 1 ? '1 columna enmascarada (deshazible con Deshacer)' : applied + ' columnas enmascaradas (deshacibles con Deshacer)');
  } else if (applied > 0) {
    toast(`Se enmascararon ${applied} de ${suggs.length} columnas`, 'info');
  }
}
