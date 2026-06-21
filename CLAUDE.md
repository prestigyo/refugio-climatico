# refugio-climatico — contexto del proyecto para Claude Code

## Qué es esto

Sistema automatizado que descarga datos meteorológicos de AEMET y los analiza para identificar **refugios climáticos nocturnos** en España — pueblos donde se sigue durmiendo bien en verano. La pieza pública es una calculadora web (GitHub Pages) donde cualquier persona puede meter su pueblo y ver sus métricas.

Objetivo a corto plazo: **lanzamiento mediático**. La audiencia son periodistas españoles.

## Estructura del repo

```
refugio-climatico/
├── .github/workflows/        # Workflows de GitHub Actions
│   ├── main.yml              # Descarga diaria (10:30 UTC)
│   ├── backfill.yml          # Backfill histórico manual
│   ├── normales.yml          # Descarga única de valores normales 1991-2020
│   └── analisis.yml          # Análisis mensual + manual
├── aemet-temperaturas/       # TODO el proyecto vive aquí (no en raíz)
│   ├── scripts/              # Scripts Python
│   ├── datos/                # CSVs (no commitear si crecen mucho)
│   ├── images/               # Mapas PNG diarios de AEMET
│   └── analisis/             # Outputs de los análisis
└── docs/                     # GitHub Pages sirve esta carpeta
    └── index.html            # Calculadora pública (autogenerada)
```

**Crítico**: el proyecto está **bajo `aemet-temperaturas/`**, no en raíz. Pero `docs/` SÍ está en raíz (GitHub Pages exige `/docs` o `/` a nivel de repo, no de subcarpeta).

## Flujo de datos

1. `descarga_aemet.py` — scraper de los mapas PNG diarios (máximas y mínimas, península + canarias)
2. `descarga_datos.py` — API OpenData de AEMET, datos diarios de ~750 estaciones (limite 14 días por petición)
3. `backfill_historico.py` — backfill por año en chunks de 14 días, idempotente
4. `analisis_*.py` — análisis varios (refugios diurnos, nocturnos, peor noche, comparativas)
5. `generar_calculadora.py` — regenera `docs/index.html` a partir de los CSVs

Los outputs se commitean automáticamente al repo (los workflows tienen permiso de escritura).

## Convenciones del proyecto

- **Idioma**: español. Todos los nombres de variables, comentarios, mensajes de log y outputs en español.
- **Reproducibilidad**: todo lo publicado tiene que ser regenerable ejecutando un script del repo. NO archivos estáticos one-off entregados manualmente.
- **Estilo de plots**: paleta cálida (papel/teja/teal), tipografías Fraunces + Lora cuando se generan informes HTML; matplotlib por defecto en análisis técnicos.
- **Idempotencia**: scripts pensados para re-ejecutarse sin romper nada. Los workflows hacen `git commit` solo si hay cambios reales.
- **Métricas honestas**: para identificar refugios no usamos medias (esconden picos). Usamos P95 de Tmin de verano, racha máxima consecutiva de noches tropicales, y conteos por umbral.

## Gotchas aprendidos a las malas

- **AEMET bloquea User-Agents personalizados con 403**. Usar UA de Chrome real en los scrapers.
- **API OpenData "todasestaciones": máximo 15 días por petición**. De ahí el chunking de 14 días.
- **Decimales con coma y encoding ISO-8859-15** en los CSVs de AEMET.
- **Bash NO admite ñ en nombres de variables** (exit 127). En workflows usar `ANIO` no `AÑO`.
- **pandas devuelve int como float en groupby**. Cast explícito a `int()` antes de usar `:d` en f-strings.
- **matplotlib boxplot**: `labels=` está deprecated, usar `tick_labels=`.
- **GitHub Pages** sirve desde `<repo>/docs/` o `<repo>/` solo, no desde subcarpetas anidadas.
- **Permisos de workflow**: Settings → Actions → General → "Read and write permissions" tiene que estar activado para que los workflows puedan commitear.
- **Las normales 1991-2020 se descargaron** pero el cruce salió con `tmax_normal_verano` vacío — bug pendiente.

