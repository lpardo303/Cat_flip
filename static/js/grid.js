// Cat_flip — buscador, menú contextual de columnas, renderTable, código generado
// ── BUSCADOR REACTIVO EN DATA GRID (F2.5) ───────────────────────────────
let currentRawData = null;
let currentSearchQuery = '';

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeRegExp(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightEscaped(escapedText, query) {
  if (!query) return escapedText;
  const escapedQuery = escapeHtml(query);
  const regex = new RegExp(`(${escapeRegExp(escapedQuery)})`, 'gi');
  return escapedText.replace(regex, '<mark class="search-hl">$1</mark>');
}

let searchDebounceTimer = null;

function onSearchInput(val) {
  currentSearchQuery = (val || '').trim();
  const clearBtn = document.getElementById('search-clear');
  if (clearBtn) clearBtn.classList.toggle('visible', currentSearchQuery.length > 0);
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = null;
  }
  if (!currentSearchQuery) {
    // Borrar la búsqueda es instantáneo: el usuario ya no espera nada.
    if (currentRawData) renderTable(currentRawData);
    return;
  }
  // Escribir: debounce de 120ms. El filtro en sí cuesta <1ms, pero el
  // re-render del grid no (medido: 176ms/tecla con 78 columnas); sin
  // esto cada pulsación bloquea el hilo principal.
  searchDebounceTimer = setTimeout(() => {
    searchDebounceTimer = null;
    if (currentRawData) renderTable(currentRawData);
  }, 120);
}

function clearSearch() {
  const input = document.getElementById('ribbon-search');
  if (input) input.value = '';
  onSearchInput('');
}

// ── MENÚ CONTEXTUAL DE COLUMNAS (F2.8) ──────────────────────────
let activeColMenuCol = null;

