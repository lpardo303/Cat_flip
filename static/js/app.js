// Cat_flip — tema, paneles colapsables, init, listeners globales
// ── CATÁLOGO DE ÉNFASIS (ortogonal al tema) ──────────────────────────────────
// Un solo catálogo para claro, oscuro, Sistema y los temas premium: el
// usuario elige un color de énfasis y de él se derivan variables por
// CONTRASTE WCAG real (no el umbral de luminancia percibida del prototipo,
// que ponía texto blanco sobre naranja = 3.2:1 y suspendería axe):
//   · --accent / --accent-hover / --accent-subtle / --accent-glow
//   · --accent-contrast  → texto SOBRE el relleno (blanco vs #0c0d10, el
//     de mayor contraste; sobre naranja sale texto oscuro = 6.0:1)
//   · --accent-text       → texto acento SOBRE superficie (se oscurece o
//     mezcla con blanco hasta ≥4.6:1 contra la superficie del tema vigente)
// applyTheme() llama a applyAccent() → los derivados se recalculan al
// cambiar de paleta (la ortogonalidad con Aurora/Solar es este cálculo).
// Persistencia: localStorage['catflip-accent'].
const ACCENTS = [
  { hex: '#FF5414', name: 'Naranja Eléctrico' },
  { hex: '#00F0FF', name: 'Cyan Quantum' },
  { hex: '#10B981', name: 'Lima Cyber' },
  { hex: '#8B5CF6', name: 'Violeta Tensor' },
  { hex: '#F59E0B', name: 'Ámbar Neón' },
  { hex: '#237373', name: 'Teal Cat_flip' },
];
let activeAccent = '#FF5414';

function normalizeHex(v) {
  if (typeof v !== 'string') return null;
  let h = v.trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(h)) h = h.split('').map(c => c + c).join('');
  return /^[0-9a-f]{6}$/i.test(h) ? '#' + h.toUpperCase() : null;
}

