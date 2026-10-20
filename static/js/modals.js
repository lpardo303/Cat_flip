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

// ── Regex Mask (op #21) — visibilidad condicional del modal ───────────
// Los selectores cambian qué campos aplican: 'custom' muestra la regex
// libre; 'extract' cambia el relleno por el nombre de la columna nueva.
function toggleRegexMaskPattern() {
  const wrap = document.getElementById('rm-custom-wrap');
  if (wrap) wrap.style.display = document.getElementById('rm-pattern').value === 'custom' ? 'block' : 'none';
}

function toggleRegexMaskMode() {
  const isExtract = document.getElementById('rm-mode').value === 'extract';
  const fillWrap = document.getElementById('rm-fill-wrap');
  const newWrap = document.getElementById('rm-newcol-wrap');
  if (fillWrap) fillWrap.style.display = isExtract ? 'none' : 'block';
  if (newWrap) newWrap.style.display = isExtract ? 'block' : 'none';
}

const modalDefs = {
  unpivot: {
    title: icon('move-vertical') + ' Unpivot (Anular dinamización)',
    body: () => '<label>Columnas ID (se mantienen fijas):</label>'+selectAllHtml('id-cols-check')+'<div class="col-check" id="id-cols-check">'+colOptions(true)+'</div><label>Nombre columna variable:</label><input type="text" id="var-name" aria-label="Nombre de la columna variable" value="Variable"><label>Nombre columna valor:</label><input type="text" id="val-name" aria-label="Nombre de la columna valor" value="Valor">',
    params: () => ({ id_cols: [...document.querySelectorAll('#id-cols-check input:checked')].map(i=>i.value), var_name: document.getElementById('var-name').value, value_name: document.getElementById('val-name').value })
  },
  pivot: {
    title: icon('move-horizontal') + ' Pivot (Dinamizar)',
    body: () => '<label>Columna índice (filas):</label><select id="pivot-index" aria-label="Columna índice (filas) para pivotar">'+colOptions()+'</select><label>Columna a pivotar (encabezados):</label><select id="pivot-cols" aria-label="Columna a pivotar (nuevos encabezados)">'+colOptions()+'</select><label>Columna de valores:</label><select id="pivot-vals" aria-label="Columna de valores para pivotar">'+colOptions()+'</select>',
    params: () => ({ index: document.getElementById('pivot-index').value, columns: document.getElementById('pivot-cols').value, values: document.getElementById('pivot-vals').value })
  },
  split_column: {
    title: icon('scissors') + ' Separar columna',
    body: () => '<label>Columna a separar:</label><select id="split-col" aria-label="Columna a separar en partes">'+colOptions()+'</select><label>Delimitador:</label><input type="text" id="split-delim" aria-label="Delimitador para separar la columna" value=","><label>Prefijo para nuevas columnas:</label><input type="text" id="split-prefix" aria-label="Prefijo para las nuevas columnas" value="Parte"><p style="font-size:0.75rem;color:var(--text2);margin-top:-0.3rem;margin-bottom:0.5rem">Se crearán columnas <em>Prefijo_1</em>, <em>Prefijo_2</em>, etc., según los fragmentos resultantes.</p><label>¿Cuántas veces separar?</label><select id="split-mode" aria-label="Frecuencia de separación" onchange="document.getElementById(\'split-n-wrap\').style.display=this.value===\'n\'?\'block\':\'none\'"><option value="all">Siempre (todas las ocurrencias)</option><option value="n">N veces</option></select><div id="split-n-wrap" style="display:none;margin-top:0.4rem"><input type="number" id="split-n" aria-label="Número de veces a separar" value="1" min="1"></div>',
    params: () => { const mode = document.getElementById('split-mode').value; return { column: document.getElementById('split-col').value, delimiter: document.getElementById('split-delim').value, col_prefix: document.getElementById('split-prefix').value || document.getElementById('split-col').value, max_split: mode === 'n' ? parseInt(document.getElementById('split-n').value) || 1 : 0 }; }
  },
  filter: {
    title: icon('filter') + ' Filtrar filas',
    body: () => '<label>Columna:</label><select id="filter-col" aria-label="Columna a filtrar">'+colOptions()+'</select><label>Condición:</label><select id="filter-op" aria-label="Condición del filtro"><option value="==">== igual a</option><option value="!=">!= distinto de</option><option value="contiene">contiene</option><option value="no contiene">no contiene</option><option value=">">&gt; mayor que</option><option value="<">&lt; menor que</option></select><label>Valor:</label><input type="text" id="filter-val" aria-label="Valor del filtro" placeholder="Escribe el valor...">',
    params: () => ({ column: document.getElementById('filter-col').value, operator: document.getElementById('filter-op').value, value: document.getElementById('filter-val').value })
  },
  drop_nulls: {
    title: icon('sparkles') + ' Eliminar filas con nulos',
    body: () => '<label>Columnas (vacío = todas):</label>'+selectAllHtml('nulls-check')+'<div class="col-check" id="nulls-check">'+colOptions(true)+'</div><label>Eliminar fila si:</label><select id="nulls-how" aria-label="Condición de eliminación de nulos"><option value="any">ANY — alguna columna es nula</option><option value="all">ALL — todas las columnas son nulas</option></select>',
    params: () => { const c=[...document.querySelectorAll('#nulls-check input:checked')].map(i=>i.value); return { columns: c.length===currentColumns.length?null:c, how: document.getElementById('nulls-how').value }; }
  },
  drop_duplicates: {
    title: icon('trash-2') + ' Eliminar duplicados',
    body: () => '<label>Basado en columnas:</label>'+selectAllHtml('dup-check')+'<div class="col-check" id="dup-check">'+colOptions(true)+'</div>',
    params: () => { const c=[...document.querySelectorAll('#dup-check input:checked')].map(i=>i.value); return { columns: c.length===currentColumns.length?null:c }; }
  },
  rename_column: {
    title: icon('pencil') + ' Renombrar columna',
    body: () => '<label>Columna a renombrar:</label><select id="rename-old" aria-label="Columna a renombrar">'+colOptions()+'</select><label>Nuevo nombre:</label><input type="text" id="rename-new" aria-label="Nuevo nombre de la columna" placeholder="Nuevo nombre...">',
    params: () => ({ old_name: document.getElementById('rename-old').value, new_name: document.getElementById('rename-new').value })
  },
  drop_column: {
    title: icon('x') + ' Eliminar columna',
    body: () => '<label>Columna a eliminar:</label><select id="drop-col" aria-label="Columna a eliminar">'+colOptions()+'</select><p class="modal-warn">'+icon('triangle-alert')+'<span>Puedes deshacer con '+icon('undo-2')+' Deshacer paso</span></p>',
    params: () => ({ column: document.getElementById('drop-col').value })
  },
  trim: {
    title: icon('eraser') + ' Eliminar espacios extra',
    body: () => '<label>Columnas:</label>'+selectAllHtml('trim-check')+'<div class="col-check" id="trim-check">'+colOptions(true)+'</div>',
    params: () => ({ columns: [...document.querySelectorAll('#trim-check input:checked')].map(i=>i.value) })
  },
  change_case: {
    title: icon('case-sensitive') + ' Formateo de texto',
    body: () => '<label>Columna:</label><select id="case-col" aria-label="Columna para transformar texto">'+colOptions()+'</select><label>Transformar a:</label><select id="case-type" aria-label="Tipo de transformación de texto"><option value="lower">minúsculas (lower)</option><option value="upper">MAYÚSCULAS (upper)</option><option value="title">Título Caso (title)</option><option value="capitalize">Primera letra (capitalize)</option></select>',
    params: () => ({ column: document.getElementById('case-col').value, case: document.getElementById('case-type').value })
  },
  clean_newlines: {
    title: '↵ Limpiar saltos de línea',
    body: () => '<label>Columnas:</label>'+selectAllHtml('nl-check')+'<div class="col-check" id="nl-check">'+colOptions(true)+'</div><p style="font-size:0.75rem;color:var(--text2);margin-top:0.5rem">Reemplaza \\n, \\r\\n y \\r por un espacio y aplica trim.</p>',
    params: () => { const c=[...document.querySelectorAll('#nl-check input:checked')].map(i=>i.value); return { columns: c.length===currentColumns.length ? null : c }; }
  },
  replace: {
    title: icon('refresh-cw') + ' Reemplazar valores',
    body: () => '<label>Columna:</label><select id="rep-col" aria-label="Columna para reemplazar valores">'+colOptions()+'</select><label>Valor a reemplazar:</label><input type="text" id="rep-old" aria-label="Valor a reemplazar" placeholder="Texto original..."><label>Reemplazar por:</label><input type="text" id="rep-new" aria-label="Valor de reemplazo" placeholder="Texto nuevo...">',
    params: () => ({ column: document.getElementById('rep-col').value, old_value: document.getElementById('rep-old').value, new_value: document.getElementById('rep-new').value })
  },
  change_type: {
    title: icon('tag') + ' Cambiar tipo de dato',
    body: () => '<label>Columna:</label><select id="type-col" aria-label="Columna para cambiar tipo de dato">'+colOptions()+'</select><label>Nuevo tipo:</label><select id="type-dtype" aria-label="Nuevo tipo de dato"><option value="str">Texto (str)</option><option value="int">Número entero (int)</option><option value="float">Número decimal (float)</option><option value="datetime">Fecha/hora (datetime)</option></select>',
    params: () => ({ column: document.getElementById('type-col').value, dtype: document.getElementById('type-dtype').value })
  },
  sort: {
    title: icon('arrow-down-wide-narrow') + ' Ordenar',
    body: () => '<label>Columna:</label><select id="sort-col" aria-label="Columna para ordenar">'+colOptions()+'</select><label>Orden:</label><select id="sort-asc" aria-label="Dirección del orden"><option value="true">Ascendente (A→Z)</option><option value="false">Descendente (Z→A)</option></select>',
    params: () => ({ column: document.getElementById('sort-col').value, ascending: document.getElementById('sort-asc').value==='true' })
  },
  split_to_rows: {
    title: icon('arrow-down-to-line') + ' Separar por filas',
    body: () => '<label>Columna a separar:</label><select id="str-col" aria-label="Columna a separar por filas">'+colOptions()+'</select><label>Delimitador:</label><input type="text" id="str-delim" aria-label="Delimitador para separar por filas" value=","><p style="font-size:0.75rem;color:var(--text2);margin-top:0.5rem">Cada valor separado por el delimitador se convertirá en una fila nueva.</p>',
    params: () => ({ column: document.getElementById('str-col').value, delimiter: document.getElementById('str-delim').value, strip: true })
  },
  drop_rows: {
    title: icon('scissors') + ' Eliminar filas por posición',
    body: () => '<label>¿Desde dónde?</label><select id="dr-pos" aria-label="Posición de las filas a eliminar"><option value="top">Desde el inicio (primeras filas)</option><option value="bottom">Desde el final (últimas filas)</option></select><label>¿Cuántas filas eliminar?</label><input type="number" id="dr-n" aria-label="Cantidad de filas a eliminar" value="1" min="1">',
    params: () => ({ position: document.getElementById('dr-pos').value, n: parseInt(document.getElementById('dr-n').value) || 1 })
  },
  set_header: {
    title: icon('pin') + ' Definir fila como encabezado',
    body: () => '<label>Índice de la fila (0 = primera fila):</label><input type="number" id="sh-idx" aria-label="Índice de la fila a usar como encabezado" value="0" min="0"><p style="font-size:0.75rem;color:var(--text2);margin-top:0.5rem">Los valores de esa fila se usarán como nombres de columna y la fila será eliminada.</p>',
    params: () => ({ row_index: parseInt(document.getElementById('sh-idx').value) || 0 })
  },
  group_by: {
    title: icon('layers') + ' Group By (Agregación)',
    body: () => '<label>Agrupar por (columna):</label><select id=\"gb-by\" aria-label=\"Columna para agrupar\">'+colOptions()+'</select><label>Columna numérica a agregar:</label><select id=\"gb-col\" aria-label=\"Columna numérica a agregar\">'+colOptions()+'</select><label>Función de agregación:</label><select id=\"gb-func\" aria-label=\"Función de agregación\"><option value=\"sum\">sum — suma</option><option value=\"mean\">mean — media</option><option value=\"count\">count — conteo</option><option value=\"min\">min — mínimo</option><option value=\"max\">max — máximo</option><option value=\"median\">median — mediana</option><option value=\"nunique\">nunique — valores únicos</option></select>',
    params: () => ({ by: document.getElementById('gb-by').value, column: document.getElementById('gb-col').value, func: document.getElementById('gb-func').value })
  },
  merge: {
    title: icon('git-merge') + ' Join / Merge (Cruzar datasets)',
    body: () => '<div class="merge-src"><div class="merge-src-head"><span>Frame derecho:</span><span id="merge-right-info">Sin cargar</span></div><div class="merge-src-actions"><select id="merge-right-demo" aria-label="Dataset demo para el frame derecho"><option value="">Elegir demo…</option>'+DEMO_DATASETS.map((d, i) => '<option value="'+i+'">'+d.name+'</option>').join('')+'</select><button type="button" class="btn btn-secondary" id="merge-right-browse">Examinar…</button><input type="file" id="merge-right-file" accept=".csv,.tsv,.xlsx,.xls" hidden></div></div>'
      + '<label>Columna de cruce (dataset activo):</label><select id="merge-left-col" aria-label="Columna de cruce del dataset activo">'+colOptions()+'</select>'
      + '<label>Columna de cruce (frame derecho):</label><select id="merge-right-col" aria-label="Columna de cruce del frame derecho"><option value="">— carga primero el frame derecho —</option></select>'
      + '<label>Tipo de cruce:</label><select id="merge-how" aria-label="Tipo de cruce"><option value="inner">inner — solo coincidencias</option><option value="left" selected>left — todas las filas izquierdas</option><option value="right">right — todas las filas derechas</option><option value="outer">outer — unión de ambos</option></select>'
      + '<label>Sufijo columnas izquierda:</label><input type="text" id="merge-suffix-left" aria-label="Sufijo para columnas solo izquierda" value="_x">'
      + '<label>Sufijo columnas derecha:</label><input type="text" id="merge-suffix-right" aria-label="Sufijo para columnas solo derecha" value="_y">'
      + '<p class="modal-warn">'+icon('triangle-alert')+'<span>Las claves sin coincidir quedan con valores vacíos. Puedes deshacer con '+icon('undo-2')+' Deshacer paso</span></p>',
    validate: (p) => !p.left_on ? 'Elige la columna de cruce del dataset activo'
      : (!p.right_on ? 'Carga un frame derecho y elige su columna de cruce' : null),
    params: () => ({
      left_on: document.getElementById('merge-left-col').value,
      right_on: document.getElementById('merge-right-col').value,
      how: document.getElementById('merge-how').value,
      suffixes: [document.getElementById('merge-suffix-left').value || '_x',
                 document.getElementById('merge-suffix-right').value || '_y']
    }),
    init: () => {
      const browse = document.getElementById('merge-right-browse');
      const file = document.getElementById('merge-right-file');
      const demo = document.getElementById('merge-right-demo');
      browse.addEventListener('click', () => file.click());
      file.addEventListener('change', e => {
        if (e.target.files[0]) sendRightFile(e.target.files[0]);
        e.target.value = '';
      });
      demo.addEventListener('change', e => {
        const d = DEMO_DATASETS[Number(e.target.value)];
        e.target.value = '';
        if (d) sendRightFile(new File([d.csv], d.file, { type: 'text/csv' }));
      });
      refreshRightInfo();
    }
  },
  regex_mask: {
    title: icon('eye-off') + ' Enmascarar / extraer PII (Regex Mask)',
    body: () => '<label>Columna:</label><select id="rm-col" aria-label="Columna para enmascarar o extraer PII">'+colOptions()+'</select>'
      + '<label>Patrón PII:</label><select id="rm-pattern" aria-label="Patrón de PII a detectar"><option value="email">Email</option><option value="phone">Teléfono</option><option value="id">Identificador (SN-001, X204, tarjeta)</option><option value="custom">Regex personalizada</option></select>'
      + '<div id="rm-custom-wrap" style="display:none"><label>Regex personalizada:</label><input type="text" id="rm-custom" aria-label="Regex personalizada" placeholder="ej: [A-Z]{2}-\\d{4}"></div>'
      + '<label>Modo:</label><select id="rm-mode" aria-label="Modo de la operación"><option value="mask">Enmascarar (sustituir en la misma columna)</option><option value="extract">Extraer a columna nueva (1ª coincidencia)</option></select>'
      + '<div id="rm-fill-wrap"><label>Relleno del enmascaramiento:</label><input type="text" id="rm-fill" aria-label="Texto de relleno para enmascarar" value="****"><p style="font-size:0.75rem;color:var(--text2);margin-top:-0.3rem;margin-bottom:0.5rem">Vacío = borrar la coincidencia.</p></div>'
      + '<div id="rm-newcol-wrap" style="display:none"><label>Nombre columna nueva:</label><input type="text" id="rm-newcol" aria-label="Nombre de la columna de destino" placeholder="vacío = columna_mask"></div>'
      + '<p class="modal-warn">'+icon('triangle-alert')+'<span>El patrón se aplica solo sobre la columna elegida. Los nulos reales se conservan; puedes deshacer con '+icon('undo-2')+' Deshacer paso</span></p>',
    params: () => ({
      column: document.getElementById('rm-col').value,
      pattern: document.getElementById('rm-pattern').value,
      custom_pattern: document.getElementById('rm-custom').value.trim(),
      mode: document.getElementById('rm-mode').value,
      mask: document.getElementById('rm-fill').value,
      new_column: document.getElementById('rm-newcol').value.trim()
    }),
    validate: (p) => (p.pattern === 'custom' && !p.custom_pattern) ? 'Escribe la regex personalizada.' : null,
    init: () => {
      document.getElementById('rm-pattern').addEventListener('change', toggleRegexMaskPattern);
      document.getElementById('rm-mode').addEventListener('change', toggleRegexMaskMode);
    }
  },
  concatenar_columnas: {
    title: icon('text') + ' Concatenar columnas',
    body: () => '<label>Columnas (se unen en el orden marcado):</label>'+selectAllHtml('cc-check')+'<div class="col-check" id="cc-check">'+colOptions(true)+'</div><label>Delimitador:</label><input type="text" id="cc-delim" aria-label="Delimitador entre columnas" value=" "><p style="font-size:0.75rem;color:var(--text2);margin-top:-0.3rem;margin-bottom:0.5rem">Vacío = unir sin separador. Los nulos se omiten: sin delimitadores sueltos.</p><label>Nombre columna nueva:</label><input type="text" id="cc-name" aria-label="Nombre de la columna nueva" placeholder="ej: Nombre Completo"><label style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0.35rem;font-size:0.78rem;font-weight:600;cursor:pointer"><input type="checkbox" id="cc-drop"> Eliminar columnas originales</label><p class="modal-warn">'+icon('triangle-alert')+'<span>Puedes deshacer con '+icon('undo-2')+' Deshacer paso</span></p>',
    params: () => ({
      columns: [...document.querySelectorAll('#cc-check input:checked')].map(i=>i.value),
      delimiter: document.getElementById('cc-delim').value,
      new_name: document.getElementById('cc-name').value.trim(),
      drop_sources: document.getElementById('cc-drop').checked
    }),
    validate: (p) => {
      if (p.columns.length < 2) return 'Elige al menos 2 columnas para concatenar.';
      if (!p.new_name) return 'La columna nueva necesita un nombre.';
      return null;
    }
  },
  detectar_outliers: {
    title: icon('activity') + ' Detectar Outliers',
    body: () => {
      const numeric = currentColumns.filter(c => currentDtypes[c] === 'INT' || currentDtypes[c] === 'FLOAT');
      if (!numeric.length) {
        return '<p class="modal-warn">'+icon('triangle-alert')+'<span>No hay columnas numéricas (INT/FLOAT) en el dataset. Cambia el tipo con Tipo dato para analizar una.</span></p>';
      }
      const list = numeric.map(c => '<label><input type="checkbox" value="'+c+'" checked> '+c+'</label>').join('');
      return '<label>Columnas numéricas a analizar:</label>'+selectAllHtml('do-check')+'<div class="col-check" id="do-check">'+list+'</div>'
        + '<label>Método:</label><select id="do-method" aria-label="Método de detección de outliers"><option value="zscore">Z-Score — |x − media| / desv. &gt; umbral</option><option value="iqr">IQR — fuera de Q1 − k·IQR … Q3 + k·IQR</option></select>'
        + '<label>Umbral:</label><input type="number" id="do-threshold" aria-label="Umbral de detección" value="2.5" step="0.1" min="0.1">'
        + '<p style="font-size:0.75rem;color:var(--text2);margin-top:-0.3rem;margin-bottom:0.5rem">Z-Score por defecto 2.5 (desviación de población); IQR usa k = 1.5. El cambio de método restablece el umbral.</p>'
        + '<p class="modal-warn">'+icon('triangle-alert')+'<span>La operación <strong>marca</strong> ({col}_outlier: TRUE/FALSE), no elimina filas: filtra después con Filtrar filas o Eliminar filas. Columnas constantes → todo FALSE. Puedes deshacer con '+icon('undo-2')+' Deshacer paso</span></p>';
    },
    params: () => ({
      columns: [...document.querySelectorAll('#do-check input:checked')].map(i=>i.value),
      method: document.getElementById('do-method').value,
      threshold: document.getElementById('do-threshold').value
    }),
    validate: (p) => (!p.columns.length ? 'Elige al menos una columna numérica.' : null),
    init: () => {
      document.getElementById('do-method').addEventListener('change', () => {
        const m = document.getElementById('do-method').value;
        document.getElementById('do-threshold').value = m === 'iqr' ? '1.5' : '2.5';
      });
    }
  },
  sampling: {
    title: icon('shuffle') + ' Muestreo (Sampling)',
    body: () => '<label>Modo de muestreo:</label><select id="samp-mode" aria-label="Modo de muestreo"><option value="head">head — primeras N filas</option><option value="tail">tail — últimas N filas</option><option value="random">random — N filas aleatorias</option><option value="stratified">stratified — N filas por estrato de una columna</option></select>'
      + '<div id="samp-n-wrap"><label>Cantidad de filas:</label><input type="number" id="samp-n" aria-label="Cantidad de filas a muestrear" value="10" min="1"></div>'
      + '<div id="samp-by-wrap" style="display:none"><label>Columna para estratificar:</label><select id="samp-by" aria-label="Columna para estratificar el muestreo">'+colOptions()+'</select><p style="font-size:0.75rem;color:var(--text2);margin-top:-0.3rem;margin-bottom:0.5rem">Se toman N filas por cada valor distinto de la columna (los nulos cuentan como un estrato más). Un estrato con menos de N filas se toma completo.</p></div>'
      + '<p style="font-size:0.75rem;color:var(--text2);margin-top:-0.3rem;margin-bottom:0.5rem">El muestreo aleatorio usa una semilla fija (42): la receta y el script exportado reproducen exactamente las mismas filas.</p>'
      + '<p class="modal-warn">'+icon('triangle-alert')+'<span>Puedes deshacer con '+icon('undo-2')+' Deshacer paso</span></p>',
    params: () => ({
      mode: document.getElementById('samp-mode').value,
      n: parseInt(document.getElementById('samp-n').value) || 1,
      by: document.getElementById('samp-mode').value === 'stratified' ? document.getElementById('samp-by').value : undefined
    }),
    validate: (p) => (p.mode === 'stratified' && !p.by) ? 'Elige la columna para estratificar.' : null,
    init: () => {
      document.getElementById('samp-mode').addEventListener('change', e => {
        document.getElementById('samp-by-wrap').style.display = e.target.value === 'stratified' ? 'block' : 'none';
      });
    }
  },
  calculated_column: {
    title: icon('calculator') + ' Columna Calculada',
    body: () => '<label>Nombre de la nueva columna:</label><input type="text" id="calc-name" aria-label="Nombre de la nueva columna" placeholder="ej: Ventas_con_iva"><label>Expresión pandas:</label><textarea id="calc-expr" aria-label="Expresión de la columna calculada" rows="3" placeholder="ej: Ventas * 1.21"></textarea><p style="font-size:0.75rem;color:var(--text2);margin-top:0.5rem">Usa nombres de columna, operadores (+, -, *, /, **, %), comparaciones y funciones: abs, round, log, sqrt, min, max, where(cond, a, b) y col(&#39;Nombre con espacios&#39;). El sandbox bloquea atributos, imports y lambdas.</p>',
    params: () => ({ name: document.getElementById('calc-name').value.trim(), expression: document.getElementById('calc-expr').value.trim() }),
    validate: (p) => {
      if (!p.name) return 'La columna calculada necesita un nombre.';
      if (!p.expression) return 'Escribe una expresión para la columna.';
      return null;
    }
  },
};

