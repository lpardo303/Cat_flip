# 🤝 Contribuir a Cat_flip

¡Gracias por tu interés en mejorar Cat_flip! Este documento recoge el flujo
real de desarrollo del proyecto para que cualquier contribución encaje a la
primera. El apoyo financiero (Ko-fi / GitHub Sponsors) es opcional y no
condiciona nada: **el core es y seguirá siendo MIT**.

## 🧰 Requisitos

- **Python 3.10+**
- **Node.js 18+** (solo para el gate de accesibilidad)
- **Git**

## 🚀 Puesta en marcha

```bash
git clone https://github.com/lpardo303/Cat_flip.git
cd Cat_flip
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# Solo si vas a correr el gate de axe:
npm ci && npx playwright install chromium

CATFLIP_PREMIUM_KEY=local python app.py   # http://127.0.0.1:5050
# (la key solo la necesita el gate de axe, para cubrir las paletas premium)
```

## 🔄 Flujo de trabajo

1. Crea una rama desde `main` con un nombre descriptivo (`f-…` para
   features, `fix-…` para arreglos).
2. Haz cambios pequeños y atómicos. Mantén sincronizadas las docs que
   toques: `manual_de_usuario.md`, `README.md` y una entrada nueva en la
   sección **Sin publicar** de `CHANGELOG.md`.
3. Verifica **antes** de abrir el PR — la CI repite exactamente esto:

   ```bash
   # 1) Suite completa + gate de cobertura (93% mínimo)
   .venv/bin/python -m pytest tests/ --cov=app --cov=operations --cov=cli \
     --cov-report=term-missing --cov-fail-under=93

   # 2) Sintaxis de los 5 módulos JS del frontend
   node --check static/js/app.js
   node --check static/js/state.js
   node --check static/js/grid.js
   node --check static/js/api.js
   node --check static/js/modals.js

   # 3) Gate de accesibilidad (con la app corriendo en 127.0.0.1:5050)
   npm run test:axe                 # 15 corridas: 0 violaciones y 0 fallos
   # (el servidor debe correr con CATFLIP_PREMIUM_KEY; sin ella el gate
   #  falla: no se omiten las superficies premium en silencio)
   ```

4. Abre un PR contra `main`. Los jobs de CI (`test` y `axe`) deben estar
   en verde; `main` está protegida (1 review aprobatoria + checks de estado).

## 🧪 Convenciones de código

- **Operaciones de backend** (`operations.py`): copia del DataFrame →
  transformación → códigos de receta. Los mensajes de error van en español
  y citan la columna o el paso exacto.
- **Estado global** (`app.py`): si añades estado nuevo, acuérdate del reset
  en `/upload` y del equivalente en `tests/conftest.py` — cada test debe
  arrancar con el estado limpio.
- **Diseño**: solo design tokens de `static/css/tokens.css` — **sin colores
  hex sueltos** en componentes; las variantes de color se construyen con
  `color-mix()` sobre tokens. Contraste AA verificado en los dos temas.
- **Accesibilidad**: axe debe terminar en 0 sobre las 15 corridas
  (6 superficies × claro/oscuro — incluido el selector de tema abierto —
  + la página en modo Automático con el sistema en oscuro + las 2 paletas
  premium Aurora/Solar). Teclado completo, `aria` coherente y foco visible.
- **Tests**: toda feature nueva lleva sus tests; nunca bajes el gate de
  cobertura (93%). Los fixtures de `tests/conftest.py` resetean el estado.
  Las features de `premium/` se prueban en ambos estados (licenciado y
  no) con `monkeypatch` de `CATFLIP_PREMIUM_KEY`.
- **Commits**: mensaje en español que explique el *porqué*, no solo el qué.

## 📄 Licencia

Al contribuir aceptas que tu aporte se distribuya bajo la licencia
[MIT](LICENSE) del proyecto.