function hexToRgb(hex) {
  const h = normalizeHex(hex) || '#FF5414';
  const n = parseInt(h.slice(1), 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function rgbToHex(rgb) {
  const c = v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0');
  return ('#' + c(rgb.r) + c(rgb.g) + c(rgb.b)).toUpperCase();
}

// Luminancia relativa WCAG 2.1
function relLum(rgb) {
  const f = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(rgb.r) + 0.7152 * f(rgb.g) + 0.0722 * f(rgb.b);
}

function contrastRatio(l1, l2) {
  const hi = Math.max(l1, l2), lo = Math.min(l1, l2);
  return (hi + 0.05) / (lo + 0.05);
}

// Parsea el valor calculado de un token (#hex o rgb()/rgba()) → {r,g,b}
function parseCssRgb(str) {
  if (!str) return null;
  str = String(str).trim().toLowerCase();
  const hex = normalizeHex(str);
  if (hex) return hexToRgb(hex);
  const m = str.match(/^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/);
  return m ? { r: +m[1], g: +m[2], b: +m[3] } : null;
}

// Superficie de referencia del tema vigente para --accent-text.
// Se usa --base2 (hex) porque todas las paletas la definen y parsea;
// --bg-panel puede ser color-mix() sin resolver y no se puede leer como
// color. El objetivo 5.2 (no 4.6) deja margen sobre los tintes de acento
// (badge, chips) donde el fondo efectivo es más oscuro que la superficie.
function themeAccentRef() {
  const cs = getComputedStyle(document.documentElement);
  return parseCssRgb(cs.getPropertyValue('--base2')) ||
         parseCssRgb(cs.getPropertyValue('--bg-main')) ||
         { r: 224, g: 224, b: 224 };
}

function adjustBrightness(hex, percent) {
  const rgb = hexToRgb(hex);
  const factor = 1 + percent / 100;
  return rgbToHex({ r: rgb.r * factor, g: rgb.g * factor, b: rgb.b * factor });
}

function applyAccent() {
  const hex = normalizeHex(activeAccent);
  if (!hex) return;
  activeAccent = hex;
  const rgb = hexToRgb(hex);
  const root = document.documentElement;

  // Texto sobre el relleno: el de mayor contraste (blanco vs casi-negro)
  const lumFill = relLum(rgb);
  const whiteC = (1.0 + 0.05) / (lumFill + 0.05);
  const darkC = (lumFill + 0.05) / (relLum({ r: 12, g: 13, b: 16 }) + 0.05);
  const contrastText = whiteC >= darkC ? '#ffffff' : '#0c0d10';

  // Texto acento sobre superficie: iterar hasta ≥5.2:1 vs el tema vigente
  // (margen sobre 4.6 para los usos sobre tinte de acento, más oscuros)
  const ref = themeAccentRef();
  const refLum = relLum(ref);
  const lighten = refLum <= 0.4;   // superficie oscura → mezclar con blanco
  let textRgb = { r: rgb.r, g: rgb.g, b: rgb.b };
  for (let i = 0; i < 40 && contrastRatio(relLum(textRgb), refLum) < 5.2; i++) {
    textRgb = lighten
      ? { r: textRgb.r + (255 - textRgb.r) * 0.12,
          g: textRgb.g + (255 - textRgb.g) * 0.12,
          b: textRgb.b + (255 - textRgb.b) * 0.12 }
      : { r: textRgb.r * 0.94, g: textRgb.g * 0.94, b: textRgb.b * 0.94 };
  }

  root.style.setProperty('--accent', hex);
  root.style.setProperty('--accent-hover', adjustBrightness(hex, -14));
  root.style.setProperty('--accent-contrast', contrastText);
  root.style.setProperty('--accent-text', rgbToHex(textRgb));
  root.style.setProperty('--accent-subtle', 'rgba(' + rgb.r + ', ' + rgb.g + ', ' + rgb.b + ', 0.12)');
  root.style.setProperty('--accent-glow', 'rgba(' + rgb.r + ', ' + rgb.g + ', ' + rgb.b + ', 0.35)');

  const dot = document.getElementById('accent-dot');
  if (dot) dot.style.background = hex;
  syncAccentMenu();
  // El fondo estático (reduced-motion) se repinta con el nuevo acento; se
  // difiere a rAF para que corra tras ejecutar todo el script (evita TDZ
  // en la primera llamada, producida antes de declarar el canvas).
  requestAnimationFrame(() => {
    try { if (mathCtx && mathReduced()) drawStaticMathGrid(); } catch (e) {}
  });
}

function setAccent(hex) {
  const norm = normalizeHex(hex);
  if (!norm) return;
  activeAccent = norm;
  try { localStorage.setItem('catflip-accent', activeAccent); } catch (e) {}
  applyAccent();
}

// aria-checked + hex + picker del catálogo dentro del panel de tema
function syncAccentMenu() {
  const menu = document.getElementById('theme-menu');
  if (!menu) return;
  menu.querySelectorAll('.accent-swatch').forEach(btn => {
    btn.setAttribute('aria-checked', normalizeHex(btn.dataset.accent) === activeAccent ? 'true' : 'false');
    btn.tabIndex = -1;
  });
  const label = document.getElementById('accent-hex-label');
  if (label) label.textContent = activeAccent;
  // El botón «Personalizado» queda marcado solo si el acento activo no es
  // ninguno de los presets del catálogo (mutuamente excluyente con ellos).
  const customBtn = menu.querySelector('.accent-custom');
  if (customBtn) {
    const isPreset = ACCENTS.some(a => normalizeHex(a.hex) === activeAccent);
    customBtn.setAttribute('aria-checked', isPreset ? 'false' : 'true');
    const dot = customBtn.querySelector('.accent-custom-dot');
    if (dot) dot.style.background = activeAccent;
  }
  const custom = document.getElementById('accent-custom');
  if (custom && normalizeHex(custom.value) !== activeAccent) custom.value = activeAccent;
}

// ── TEMA (light | dark | auto | temas premium Open Core) ─────────────────────────────────────────────────────────
// 'light' y 'dark' son elección manual persistida; 'auto' (por defecto y
// resultado de no tener clave guardada) sigue `prefers-color-scheme` con
// re-aplicación en vivo. Los ids premium ('aurora', 'solar', …) llegan de
// /premium/status — solo existen con licencia y el CSS se inyecta desde
// /premium/themes/<id>.css.
// El botón NO cicla: abre el panel #theme-menu, donde cada opción lleva una
// vista previa real del tema (swatch con los tokens de esa paleta) y se
// agrupa en Claro / Oscuro / Sistema. La familia de cada tema premium
// (campo `mode`) la manda el servidor en /premium/status, nunca la adivina
// el front; sin licencia solo existen Claro, Oscuro y Sistema.
const THEME_SHORT = { light: 'Claro', dark: 'Oscuro', auto: 'Auto' };
const THEME_NAME  = { light: 'Claro', dark: 'Oscuro', auto: 'Automático' };
const THEME_GROUPS = [
  { key: 'light', title: 'Claro' },
  { key: 'dark',  title: 'Oscuro' },
  { key: 'auto',  title: 'Sistema' },
];
let themeMode = 'auto';
let themeMenuOpen = false;
let premiumThemes = [];   // [{id, name, mode}] del servidor — vacío sin licencia
const schemeMQ = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

function premiumThemeById(id) {
  return premiumThemes.find(t => t.id === id) || null;
}

function themeOrder() {
  return ['light', 'dark', 'auto'].concat(premiumThemes.map(t => t.id));
}

// Grupos del panel: el core siempre, los premium según `mode` del servidor.
function themeGroups() {
  const groups = THEME_GROUPS.map(g => ({ key: g.key, title: g.title, items: [] }));
  groups[0].items.push({ id: 'light', name: THEME_NAME.light });
  groups[1].items.push({ id: 'dark',  name: THEME_NAME.dark });
  groups[2].items.push({ id: 'auto',  name: THEME_NAME.auto });
  premiumThemes.forEach(t => {
    const g = groups.find(x => x.key === (t.mode === 'dark' ? 'dark' : 'light'));
    if (g) g.items.push({ id: t.id, name: t.name });
  });
  return groups;
}

// Qué resuelve 'auto' AHORA: la preferencia del sistema. Siempre un id con
// alcance propio ('light' incluido) para que un swatch nunca herede la
// paleta de la página, aunque esté en otro tema.
function systemThemeId() {
  return (schemeMQ && schemeMQ.matches) ? 'dark' : 'light';
}

// data-theme del swatch: 'auto' muestra lo que daría el sistema; el resto,
// su propio id.
function swatchThemeAttr(id) {
  if (id === 'auto') return systemThemeId();
  if (id === 'light') return 'light';
  return id;
}

function themeDisplayName(mode) {
  const p = premiumThemeById(mode);
  return p ? p.name : (THEME_NAME[mode] || THEME_NAME.auto);
}

function ensurePremiumCss(id) {
  const href = '/premium/themes/' + encodeURIComponent(id) + '.css';
  let link = document.getElementById('premium-theme-css');
  if (!link) {
    link = document.createElement('link');
    link.id = 'premium-theme-css';
    link.rel = 'stylesheet';
    document.head.appendChild(link);
  }
  if (link.getAttribute('href') !== href) link.setAttribute('href', href);
}

function applyTheme() {
  const html = document.documentElement;
  const premium = premiumThemeById(themeMode);
  const dark = themeMode === 'dark' || (themeMode === 'auto' && !!(schemeMQ && schemeMQ.matches));
  html.setAttribute('data-theme-mode', themeMode);
  if (premium) {
    ensurePremiumCss(premium.id);       // paleta fija, ignora el sistema
    html.setAttribute('data-theme', premium.id);
  } else if (dark) {
    html.setAttribute('data-theme', 'dark');
  } else {
    html.removeAttribute('data-theme');
  }
  const name = themeDisplayName(themeMode);
  const label = document.getElementById('theme-label');
  if (label) label.textContent = THEME_SHORT[themeMode] || name;
  const btn = document.getElementById('theme-toggle');
  if (btn) {
    btn.title = 'Elegir tema (actual: ' + name + ')';
    btn.setAttribute('aria-label', 'Elegir tema — actual: ' + name);
  }
  syncThemeMenu();
  applyAccent();   // los derivados del acento se recalculan contra la nueva paleta
}

(function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem('catflip-theme'); } catch (e) {}
  // Se respeta cualquier valor guardado (los ids premium se confirman
  // contra /premium/status justo después); sin clave → 'auto'.
  themeMode = saved || 'auto';
  applyTheme();
})();

