// Gate de accesibilidad (F3.4 + dark mode automático + Open Core + nuevo
// front Tech Labs): abre Cat_flip con Playwright y ejecuta axe (WCAG 2.0
// A/AA) en 15 corridas — la página base en modo Automático con el sistema
// en oscuro (prefers-color-scheme, perfil sin localStorage); tema claro y
// oscuro explícitos sobre 6 superficies (página base, modal «Receta desde
// CSV», modal de conectores demo, modal de validación de esquema, la
// pestaña Diagnóstico con el heatmap y el panel de selector de tema
// abierto — con el catálogo de énfasis incluido); y las 2 paletas premium
// (Aurora, Solar) con el servidor licenciado.
// Además verifica que el cambio en vivo del sistema re-aplica el tema
// (listener del matchMedia en modo 'auto') y escribe violations.json.
// Sale con código 1 si hay fallos o violaciones, así la CI falla sin
// parsear la consola.
//
// Uso: con el servidor corriendo (python app.py), `npm run test:axe`.
// El servidor debe levantar CON licencia premium (CATFLIP_PREMIUM_KEY)  // si no, las corridas premium fallan — la CI lo hace así.
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

// axe debe medir el estado en REPOSO, no a mitad de vuelo: el cambio de
// tema (transition de color/fondo), el enable de los botones al cargar el
// CSV y el fade-in de los toasts duran 150–220 ms, y muestreados en medio
// dan colores interpolados que no existen en la UI real (falsos positivos
// de contraste). Espera a que termine toda animación/transición FINITA
// (las infinitas, como el punto pulsante del badge, se ignoran) con tope
// de 2 s, y así la verificación sigue siendo sobre los valores calculados
// finales de cada superficie.
async function settleAnimations(page) {
  await page.evaluate(async () => {
    const anims = (typeof document.getAnimations === 'function' ? document.getAnimations() : [])
      .filter(a => {
        const t = a.effect && a.effect.getComputedTiming();
        return t && t.iterations !== Infinity;
      })
      .slice(0, 60);
    await Promise.race([
      Promise.all(anims.map(a => a.finished.catch(() => {}))),
      new Promise(resolve => setTimeout(resolve, 2000)),
    ]);
  }).catch(() => {});
  await page.waitForTimeout(120);
}

