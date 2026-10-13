// Cat_flip — modalDefs, apertura/preselección, aplicación de operaciones
// ── MODAL ───────────────────────────────────────────────────────────────
function colOptions(multi) {
  if (multi) return currentColumns.map(c => '<label><input type="checkbox" value="'+c+'" checked> '+c+'</label>').join('');
  return currentColumns.map(c => '<option value="'+c+'">'+c+'</option>').join('');
}

function toggleAllChecks(containerId, checked) {
  document.querySelectorAll('#' + containerId + ' input[type=checkbox]').forEach(cb => cb.checked = checked);
}

function selectAllHtml(containerId) {
  return '<label style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0.35rem;font-size:0.78rem;font-weight:600;cursor:pointer">'
       + '<input type="checkbox" checked onchange="toggleAllChecks(\''+containerId+'\',this.checked)"> Seleccionar todo</label>';
}

const modalDefs = {
  unpivot: {
    title: icon('move-vertical') + ' Unpivot (Anular dinamización)',
    body: () => '<label>Columnas ID (se mantienen fijas):</label>'+selectAllHtml('id-cols-check')+'<div class="col-check" id="id-cols-check">'+colOptions(true)+'</div><label>Nombre columna variable:</label><input type="text" id="var-name" value="Variable"><label>Nombre columna valor:</label><input type="text" id="val-name" value="Valor">',
    params: () => ({ id_cols: [...document.querySelectorAll('#id-cols-check input:checked')].map(i=>i.value), var_name: document.getElementById('var-name').value, value_name: document.getElementById('val-name').value })
  },
  pivot: {
    title: icon('move-horizontal') + ' Pivot (Dinamizar)',
    body: () => '<label>Columna índice (filas):</label><select id="pivot-index">'+colOptions()+'</select><label>Columna a pivotar (encabezados):</label><select id="pivot-cols">'+colOptions()+'</select><label>Columna de valores:</label><select id="pivot-vals">'+colOptions()+'</select>',
    params: () => ({ index: document.getElementById('pivot-index').value, columns: document.getElementById('pivot-cols').value, values: document.getElementById('pivot-vals').value })
  },
  split_column: {
    title: icon('scissors') + ' Separar columna',
    body: () => '<label>Columna a separar:</label><select id="split-col">'+colOptions()+'</select><label>Delimitador:</label><input type="text" id="split-delim" value=","><label>Prefijo para nuevas columnas:</label><input type="text" id="split-prefix" value="Parte"><p style="font-size:0.75rem;color:var(--text2);margin-top:-0.3rem;margin-bottom:0.5rem">Se crearán columnas <em>Prefijo_1</em>, <em>Prefijo_2</em>, etc., según los fragmentos resultantes.</p><label>¿Cuántas veces separar?</label><select id="split-mode" onchange="document.getElementById(\'split-n-wrap\').style.display=this.value===\'n\'?\'block\':\'none\'"><option value="all">Siempre (todas las ocurrencias)</option><option value="n">N veces</option></select><div id="split-n-wrap" style="display:none;margin-top:0.4rem"><input type="number" id="split-n" value="1" min="1"></div>',
    params: () => { const mode = document.getElementById('split-mode').value; return { column: document.getElementById('split-col').value, delimiter: document.getElementById('split-delim').value, col_prefix: document.getElementById('split-prefix').value || document.getElementById('split-col').value, max_split: mode === 'n' ? parseInt(document.getElementById('split-n').value) || 1 : 0 }; }
  },
  filter: {
    title: icon('filter') + ' Filtrar filas',
    body: () => '<label>Columna:</label><select id="filter-col">'+colOptions()+'</select><label>Condición:</label><select id="filter-op"><option value="==">== igual a</option><option value="!=">!= distinto de</option><option value="contiene">contiene</option><option value="no contiene">no contiene</option><option value=">">&gt; mayor que</option><option value="<">&lt; menor que</option></select><label>Valor:</label><input type="text" id="filter-val" placeholder="Escribe el valor...">',
    params: () => ({ column: document.getElementById('filter-col').value, operator: document.getElementById('filter-op').value, value: document.getElementById('filter-val').value })
  },
  drop_nulls: {
    title: icon('sparkles') + ' Eliminar filas con nulos',
    body: () => '<label>Columnas (vacío = todas):</label>'+selectAllHtml('nulls-check')+'<div class="col-check" id="nulls-check">'+colOptions(true)+'</div><label>Eliminar fila si:</label><select id="nulls-how"><option value="any">ANY — alguna columna es nula</option><option value="all">ALL — todas las columnas son nulas</option></select>',
    params: () => { const c=[...document.querySelectorAll('#nulls-check input:checked')].map(i=>i.value); return { columns: c.length===currentColumns.length?null:c, how: document.getElementById('nulls-how').value }; }
  },
  drop_duplicates: {
    title: icon('trash-2') + ' Eliminar duplicados',
    body: () => '<label>Basado en columnas:</label>'+selectAllHtml('dup-check')+'<div class="col-check" id="dup-check">'+colOptions(true)+'</div>',
    params: () => { const c=[...document.querySelectorAll('#dup-check input:checked')].map(i=>i.value); return { columns: c.length===currentColumns.length?null:c }; }
  },
  rename_column: {
    title: icon('pencil') + ' Renombrar columna',
    body: () => '<label>Columna a renombrar:</label><select id="rename-old">'+colOptions()+'</select><label>Nuevo nombre:</label><input type="text" id="rename-new" placeholder="Nuevo nombre...">',
    params: () => ({ old_name: document.getElementById('rename-old').value, new_name: document.getElementById('rename-new').value })
  },
  drop_column: {
    title: icon('x') + ' Eliminar columna',
    body: () => '<label>Columna a eliminar:</label><select id="drop-col">'+colOptions()+'</select><p class="modal-warn">'+icon('triangle-alert')+'<span>Puedes deshacer con '+icon('undo-2')+' Deshacer paso</span></p>',
    params: () => ({ column: document.getElementById('drop-col').value })
  },
  trim: {
    title: icon('eraser') + ' Eliminar espacios extra',
    body: () => '<label>Columnas:</label>'+selectAllHtml('trim-check')+'<div class="col-check" id="trim-check">'+colOptions(true)+'</div>',
    params: () => ({ columns: [...document.querySelectorAll('#trim-check input:checked')].map(i=>i.value) })
  },
  change_case: {
    title: icon('case-sensitive') + ' Formateo de texto',
    body: () => '<label>Columna:</label><select id="case-col">'+colOptions()+'</select><label>Transformar a:</label><select id="case-type"><option value="lower">minúsculas (lower)</option><option value="upper">MAYÚSCULAS (upper)</option><option value="title">Título Caso (title)</option><option value="capitalize">Primera letra (capitalize)</option></select>',
    params: () => ({ column: document.getElementById('case-col').value, case: document.getElementById('case-type').value })
  },
  clean_newlines: {
    title: '↵ Limpiar saltos de línea',
    body: () => '<label>Columnas:</label>'+selectAllHtml('nl-check')+'<div class="col-check" id="nl-check">'+colOptions(true)+'</div><p style="font-size:0.75rem;color:var(--text2);margin-top:0.5rem">Reemplaza \\n, \\r\\n y \\r por un espacio y aplica trim.</p>',
    params: () => { const c=[...document.querySelectorAll('#nl-check input:checked')].map(i=>i.value); return { columns: c.length===currentColumns.length ? null : c }; }
  },
  replace: {
    title: icon('refresh-cw') + ' Reemplazar valores',
    body: () => '<label>Columna:</label><select id="rep-col">'+colOptions()+'</select><label>Valor a reemplazar:</label><input type="text" id="rep-old" placeholder="Texto original..."><label>Reemplazar por:</label><input type="text" id="rep-new" placeholder="Texto nuevo...">',
    params: () => ({ column: document.getElementById('rep-col').value, old_value: document.getElementById('rep-old').value, new_value: document.getElementById('rep-new').value })
  },
  change_type: {
    title: icon('tag') + ' Cambiar tipo de dato',
    body: () => '<label>Columna:</label><select id="type-col">'+colOptions()+'</select><label>Nuevo tipo:</label><select id="type-dtype"><option value="str">Texto (str)</option><option value="int">Número entero (int)</option><option value="float">Número decimal (float)</option><option value="datetime">Fecha/hora (datetime)</option></select>',
    params: () => ({ column: document.getElementById('type-col').value, dtype: document.getElementById('type-dtype').value })
  },
  sort: {
    title: icon('arrow-down-wide-narrow') + ' Ordenar',
    body: () => '<label>Columna:</label><select id="sort-col">'+colOptions()+'</select><label>Orden:</label><select id="sort-asc"><option value="true">Ascendente (A→Z)</option><option value="false">Descendente (Z→A)</option></select>',
    params: () => ({ column: document.getElementById('sort-col').value, ascending: document.getElementById('sort-asc').value==='true' })
  },
  split_to_rows: {
    title: icon('arrow-down-to-line') + ' Separar por filas',
    body: () => '<label>Columna a separar:</label><select id="str-col">'+colOptions()+'</select><label>Delimitador:</label><input type="text" id="str-delim" value=","><p style="font-size:0.75rem;color:var(--text2);margin-top:0.5rem">Cada valor separado por el delimitador se convertirá en una fila nueva.</p>',
    params: () => ({ column: document.getElementById('str-col').value, delimiter: document.getElementById('str-delim').value, strip: true })
  },
  drop_rows: {
    title: icon('scissors') + ' Eliminar filas por posición',
    body: () => '<label>¿Desde dónde?</label><select id="dr-pos"><option value="top">Desde el inicio (primeras filas)</option><option value="bottom">Desde el final (últimas filas)</option></select><label>¿Cuántas filas eliminar?</label><input type="number" id="dr-n" value="1" min="1">',
    params: () => ({ position: document.getElementById('dr-pos').value, n: parseInt(document.getElementById('dr-n').value) || 1 })
  },
  set_header: {
    title: icon('pin') + ' Definir fila como encabezado',
    body: () => '<label>Índice de la fila (0 = primera fila):</label><input type="number" id="sh-idx" value="0" min="0"><p style="font-size:0.75rem;color:var(--text2);margin-top:0.5rem">Los valores de esa fila se usarán como nombres de columna y la fila será eliminada.</p>',
    params: () => ({ row_index: parseInt(document.getElementById('sh-idx').value) || 0 })
  },
};