// Acento guardado (o Naranja Eléctrico por defecto). Va después de
// initTheme para derivar contra la paleta ya aplicada.
(function initAccent() {
  let saved = null;
  try { saved = localStorage.getItem('catflip-accent'); } catch (e) {}
  activeAccent = normalizeHex(saved) || '#FF5414';
  applyAccent();
})();

// Licencia premium (Open Core): confirma/corrige el modo guardado y
// amplía el panel con los temas del manifiesto del servidor.
// Un id premium guardado sin licencia degrada a 'auto' aquí mismo.
async function initPremiumThemes() {
  let connectors = [];
  try {
    const res = await fetch('/premium/status');
    const data = await res.json();
    premiumThemes = (data.licensed && Array.isArray(data.themes)) ? data.themes : [];
    connectors = Array.isArray(data.connectors) ? data.connectors : [];
  } catch (e) { premiumThemes = []; }
  // Conectores reales: la sección «Destino real» solo existe con licencia
  // (el servidor además devuelve 404 en /connectors/* sin ella).
  const pgSection = document.getElementById('pg-section');
  if (pgSection) pgSection.hidden = connectors.length === 0;
  if (themeOrder().indexOf(themeMode) === -1) themeMode = 'auto';
  preloadPremiumCss();   // solo con licencia: la lista viene vacía sin ella
  buildThemeMenu();
  applyTheme();
}
initPremiumThemes();

// Aviso de versión nueva: el servidor compara la última release de
// GitHub con package.json y solo pinta el toast si hay algo más nuevo
// (sin red, con rate limit o tag ilegible responde checked=false y aquí
// no ocurre nada). Se lanza después del primer pintado para no competir
// con los avisos de carga; el enlace abre la release en pestaña nueva.
// La última versión DESCARTADA viaja como `?dismissed=` para que el
// servidor suprima el aviso hasta que haya algo más nuevo que ella.
const VERSION_DISMISS_KEY = 'catflip-version-dismissed';