// ── FRAME DERECHO DEL JOIN/MERGE (op #19) ─────────────────────────────
async function sendRightFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch('/upload_right', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.error) { toast(data.error, 'error'); return; }
    applyRightInfo(data.name, data.data.columns, data.data.shape);
    toast('Frame derecho cargado: ' + data.name);
  } catch (e) { toast('Error al cargar el frame derecho', 'error'); }
}

async function refreshRightInfo() {
  try {
    const res = await fetch('/right_info');
    const data = await res.json();
    if (data.loaded) applyRightInfo(data.name, data.columns, data.shape);
  } catch (e) { /* sin red: el modal queda en "Sin cargar" */ }
}

function applyRightInfo(name, columns, shape) {
  const info = document.getElementById('merge-right-info');
  const sel = document.getElementById('merge-right-col');
  if (!info || !sel) return; // modal cerrado
  info.textContent = name + ' — ' + shape[0] + '×' + shape[1];
  sel.innerHTML = columns.map(c => '<option value="' + escapeHtml(c) + '">' + escapeHtml(c) + '</option>').join('');
  const left = document.getElementById('merge-left-col');
  if (left && columns.includes(left.value)) sel.value = left.value;
}

function openModal(op) {
  if (!currentColumns.length) return;
  currentOp = op;
  const def = modalDefs[op];
  document.getElementById('modal-title').innerHTML = def.title;
  document.getElementById('modal-body').innerHTML = def.body();
  if (def.init) def.init();
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
      split_to_rows: 'str-col',
      regex_mask: 'rm-col'
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
      drop_duplicates: 'dup-check',
      concatenar_columnas: 'cc-check',
      detectar_outliers: 'do-check'
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

// Éxito compartido de una operación aplicada (confirmModal y el auto-mapeo
// de tipos de api.js). `notify=false` calla el toast (para ráfagas de N ops).
function handleOpResponse(op, params, data, notify = true) {
  renderTable(data.data);
  updateCode(data.code);
  addPipelineStep(op, params);
  // Avance del pipeline → la rama de rehacer se invalida (el backend
  // hace lo mismo con su `redo_history`).
  redoSteps = [];
  updateUndoRedoButtons(true, false);
  loadStats();   // refrescar diagnóstico en segundo plano
  loadLineage(); // refrescar linaje en segundo plano (F3.3)
  if (notify) toast(op.replace(/_/g, ' ') + ' aplicado');
}

async function confirmModal() {
  if (!currentOp) return;
  const op = currentOp;
  const params = modalDefs[op].params();
  if (modalDefs[op].validate) {
    const err = modalDefs[op].validate(params);
    if (err) { toast(err, 'error'); return; }
  }
  closeModal();
  showLoading();
  try {
    const res = await fetch('/operation', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({operation: op, params}) });
    const data = await res.json();
    hideLoading();
    if (data.error) { toast(data.error, 'error'); return; }
    handleOpResponse(op, params, data);
  } catch(e) { hideLoading(); toast('Error al aplicar operación', 'error'); }
}

