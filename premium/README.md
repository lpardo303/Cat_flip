# 📦 Cat_flip Premium (Open Core)

El core de Cat_flip es **MIT** y siempre lo será: sin licencia la app es
idéntica, sin telemetría ni funciones de pago. Este paquete concentra las
mejoras *premium* del modelo Open Core — solo se sirven cuando la
instalación está licenciada.

## Activación

La licencia se activa con **cualquiera** de estas dos señales:

```bash
# 1) Variable de entorno (ideal para CI y packaging)
CATFLIP_PREMIUM_KEY=tu-clave python app.py

# 2) Fichero premium.key junto a este paquete (una vez, queda fija)
echo "tu-clave" > premium/premium.key   # premium.key está en .gitignore
```

El gating vive en el servidor: `/premium/status` devuelve `themes: []` y
`/premium/themes/<id>.css` responde **404** sin licencia. El front nunca
recibe CSS premium que no deba ver.

## Qué hay dentro ahora

| Feature | Estado |
| --- | --- |
| Temas visuales **Aurora** (violeta) y **Solar** (ámbar) | ✅ |
| Packaging firmado (Flatpak + AppImage + `.exe`) | ⏳ roadmap |
| Auto-update integrado | ⏳ roadmap |
| Conectores reales (Postgres / S3 / BigQuery) | ⏳ roadmap |

Con licencia, el botón de tema del encabezado amplía su ciclo:
**Claro → Oscuro → Automático → Aurora → Solar → Claro**.

## Cómo añadir un feature premium nuevo

1. Crea el módulo/carpeta dentro de `premium/`.
2. Regístralo en `THEMES` (temas) o expórtalo desde `premium/__init__.py`.
3. Sírvelo desde un endpoint de `app.py` que empiece comprobando
   `premium.is_licensed()` — nunca expongas el recurso sin esa comprobación.
4. Añade tests en `tests/test_premium.py` con `monkeypatch` de
   `CATFLIP_PREMIUM_KEY` (ambos estados: licenciado y no licenciado).
5. Documenta el feature en README, manual, CHANGELOG y bitácora.

## Licencia del paquete

Estos archivos **no** son MIT: caen bajo [LICENSE-PREMIUM.txt](../LICENSE-PREMIUM.txt)
(licencia comercial para uso empresarial embebido). El resto del
repositorio sigue el [LICENSE](../LICENSE) MIT.