async function checkNewVersion() {
  let dismissed = '';
  try { dismissed = localStorage.getItem(VERSION_DISMISS_KEY) || ''; } catch (e) {}
  let data;
  try {
    const qs = dismissed ? '?dismissed=' + encodeURIComponent(dismissed) : '';
    const res = await fetch('/version/check' + qs);
    if (!res.ok) return;
    data = await res.json();
  } catch (e) { return; }
  if (!data || !data.update_available || !data.html_url) return;
  const url = String(data.html_url);
  if (!/^https?:\/\//.test(url)) return;  // el enlace se abre en el navegador del usuario
  showVersionToast(String(data.latest || ''), url);
}
setTimeout(checkNewVersion, 2000);

// Toast propio con botón ×: cerrarlo DE VERDAD (no el auto-cierre a los
// 8 s) guarda la versión en localStorage — el aviso no vuelve a aparecer
// para esa versión, pero sí para una más nueva. El auto-cierre no
// descarta nada: si el usuario no decidió, la próxima carga vuelve a
// mostrarlo.
function showVersionToast(latest, url) {
  const t = document.createElement('div');
  t.className = 'toast info';
  t.innerHTML = '<span>' + icon('info') + '</span>' +
    '<span>Nueva versión ' + escapeHtml(latest) + ' disponible — ' +
    '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">ver release</a></span>';
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'toast-close';
  close.setAttribute('aria-label', 'Descartar este aviso de versión nueva');
  close.title = 'No volver a avisar con esta versión';
  close.innerHTML = icon('x');
  close.addEventListener('click', () => {
    try { localStorage.setItem(VERSION_DISMISS_KEY, latest); } catch (e) {}
    t.remove();
  });
  t.appendChild(close);
  document.getElementById('toast-container').appendChild(t);
  setTimeout(() => t.remove(), 8000);
}

// Cambios del sistema: solo re-aplican si el usuario no forzó claro/oscuro
if (schemeMQ) {
  const onSchemeChange = () => { if (themeMode === 'auto') applyTheme(); };
  if (schemeMQ.addEventListener) schemeMQ.addEventListener('change', onSchemeChange);
  else if (schemeMQ.addListener) schemeMQ.addListener(onSchemeChange); // Safari <14
}

function setThemeMode(id) {
  if (themeOrder().indexOf(id) === -1) return;
  themeMode = id;
  try { localStorage.setItem('catflip-theme', themeMode); } catch (e) {}
  applyTheme();
  closeThemeMenu(true);
}

// ── PANEL DE TEMA (lista con vista previa, agrupada Claro/Oscuro/Sistema) ─
// El panel es estático en el HTML (#theme-menu); aquí se construye su
// contenido y se gestiona apertura, teclado y foco.
function preloadPremiumCss() {
  premiumThemes.forEach(t => {
    const id = 'premium-preview-css-' + t.id;
    if (document.getElementById(id)) return;
    const link = document.createElement('link');
    link.id = id;
    link.rel = 'stylesheet';
    link.href = '/premium/themes/' + encodeURIComponent(t.id) + '.css';
    document.head.appendChild(link);
  });
}

function buildThemeMenu() {
  const menu = document.getElementById('theme-menu');
  if (!menu) return;
  menu.textContent = '';
  themeGroups().forEach(group => {
    const wrap = document.createElement('div');
    wrap.className = 'theme-menu-group';
    wrap.setAttribute('role', 'group');
    const title = document.createElement('span');
    title.className = 'theme-menu-title';
    title.id = 'theme-group-' + group.key;
    title.textContent = group.title;
    wrap.setAttribute('aria-labelledby', title.id);
    wrap.appendChild(title);

    group.items.forEach(item => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'theme-menu-item';
      btn.setAttribute('role', 'menuitemradio');
      btn.setAttribute('aria-checked', 'false');
      btn.tabIndex = -1;
      btn.dataset.themeId = item.id;

      const sw = document.createElement('span');
      sw.className = 'theme-swatch';
      sw.setAttribute('aria-hidden', 'true');
      ['sw-head', 'sw-line', 'sw-line sw-line-short', 'sw-pill'].forEach(cls => {
        const part = document.createElement('span');
        part.className = cls;
        sw.appendChild(part);
      });

      const name = document.createElement('span');
      name.className = 'theme-menu-name';
      name.textContent = item.name;

      // icon() devuelve cadena HTML → se materializa en un nodo suelto
      const holder = document.createElement('span');
      holder.innerHTML = icon('check');
      const check = holder.firstElementChild;
      check.setAttribute('class', 'icon-svg theme-menu-check');

      btn.appendChild(sw);
      btn.appendChild(name);
      btn.appendChild(check);
      btn.addEventListener('click', () => setThemeMode(item.id));
      wrap.appendChild(btn);
    });
    menu.appendChild(wrap);
  });

  // Sección «Color de énfasis» — catálogo orthogonal al tema (mismo menú,
  // mismas reglas de teclado: flechas/Home/End recorren también aquí).
  const accWrap = document.createElement('div');
  accWrap.className = 'theme-menu-group';
  accWrap.setAttribute('role', 'group');
  const accTitle = document.createElement('span');
  accTitle.className = 'theme-menu-title';
  accTitle.id = 'accent-group-title';
  accTitle.textContent = 'Color de énfasis';
  accWrap.setAttribute('aria-labelledby', accTitle.id);
  accWrap.appendChild(accTitle);

  const accRow = document.createElement('div');
  accRow.className = 'accent-row';
  ACCENTS.forEach(a => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'accent-swatch';
    btn.setAttribute('role', 'menuitemradio');
    btn.setAttribute('aria-checked', 'false');
    btn.setAttribute('aria-label', a.name);
    btn.title = a.name + ' — ' + a.hex;
    btn.dataset.accent = a.hex;
    btn.tabIndex = -1;
    const dotEl = document.createElement('span');
    dotEl.className = 'accent-swatch-dot';
    dotEl.setAttribute('aria-hidden', 'true');
    dotEl.style.background = a.hex;
    btn.appendChild(dotEl);
    btn.addEventListener('click', () => setAccent(a.hex));
    accRow.appendChild(btn);
  });
  accWrap.appendChild(accRow);

  const customWrap = document.createElement('div');
  customWrap.className = 'accent-custom-wrap';
  const customLabel = document.createElement('label');
  customLabel.className = 'accent-custom-label';
  customLabel.htmlFor = 'accent-custom';
  customLabel.textContent = 'Personalizado';

  // El <input type="color"> nativo no puede vivir dentro de role="menu"
  // (solo admite menuitem*): vive FUERA del panel — en <body>, invisible
  // pero renderizado — y el botón del menú lo abre con showPicker() (o
  // click() como respaldo). Misma UX, ARIA válido (axe wcag2a/aa).
  let custom = document.getElementById('accent-custom');
  if (!custom) {
    custom = document.createElement('input');
    custom.type = 'color';
    custom.id = 'accent-custom';
    custom.className = 'accent-native-picker';
    custom.title = 'Elegir un color de énfasis personalizado';
    custom.setAttribute('aria-hidden', 'true');
    custom.tabIndex = -1;
    custom.addEventListener('input', () => setAccent(custom.value));
    document.body.appendChild(custom);
  }
  custom.value = activeAccent;

  const customBtn = document.createElement('button');
  customBtn.type = 'button';
  customBtn.className = 'accent-custom';
  customBtn.setAttribute('role', 'menuitemradio');
  customBtn.setAttribute('aria-checked', 'false');
  customBtn.setAttribute('aria-label', 'Color de énfasis personalizado');
  customBtn.title = 'Elegir un color de énfasis personalizado';
  customBtn.tabIndex = -1;
  const customDot = document.createElement('span');
  customDot.className = 'accent-swatch-dot accent-custom-dot';
  customDot.setAttribute('aria-hidden', 'true');
  customDot.style.background = activeAccent;
  customBtn.appendChild(customDot);
  customBtn.addEventListener('click', () => {
    // showPicker() exige gesto del usuario → va dentro de este click.
    if (typeof custom.showPicker === 'function') {
      try { custom.showPicker(); return; } catch (e) { /* sin soporte → click */ }
    }
    custom.click();
  });

  const hexLabel = document.createElement('span');
  hexLabel.className = 'accent-hex';
  hexLabel.id = 'accent-hex-label';
  hexLabel.textContent = activeAccent;
  customWrap.appendChild(customLabel);
  customWrap.appendChild(customBtn);
  customWrap.appendChild(hexLabel);
  accWrap.appendChild(customWrap);
  menu.appendChild(accWrap);

  syncThemeMenu();
  syncAccentMenu();
}