function escapeColArg(s) {
  return String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

function closeColMenu() {
  const dropdown = document.getElementById('col-menu-dropdown');
  if (dropdown) {
    dropdown.style.display = 'none';
    dropdown.innerHTML = '';
  }
  document.querySelectorAll('.th-menu-btn.active').forEach(b => b.classList.remove('active'));
  activeColMenuCol = null;
}

function buildColMenuHtml(col, dtype) {
  const isText = (dtype === 'STR' || !['INT', 'FLOAT', 'DATE', 'BOOL'].includes(dtype));
  let html = `
    <div class="col-menu-header">
      <span title="${escapeHtml(col)}">${escapeHtml(col)}</span>
      <span class="type-badge ${dtype}">${dtype}</span>
    </div>
    <div class="col-menu-group-title">Ordenar y filtrar</div>
    <div class="col-menu-item" onclick="handleColMenuAction('sort')">
      ${icon('arrow-down-wide-narrow')}<span>Ordenar</span>
    </div>
    <div class="col-menu-item" onclick="handleColMenuAction('filter')">
      ${icon('filter')}<span>Filtrar filas</span>
    </div>
  `;

  if (isText) {
    html += `
      <div class="col-menu-divider"></div>
      <div class="col-menu-group-title">Texto y formato</div>
      <div class="col-menu-item" onclick="handleColMenuAction('change_case')">
        ${icon('case-sensitive')}<span>Mayúsculas / Minúsculas</span>
      </div>
      <div class="col-menu-item" onclick="handleColMenuAction('trim')">
        ${icon('eraser')}<span>Eliminar espacios (Trim)</span>
      </div>
      <div class="col-menu-item" onclick="handleColMenuAction('clean_newlines')">
        <span style="font-family:var(--font-mono);font-size:0.75rem;width:14px;display:inline-block;text-align:center">↵</span><span>Limpiar saltos de línea</span>
      </div>
      <div class="col-menu-item" onclick="handleColMenuAction('replace')">
        ${icon('refresh-cw')}<span>Reemplazar valores</span>
      </div>
      <div class="col-menu-item" onclick="handleColMenuAction('regex_mask')">
        ${icon('eye-off')}<span>Enmascarar / extraer PII</span>
      </div>
      <div class="col-menu-item" onclick="handleColMenuAction('concatenar_columnas')">
        ${icon('text')}<span>Concatenar columnas</span>
      </div>
      <div class="col-menu-item" onclick="handleColMenuAction('split_column')">
        ${icon('scissors')}<span>Separar en columnas</span>
      </div>
      <div class="col-menu-item" onclick="handleColMenuAction('split_to_rows')">
        ${icon('arrow-down-to-line')}<span>Separar por filas</span>
      </div>
    `;
  } else {
    html += `
      <div class="col-menu-divider"></div>
      <div class="col-menu-group-title">Transformación</div>
      <div class="col-menu-item" onclick="handleColMenuAction('replace')">
        ${icon('refresh-cw')}<span>Reemplazar valores</span>
      </div>
      <div class="col-menu-item" onclick="handleColMenuAction('detectar_outliers')">
        ${icon('activity')}<span>Detectar outliers</span>
      </div>
    `;
  }

  html += `
    <div class="col-menu-divider"></div>
    <div class="col-menu-group-title">Calidad y limpieza</div>
    <div class="col-menu-item" onclick="handleColMenuAction('drop_nulls')">
      ${icon('sparkles')}<span>Eliminar filas con nulos</span>
    </div>
    <div class="col-menu-item" onclick="handleColMenuAction('drop_duplicates')">
      ${icon('trash-2')}<span>Eliminar duplicados</span>
    </div>
    <div class="col-menu-divider"></div>
    <div class="col-menu-group-title">Esquema</div>
    <div class="col-menu-item" onclick="handleColMenuAction('change_type')">
      ${icon('tag')}<span>Cambiar tipo de dato</span>
    </div>
    <div class="col-menu-item" onclick="handleColMenuAction('rename_column')">
      ${icon('pencil')}<span>Renombrar columna</span>
    </div>
    <div class="col-menu-item" onclick="handleColMenuAction('reorder_columns')">
      ${icon('list-ordered')}<span>Reordenar columnas</span>
    </div>
    <div class="col-menu-item" onclick="handleColMenuAction('hide_column')">
      ${icon('x')}<span>Ocultar columna</span>
    </div>
    <div class="col-menu-divider"></div>
    <div class="col-menu-item danger" onclick="handleColMenuAction('drop_column')">
      ${icon('trash-2')}<span>Eliminar columna</span>
    </div>
  `;

  return html;
}

function openColMenu(event, col) {
  event.stopPropagation();
  const dropdown = document.getElementById('col-menu-dropdown');
  if (!dropdown) return;

  if (dropdown.style.display !== 'none' && activeColMenuCol === col) {
    closeColMenu();
    return;
  }

  activeColMenuCol = col;
  const dtype = currentDtypes[col] || 'STR';
  dropdown.innerHTML = buildColMenuHtml(col, dtype);
  dropdown.setAttribute('aria-label', 'Transformaciones para ' + col);
  dropdown.style.display = 'block';

  const btn = event.currentTarget;
  const rect = btn.getBoundingClientRect();
  const menuWidth = 220;

  let left = rect.left;
  if (left + menuWidth > window.innerWidth - 12) {
    left = Math.max(12, rect.right - menuWidth);
  }

  let top = rect.bottom + 4;
  const menuHeight = dropdown.offsetHeight || 320;
  if (top + menuHeight > window.innerHeight - 12) {
    top = Math.max(12, rect.top - menuHeight - 4);
  }

  dropdown.style.left = `${left}px`;
  dropdown.style.top = `${top}px`;

  document.querySelectorAll('.th-menu-btn.active').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

function handleColMenuAction(action) {
  const targetCol = activeColMenuCol;
  closeColMenu();
  if (!targetCol) return;

  if (action === 'hide_column') {
    hiddenColumns.add(targetCol);
    localStorage.setItem('catflip-hidden-cols', JSON.stringify([...hiddenColumns]));
    updateColVisBadge();
    if (currentRawData) renderTable(currentRawData);
    toast(`Columna "${targetCol}" oculta`);
    return;
  }

  openModalForCol(action, targetCol);
}

// ── F3.6: VIRTUALIZACIÓN DEL DATA GRID (filas Y columnas) ──────────────
// Con el preview ampliado a 5000 filas, el tbody solo materializa el
// viewport + buffer de 10 filas por lado; con datasets anchos (78+ col)
// las celdas también se ventanean en horizontal: thead y tbody solo
// pintan las columnas visibles + 3 de buffer, con celdas colspan como
// spacer a cada lado. Dos filas spacer (`.vs-spacer`) simulan la altura
// total: la barra de scroll y el thead sticky quedan correctos.
//
// Medido con 515×78 antes de ventanear columnas: frame de scroll 185ms
// (5 fps), renderTable 283ms — el coste es lineal en celdas en el DOM
// (parse + style + layout + paint). Por eso el layout se estabiliza con
// `table-layout: fixed` + <colgroup> de anchos CALIBRADOS (un render
// completo en auto layout solo cuando aparece una columna nueva): además
// evita el «jitter» de anchos al cambiar de slice de filas.
const GRID_ROW_H_FALLBACK = 28;
const GRID_BUFFER = 10;          // filas de buffer vertical por lado
const COL_BUFFER = 3;            // columnas de buffer horizontal por lado
const COL_W_MIN = 80;            // clamp del ancho calibrado (px)
const COL_W_MAX = 260;
const COL_W_FALLBACK = 160;      // ancho de respaldo si la medición falla
const CALIB_SAMPLE_N = 128;      // filas objetivo del muestreo de calibración
let gridView = null;             // estado del render virtualizado activo
let gridRafPending = false;
let gridColWidths = new Map();   // nombre de columna → ancho calibrado (px)
let gridIdxW = 41;               // ancho calibrado de la columna #
let gridColSig = null;           // firma del colgroup ya pintado
let gridTheadSig = null;         // firma del thead ya pintado
let gridFontsArmed = false;      // recalibración única pendiente de web fonts

function gridClampW(w) { return Math.max(COL_W_MIN, Math.min(COL_W_MAX, Math.round(w))); }

// Si la calibración corre con las web fonts aún cargando (display=swap),
// los anchos medidos con la fuente fallback no sirven: cuando terminen de
// cargar, se limpian y se recalibra (una sola vez; después status === 'loaded').
function armGridFontRecalib() {
  if (gridFontsArmed || !document.fonts || document.fonts.status === 'loaded') return;
  gridFontsArmed = true;
  document.fonts.ready.then(() => {
    if (!currentRawData) return;
    gridColWidths.clear();
    gridIdxW = 41;
    gridColSig = null;
    gridTheadSig = null;
    renderTable(currentRawData);
  });
}

// Celda de cabecera de una columna: nombre + badge de tipo + menú +
// quality bar (idéntico al markup histórico; solo se añade title al
// nombre para cuando el ancho calibrado lo recorte con ellipsis).
function gridThCellHtml(col, g) {
  const dtype = currentDtypes[col] || 'STR';
  const nullCount = g.nulls[col] || 0;
  const quality = g.totalRows > 0 ? ((g.totalRows - nullCount) / g.totalRows) : 1;
  const pct = (quality * 100).toFixed(1);
  const isPerfect = nullCount === 0;
  const barColor = quality >= 0.9 ? 'var(--green)' : quality >= 0.6 ? 'var(--yellow)' : 'var(--red)';
  const tooltip = isPerfect
    ? `${col} — Sin nulos (100% válido)`
    : `${col} — ${nullCount} nulo${nullCount>1?'s':''} (${pct}% válido)`;
  return `<th title="${tooltip}">
      <div class="th-content">
        <span class="th-name" title="${escapeHtml(col)}">${escapeHtml(col)}</span>
        <span class="type-badge ${dtype}" data-col="${escapeHtml(col)}" onclick="event.stopPropagation();openModalForCol('change_type',this.dataset.col)" title="Tipo: ${dtype} — clic para cambiar">${dtype}</span>
        <button type="button" class="th-menu-btn" data-col="${escapeHtml(col)}" onclick="openColMenu(event,this.dataset.col)" title="Transformaciones para ${escapeHtml(col)}">
          ${icon('more-vertical')}
        </button>
      </div>
      <div class="quality-bar-wrap${isPerfect?' perfect':''}">
        <div class="quality-bar-fill" style="width:${pct}%;background:${barColor}"></div>
      </div>
    </th>`;
}

// Builder de fila: la ventana de columnas (colStart/colEnd) se lee en
// tiempo de ejecución desde `g`, así que al hacer scroll horizontal solo
// hay que repintar el thead y forzar el repintado de filas — el builder
// no se recrea.
function makeRowBuilder(g) {
  return (item) => {
    const L = g.colStart;
    const R = g.totalSlots - g.colEnd;
    let h = '<tr class="' + (item.i % 2 === 1 ? 'row-alt' : '') + '">';
    if (L > 0) h += '<td class="col-spacer" colspan="' + L + '"></td>';
    if (L === 0) h += '<td>' + (item.i + 1) + '</td>';
    for (let s = Math.max(1, L); s < g.colEnd; s++) {
      const idx = g.visibleIndices[s - 1];
      const cellVal = item.row[idx];
      // Validación de esquema: ¿incumple alguna regla? (clave = posición
      // de fila + nombre de columna; las etiquetas del índice no pintan)
      const violRule = currentViolations.get(item.i + '\u0000' + currentColumns[idx]);
      const violTitle = violRule ? ' — incumple: ' + SV_RULE_LABELS[violRule] : '';
      // Bug 4: el backend envía JSON null para nulos reales de pandas (NaN)
      if (cellVal === null || cellVal === undefined) {
        const nullCls = violRule ? 'cell-null-td cell-viol' : 'cell-null-td';
        h += '<td class="' + nullCls + '"><span class="cell-null" title="Nulo real de pandas (NaN)' + violTitle + '">null</span></td>';
        continue;
      }
      const escaped = escapeHtml(String(cellVal));
      const highlighted = g.query ? highlightEscaped(escaped, g.query) : escaped;
      const violCls = violRule ? ' class="cell-viol"' : '';
      h += '<td' + violCls + ' title="' + escaped + violTitle + '">' + highlighted + '</td>';
    }
    if (R > 0) h += '<td class="col-spacer" colspan="' + R + '"></td>';
    return h + '</tr>';
  };
}

// Rango de slots visibles (sin buffer) para un scrollLeft dado.
// El extremo final es excluido, como en computeColWindow.
function computeVisibleRange(scrollLeft, g) {
  const total = g.totalSlots;
  const w = g.widths;
  const wrap = document.getElementById('table-wrap');
  const viewW = wrap.clientWidth || 800;
  let start = 0;
  let acc = 0;
  while (start < total && acc + w[start] <= scrollLeft) { acc += w[start]; start++; }
  let end = start;
  const rightEdge = scrollLeft + viewW;
  while (end < total && acc < rightEdge) { acc += w[end]; end++; }
  return { start, end };
}

// Ventana de columnas visible a partir del scrollLeft (con buffer)
function computeColWindow(scrollLeft, g) {
  const total = g.totalSlots;
  const vis = computeVisibleRange(scrollLeft, g);
  let start = Math.max(0, vis.start - COL_BUFFER);
  let end = Math.min(total, vis.end + COL_BUFFER);
  if (end <= start) end = Math.min(total, start + 1);
  return { start, end };
}

// Estructura del grid: <table><colgroup><thead><tbody> — se crea una vez
// y se actualiza por partes. Reemplazar wrap.innerHTML entero en cada
// render re-parseaba las 79 cabeceras y forzaba el layout de la tabla
// completo (medido: 283ms por render con 78 columnas).
function ensureGridTable(wrap) {
  let table = wrap.querySelector('table');
  if (!table || !table.querySelector('#grid-tbody') || !table.querySelector('#grid-colgroup')) {
    wrap.innerHTML = '<table><colgroup id="grid-colgroup"></colgroup><thead id="grid-thead"></thead><tbody id="grid-tbody"></tbody></table>';
    gridColSig = null;
    gridTheadSig = null;
    table = wrap.querySelector('table');
  }
  return table;
}

// Colgroup con TODAS las columnas (aunque solo se pinten las de la
// ventana): el ancho total del tabla y el scrollbar horizontal quedan
// iguales al de la tabla completa, y las celdas colspan se alinean con
// las columnas declaradas. Solo se repinta si cambian los anchos.
function paintColgroup(table, g) {
  const sig = g.widths.join(',');
  if (sig === gridColSig) return;
  const cg = table.querySelector('#grid-colgroup');
  cg.innerHTML = g.widths.map(w => '<col style="width:' + Math.round(w) + 'px">').join('');
  const total = g.widths.reduce((a, b) => a + b, 0);
  table.style.width = 'max(' + Math.round(total) + 'px, 100%)';
  gridColSig = sig;
}

// thead de la ventana actual, con firma: si no cambió nada (columnas,
// tipos, nulos, ventana), no se toca el DOM de la cabecera — una
// búsqueda o una operación de valores no re-parsea cabeceras pesadas.
function paintThead(table, g) {
  const sig = g.colStart + '|' + g.colEnd + '|' + g.totalRows + '|'
    + g.visibleCols.map(c => c + ':' + (currentDtypes[c] || 'STR') + ':' + (g.nulls[c] || 0)).join('|');
  if (sig === gridTheadSig) return;
  const L = g.colStart;
  const R = g.totalSlots - g.colEnd;
  let h = '<tr>';
  if (L > 0) h += '<th class="col-spacer" colspan="' + L + '"></th>';
  if (L === 0) h += '<th>#</th>';
  for (let s = Math.max(1, L); s < g.colEnd; s++) h += gridThCellHtml(g.visibleCols[s - 1], g);
  if (R > 0) h += '<th class="col-spacer" colspan="' + R + '"></th>';
  table.querySelector('#grid-thead').innerHTML = h + '</tr>';
  gridTheadSig = sig;
}

// Re-ventanear columnas tras scroll horizontal o resize. Devuelve true
// si la ventana cambió (el caller debe forzar el repintado de filas).
function updateVirtualCols() {
  const g = gridView;
  if (!g) return false;
  const wrap = document.getElementById('table-wrap');
  // Histeresis: mientras la franja visible siga DENTRO de la ventana ya
  // pintada no se re-ventanea. Cada re-ventaneo obliga a reconstruir el
  // tbody entero (medido: ~10 ms de JS + layout; en scroll horizontal se
  // cruzaba una columna cada ~77 ms → 39 reconstrucciones en 3 s). Con
  // buffer 3 la ventana solo se mueve cada 3-4 cruces → ÷3-4 reconstrucciones.
  const vis = computeVisibleRange(wrap.scrollLeft, g);
  if (vis.start >= g.colStart && vis.end <= g.colEnd) return false;
  const win = computeColWindow(wrap.scrollLeft, g);
  if (win.start === g.colStart && win.end === g.colEnd) return false;
  g.colStart = win.start;
  g.colEnd = win.end;
  const table = wrap.querySelector('table');
  if (table) paintThead(table, g);
  return true;
}

function updateVirtualRows() {
  const g = gridView;
  if (!g) return;
  const wrap = document.getElementById('table-wrap');
  const tbody = wrap.querySelector('#grid-tbody');
  if (!tbody) return;
  const rowH = g.rowH || GRID_ROW_H_FALLBACK;
  const viewCount = Math.ceil((wrap.clientHeight || 400) / rowH) + 1;
  let start = Math.floor(wrap.scrollTop / rowH) - GRID_BUFFER;
  if (start < 0) start = 0;
  const maxStart = Math.max(0, g.rows.length - viewCount - GRID_BUFFER);
  if (start > maxStart) start = maxStart;
  const end = Math.min(g.rows.length, start + viewCount + 2 * GRID_BUFFER);
  if (start === g.start && end === g.end) return;
  g.start = start;
  g.end = end;
  const topH = start * rowH;
  const bottomH = (g.rows.length - end) * rowH;
  const span = g.totalSlots;
  let html = '';
  if (topH > 0) html += '<tr class="vs-spacer" style="height:' + topH + 'px"><td colspan="' + span + '"></td></tr>';
  for (let k = start; k < end; k++) html += g.buildRowHtml(g.rows[k]);
  if (bottomH > 0) html += '<tr class="vs-spacer" style="height:' + bottomH + 'px"><td colspan="' + span + '"></td></tr>';
  tbody.innerHTML = html;
}

// Throttle con requestAnimationFrame: recalcular solo cuando el navegador
// va a pintar; updateVirtualRows es no-op si el rango no cambió.
function gridOnScroll() {
  if (!gridView || gridRafPending) return;
  gridRafPending = true;
  requestAnimationFrame(() => {
    gridRafPending = false;
    if (!gridView) return;
    // El scroll horizontal cambia la ventana de columnas → repintar la
    // cabecera y forzar el repintado de filas aunque el rango no cambie
    if (updateVirtualCols()) gridView.end = -1;
    updateVirtualRows();
  });
}

// Un cambio de ancho del wrap deja la ventana de columnas corta (zonas
// sin pintar a la derecha) → re-ventanear y re-slicear. ResizeObserver
// sobre #table-wrap en vez de window.resize: el ancho del wrap también
// cambia al colapsar/expandir un panel lateral (F2.3) y al volver de
// otra pestaña, y esos cambios no disparan el evento resize de window.
function gridOnResize() {
  if (!gridView) return;
  requestAnimationFrame(() => {
    if (!gridView) return;
    updateVirtualCols();
    gridView.end = -1;
    updateVirtualRows();
  });
}
const gridWrapObserved = document.getElementById('table-wrap');
if (gridWrapObserved && typeof ResizeObserver !== 'undefined') {
  new ResizeObserver(gridOnResize).observe(gridWrapObserved);
} else {
  window.addEventListener('resize', gridOnResize);
}

// ── Calibración de anchos de columna ─────────────────────────────────────
// Render en auto layout para medir el ancho real de cada cabecera; después
// todo el grid usa table-layout: fixed con esos anchos. Solo ocurre cuando
// aparece una columna sin ancho conocido (upload, split, rename, unhide…).
// Muestreo: renderizar TODAS las filas (515×78 en el caso real) cuesta
// ~1.6 s de bloqueo (medido); una estrada que cubre todo el dataset
// (~CALIB_SAMPLE_N filas) lo baja a ~0.3 s, con desviación de anchos de
// ≤19 px en una sola columna de 78 (el valor extremo aislado se recorta
// con ellipsis + tooltip, el mismo mecanismo del clamp).
function calibSampleRows(g) {
  const n = g.rows.length;
  if (n <= CALIB_SAMPLE_N) return g.rows;
  const stride = Math.ceil(n / CALIB_SAMPLE_N);
  return g.rows.filter((_, i) => i % stride === 0);
}

function calibrateGridWidths(g) {
  const wrap = document.getElementById('table-wrap');
  // Sin la clase grid-fixed: el HTML nuevo ya nace en auto layout
  wrap.innerHTML = '<table><thead><tr><th>#</th>'
    + g.visibleCols.map(c => gridThCellHtml(c, g)).join('')
    + '</tr></thead><tbody>' + calibSampleRows(g).map(makeRowBuilder(g)).join('') + '</tbody></table>';
  const ths = wrap.querySelectorAll('thead th');
  if (ths.length === g.visibleCols.length + 1) {
    const idxW = ths[0].getBoundingClientRect().width;
    if (idxW > 0) gridIdxW = Math.max(24, Math.min(96, Math.round(idxW)));
    g.visibleCols.forEach((c, i) => {
      const w = ths[i + 1].getBoundingClientRect().width;
      gridColWidths.set(c, w > 0 ? gridClampW(w) : COL_W_FALLBACK);
    });
  }
  // Nunca re-calibrar en bucle: lo que no se midió, ancho de respaldo
  g.visibleCols.forEach(c => { if (!gridColWidths.has(c)) gridColWidths.set(c, COL_W_FALLBACK); });
  armGridFontRecalib();
}

function renderTable(data) {
  closeColMenu();
  currentRawData = data;
  currentColumns = data.columns || [];
  currentDtypes  = data.dtypes || {};
  const nulls     = data.nulls || {};
  const totalRows = data.total_rows || (data.shape ? data.shape[0] : 0) || (data.data ? data.data.length : 0);

  updateColVisBadge();

  // % Calidad global del dataset (F2.2)
  const totalCols = currentColumns.length;
  const totalCells = totalRows * totalCols;
  let totalNulls = 0;
  currentColumns.forEach(c => { totalNulls += (nulls[c] || 0); });
  const qualityScore = totalCells > 0 ? ((totalCells - totalNulls) / totalCells) : 1;
  const qPct = Math.round(qualityScore * 100);

  const qEl = document.getElementById('metric-quality');
  if (qEl) {
    qEl.className = 'metric-quality visible ' + (qPct >= 95 ? 'q-green' : qPct >= 80 ? 'q-amber' : 'q-red');
    qEl.innerHTML = `<svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg> Calidad: <strong>${qPct}%</strong>`;
    qEl.title = `Calidad global: ${qPct}% (${(totalCells - totalNulls).toLocaleString()} celdas válidas de ${totalCells.toLocaleString()} celdas totales)`;
  }

  // Columnas visibles (F2.6)
  const visibleCols = currentColumns.filter(c => !hiddenColumns.has(c));
  const visibleIndices = visibleCols.map(c => currentColumns.indexOf(c));

  if (data.shape) {
    document.getElementById('info-rows').textContent = data.shape[0].toLocaleString();
    document.getElementById('info-cols').textContent = data.shape[1];
  }

  if (visibleCols.length === 0) {
    let html = '<table><thead><tr><th>#</th></tr></thead><tbody>';
    html += '<tr><td style="padding:2.5rem;text-align:center;color:var(--text2);font-size:0.8rem">Todas las columnas están ocultas.<br><button class="btn btn-secondary" style="margin-top:0.75rem" onclick="openColVisModal()">Gestionar columnas</button></td></tr>';
    html += '</tbody></table>';
    document.getElementById('table-wrap').innerHTML = html;
    document.getElementById('truncated-msg').style.display = 'none';
    gridColSig = null;
    gridTheadSig = null;
    gridView = null;
    return;
  }

  // El thead ya no se construye aquí: lo pinta paintThead (ventana de
  // columnas + cache de firma) sobre la estructura de ensureGridTable.

  // ── F3.6: lista de filas a mostrar (filtro de búsqueda, F2.5) ────────
  // El índice original se preserva para la columna # y para el rayado
  // alternado (row-alt por clase, no nth-child: los spacers de la
  // virtualización romperían ese patrón).
  const query = currentSearchQuery.toLowerCase();
  const rows = [];
  (data.data || []).forEach((row, i) => {
    if (query) {
      let matches = false;
      for (let idx of visibleIndices) {
        const val = row[idx];
        if (val !== undefined && val !== null && String(val).toLowerCase().includes(query)) {
          matches = true;
          break;
        }
      }
      if (!matches) return;
    }
    rows.push({ i, row });
  });

  const wrap = document.getElementById('table-wrap');
  // Conservar el scroll entre renders (F3.6): una calibración reemplaza el
  // innerHTML y resetea el scroll; aplicar una operación no debe saltar al
  // inicio. El resto de renders solo tocan colgroup/thead/tbody y el
  // scroll queda intacto de por sí.
  const prevScrollTop = wrap.scrollTop;
  const prevScrollLeft = wrap.scrollLeft;

  // Estado del grid para esta pasada: filas filtradas + ventana de columnas
  const g = {
    rows, visibleCols, visibleIndices, nulls, totalRows, query,
    totalSlots: visibleCols.length + 1,
    colStart: 0, colEnd: visibleCols.length + 1,
    widths: [gridIdxW].concat(visibleCols.map(c => gridColWidths.get(c) || COL_W_FALLBACK)),
    rowH: GRID_ROW_H_FALLBACK, start: 0, end: -1,
  };
  g.buildRowHtml = makeRowBuilder(g);

  // ¿Falta algún ancho calibrado? (columna nueva desde el último render:
  // upload, split, rename, unhide…) → un render completo en auto layout
  // para medirla; a partir de ahí, table-layout: fixed.
  if (visibleCols.some(c => !gridColWidths.has(c))) calibrateGridWidths(g);
  g.widths = [gridIdxW].concat(visibleCols.map(c => gridColWidths.get(c) || COL_W_FALLBACK));

  const table = ensureGridTable(wrap);
  table.classList.add('grid-fixed');
  paintColgroup(table, g);

  if (rows.length === 0 && query) {
    // Sin resultados: cabecera COMPLETA (todas las columnas, sin ventanear
    // — no hay filas que optimizar y el scroll horizontal debe recorrerla)
    // + una fila de mensaje a todo lo ancho.
    paintThead(table, { ...g, colStart: 0, colEnd: g.totalSlots });
    table.querySelector('#grid-tbody').innerHTML =
      '<tr><td colspan="' + g.totalSlots + '" style="padding:2.5rem;text-align:center;color:var(--text2);font-size:0.8rem">No se encontraron filas que coincidan con "<strong>' + escapeHtml(currentSearchQuery) + '</strong>".<br><button class="btn btn-secondary" style="margin-top:0.75rem" onclick="clearSearch()">Limpiar búsqueda</button></td></tr>';
    gridView = null;
    if (wrap.scrollTop !== prevScrollTop) wrap.scrollTop = prevScrollTop;
    if (wrap.scrollLeft !== prevScrollLeft) wrap.scrollLeft = prevScrollLeft;
    document.getElementById('truncated-msg').style.display = 'none';
    return;
  }

  // (el builder de filas vive en makeRowBuilder: lee la ventana de
  // columnas desde g en tiempo de ejecución)
  // Ventana de columnas visible (con buffer) + thead cacheado por firma:
  // una búsqueda o una operación de valores no toca la cabecera.
  const win = computeColWindow(prevScrollLeft, g);
  g.colStart = win.start;
  g.colEnd = win.end;
  paintThead(table, g);

  gridView = g;
  updateVirtualRows();
  // Medir la altura real de fila (fraccional: getBoundingClientRect
  // evita el redondeo de offsetHeight, que acumulaba ~1px de drift por
  // rango renderizado y temblaba el scroll al cambiar de slice) y
  // corregir el slice inicial.
  const first = wrap.querySelector('#grid-tbody tr:not(.vs-spacer)');
  if (first && first.getBoundingClientRect().height > 0
      && Math.abs(first.getBoundingClientRect().height - g.rowH) > 0.01) {
    g.rowH = first.getBoundingClientRect().height;
    g.end = -1;
  }
  // Restaurar scroll (vertical y horizontal) y re-slicear en su posición
  if (wrap.scrollTop !== prevScrollTop) wrap.scrollTop = prevScrollTop;
  if (wrap.scrollLeft !== prevScrollLeft) wrap.scrollLeft = prevScrollLeft;
  updateVirtualRows();
  wrap.onscroll = gridOnScroll;
  document.getElementById('truncated-msg').style.display = (data.truncated && !query) ? 'block' : 'none';
}

function updateCode(code) { document.getElementById('code-pre').textContent = code; }

async function loadStats() {
  const grid = document.getElementById('stats-grid');
  // Sesión vacía: sin dataset en el cliente NO se consulta al servidor, para
  // que una carga fresca no pinte datos de sesiones anteriores.
  if (!currentRawData) {
    grid.innerHTML = '<div style="padding:2rem;color:var(--text2);font-size:0.82rem;text-align:center">Carga un archivo para ver el diagnóstico.</div>';
    const topE = document.getElementById('diag-top');
    if (topE) topE.innerHTML = '';
    return;
  }
  const res = await fetch('/stats');
  const data = await res.json();
  if (data.error) {
    grid.innerHTML = '<div style="padding:2rem;color:var(--text2);font-size:0.82rem;text-align:center">Carga un archivo para ver el diagnóstico.</div>';
    const top0 = document.getElementById('diag-top');
    if (top0) top0.innerHTML = '';
    return;
  }
  lastStatsData = data;
  const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const totalRows = (currentRawData && currentRawData.shape) ? currentRawData.shape[0] : 0;

  // ── F3.2: tarjetas KPI + distribución (contenedor creado por JS) ──
  let top = document.getElementById('diag-top');
  if (!top) {
    top = document.createElement('div');
    top.id = 'diag-top';
    grid.parentElement.insertBefore(top, grid);
  }
  const cols = data.columns;
  const totalCells = totalRows * cols.length;
  let nullSum = 0;
  cols.forEach(c => { const n = (data.stats[c] || {}).nulls; if (typeof n === 'number') nullSum += n; });
  const integrity = totalCells > 0 ? ((1 - nullSum / totalCells) * 100) : 100;
  const integrityColor = integrity >= 99 ? 'var(--green)' : (integrity >= 90 ? 'var(--yellow)' : 'var(--red)');
  const dups = (typeof data.duplicates === 'number') ? data.duplicates : null;
  const typed = cols.filter(c => !/^(object|str|string)/.test(String((data.stats[c] || {}).dtype || ''))).length;
  const typedPct = cols.length ? (typed / cols.length * 100) : 0;

  const catCols = cols.filter(c => Array.isArray((data.stats[c] || {}).top) && (data.stats[c].top.length > 0));
  const distHtml = catCols.length
    ? '<div class="dist-block"><div class="dist-head"><span class="dist-title">Distribución — top 5 valores</span>'
      + '<select id="dist-col" aria-label="Columna categórica para la distribución" onchange="renderDistBars()">'
      + catCols.map(c => '<option value="' + esc(c) + '">' + esc(c) + '</option>').join('')
      + '</select></div><div id="dist-bars"></div></div>'
    : '<div class="dist-block"><div class="dist-head"><span class="dist-title">Distribución — top 5 valores</span></div><div class="dist-empty">Sin columnas categóricas con valores.</div></div>';

  top.innerHTML =
      '<div class="kpi-grid">'
    + '<div class="kpi-card"><span class="kpi-label">Integridad Nulos</span><span class="kpi-value" style="color:' + integrityColor + '">' + integrity.toFixed(1) + '%</span><span class="kpi-hint">celdas no nulas</span></div>'
    + '<div class="kpi-card"><span class="kpi-label">Duplicados Excluidos</span><span class="kpi-value" style="color:' + (dups > 0 ? 'var(--orange)' : 'var(--green)') + '">' + (dups === null ? '–' : dups) + '</span><span class="kpi-hint">filas idénticas</span></div>'
    + '<div class="kpi-card"><span class="kpi-label">Tipos Válidos</span><span class="kpi-value">' + typedPct.toFixed(0) + '%</span><span class="kpi-hint">' + typed + ' de ' + cols.length + ' columnas tipadas</span></div>'
    + '</div>' + distHtml;
  if (catCols.length) renderDistBars();

  grid.innerHTML = '';
  data.columns.forEach(col => {
    const s = data.stats[col] || {};
    let rows = '<div class="stat-row"><span>Tipo</span><span>'+(s.dtype||'–')+'</span></div>';
    rows += '<div class="stat-row"><span>Nulos</span><span style="color:'+(s.nulls>0?'var(--yellow)':'var(--green)')+'">'+  (s.nulls!==undefined?s.nulls:'–')+'</span></div>';
    rows += '<div class="stat-row"><span>Únicos</span><span>'+(s.unique!==undefined?s.unique:'–')+'</span></div>';
    if (s.min !== undefined && s.min !== null) {
      rows += '<div class="stat-row"><span>Min</span><span>'+s.min+'</span></div>';
      rows += '<div class="stat-row"><span>Max</span><span>'+s.max+'</span></div>';
      rows += '<div class="stat-row"><span>Media</span><span>'+s.mean+'</span></div>';
    }
    grid.innerHTML += '<div class="stat-card"><h2 title="'+col+'">'+col+'</h2>'+rows+'</div>';
  });
  // Refrescar Schema & Profiling si está visible (F3.1)
  const schemaTab = document.getElementById('tab-schema');
  if (schemaTab && schemaTab.classList.contains('active')) loadSchema();
}

// ── Perfilado de correlaciones — heatmap (roadmap) ─────────────────────
// GET /correlations: matriz de Pearson de las columnas numéricas, solo
// lectura como /stats. El color de cada celda interpola tokens con
// `color-mix()` (sin hex sueltos) con intensidad tope del 50% para que el
// texto conserve el contraste AA en ambos temas. Se refresca junto a
// loadStats (ops, undo/redo, receta, upload y pestaña Diagnóstico).
async function loadCorrelations() {
  const box = document.getElementById('corr-grid');
  if (!box) return;
  // Sesión vacía (ver loadStats): sin dataset local no se pinta nada.
  if (!currentRawData) {
    box.innerHTML = '<p class="corr-hint">Carga un archivo para ver las correlaciones.</p>';
    return;
  }
  try {
    const res = await fetch('/correlations');
    const data = await res.json();
    if (data.error) {
      box.innerHTML = '<p class="corr-hint">' + escapeHtml(data.error) + '</p>';
      return;
    }
    renderCorrelations(data);
  } catch (e) {
    box.innerHTML = '<p class="corr-hint">Error al calcular las correlaciones.</p>';
  }
}

// Color divergente: teal para r > 0, rojo para r < 0; la intensidad es
// |r| limitada al 50% de mezcla para que el texto siga pasando AA.
function heatColor(r) {
  const pct = Math.round(Math.min(Math.abs(r), 1) * 50);
  const token = r >= 0 ? 'var(--teal-500)' : 'var(--red)';
  return 'color-mix(in srgb, ' + token + ' ' + pct + '%, var(--surface))';
}

function renderCorrelations(data) {
  const box = document.getElementById('corr-grid');
  const cols = data.columns || [];
  const matrix = data.matrix || [];
  if (cols.length < 2) {
    box.innerHTML = '<p class="corr-hint">Se necesitan al menos 2 columnas numéricas para calcular correlaciones ('
      + cols.length + ' detectada' + (cols.length === 1 ? '' : 's') + ').</p>';
    return;
  }
  let html = '<table class="corr-heat" aria-label="Matriz de correlación de Pearson entre columnas numéricas">';
  html += '<thead><tr><th scope="col" class="corr-corner" title="Correlación de Pearson (−1 a 1)">r</th>';
  cols.forEach(c => {
    html += '<th scope="col" title="' + escapeHtml(c) + '">' + escapeHtml(c) + '</th>';
  });
  html += '</tr></thead><tbody>';
  matrix.forEach((row, i) => {
    html += '<tr><th scope="row" title="' + escapeHtml(cols[i]) + '">' + escapeHtml(cols[i]) + '</th>';
    row.forEach((v, j) => {
      const has = v !== null && v !== undefined;
      const style = has ? ' style="background:' + heatColor(v) + '"' : '';
      const txt = has ? Number(v).toFixed(2) : '—';
      const title = has
        ? cols[i] + ' — ' + cols[j] + ': r = ' + v
        : cols[i] + ' — ' + cols[j] + ': sin variación suficiente (columna constante)';
      html += '<td' + style + ' title="' + escapeHtml(title) + '">' + txt + '</td>';
    });
    html += '</tr>';
  });
  html += '</tbody></table>' +
    '<p class="corr-hint">Pearson sobre filas con valores en ambos pares · 1 = correlación perfecta · 0 = ninguna · −1 = inversa · «—» = sin variación suficiente.</p>';
  box.innerHTML = html;
}

// Última respuesta de /stats (para redibujar la distribución sin re-fetch)
let lastStatsData = null;

// F3.2 — barras top-5 de la columna categórica seleccionada
function renderDistBars() {
  const box = document.getElementById('dist-bars');
  const sel = document.getElementById('dist-col');
  if (!box || !sel || !lastStatsData) return;
  const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const totalRows = (currentRawData && currentRawData.shape) ? currentRawData.shape[0] : 0;
  const top5 = (lastStatsData.stats[sel.value] || {}).top || [];
  if (!top5.length) { box.innerHTML = '<div class="dist-empty">Sin valores para mostrar.</div>'; return; }
  const max = top5[0][1] || 1;
  box.innerHTML = top5.map(([val, count]) => {
    const pct = totalRows > 0 ? (count / totalRows * 100) : 0;
    return '<div class="dist-row">'
      + '<span class="dist-label" title="' + esc(val) + '">' + esc(val) + '</span>'
      + '<div class="dist-track"><div class="dist-fill" style="width:' + (count / max * 100).toFixed(1) + '%"></div></div>'
      + '<span class="dist-count">' + count + ' · ' + pct.toFixed(1) + '%</span>'
      + '</div>';
  }).join('');
}

// ── LINEAGE GRAPH (F3.3): cadena SVG de pasos del pipeline ─────────────
async function loadLineage() {
  const wrap = document.getElementById('lin-wrap');
  if (!wrap) return;
  // Sesión vacía (ver loadStats): sin dataset local no se pinta nada.
  if (!currentRawData) {
    wrap.innerHTML = '<div class="lin-empty">Carga un archivo para ver el linaje del pipeline.</div>';
    return;
  }
  const res = await fetch('/lineage');
  const data = await res.json();
  const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  if (data.error) {
    wrap.innerHTML = '<div class="lin-empty">Carga un archivo para ver el linaje del pipeline.</div>';
    return;
  }
  const nodes = data.nodes || [];
  if (!nodes.length) {
    wrap.innerHTML = '<div class="lin-empty">Sin pasos registrados.</div>';
    return;
  }

  const OP_LABELS = {
    dataset: 'Dataset original',
  };
  const clip = (s, n) => s.length > n ? s.slice(0, n - 1) + '…' : s;
  const labelOf = n => clip(OP_LABELS[n.op] || String(n.op || '?').replace(/_/g, ' '), 28);
  const paramsOf = n => clip(Object.entries(n.params || {})
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => k + ': ' + (Array.isArray(v) ? v.join(', ') : v))
    .join(' · '), 44);

  // Geometría: cadena vertical, nodo = tarjeta SVG
  const W = 360, NH = 68, GAP = 40, PAD = 8;
  const H = nodes.length * NH + (nodes.length - 1) * GAP + PAD * 2;
  const X = (W - 300) / 2, NW = 300;
  let svg = '<svg class="lin-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Linaje del pipeline: '
    + esc(nodes.map(labelOf).join(' → ')) + '">'
    + '<defs><marker id="lin-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
    + '<path d="M 0 0 L 10 5 L 0 10 z" class="lin-arrow-head"/></marker></defs>';
  nodes.forEach((n, i) => {
    const y = PAD + i * (NH + GAP);
    const cls = n.op === 'dataset' ? ' lin-node-source' : '';
    svg += '<g class="lin-node' + cls + '">'
      + '<rect x="' + X + '" y="' + y + '" width="' + NW + '" height="' + NH + '" rx="10"/>'
      + '<text class="lin-op" x="' + (X + 14) + '" y="' + (y + 22) + '">' + esc(labelOf(n)) + '</text>'
      + '<text class="lin-shape" x="' + (X + NW - 14) + '" y="' + (y + 22) + '" text-anchor="end">' + n.rows + '×' + n.cols + '</text>'
      + '<text class="lin-params" x="' + (X + 14) + '" y="' + (y + 42) + '">' + esc(paramsOf(n) || '—') + '</text>'
      + '</g>';
    if (i < nodes.length - 1) {
      const x = W / 2;
      svg += '<line class="lin-edge" x1="' + x + '" y1="' + (y + NH + 4) + '" x2="' + x + '" y2="' + (y + NH + GAP - 6) + '" marker-end="url(#lin-arrow)"/>';
    }
  });
  svg += '</svg>';

  // Alternativa textual accesible (lista de pasos, visible solo para lectores)
  const srList = '<ol class="lin-sr-only">' + nodes.map(n =>
    '<li>' + esc(labelOf(n)) + (paramsOf(n) ? ' — ' + esc(paramsOf(n)) : '') + ' — ' + n.rows + ' filas × ' + n.cols + ' columnas</li>'
  ).join('') + '</ol>';

  const hint = nodes.length === 1
    ? '<div class="lin-hint">Aplica transformaciones para ver cómo evoluciona el dataset.</div>'
    : '';
  wrap.innerHTML = '<div class="lin-summary">' + nodes.length + ' estado' + (nodes.length > 1 ? 's' : '') + ' en el pipeline · ' + (nodes[nodes.length - 1].rows).toLocaleString() + ' fila(s) actual(es)</div>' + svg + srList + hint;
}

// ── SCHEMA & PROFILING (F3.1): tabla de metadatos por columna ─────────
async function loadSchema() {
  const wrap = document.getElementById('schema-wrap');
  if (!wrap) return;
  // Sesión vacía (ver loadStats): sin dataset local no se pinta nada.
  if (!currentRawData) {
    wrap.innerHTML = '<div class="schema-empty">Carga un archivo para ver el esquema y el perfilado de columnas.</div>';
    return;
  }
  const res = await fetch('/stats');
  const data = await res.json();
  const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  if (data.error) {
    wrap.innerHTML = '<div class="schema-empty">Carga un archivo para ver el esquema y el perfilado de columnas.</div>';
    return;
  }
  const totalRows = (currentRawData && currentRawData.shape) ? currentRawData.shape[0] : 0;
  const kindOf = dtype => {
    const t = String(dtype || '');
    if (/int/.test(t)) return 'INT';
    if (/float/.test(t)) return 'FLOAT';
    if (/bool/.test(t)) return 'BOOL';
    if (/datetime/.test(t)) return 'DATE';
    return 'STR';
  };
  let rows = '';
  data.columns.forEach((col, ci) => {
    const s = data.stats[col] || {};
    const hasNulls = (s.nulls !== undefined && s.nulls !== null);
    const nulls = hasNulls ? s.nulls : null;
    const nullPct = (hasNulls && totalRows > 0) ? (nulls / totalRows * 100) : 0;
    const hasUnique = (s.unique !== undefined && s.unique !== null);
    const unique = hasUnique ? s.unique : null;
    const cardPct = (hasUnique && totalRows > 0) ? (unique / totalRows * 100) : null;
    const isNum = (s.min !== undefined && s.min !== null);
    const kind = kindOf(s.dtype);
    const nullCell = !hasNulls ? '–'
      : nulls + ' <span class="schema-pct">(' + nullPct.toFixed(1) + '%)</span>';
    // Paridad explícita (F3.6): el rayado por nth-child fue retirado del
    // CSS global porque los spacers del grid lo romperían.
    rows += '<tr' + (ci % 2 ? ' class="row-alt"' : '') + '>'
      + '<td class="schema-col" title="' + esc(col) + '">' + esc(col) + '</td>'
      + '<td><span class="type-badge ' + kind + '" title="' + esc(s.dtype || '') + '">' + kind + '</span></td>'
      + '<td style="color:' + (nulls > 0 ? 'var(--yellow)' : 'var(--green)') + '">' + nullCell + '</td>'
      + '<td>' + (hasUnique ? unique : '–') + '</td>'
      + '<td>' + (cardPct !== null ? cardPct.toFixed(1) + '%' : '–') + '</td>'
      + '<td>' + (isNum ? esc(s.min) : '–') + '</td>'
      + '<td>' + (isNum ? esc(s.max) : '–') + '</td>'
      + '<td>' + (isNum && s.mean !== undefined && s.mean !== null ? esc(s.mean) : '–') + '</td>'
      + '</tr>';
  });
  wrap.innerHTML =
      '<div class="schema-summary">' + data.columns.length + ' columna(s) · ' + totalRows + ' fila(s) · perfilado en vivo desde <code>GET /stats</code></div>'
    + '<table class="schema-table">'
    + '<thead><tr><th scope="col">Columna</th><th scope="col">Tipo</th><th scope="col">Nulos</th><th scope="col">Únicos</th><th scope="col">Cardinalidad</th><th scope="col">Min</th><th scope="col">Max</th><th scope="col">Media</th></tr></thead>'
    + '<tbody>' + rows + '</tbody></table>';
}

// Cerrar menú contextual al hacer clic fuera
document.addEventListener('click', e => {
  const dropdown = document.getElementById('col-menu-dropdown');
  if (dropdown && dropdown.style.display !== 'none' && !dropdown.contains(e.target)) {
    closeColMenu();
  }
});

// Cerrar menú contextual en resize o scroll (excepto scroll interno del propio dropdown)
window.addEventListener('resize', closeColMenu);
window.addEventListener('scroll', e => {
  const dropdown = document.getElementById('col-menu-dropdown');
  if (dropdown && dropdown.contains(e.target)) return;
  closeColMenu();
}, true);

// ── RECETA DESDE CSV (F3.4: «Receta desde CSV…») ───────────────────────
// Heurística determinista que PROPONE una receta a partir de un CSV
// elegido por el usuario. Reglas: propone solo (nada se aplica sin pasar
// por el ExecutePipelineModal de F3.5), evita ops destructivas a medias
// (drop_duplicates SIEMPRE al final), no adivina tipos (INT/FLOAT solo si
// TODAS las celdas no vacías casan el patrón), y cada op propuesta es
// válida en el registro del backend — la receta resultante se puede
// exportar (.catrecipe), ejecutar en la app o exportar como script .py.

function _parseDelimited(text, delim) {
  // Parser RFC-4180 mínimo: comillas escapadas ("") y saltos de línea
  // dentro de campos entrecomillados. Filas 100% vacías se descartan.
  const rows = [];
  let row = [], cell = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; }
        else quoted = false;
      } else cell += ch;
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === delim) {
      row.push(cell); cell = '';
    } else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(cell); cell = '';
      rows.push(row); row = [];
    } else {
      cell += ch;
    }
  }
  if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
  return rows.filter(r => r.some(c => c.trim() !== ''));
}