## Stack técnico

- **Python 3.11+** con `pandas`, `numpy`, `matplotlib`, `requests`, `Pillow` (para GIFs/composiciones).
- **GitHub Actions** (sin servidor propio). Secret: `AEMET_API_KEY`.
- **No hay tests** todavía. Sería bienvenido tenerlos para los parsers de fechas y conversión DMS→decimal.

## Datos disponibles

- 10 años de datos diarios (2017-2026), ~2 millones de registros
- `datos/diarios_YYYY.csv` (uno por año, ~25 MB cada uno)
- `datos/diarios_estaciones.csv` (rolling de los últimos 14 días)
- `datos/estaciones.csv` (catálogo: indicativo, nombre, provincia, lat/lon en formato DMS, altitud)
- `datos/normales_1991_2020.csv` (valores normales por estación)

## Hallazgos clave del análisis hasta ahora

- Los **refugios nocturnos garantizados** son pueblos de montaña interior 600-1500m, climas continentales secos: Sanabria, Puerto del Pico, Rascafría, Benasque, Vall de Boí, Beariz, Reinosa, Isaba...
- La **costa mediterránea** es de los PEORES sitios de España para dormir en verano: Palma, Cartagena, Capdepera con rachas de **86 noches tropicales consecutivas**.
- El **interior de Gran Canaria** (Tejeda, San Bartolomé de Tirajana) es el peor sitio de España para dormir, peor que la costa andaluza, por efecto foehn.
- **Alcalá de la Selva** (Teruel, sierra de Gúdar) tiene **0.5 noches tropicales/año** vs **72/año** en Valencia capital. Ratio 180:1.
- **Empíricamente verificado**: los incendios forestales NO calientan los termómetros a >5-20km del foco. La causalidad es calor→fuego, no al revés (caso Sierra de la Culebra 2022).

## Estado actual y próximas tareas

**Hecho:**
- Pipeline diario funcionando
- Backfill de 10 años
- Análisis "peor noche" con P95 y rachas
- Estudio de caso Alcalá de la Selva
- Informe HTML editorial (autocontenido)
- Script `generar_calculadora.py` que genera `docs/index.html`

**Pendiente para el lanzamiento mediático:**
- Activar GitHub Pages (Settings → Pages → branch main, folder `/docs`)
- Generar press kit PDF de 2 páginas
- Lista de ~20-25 periodistas españoles (clima/medio ambiente, nacionales + regionales)
- Email pitch template
- Plan de lanzamiento coordinado

**Ideas para más adelante:**
- Estudio sistemático "huella térmica de incendios" cruzando EFFIS (Copernicus) con AEMET
- Más años de backfill si interesa serie larga
- Análisis comparativo con normales 1991-2020 (anomalías vs clima histórico)
- Extensión a otros países europeos vía MeteoStat o Copernicus

## Comandos útiles

```bash
# Generar la calculadora localmente
cd aemet-temperaturas
python scripts/generar_calculadora.py
# Output: ../docs/index.html

# Backfill un año
python scripts/backfill_historico.py --anio 2025

# Análisis "peor noche"
python scripts/analisis_peor_noche.py

# Ver el HTML generado
open ../docs/index.html  # macOS
xdg-open ../docs/index.html  # Linux
```

## Cómo trabajar conmigo (Claude Code)

- **No tocar `docs/index.html` a mano** — siempre se regenera por script.
- **No commitear datos personales** (claves API): solo `AEMET_API_KEY` como secret de GitHub.
- **Antes de añadir un análisis nuevo**: comprobar que las métricas no se solapan con las existentes; preferir extender un script existente a crear uno nuevo.
- **Cuando hagamos cambios en los workflows**: probar con `workflow_dispatch` manual antes de fiar de la ejecución diaria.
- **Si una decisión técnica es controvertida** (e.g., cambiar de matplotlib a plotly): preguntar antes de migrar.