// aria-checked + tabindex móvil (roving) + data-theme de cada swatch.
function syncThemeMenu() {
  const menu = document.getElementById('theme-menu');
  if (!menu) return;
  let active = null;
  const items = menu.querySelectorAll('.theme-menu-item');
  items.forEach(btn => {
    const on = btn.dataset.themeId === themeMode;
    btn.setAttribute('aria-checked', on ? 'true' : 'false');
    btn.tabIndex = on ? 0 : -1;
    if (on) active = btn;
    const sw = btn.querySelector('.theme-swatch');
    const attr = swatchThemeAttr(btn.dataset.themeId);
    if (sw) {
      if (attr) sw.setAttribute('data-theme', attr);
      else sw.removeAttribute('data-theme');
    }
  });
  if (!active && items.length) items[0].tabIndex = 0;
}

function positionThemeMenu() {
  const menu = document.getElementById('theme-menu');
  const btn = document.getElementById('theme-toggle');
  if (!menu || !btn) return;
  const r = btn.getBoundingClientRect();
  const width = menu.offsetWidth || 208;
  menu.style.top = (r.bottom + 6) + 'px';
  let left = r.right - width;
  const maxLeft = Math.max(8, window.innerWidth - width - 8);
  if (left > maxLeft) left = maxLeft;
  if (left < 8) left = 8;
  menu.style.left = left + 'px';
}

function openThemeMenu() {
  const menu = document.getElementById('theme-menu');
  const btn = document.getElementById('theme-toggle');
  if (!menu || !btn) return;
  themeMenuOpen = true;
  menu.hidden = false;
  btn.setAttribute('aria-expanded', 'true');
  syncThemeMenu();
  positionThemeMenu();
  const active = menu.querySelector('.theme-menu-item[aria-checked="true"]') ||
                 menu.querySelector('.theme-menu-item');
  if (active) active.focus();
}