function openModal(op) {
  if (!currentColumns.length) return;
  currentOp = op;
  const def = modalDefs[op];
  document.getElementById('modal-title').innerHTML = def.title;
  document.getElementById('modal-body').innerHTML = def.body();
  document.getElementById('modal-overlay').classList.add('open');
}

// Abre un modal pre-seleccionando una columna específica (badges de tipo y menú contextual)
function openModalForCol(op, col) {
  openModal(op);
  setTimeout(() => {
    // 1. Mapeo de selects de columna individual
    const selectMap = {
      sort: 'sort-col',
      filter: 'filter-col',
      change_type: 'type-col',
      rename_column: 'rename-old',
      drop_column: 'drop-col',
      change_case: 'case-col',
      replace: 'rep-col',
      split_column: 'split-col',
      split_to_rows: 'str-col'
    };

    const selId = selectMap[op];
    if (selId) {
      const sel = document.getElementById(selId);
      if (sel) sel.value = col;
    }

    // Caso especial para change_type: pre-seleccionar el tipo actual
    if (op === 'change_type') {
      const dtypeMap = { INT: 'int', FLOAT: 'float', STR: 'str', DATE: 'datetime', BOOL: 'str' };
      const dtypeSel = document.getElementById('type-dtype');
      if (dtypeSel && currentDtypes[col]) {
        dtypeSel.value = dtypeMap[currentDtypes[col]] || 'str';
      }
    }

    // 2. Mapeo de contenedores con checkboxes múltiples
    const checkMap = {
      trim: 'trim-check',
      clean_newlines: 'nl-check',
      drop_nulls: 'nulls-check',
      drop_duplicates: 'dup-check'
    };

    const containerId = checkMap[op];
    if (containerId) {
      const container = document.getElementById(containerId);
      if (container) {
        // Desmarcar "Seleccionar todo" si existe
        const parent = container.parentElement;
        if (parent) {
          const selectAllCb = parent.querySelector('input[type="checkbox"][onchange*="toggleAllChecks"]');
          if (selectAllCb) selectAllCb.checked = false;
        }

        // Desmarcar todas las opciones y marcar exclusivamente la columna elegida
        container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
          cb.checked = (cb.value === col);
        });
      }
    }
  }, 0);
}
function closeModal() { document.getElementById('modal-overlay').classList.remove('open'); currentOp=null; }

