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

4. Abre un PR contra `main`. Los jobs de CI (`test`, `pg-smoke`,
   `s3-smoke` y `axe`) deben estar en verde; `main` está protegida
   (1 review aprobatoria + checks de estado).

## 🐘 Smoke real de conectores (Postgres y S3)

La CI levanta dos servidores de verdad y ejecuta los conectores contra
ellos (jobs `pg-smoke` y `s3-smoke`). Esos tests **se saltan sin su
variable de entorno**, así que la suite normal no necesita nada de esto:

| Job | Contenedor | Variable que lo activa | Fichero |
| --- | --- | --- | --- |
| `pg-smoke` | `postgres:16` | `CATFLIP_PG_SMOKE=1` | `tests/test_connectors_postgres_live.py` |
| `s3-smoke` | `localstack/localstack:4.13.1` | `CATFLIP_S3_SMOKE=1` | `tests/test_connectors_s3_live.py` |

Solo hacen falta un motor de contenedores (podman o docker) y los
drivers opcionales:

```bash
pip install -r requirements-connectors.txt
```

**Atajo**: `scripts/smoke.sh` hace todo lo de esta sección en un comando
— levanta los contenededores, espera a que estén sanos, ejecuta los dos
smokes y los **limpia siempre** (también si un test falla o cortas con
Ctrl+C):

```bash
scripts/smoke.sh            # ambos
scripts/smoke.sh --pg       # solo Postgres
scripts/smoke.sh --s3       # solo S3
scripts/smoke.sh --help     # variables que acepta
```

Los pasos manuales, por si prefieres tener los contenededores a mano:

**Postgres:**

```bash
podman run -d --name catflip-pg-test \
  -e POSTGRES_USER=catflip -e POSTGRES_PASSWORD=smoke_pg_2026 \
  -e POSTGRES_DB=catflip_smoke -p 5432:5432 postgres:16

CATFLIP_PG_SMOKE=1 .venv/bin/python -m pytest \
  tests/test_connectors_postgres_live.py -v

podman rm -f catflip-pg-test      # al terminar
```

Credenciales y destino por defecto, sobrescribibles con
`CATFLIP_PG_HOST`, `CATFLIP_PG_PORT`, `CATFLIP_PG_DB`, `CATFLIP_PG_USER`
y `CATFLIP_PG_PASSWORD`: usuario `catflip`, contraseña `smoke_pg_2026`,
base `catflip_smoke` en `127.0.0.1:5432`.

**S3** — LocalStack, porque MinIO dejó de distribuirse en 2026 y su tag
`latest` exige `LOCALSTACK_AUTH_TOKEN` (por eso va pineado a `4.13.1`):

```bash
podman run -d --name catflip-s3-test -p 4566:4566 \
  localstack/localstack:4.13.1

CATFLIP_S3_SMOKE=1 .venv/bin/python -m pytest \
  tests/test_connectors_s3_live.py -v

podman rm -f catflip-s3-test      # al terminar
```

Endpoint y credenciales por defecto, sobrescribibles con
`CATFLIP_S3_ENDPOINT`, `CATFLIP_S3_REGION`, `CATFLIP_S3_BUCKET`,
`CATFLIP_S3_ACCESS_KEY` y `CATFLIP_S3_SECRET_KEY`: `http://127.0.0.1:4566`,
`us-east-1`, bucket `catflip-smoke`, `test`/`test` (el bucket lo crea el
propio test, el conector solo hace `head`). LocalStack tarda unos
segundos en estar listo; si falla la primera conexión, repite.

Qué comprueba cada smoke: la conexión real (`SELECT version()` / 
`head_bucket`), el DDL derivado de los dtypes leído de
`information_schema`, la subida y relectura del CSV (prefijo y bytes),
`fail` frente a `overwrite`, nulos reales, el rollback de una transacción
a mitad de lote y que ninguna credencial se refleje en un mensaje de
error.

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