function closeThemeMenu(refocus) {
  const menu = document.getElementById('theme-menu');
  const btn = document.getElementById('theme-toggle');
  if (!menu || !btn || !themeMenuOpen) return;
  themeMenuOpen = false;
  menu.hidden = true;
  btn.setAttribute('aria-expanded', 'false');
  if (refocus) btn.focus();
}

function toggleThemeMenu() {
  if (themeMenuOpen) closeThemeMenu(false);
  else openThemeMenu();
}

// Teclado del panel: flechas recorren las opciones de TODOS los grupos,
// Home/End saltan a los extremos, Escape cierra y devuelve el foco al
// botón, Tab cierra (el foco sigue su curso natural).
document.addEventListener('keydown', e => {
  if (!themeMenuOpen) return;
  const menu = document.getElementById('theme-menu');
  if (!menu) return;
  const items = Array.prototype.slice.call(menu.querySelectorAll('.theme-menu-item, .accent-swatch, .accent-custom'));
  if (!items.length) return;
  const i = items.indexOf(document.activeElement);
  if (e.key === 'Escape') {
    e.preventDefault();
    closeThemeMenu(true);
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    items[(i + 1) % items.length].focus();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    items[(i - 1 + items.length) % items.length].focus();
  } else if (e.key === 'Home') {
    e.preventDefault();
    items[0].focus();
  } else if (e.key === 'End') {
    e.preventDefault();
    items[items.length - 1].focus();
  } else if (e.key === 'Tab') {
    closeThemeMenu(false);
  }
});

// Clic fuera del panel o del botón → cierra (el propio clic del botón ya
// alternó antes de burbujear hasta aquí).
document.addEventListener('click', e => {
  if (!themeMenuOpen) return;
  const t = e.target;
  if (t && typeof t.closest === 'function' && t.closest('#theme-menu, #theme-toggle')) return;
  closeThemeMenu(false);
});

window.addEventListener('resize', () => { if (themeMenuOpen) positionThemeMenu(); });

// ── CANVAS MATEMÁTICO DE FONDO (grid isométrico ondulante, Tech Labs) ───
// Firma visual del prototipo: malla 28×20 en proyección isométrica con onda
// armónica, repulsión al ratón y tinte del color de énfasis activo. Con
// prefers-reduced-motion se pinta UNA vez estático (sin rAF, sin ratón).
const mathCanvas = document.getElementById('math-grid-bg');
const mathCtx = mathCanvas ? mathCanvas.getContext('2d') : null;
const MCOLS = 28;
const MROWS = 20;
const motionMQ = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
let mathMouse = { x: -9999, y: -9999, tx: -9999, ty: -9999 };
let mathW = 0;
let mathH = 0;
let mathPhase = 0;
let mathRaf = null;

function mathReduced() { return !!(motionMQ && motionMQ.matches); }

function resizeMathGrid() {
  if (!mathCtx) return;
  mathW = window.innerWidth;
  mathH = window.innerHeight;
  // setTransform (no scale) — reiniciar el bitmap ya limpia la transformación
  mathCanvas.width = mathW * window.devicePixelRatio;
  mathCanvas.height = mathH * window.devicePixelRatio;
  mathCtx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
}

function drawMathGrid() {
  if (!mathCtx) return;
  if (mathReduced()) { drawStaticMathGrid(); return; }

  mathMouse.x += (mathMouse.tx - mathMouse.x) * 0.08;
  mathMouse.y += (mathMouse.ty - mathMouse.y) * 0.08;
  mathCtx.clearRect(0, 0, mathW, mathH);

  const rgb = hexToRgb(activeAccent);
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  mathPhase += 0.022;

  const originX = mathW * 0.5;
  const originY = mathH * 0.48;
  const cellW = Math.max(34, mathW / (MCOLS * 0.9));
  const cellH = cellW * 0.52;

  const points = [];
  for (let r = 0; r < MROWS; r++) {
    points[r] = [];
    for (let c = 0; c < MCOLS; c++) {
      const u = c - MCOLS / 2;
      const v = r - MROWS / 2;
      const screenX = originX + (u - v) * cellW * 0.5;
      const screenY = originY + (u + v) * cellH * 0.5;
      const dist = Math.sqrt(u * u + v * v);
      const wave = Math.sin(dist * 0.45 - mathPhase) * 16 +
                   Math.cos(u * 0.35 + mathPhase * 0.7) * 8;
      const dx = screenX - mathMouse.x;
      const dy = (screenY + wave) - mathMouse.y;
      const distMouse = Math.sqrt(dx * dx + dy * dy);
      let push = 0;
      if (distMouse < 260) push = Math.sin((1 - distMouse / 260) * Math.PI) * -22;
      points[r][c] = {
        x: screenX,
        y: screenY + wave + push,
        intensity: Math.max(0, 1 - dist / (MCOLS * 0.65)),
      };
    }
  }

  const baseAlpha = isDark ? 0.22 : 0.16;
  mathCtx.lineWidth = 1;
  for (let r = 0; r < MROWS; r++) {
    for (let c = 0; c < MCOLS; c++) {
      const p = points[r][c];
      if (c < MCOLS - 1) {
        const pr = points[r][c + 1];
        const a = (((p.intensity + pr.intensity) * 0.5) * baseAlpha).toFixed(3);
        mathCtx.strokeStyle = 'rgba(' + rgb.r + ', ' + rgb.g + ', ' + rgb.b + ', ' + a + ')';
        mathCtx.beginPath();
        mathCtx.moveTo(p.x, p.y);
        mathCtx.lineTo(pr.x, pr.y);
        mathCtx.stroke();
      }
      if (r < MROWS - 1) {
        const pd = points[r + 1][c];
        const a = (((p.intensity + pd.intensity) * 0.5) * baseAlpha).toFixed(3);
        mathCtx.strokeStyle = 'rgba(' + rgb.r + ', ' + rgb.g + ', ' + rgb.b + ', ' + a + ')';
        mathCtx.beginPath();
        mathCtx.moveTo(p.x, p.y);
        mathCtx.lineTo(pd.x, pd.y);
        mathCtx.stroke();
      }
      if (r % 2 === 0 && c % 2 === 0 && p.intensity > 0.1) {
        const a = (p.intensity * (isDark ? 0.6 : 0.4)).toFixed(3);
        mathCtx.fillStyle = 'rgba(' + rgb.r + ', ' + rgb.g + ', ' + rgb.b + ', ' + a + ')';
        mathCtx.beginPath();
        mathCtx.arc(p.x, p.y, 1.6, 0, Math.PI * 2);
        mathCtx.fill();
      }
    }
  }
  mathRaf = requestAnimationFrame(drawMathGrid);
}