async function runAxe(page, label) {
  await settleAnimations(page);
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

  const dir = mkdtempSync(join(tmpdir(), 'catflip-axe-'));
  const csvPath = join(dir, 'demo.csv');
  writeFileSync(csvPath, CSV);

  // Modo Automático con el SO en oscuro: contexto Playwright fresco (sin
  // localStorage) → themeMode='auto' debe resolver data-theme=dark al cargar
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto(BASE_URL);
  const autoDark = await page.evaluate(() =>
    document.documentElement.getAttribute('data-theme-mode') === 'auto' &&
    document.documentElement.getAttribute('data-theme') === 'dark');
  if (!autoDark) {
    console.log('auto-oscuro: FALLO — prefers-color-scheme oscuro no aplicó data-theme=dark');
    results.push({ label: 'página (automático · sistema oscuro)', violations: [], error: 'auto-dark no aplicado' });
    failures += 1;
  }

  // Sube el CSV por el input real del app (mismo camino que un usuario)
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

  // Superficie extra: la página ya con datos en Automático + sistema oscuro
  if (autoDark) await runAxe(page, 'página (automático · sistema oscuro)');

  // El cambio del sistema en vivo debe re-aplicar el tema (modo 'auto'):
  // al emular claro, el listener del matchMedia quita data-theme=dark.
  await page.emulateMedia({ colorScheme: 'light' });
  const liveFlip = await page.waitForFunction(
    () => document.documentElement.getAttribute('data-theme-mode') === 'auto' &&
          !document.documentElement.hasAttribute('data-theme'),
    null, { timeout: 3000 },
  ).then(() => true).catch(() => false);
  if (!liveFlip) {
    console.log('cambio en vivo: FALLO — prefers-color-scheme claro no re-aplicó el tema');
    results.push({ label: 'cambio-en-vivo-scheme', violations: [], error: 'listener no re-aplicó' });
    failures += 1;
  }

  for (const theme of ['light', 'dark']) {
    // Mismo mecanismo que el usuario (setThemeMode → applyTheme): un
    // setAttribute('data-theme') directo cambiaría el CSS pero dejaría los
    // tokens DERIVADOS por JS (--accent-text, calculado contra la superficie
    // del tema anterior) desincronizados → mediría un estado que la app nunca
    // produce y daría falsos positivos de contraste (toast info, badges).
    await page.evaluate(t => { themeMode = t; applyTheme(); }, theme);
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

    // Selector de tema abierto (6ª superficie): el panel con vista previa,
    // los grupos Claro/Oscuro/Sistema Y el catálogo de énfasis (6 presets +
    // personalizado), abierto por el mismo mecanismo que el usuario
    // (aria-expanded, foco roving y swatches en su estado real).
    await page.evaluate(() => openThemeMenu());
    await page.waitForSelector('#theme-menu:not([hidden])');
    const menuItems = await page.evaluate(() => ({
      themes: document.querySelectorAll('#theme-menu [data-theme-id]').length,
      groups: document.querySelectorAll('#theme-menu [role="group"]').length,
      checked: document.querySelectorAll('#theme-menu [data-theme-id][aria-checked="true"]').length,
      accents: document.querySelectorAll('#theme-menu .accent-swatch').length,
      accentChecked: document.querySelectorAll('#theme-menu .accent-swatch[aria-checked="true"]').length,
    }));
    if (menuItems.themes < 3 || menuItems.groups !== 4 || menuItems.checked !== 1 ||
        menuItems.accents < 6 || menuItems.accentChecked !== 1) {
      console.log(`selector de tema: FALLO — panel mal construido (${JSON.stringify(menuItems)})`);
      results.push({ label: `selector-tema-abierto-${theme}`, violations: [], error: 'panel de tema o catálogo de énfasis inválido' });
      failures += 1;
    } else {
      await runAxe(page, `selector-tema-abierto (${theme})`);
    }
    await page.evaluate(() => closeThemeMenu(false));
  }

  // ── Superficies premium (Open Core): Aurora y Solar ─────────────────
  // Usa el mismo mecanismo que el usuario (themeMode + applyTheme + link
  // /premium/themes/<id>.css). Sin licencia en el servidor, FALLO: el
  // gate de CI siempre levanta con CATFLIP_PREMIUM_KEY, así las 15
  // corridas son reales y nunca se omiten en silencio.
  const premium = await page.evaluate(() =>
    fetch('/premium/status').then(r => r.json()).catch(() => null));
  if (!(premium && premium.licensed && premium.themes.length)) {
    console.log('temas premium: FALLO — servidor sin licencia (levántalo con CATFLIP_PREMIUM_KEY)');
    results.push({ label: 'temas-premium', violations: [], error: 'servidor sin licencia premium' });
    failures += 1;
  } else {
    for (const t of premium.themes) {
      await page.evaluate(async (id) => {
        themeMode = id;
        applyTheme();
        await new Promise(resolve => {
          const link = document.getElementById('premium-theme-css');
          if (!link) return resolve();
          if (link.sheet) return resolve();
          link.addEventListener('load', resolve, { once: true });
          link.addEventListener('error', resolve, { once: true });
          setTimeout(resolve, 3000);
        });
      }, t.id);
      const applied = await page.evaluate(id => ({
        mode: document.documentElement.getAttribute('data-theme-mode') === id,
        theme: document.documentElement.getAttribute('data-theme') === id,
        css: !!(document.getElementById('premium-theme-css') || {}).sheet,
      }), t.id);
      if (!applied.mode || !applied.theme || !applied.css) {
        console.log(`tema premium ${t.name}: FALLO — no aplicó (${JSON.stringify(applied)})`);
        results.push({ label: `tema-premium-${t.id}`, violations: [], error: 'tema premium no aplicado' });
        failures += 1;
      } else {
        await runAxe(page, `tema premium ${t.name}`);
      }
    }
    // Deja el DOM como lo dejó el bucle de claro/oscuro
    await page.evaluate(() => { themeMode = 'light'; applyTheme(); });
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
