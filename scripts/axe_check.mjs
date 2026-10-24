// Gate de accesibilidad (F3.4): abre Cat_flip con Playwright, ejecuta axe
// (WCAG 2.0 A/AA) en tema claro y oscuro sobre 5 superficies — página
// base, modal «Receta desde CSV», modal de conectores demo, modal de
// validación de esquema y la pestaña Diagnóstico con el heatmap de
// correlaciones — y escribe violations.json. Sale con código 1 si hay
// violaciones, así la CI falla sin parsear la consola.
//
// Uso: con el servidor corriendo (python app.py), `npm run test:axe`.
// Variables: AXE_BASE_URL (default http://127.0.0.1:5050), AXE_OUT.
import { chromium } from 'playwright';
import { createRequire } from 'node:module';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const require = createRequire(import.meta.url);
const AXE_PATH = require.resolve('axe-core/axe.min.js');
const BASE_URL = process.env.AXE_BASE_URL || 'http://127.0.0.1:5050';
const OUT = process.env.AXE_OUT || 'violations.json';

// CSV de prueba con los males que la heurística detecta: espacios
// sobrantes, una celda vacía y una fila duplicada
const CSV = 'Nombre,Edad,Ciudad\n Ana ,30,Madrid\nLuis,25,\nAna ,30,Madrid\nCarla,35,Sevilla\n';

const results = [];
let failures = 0;

async function runAxe(page, label) {
  await page.addScriptTag({ path: AXE_PATH });
  const violations = await page.evaluate(async () => {
    const r = await window.axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] },
    });
    return r.violations.map(v => ({
      id: v.id,
      impact: v.impact,
      help: v.help,
      nodes: v.nodes.map(n => n.target),
    }));
  });
  results.push({ label, violations });
  if (violations.length) failures += violations.length;
  console.log(`${label}: ${violations.length === 0 ? 'OK (0 violaciones)' : violations.length + ' violación(es)'}`);
  for (const v of violations) console.log(`  ✘ ${v.id} (${v.impact}) — ${v.help}`);
}

const browser = await chromium.launch();

try {
  const page = await browser.newPage();

  // Sube el CSV por el input real del app (mismo camino que un usuario)
  const dir = mkdtempSync(join(tmpdir(), 'catflip-axe-'));
  const csvPath = join(dir, 'demo.csv');
  writeFileSync(csvPath, CSV);
  await page.goto(BASE_URL);
  await page.setInputFiles('#file-input', csvPath);
  await page.waitForFunction(
    () => document.getElementById('header-metrics').style.display === 'flex',
    null,
    { timeout: 20000 },
  );

  // Un paso manual para que el panel de recetas tenga contenido real
  await page.evaluate(async () => {
    const res = await fetch('/operation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operation: 'change_case', params: { column: 'Nombre', case: 'upper' } }),
    });
    const data = await res.json();
    if (!data.error) handleOpResponse('change_case', { column: 'Nombre', case: 'upper' }, data, false);
  });

  for (const theme of ['light', 'dark']) {
    await page.evaluate(t => document.documentElement.setAttribute('data-theme', t), theme);
    await runAxe(page, `página (${theme})`);

    // Modal «Receta desde CSV» abierto (nueva superficie de F3.4)
    await page.evaluate(async () => {
      const f = new File(['Nombre,Edad,Ciudad\n Ana ,30,Madrid\nLuis,25,\n'], 'sucio.csv', { type: 'text/csv' });
      await openCsvRecipe({ files: [f], value: '' });
    });
    await page.waitForSelector('#csvrecipe-overlay.open');
    await runAxe(page, `modal receta-desde-CSV (${theme})`);
    await page.evaluate(() => closeCsvRecipe());

    // Modal de conectores demo (conectores mock: BigQuery/Snowflake/Webhook)
    await page.evaluate(() => openConnector('webhook'));
    await page.waitForSelector('#connector-overlay.open');
    await runAxe(page, `modal conector-webhook (${theme})`);
    await page.evaluate(() => closeConnector());

    // Modal de validación de esquema (reglas no-nulo/único/regex/rango):
    // se añade y aplica una regla real para que el resumen tenga contenido.
    // En la 2ª pasada (tema oscuro) la regla ya existe → addSchemaRule la
    // descarta como duplicada y apply reenvía la misma lista: superficie idéntica.
    await page.evaluate(async () => {
      await openSchemaRules();
      document.getElementById('sv-col').value = 'Ciudad';
      document.getElementById('sv-rule').value = 'not_null';
      addSchemaRule();
      await applySchemaRules();
    });
    await page.waitForSelector('#schemaval-overlay.open');
    await runAxe(page, `modal validación-esquema (${theme})`);
    await page.evaluate(() => closeSchemaRules());

    // Pestaña Diagnóstico con el heatmap de correlaciones (5ª superficie):
    // calculated_column crea la 2ª numérica (sobrescribe → idempotente en
    // la 2ª pasada) y switchTab + loadCorrelations pinta la matriz.
    await page.evaluate(async () => {
      const params = { name: 'Edad_x2', expression: 'Edad * 2' };
      const res = await fetch('/operation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operation: 'calculated_column', params }),
      });
      const data = await res.json();
      if (!data.error) handleOpResponse('calculated_column', params, data, false);
      switchTab('stats');
      await loadCorrelations();
    });
    await page.waitForSelector('#corr-grid table');
    await runAxe(page, `diagnóstico-correlaciones (${theme})`);
    await page.evaluate(() => switchTab('data'));
  }
} catch (err) {
  console.error('Error inesperado del gate de axe:', err);
  results.push({ label: 'error-del-gate', violations: [], error: String(err && err.message || err) });
  failures += 1;
} finally {
  await browser.close();
}

writeFileSync(OUT, JSON.stringify({ base_url: BASE_URL, results }, null, 2));
console.log(`\nResultados escritos en ${OUT}`);
process.exit(failures ? 1 : 0);