function drawStaticMathGrid() {
  if (!mathCtx) return;
  mathCtx.clearRect(0, 0, mathW, mathH);
  const rgb = hexToRgb(activeAccent);
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const alpha = isDark ? 0.15 : 0.12;
  const originX = mathW * 0.5;
  const originY = mathH * 0.5;
  const cellW = Math.max(34, mathW / (MCOLS * 0.9));
  const cellH = cellW * 0.52;
  mathCtx.lineWidth = 1;
  mathCtx.strokeStyle = 'rgba(' + rgb.r + ', ' + rgb.g + ', ' + rgb.b + ', ' + alpha + ')';
  for (let r = 0; r < MROWS; r++) {
    for (let c = 0; c < MCOLS; c++) {
      const u = c - MCOLS / 2;
      const v = r - MROWS / 2;
      const x = originX + (u - v) * cellW * 0.5;
      const y = originY + (u + v) * cellH * 0.5;
      if (c < MCOLS - 1) {
        mathCtx.beginPath();
        mathCtx.moveTo(x, y);
        mathCtx.lineTo(originX + (u + 1 - v) * cellW * 0.5, originY + (u + 1 + v) * cellH * 0.5);
        mathCtx.stroke();
      }
      if (r < MROWS - 1) {
        const vNext = (r + 1) - MROWS / 2;
        mathCtx.beginPath();
        mathCtx.moveTo(x, y);
        mathCtx.lineTo(originX + (u - vNext) * cellW * 0.5, originY + (u + vNext) * cellH * 0.5);
        mathCtx.stroke();
      }
    }
  }
}

function initMathGrid() {
  if (!mathCtx) return;
  resizeMathGrid();
  if (mathReduced()) { drawStaticMathGrid(); return; }
  mathRaf = requestAnimationFrame(drawMathGrid);
}

window.addEventListener('resize', () => {
  resizeMathGrid();
  if (mathReduced()) drawStaticMathGrid();
});
window.addEventListener('mousemove', e => {
  mathMouse.tx = e.clientX;
  mathMouse.ty = e.clientY;
});
if (motionMQ) {
  const onMotionChange = () => {
    if (mathReduced()) {
      if (mathRaf) cancelAnimationFrame(mathRaf);
      mathRaf = null;
      drawStaticMathGrid();
    } else if (!mathRaf && mathCtx) {
      mathRaf = requestAnimationFrame(drawMathGrid);
    }
  };
  if (motionMQ.addEventListener) motionMQ.addEventListener('change', onMotionChange);
  else if (motionMQ.addListener) motionMQ.addListener(onMotionChange);
}
initMathGrid();