// La vista previa analiza hasta estas filas; el AVISO aclara que la receta
// propuesta se aplica al dataset completo aunque el análisis sea parcial.
const CSV_RECIPE_MAX_PREVIEW_ROWS = 5000;

function csvToRecipe(text) {
  if (!text || !text.trim()) return { error: 'El archivo está vacío.' };
  // Mismo desempate de separador que el backend: gana la coma (solo se
  // cambia a ';' si la cabecera tiene más ';' que ',')
  const firstLine = text.split(/\r?\n/).find(l => l.trim()) || '';
  const delim = (firstLine.match(/;/g) || []).length > (firstLine.match(/,/g) || []).length ? ';' : ',';
  const rows = _parseDelimited(text, delim);
  if (rows.length < 2) return { error: 'El CSV necesita una cabecera y al menos una fila de datos.' };
  const headers = rows[0].map(h => h.trim());
  if (headers.some(h => !h)) return { error: 'Hay columnas sin nombre en la cabecera del CSV.' };
  const allRows = rows.slice(1);
  const body = allRows.slice(0, CSV_RECIPE_MAX_PREVIEW_ROWS);
  const steps = [];
  const warnings = [];
  const cellOf = (r, ci) => (r[ci] === undefined ? '' : String(r[ci]).trim());

  // 1) Quitar espacios (trim): solo si ALGUNA celda de la columna tiene
  //    espacios sobrantes (mismo criterio visible que la op trim)
  const trimCols = headers.filter((h, ci) =>
    body.some(r => r[ci] !== undefined && String(r[ci]) !== cellOf(r, ci)));
  if (trimCols.length) steps.push({ op: 'trim', params: { columns: trimCols } });

  // 2) Filas con huecos → drop_nulls (how='any', todas las columnas)
  const nullRows = body.filter(r => headers.some((h, ci) => cellOf(r, ci) === '')).length;
  if (nullRows > 0) steps.push({ op: 'drop_nulls', params: { columns: [], how: 'any' } });

  // 3) Tipos: INT solo si TODAS las celdas no vacías casan ^-?\d+$;
  //    FLOAT si todas casan número decimal. DATE nunca (irreversible en
  //    el roundtrip y con formato local ambiguo).
  const intCols = [], floatCols = [];
  headers.forEach((h, ci) => {
    const vals = body.map(r => cellOf(r, ci)).filter(v => v !== '');
    if (!vals.length) return;
    if (vals.every(v => /^-?\d+$/.test(v))) intCols.push(h);
    else if (vals.every(v => /^-?\d+(\.\d+)?$/.test(v))) floatCols.push(h);
  });
  intCols.forEach(col => steps.push({ op: 'change_type', params: { column: col, dtype: 'int' } }));
  floatCols.forEach(col => steps.push({ op: 'change_type', params: { column: col, dtype: 'float' } }));

  // 4) Duplicados exactos → drop_duplicates SIEMPRE al final: la única op
  //    que puede perder filas no puede quedar antes de las limpiezas
  const seen = new Set();
  let dupes = 0;
  for (const r of body) {
    const key = headers.map((h, ci) => cellOf(r, ci)).join('\u0000');
    if (seen.has(key)) dupes++; else seen.add(key);
  }
  if (dupes > 0) steps.push({ op: 'drop_duplicates', params: { columns: headers } });

  if (!steps.length) {
    return { steps: [], warnings: ['Sin cambios sugeridos: el CSV no muestra espacios, huecos, duplicados ni tipos detectables.'] };
  }
  if (allRows.length > body.length) {
    warnings.push(`Vista previa limitada a las primeras ${body.length.toLocaleString('es')} filas; la receta se aplica al dataset completo.`);
  }
  if (nullRows > 0) {
    warnings.push(`${nullRows} fila(s) con celdas vacías → se eliminarán con drop_nulls.`);
  }
  if (dupes > 0) {
    warnings.push(`${dupes} fila(s) duplicada(s) → se eliminarán con drop_duplicates (al final).`);
  }
  if (intCols.length + floatCols.length > 0) {
    warnings.push('Cambio de tipo propuesto solo donde TODAS las celdas casan: ' + intCols.concat(floatCols).join(', ') + '.');
  }
  return { steps, warnings };
}