async function undo() {
  showLoading();
  const res = await fetch('/undo', {method:'POST'});
  const data = await res.json();
  hideLoading();
  if (data.error) { toast(data.error, 'info'); return; }
  renderTable(data.data); updateCode(data.code);
  if (pipelineSteps.length > 0) { redoSteps.push(pipelineSteps.pop()); renderPipeline(); }
  updateUndoRedoButtons(data.can_undo, data.can_redo);
  loadStats(); // refrescar diagnóstico en segundo plano
  loadLineage(); // refrescar linaje en segundo plano (F3.3)
  toast('Paso deshecho', 'info');
}

async function redo() {
  showLoading();
  const res = await fetch('/redo', {method:'POST'});
  const data = await res.json();
  hideLoading();
  if (data.error) { toast(data.error, 'info'); return; }
  renderTable(data.data); updateCode(data.code);
  if (redoSteps.length > 0) { pipelineSteps.push(redoSteps.pop()); renderPipeline(); }
  updateUndoRedoButtons(data.can_undo, data.can_redo);
  loadStats(); // refrescar diagnóstico en segundo plano
  loadLineage(); // refrescar linaje en segundo plano (F3.3)
  toast('Paso rehecho', 'info');
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

// ── DATASET PICKER (F2.7) ─────────────────────────────────────────────
// 3 datasets demo embebidos como CSV. Elegir uno crea un File y reutiliza
// uploadFile() de api.js — sin cambios de backend.
const DEMO_DATASETS = [
  {
    name: 'Ventas Q4',
    file: 'ventas_q4.csv',
    desc: 'Ventas por región. Tipos limpios: INT, FLOAT y texto.',
    icon: 'arrow-down-wide-narrow',
    csv: `Fecha,Region,Producto,Unidades,Precio,Total
2026-10-01,Norte,Teclado,12,45.90,550.80
2026-10-02,Sur,Ratón,30,25.50,765.00
2026-10-03,Este,Monitor,5,189.00,945.00
2026-10-04,Oeste,Audífonos,8,79.90,639.20
2026-10-05,Norte,Ratón,22,25.50,561.00
2026-10-06,Sur,Teclado,15,45.90,688.50
2026-10-07,Este,Audífonos,11,79.90,878.90
2026-10-08,Oeste,Monitor,3,189.00,567.00
2026-10-09,Norte,Monitor,7,189.00,1323.00
2026-10-10,Sur,Audífonos,9,79.90,719.10
2026-10-11,Este,Teclado,18,45.90,826.20
2026-10-12,Oeste,Ratón,27,25.50,688.50
2026-10-13,Norte,Audífonos,6,79.90,479.40
2026-10-14,Sur,Monitor,4,189.00,756.00
2026-10-15,Este,Ratón,35,25.50,892.50
2026-10-16,Oeste,Teclado,10,45.90,459.00
2026-10-17,Norte,Teclado,25,45.90,1147.50
2026-10-18,Sur,Ratón,14,25.50,357.00
2026-10-19,Este,Monitor,2,189.00,378.00
2026-10-20,Oeste,Audífonos,13,79.90,1038.70
2026-10-21,Norte,Ratón,19,25.50,484.50
2026-10-22,Sur,Teclado,8,45.90,367.20
2026-10-23,Este,Audífonos,16,79.90,1278.40
2026-10-24,Oeste,Monitor,6,189.00,1134.00
2026-10-25,Norte,Monitor,4,189.00,756.00
2026-10-26,Sur,Audífonos,7,79.90,559.30
2026-10-27,Este,Teclado,21,45.90,963.90
2026-10-28,Oeste,Ratón,31,25.50,790.50
2026-10-29,Norte,Audífonos,10,79.90,799.00
2026-10-30,Sur,Monitor,5,189.00,945.00
2026-10-31,Este,Ratón,28,25.50,714.00
2026-11-01,Oeste,Teclado,13,45.90,596.70
2026-11-02,Norte,Teclado,17,45.90,780.30
2026-11-03,Sur,Ratón,24,25.50,612.00
2026-11-04,Este,Monitor,9,189.00,1701.00
2026-11-05,Oeste,Audífonos,5,79.90,399.50
2026-11-06,Norte,Ratón,33,25.50,841.50
2026-11-07,Sur,Teclado,11,45.90,504.90
2026-11-08,Este,Audífonos,14,79.90,1118.60
2026-11-09,Oeste,Monitor,8,189.00,1512.00`
  },
  {
    name: 'Empleados',
    file: 'empleados.csv',
    desc: 'Celdas vacías reales (NaN). Ideal para nulos y trim.',
    icon: 'sparkles',
    csv: `ID,Nombre,Departamento,Salario,Email
1,Ana Torres,Dirección,9500.00,ana.torres@catflip.dev
2,Luis Pardo,Ingeniería,7200.00,luis.pardo@catflip.dev
3,María Ruiz,Marketing,5400.00,maria.ruiz@catflip.dev
4,Carlos Vega,Ingeniería,7800.00,
5,Lucía Herrera,,,
6,Jorge Molina,Soporte,4100.00,jorge.molina@catflip.dev
7,Carmen Lozano,Marketing,,carmen.lozano@catflip.dev
8,Diego Navarro,Ingeniería,6900.00,
9,Sofía Ramos,Ventas,4800.00,sofia.ramos@catflip.dev
10,Pablo Serrano,Ventas,5100.00,pablo.serrano@catflip.dev
11,Elena Bravo,,,
12,Óscar Vidal,Soporte,3900.00,oscar.vidal@catflip.dev
13,Paula Ortega,Marketing,5200.00,
14,Iván Castillo,Ingeniería,,ivan.castillo@catflip.dev
15,Beatriz Gil,Ventas,4600.00,beatriz.gil@catflip.dev
16,Raúl Reyes,Dirección,8700.00,raul.reyes@catflip.dev
17,Nuria Peña,Soporte,,nuria.pena@catflip.dev
18,Andrés Cruz,Ingeniería,7100.00,
19,Irene Santos,Marketing,4900.00,irene.santos@catflip.dev
20,Mario Ríos,Ventas,,mario.rios@catflip.dev
21,Julia Pastor,Ingeniería,6500.00,julia.pastor@catflip.dev
22,Hugo Sáez,Soporte,4200.00,
23,Teresa León,Dirección,,
24,Adrián Mora,Ventas,5000.00,adrian.mora@catflip.dev
25,Rosa Iglesias,Marketing,5300.00,rosa.iglesias@catflip.dev`
  },
  {
    name: 'Sensores IoT',
    file: 'sensores_iot.csv',
    desc: 'Fechas ISO, booleanos y FLOAT negativos. Para change_type.',
    icon: 'tag',
    csv: `timestamp,sensor_id,temp_c,humedad,activo
2026-11-01T08:00:00,SN-01,18.4,61.2,TRUE
2026-11-01T09:00:00,SN-02,19.1,58.7,TRUE
2026-11-01T10:00:00,SN-03,21.6,55.3,TRUE
2026-11-01T11:00:00,SN-04,23.2,52.1,FALSE
2026-11-01T12:00:00,SN-05,24.8,49.6,TRUE
2026-11-01T13:00:00,SN-01,25.5,47.2,TRUE
2026-11-01T14:00:00,SN-02,26.1,45.8,TRUE
2026-11-01T15:00:00,SN-03,27.4,43.5,FALSE
2026-11-01T16:00:00,SN-04,26.8,44.9,TRUE
2026-11-01T17:00:00,SN-05,25.2,48.3,TRUE
2026-11-01T18:00:00,SN-01,23.7,51.6,TRUE
2026-11-01T19:00:00,SN-02,22.1,54.4,FALSE
2026-11-01T20:00:00,SN-03,20.5,57.8,TRUE
2026-11-01T21:00:00,SN-04,19.2,60.1,TRUE
2026-11-01T22:00:00,SN-05,17.8,62.9,TRUE
2026-11-01T23:00:00,SN-01,16.4,64.5,FALSE
2026-11-02T00:00:00,SN-02,15.1,66.2,TRUE
2026-11-02T01:00:00,SN-03,13.7,68.4,TRUE
2026-11-02T02:00:00,SN-04,12.3,70.1,TRUE
2026-11-02T03:00:00,SN-05,10.9,71.8,FALSE
2026-11-02T04:00:00,SN-01,9.5,73.2,TRUE
2026-11-02T05:00:00,SN-02,8.2,74.6,TRUE
2026-11-02T06:00:00,SN-03,6.8,75.9,TRUE
2026-11-02T07:00:00,SN-04,5.4,77.3,FALSE
2026-11-02T08:00:00,SN-05,4.1,78.5,TRUE
2026-11-02T08:00:00,SN-01,2.7,79.4,TRUE
2026-11-02T09:00:00,SN-02,1.3,80.6,TRUE
2026-11-02T10:00:00,SN-03,-0.1,81.9,TRUE
2026-11-02T11:00:00,SN-04,-1.5,83.2,FALSE
2026-11-02T12:00:00,SN-05,-2.8,84.1,TRUE
2026-11-02T13:00:00,SN-01,-4.2,85.6,TRUE
2026-11-02T14:00:00,SN-02,-5.2,86.3,TRUE
2026-11-02T15:00:00,SN-03,-3.7,84.8,FALSE
2026-11-02T16:00:00,SN-04,-1.9,82.5,TRUE
2026-11-02T17:00:00,SN-05,0.4,80.1,TRUE
2026-11-02T18:00:00,SN-01,2.6,77.6,TRUE
2026-11-02T19:00:00,SN-02,4.9,75.2,FALSE
2026-11-02T20:00:00,SN-03,7.3,72.8,TRUE
2026-11-02T21:00:00,SN-04,9.6,70.4,TRUE
2026-11-02T22:00:00,SN-05,11.8,68.0,TRUE
2026-11-02T23:00:00,SN-01,13.5,66.1,FALSE
2026-11-03T00:00:00,SN-02,14.9,64.3,TRUE
2026-11-03T01:00:00,SN-03,16.2,62.5,TRUE
2026-11-03T02:00:00,SN-04,15.7,63.8,TRUE
2026-11-03T03:00:00,SN-05,14.3,65.6,FALSE
2026-11-03T04:00:00,SN-01,12.8,67.4,TRUE
2026-11-03T05:00:00,SN-02,11.2,69.1,TRUE
2026-11-03T06:00:00,SN-03,9.7,71.0,TRUE
2026-11-03T07:00:00,SN-04,8.1,72.7,FALSE
2026-11-03T08:00:00,SN-05,7.6,73.4,TRUE`
  }
];

function openDatasetPicker() {
  const grid = document.getElementById('ds-grid');
  grid.innerHTML = DEMO_DATASETS.map((d, i) => {
    const lines = d.csv.trim().split('\n');
    const cols = lines[0].split(',').length;
    return '<button type="button" class="ds-card" onclick="loadDemoDataset(' + i + ')">'
         + '<span class="ds-card-icon">' + icon(d.icon) + '</span>'
         + '<span class="ds-card-name">' + d.name + '</span>'
         + '<span class="ds-card-meta">' + (lines.length - 1) + ' filas × ' + cols + ' columnas</span>'
         + '<span class="ds-card-desc">' + d.desc + '</span>'
         + '</button>';
  }).join('');
  document.getElementById('datasetpicker-overlay').classList.add('open');
}

function closeDatasetPicker() {
  const overlay = document.getElementById('datasetpicker-overlay');
  if (overlay) overlay.classList.remove('open');
}

function loadDemoDataset(i) {
  const d = DEMO_DATASETS[i];
  if (!d) return;
  closeDatasetPicker();
  uploadFile(new File([d.csv], d.file, { type: 'text/csv' }), 0);
}

// Dropzone del picker: mismo flujo handleFile que el upload-area original
const dsDropzone = document.getElementById('ds-dropzone');
if (dsDropzone) {
  dsDropzone.addEventListener('dragover', e => { e.preventDefault(); dsDropzone.classList.add('drag-over'); });
  dsDropzone.addEventListener('dragleave', () => dsDropzone.classList.remove('drag-over'));
  dsDropzone.addEventListener('drop', e => {
    e.preventDefault();
    dsDropzone.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  });
}