function icon(name) {
  const paths = {
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>',
    'move-vertical': '<path d="m21 16-4 4-4-4"/><path d="M17 20V4"/><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/>',
    'move-horizontal': '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
    scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" x2="8.12" y1="4" y2="15.88"/><line x1="14.47" x2="20" y1="14.48" y2="20"/><line x1="8.12" x2="12" y1="8.12" y2="12"/>',
    filter: '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    sparkles: '<path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>',
    'trash-2': '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>',
    pencil: '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    eraser: '<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21"/><path d="M22 21H7"/><path d="m5 11 9 9"/>',
    'case-sensitive': '<path d="m3 15 4-8 4 8"/><path d="M4 13h6"/><circle cx="18" cy="12" r="3"/><path d="M21 9v6"/>',
    'refresh-cw': '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    tag: '<path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r=".5" fill="currentColor"/>',
    'arrow-down-wide-narrow': '<path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="M11 4h10"/><path d="M11 8h7"/><path d="M11 12h4"/>',
    'arrow-down-to-line': '<path d="M12 17V3"/><path d="m6 11 6 6 6-6"/><path d="M19 21H5"/>',
    pin: '<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>',
    check: '<polyline points="20 6 9 17 4 12"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    'triangle-alert': '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>',
    'undo-2': '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
    'redo-2': '<path d="m15 14 5-5-5-5"/><path d="M4 20v-7a4 4 0 0 1 4-4h12"/>',
    'more-vertical': '<circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="19" r="1.5"/>',
    layers: '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
    'git-merge': '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/>',
    'git-compare': '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><path d="M11 18H8a2 2 0 0 1-2-2V9"/>',
    calculator: '<rect width="16" height="20" x="4" y="2" rx="2"/><line x1="8" x2="16" y1="6" y2="6"/><line x1="16" x2="16" y1="14" y2="18"/><path d="M16 10h.01"/><path d="M12 10h.01"/><path d="M8 10h.01"/><path d="M12 14h.01"/><path d="M8 14h.01"/><path d="M12 18h.01"/><path d="M8 18h.01"/>',
    'eye-off': '<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/><path d="m2 2 20 20"/>',
    text: '<path d="M17 6.1H3"/><path d="M21 12.1H3"/><path d="M15.1 18H3"/>',
    activity: '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
    shuffle: '<polygon points="16 3 21 3 21 8"/><line x1="4" x2="21" y1="20" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" x2="21" y1="15" y2="21"/><line x1="4" x2="9" y1="4" y2="9"/>',
    'list-ordered': '<path d="M11 6h9"/><path d="M11 12h9"/><path d="M11 18h9"/><path d="M4 4.5 3 5.5V9"/><path d="M2.5 9h3"/><path d="M3.5 13.75a1.5 1.5 0 1 1 2.5 1.25L3.5 18h3"/>',
  };
  return '<svg class="icon-svg" viewBox="0 0 24 24">' + (paths[name] || '') + '</svg>';
}

// Sincronizar layout al cargar (el tema ya se aplicó en initTheme al
// cargar este script — mismo punto que antes, sin flash adicional)
document.addEventListener('DOMContentLoaded', () => {
  applyPanelClasses();
  updateColVisBadge();
  buildThemeMenu();   // núcleo (Claro/Oscuro/Sistema) antes de /premium/status
});

// ── PANELES COLAPSABLES (F2.3) ──────────────────────────────────────────
let panelState = { left: false, right: false };
try {
  const savedPanels = JSON.parse(localStorage.getItem('catflip-panels') || '{}');
  if (savedPanels.left) panelState.left = true;
  if (savedPanels.right) panelState.right = true;
} catch(e) {}

function applyPanelClasses() {
  const layout = document.getElementById('layout');
  const panelL = document.getElementById('panel-left');
  const panelR = document.getElementById('panel-right');
  const badgeExp = document.getElementById('badge-expanded');
  if (!layout) return;

  if (panelL) panelL.classList.toggle('collapsed', !!panelState.left);
  if (panelR) panelR.classList.toggle('collapsed', !!panelState.right);

  layout.classList.remove('left-collapsed', 'right-collapsed', 'both-collapsed');
  if (panelState.left && panelState.right) layout.classList.add('both-collapsed');
  else if (panelState.left) layout.classList.add('left-collapsed');
  else if (panelState.right) layout.classList.add('right-collapsed');

  if (badgeExp) {
    badgeExp.classList.toggle('visible', !!(panelState.left || panelState.right));
  }
}

function togglePanel(side) {
  if (side === 'left') panelState.left = !panelState.left;
  if (side === 'right') panelState.right = !panelState.right;
  localStorage.setItem('catflip-panels', JSON.stringify(panelState));
  applyPanelClasses();
}

document.addEventListener('keydown', e => {
  if (e.key==='Escape') {
    closeModal();
    closeColVisModal();
    closeColMenu();
    closeDatasetPicker();
    closeExecPipe();
    closeStepDiff();
    closeCsvRecipe();
    closeConnector();
    closeSchemaRules();
  }
  if ((e.ctrlKey||e.metaKey) && (e.key==='z' || e.key==='Z')) {
    e.preventDefault();
    if (e.shiftKey) redo(); else undo();
  }
  if ((e.ctrlKey||e.metaKey) && (e.key==='y' || e.key==='Y')) { e.preventDefault(); redo(); }
  if (e.key==='Enter') {
    if (document.getElementById('modal-overlay').classList.contains('open')) confirmModal();
    if (document.getElementById('colvis-overlay').classList.contains('open')) applyColVis();
  }
});

// Los listeners del menú contextual viven en grid.js (junto a closeColMenu),
// porque app.js carga antes que grid.js (orden de scripts en index.html).