async function confirmModal() {
  if (!currentOp) return;
  const op = currentOp;
  const params = modalDefs[op].params();
  closeModal();
  showLoading();
  try {
    const res = await fetch('/operation', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({operation: op, params}) });
    const data = await res.json();
    hideLoading();
    if (data.error) { toast(data.error, 'error'); return; }
    renderTable(data.data);
    updateCode(data.code);
    addPipelineStep(op, params);
    loadStats(); // refrescar diagnóstico en segundo plano
    toast(op.replace(/_/g,' ') + ' aplicado');
  } catch(e) { hideLoading(); toast('Error al aplicar operación', 'error'); }
}

async function undo() {
  showLoading();
  const res = await fetch('/undo', {method:'POST'});
  const data = await res.json();
  hideLoading();
  if (data.error) { toast(data.error, 'info'); return; }
  renderTable(data.data); updateCode(data.code);
  if (pipelineSteps.length > 0) { pipelineSteps.pop(); renderPipeline(); }
  loadStats(); // refrescar diagnóstico en segundo plano
  toast('Paso deshecho', 'info');
}

async function exportData(fmt) {
  showLoading();
  const filename = prompt('Nombre del archivo (sin extensión):', 'resultado') || 'resultado';
  try {
    const res = await fetch('/export', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({format:fmt, filename}) });
    hideLoading();
    if (!res.ok) { toast('Error al exportar', 'error'); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href=url; a.download=filename+'.'+fmt; a.click();
    URL.revokeObjectURL(url);
    toast('Exportado como ' + filename + '.' + fmt);
  } catch(e) { hideLoading(); toast('Error al exportar', 'error'); }
}

async function exportScript() {
  const filename = prompt('Nombre del script (sin extensión):', 'pipeline_catflip') || 'pipeline_catflip';
  showLoading();
  try {
    const res = await fetch('/export_script', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({filename}) });
    hideLoading();
    if (!res.ok) { const err = await res.json(); toast(err.error || 'Error al exportar script', 'error'); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href=url; a.download=filename+'.py'; a.click();
    URL.revokeObjectURL(url);
    toast('Script exportado: ' + filename + '.py', 'info');
  } catch(e) { hideLoading(); toast('Error al exportar script', 'error'); }
}

function copyCode() {
  navigator.clipboard.writeText(document.getElementById('code-pre').textContent)
    .then(() => toast('Código copiado al portapapeles', 'info'));
}
