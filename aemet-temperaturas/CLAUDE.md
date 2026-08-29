# refugio-climatico — contexto del proyecto para Claude Code

> Última revisión: 2026-08-09. Este fichero no se actualiza solo: si cambias la
> estructura, añades un workflow o publicas una sección nueva, actualízalo en el
> mismo commit.

## Qué es esto

Sistema automatizado que descarga datos meteorológicos de AEMET y los analiza para identificar **refugios climáticos nocturnos** en España — pueblos donde se sigue durmiendo bien en verano.

Lo público ya **no** es solo una calculadora: es un sitio entero, **https://nochetropical.es** (GitHub Pages sirviendo `docs/`, dominio propio vía `docs/CNAME`), con reportaje scrollytelling, calculadora, 52 landings provinciales, mapa interactivo de ~848 estaciones, un parte diario que se autopublica en X, certificados para ayuntamientos y varias landings temáticas.

Objetivo a corto plazo: **lanzamiento mediático**. La audiencia son periodistas españoles.

## Estructura del repo

```
refugio-climatico/
├── .github/workflows/        # 10 workflows (ver tabla abajo)
├── aemet-temperaturas/       # TODO el pipeline vive aquí (no en raíz)
│   ├── scripts/              # Scripts Python (+ apps_script_observatorio.gs)
│   ├── datos/                # CSVs de AEMET y auxiliares (~217 MB, versionados)
│   ├── images/               # Mapas PNG diarios de AEMET (~16 MB)
│   ├── img/ y fotos/         # Imágenes de artículos (originales → webp/jpg)
│   ├── analisis/             # Outputs de los análisis (rankings, PNGs, informes)
│   ├── metadata.csv          # Registro de cada mapa descargado (fecha, hash, estado)
│   └── requirements.txt
└── docs/                     # GitHub Pages sirve esta carpeta. TODO autogenerado.
```

**Crítico**: el pipeline está **bajo `aemet-temperaturas/`**, pero `docs/` está en la **raíz** (GitHub Pages solo admite `/docs` o `/` a nivel de repo, no subcarpetas anidadas).

### Restos que hay en la raíz y no deberían estar

`descarga_aemet.py` (copia idéntica de `aemet-temperaturas/scripts/descarga_aemet.py`), `descarga-diaria.yml` (workflow viejo, fuera de `.github/`, ya reemplazado por `main.yml`), `sitemap.xml` (distinto del bueno, que es `docs/sitemap.xml`) y `googlec4a9496b93a0dbfb.html` (verificación de Search Console; en la raíz del repo no la sirve nadie, tendría que estar en `docs/`). No los uses como fuente de verdad.

## docs/ — qué genera qué

**Ningún fichero de `docs/` se edita a mano.** Todo sale de un script:

| Script | Qué escribe en `docs/` |
|---|---|
| `generar_calculadora.py` (9.300 líneas, el núcleo) | `index.html` (reportaje + calculadora), las **52 landings de provincia**, `ranking-noches-tropicales/`, `prensa/`, `metodologia/`, `confortometro/`, `observatorio-del-descanso/`, `ola-de-calor/`, `la-espana-que-nunca-se-colorea/`, `refugios-climaticos-naturales-cerca-de-mi/`, `refugios-y-espana-vaciada/`, `hoteles-refugio-climatico/`, `tu-hotel/`, `tu-pueblo/`, `dormir-con-calor/`, `dormir-con-manta-en-verano/`, `vacaciones-sin-calor/`, `informes/`, `estudios/`, `en/` (versión inglesa), `badges/`, `sitemap.xml`, `robots.txt`, `favicon.svg`, `.nojekyll`, `CNAME` |
| `generar_pagina_mapa.py` | `mapa-estaciones/index.html` — mapa interactivo, provincias y puntos proyectados en Python con la misma `project()`, sin librerías JS |
| `generar_gif.py` | `ola-minimas.gif`, `ola-maximas.gif`, `ola-dia-noche.gif`, `ola-canarias-minimas.gif`, `og.png` |
| `estudio_colores.py` | `estudios/*.png` + `estudios/estudio-datos.json` |
| `generar_certificados.py` | `certificados/certificado-<slug>.png` (25 diplomas para ayuntamientos) |
| `generar_calendario_datos.py` | `datos/<slug-provincia>.json` (calendario de calor que carga la calculadora bajo demanda) |
| `parte_nocturno.py` | `parte/index.html`, `parte/parte.txt`, `parte/parte.json` |

**`generar_calculadora.py` es además un módulo compartido**: varios scripts hacen `import generar_calculadora as g` para reutilizar `PROVINCIAS`, `slug()`, `RANKING_CSV`, `DOCS_DIR` (lo hacen `generar_certificados.py`, `generar_calendario_datos.py`, `generar_informe_lead.py`, `publicar_x.py`). Si tocas esos nombres, rompes a los demás.

## Workflows

| Workflow | Cuándo | Qué hace |
|---|---|---|
| `main.yml` | cron 10:30 UTC | `descarga_aemet.py` (mapas PNG) + `descarga_datos.py` (OpenData) |
| `construir-web.yml` | cron 11:00 UTC + push a los generadores + manual | Reconstruye **toda** la web: gif → estudios → calculadora → mapa |
| `parte-nocturno.yml` | cron 07:15 UTC (+ 08:50 de red de seguridad) | `parte_nocturno.py` (parte + **archivo horario**) + `publicar_x.py` |
| `actualizar-gifs.yml` | cron 11:00 UTC + manual | Solo `generar_gif.py` (se solapa con construir-web) |
| `datos-calendario.yml` | lunes 05:00 UTC | `generar_calendario_datos.py` |
| `analisis.yml` | mensual (día 1, 06:00 UTC) | `analisis_refugios.py` + `analisis_refugios_nocturnos.py` |
| `certificados.yml` | manual | `generar_certificados.py` |
| `evolucion.yml` | manual (input `buscar`) | `evolucion_estacion.py` para una estación |
| `backfill.yml` | manual | `backfill_historico.py` |
| `normales.yml` | manual | `descarga_normales.py` (una sola vez) |

Los workflows que escriben en `docs/` comparten `concurrency: group: commit-docs` para no pisarse, y el push reintenta con `pull --rebase --autostash` hasta 5 veces.

**Secrets**: `AEMET_API_KEY`, y para publicar el parte en X (`@nochetropicales`): `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`. `publicar_x.py` sale limpio sin fallar si faltan.

**Backend externo**: el Observatorio del Descanso y el Confortómetro guardan votos en un Google Apps Script (`scripts/apps_script_observatorio.gs`, desplegado como web app). Su URL `/exec` va en `APPS_SCRIPT_OBS_URL` dentro de `generar_calculadora.py`.

## Flujo de datos

1. `descarga_aemet.py` — scraper de los mapas PNG diarios (máximas/mínimas, península + canarias), registra cada descarga en `metadata.csv`
2. `descarga_datos.py` — API OpenData de AEMET, valores climatológicos diarios de ~848 estaciones; pide los últimos 20 días porque AEMET publica con 3-5 días de retraso
3. `backfill_historico.py` — backfill por año en chunks de 14 días, idempotente
4. `descarga_normales.py` — normales 1991-2020 por estación (ejecución única)
5. `analisis_refugios*.py` — rankings diurno y nocturno → `analisis/*.csv` + PNGs
6. `parte_nocturno.py` — observación en tiempo real (últimas 24 h), sin el retraso de los climatológicos; los datos son **provisionales** y así se indica en la página
7. `parte_nocturno.py` — además del parte, **archiva las lecturas horarias** en
   `datos/horarias/AAAA/AAAA-MM-DD.csv.gz` (fint, idema, ta, tamin, tamax, hr, prec).
   AEMET no publica ningún histórico horario: la observación se borra a las ~12 h, así
   que o se guarda según pasa o ese dato no existe. ~88 KB/día → ~32 MB/año.
   Idempotente: el workflow corre dos veces y fusiona por (fint, idema).
8. `generar_*.py` — regeneran `docs/`

Los outputs se commitean automáticamente (los workflows tienen permiso de escritura).

## Convenciones del proyecto

- **Idioma**: español. Nombres de variables, comentarios, logs y outputs en español.
- **Reproducibilidad**: todo lo publicado tiene que ser regenerable ejecutando un script del repo. NO archivos estáticos one-off subidos a mano.
- **Estilo**: paleta cálida (fondos `#161009`/`#241b11`, papel `#efe6d6`, teja `#d9744e`, verde `#8fb07a`), tipografías Fraunces + Lora en HTML; matplotlib por defecto en análisis técnicos.
- **Sin dependencias JS externas**: las páginas son HTML+CSS+JS vanilla, autocontenidas. El mapa se proyecta en Python, no con Leaflet.
- **Idempotencia**: scripts pensados para re-ejecutarse sin romper nada. Los workflows commitean solo si hay cambios reales.
- **Métricas honestas**: para identificar refugios no usamos medias (esconden picos). Usamos P95 de Tmin de verano, racha máxima consecutiva de noches tropicales, y conteos por umbral.
- **Nada interpolado**: todo lo que se afirma sale de una estación medida de AEMET.

## Gotchas aprendidos a las malas

- **AEMET bloquea User-Agents personalizados con 403**. Usar UA de Chrome real en los scrapers.
- **API OpenData "todasestaciones": máximo 15 días por petición**. De ahí el chunking de 14 días.
- **Decimales con coma y encoding ISO-8859-15** en los CSVs de AEMET.
- **Bash NO admite ñ en nombres de variables** (exit 127). En workflows usar `ANIO`, no `AÑO`.
- **pandas devuelve int como float en groupby**. Cast explícito a `int()` antes de usar `:d` en f-strings.
- **matplotlib boxplot**: `labels=` está deprecated, usar `tick_labels=`.
- **GitHub Pages** sirve desde `<repo>/docs/` o `<repo>/`, no desde subcarpetas anidadas.
- **Permisos de workflow**: Settings → Actions → General → "Read and write permissions" activado.
- **`requirements.txt` no incluye Pillow** aunque varios scripts la necesitan; los workflows hacen `pip install pillow numpy` a mano. Si añades un script con Pillow, revisa el workflow.
- **`spain-provinces.geojson` no es topológicamente limpio**: provincias vecinas no comparten vértices, así que no se pueden unir polígonos por tramos (por eso `generar_silueta.py` rasteriza y traza el contorno).
- **Ids duplicados en `lugares.csv` mezclan votos de pueblos distintos** en el Observatorio. `generar_lugares.py` ya lo arregló (barrios de Madrid/Barcelona renombrados como «Salamanca (Madrid)»); no reintroducir duplicados.
- **Las normales 1991-2020 se descargaron** pero el cruce salió con `tmax_normal_verano` vacío — bug pendiente.

## Deuda técnica conocida

- **7 copias con fecha de `generar_calculadora.py`** en `scripts/` (`22-07-2026`, `23-07-26`, `26-07-26`, `29-07-26`, `-21-07-26`, `(26)`, `respaldo`) + una de `estudio_colores.py`. La buena es la que no lleva sufijo: es la que ejecutan los workflows. Las demás son ~2 MB de ruido y confunden las búsquedas.
- **`aemet-temperaturas/generar_gif.py`** existe además de `scripts/generar_gif.py` y **difiere**. Los workflows usan el de `scripts/`.
- **`README.md` está desfasado**: describe solo el archivo de mapas y apunta a `descarga-diaria.yml`, que ya no existe en `.github/`.
- **`actualizar-gifs.yml` y `construir-web.yml` corren los dos a las 11:00 UTC** y ambos generan los GIFs. Redundante.
- **No hay tests.** Serían bienvenidos para los parsers de fechas y la conversión DMS→decimal.
- **`docs/` pesa lo suyo** (GIFs de 2-5 MB, 219 certificados PNG) y `datos/` son 217 MB versionados. Sostenible hoy, vigilarlo.

## Stack técnico

- **Python 3.11** con `pandas`, `numpy`, `matplotlib`, `requests`, `beautifulsoup4`, `Pillow`.
- **GitHub Actions**, sin servidor propio. Google Apps Script como único backend (formularios del Observatorio/Confortómetro).

## Datos disponibles

- `datos/diarios_YYYY.csv` — 2017-2026, ~23 MB por año, ~2 millones de registros
- `datos/diarios_estaciones.csv` — rolling de los últimos días descargados
- `datos/estaciones.csv` — catálogo (indicativo, nombre, provincia, lat/lon en DMS, altitud)
- `datos/normales_1991_2020.csv` — valores normales por estación
- `datos/lugares.csv` — poblaciones del Observatorio (GeoNames CC BY 4.0), regenerable con `generar_lugares.py`
- `datos/hoteles.csv` — hoteles del sello "Refugio Climático"
- `datos/spain-provinces.geojson` — contornos de las 52 provincias
- `datos/horarias/AAAA/*.csv.gz` — lecturas horarias de ~857 estaciones, desde 2026-08-29.
  Cubre de 20h a 07h UTC. Es lo único que permite responder «cuántas HORAS estuvo la
  noche por debajo de 20°», frente a «cuánto bajó en el punto más frío» de los diarios
- `datos/gradiente_nocturno.json` + `pares_estaciones.csv` — gradiente térmico nocturno
- `datos/tendencia_estaciones.csv` + `tendencia_resumen.json` — tendencia de noches tropicales
- `datos/estaciones_termicas.csv` + `estaciones_termicas.json` — estaciones del año térmicas
- `analisis/refugios_nocturnos_ranking.csv` — **la fuente de verdad de la web**; todo `docs/` se construye a partir de él

## Hallazgos clave del análisis hasta ahora

- Los **refugios nocturnos garantizados** son pueblos de montaña interior 600-1500 m, climas continentales secos: Sanabria, Puerto del Pico, Rascafría, Benasque, Vall de Boí, Beariz, Reinosa, Isaba...
- La **costa mediterránea** es de los PEORES sitios de España para dormir en verano: Palma, Cartagena, Capdepera con rachas de **86 noches tropicales consecutivas**.
- El **interior de Gran Canaria** (Tejeda, San Bartolomé de Tirajana) es el peor sitio de España para dormir, peor que la costa andaluza, por efecto foehn.
- **Alcalá de la Selva** (Teruel, sierra de Gúdar) tiene **0,5 noches tropicales/año** vs **72/año** en Valencia capital. Ratio 180:1.
- El **gradiente térmico nocturno** real es **0,35 °C/100 m** (0,26 solo en península),
  no los 0,6 de manual. Y con R²=0,15: la altitud sola NO predice la mínima nocturna.
  52 de 285 pares tienen inversión pura (el pueblo alto duerme peor que el bajo).
- Las noches tropicales suben en **653 de 746 estaciones**; ninguna baja de verdad.
  El crecimiento es MAYOR en el llano (+14/década por debajo de 200 m) que en montaña
  (+5 por encima de 800): la brecha se abre, no se cierra. 54 pueblos han perdido su cero.
- **Desfase estacional**: el día más frío llega +24 días después del solsticio y el más
  cálido +45. El mar retrasa: litoral +48,9 vs interior +42,1 (Canarias, +58,4).
- **Empíricamente verificado**: los incendios forestales NO calientan los termómetros a >5-20 km del foco. La causalidad es calor→fuego, no al revés (caso Sierra de la Culebra 2022).

## Estado actual y próximas tareas

**Hecho:**
- Pipeline diario funcionando (mapas + OpenData)
- Backfill de 10 años
- Web completa en producción en **nochetropical.es**: reportaje, calculadora, 52 landings provinciales, mapa interactivo, metodología, versión en inglés
- Parte de la noche diario, autopublicado en X (`@nochetropicales`)
- Certificados "Refugio Climático de España 2026" para 25 ayuntamientos
- Observatorio del Descanso y Confortómetro con backend en Apps Script
- Sello para hoteles + landing `/tu-hotel/`
- Estudio "La España que nunca se colorea"
- Página `/prensa/`, generador de informes por lead y export a Excel por estación

**Pendiente para el lanzamiento mediático:**
- Press kit PDF de 2 páginas
- Lista de ~20-25 periodistas españoles (clima/medio ambiente, nacionales + regionales)
- Email pitch template
- Plan de lanzamiento coordinado
- Envío de los certificados a los ayuntamientos (backlinks institucionales + prensa local)

**Pendiente inmediato — archivo horario (acordado el 2026-08-29):**
- La semana del 2026-09-05, **primer ensayo** con las noches acumuladas: para cada
  estación y noche, cuántas horas por debajo de 20/18/16 °C, a qué hora cruza cada
  umbral y qué forma tiene la curva. Objetivo: responder si basta con que la mínima
  baje puntualmente de 20° o hace falta llegar a 18 para asegurar horas de sueño.
- **Rediseñar los cron para cubrir la noche, no solo duplicarla.** Los dos actuales
  (07:15 y 08:50 UTC) están a hora y media: capturan casi la misma ventana, así que
  son red de seguridad contra un cron saltado, no cobertura. Si GitHub se retrasa
  —el 27 y 28 de agosto lo hizo 10-12 h y el parte no se publicó— se pierde la noche
  entera. Plan: `parte_nocturno.py --solo-archivo` (archiva y sale, sin parte ni X) +
  workflow aparte `archivo-horario.yml` con cron a las 23:30 y 03:30 UTC. Con el
  07:15 del parte, la unión cubre 11:30→07:15 y un fallo suelto pierde solo un tramo.
  La fusión por (fint, idema) ya hace que solaparse sea inofensivo.
- **NO se puede rellenar hacia atrás**: AEMET no publica histórico horario y las
  sinópticas de NOAA (ISD) solo cubren 28 de las 87 estaciones de cero noches
  tropicales — ninguno de los refugios emblemáticos. Archivar desde hoy es la
  única vía.

**Ideas para más adelante:**
- Estudio sistemático "huella térmica de incendios" cruzando EFFIS (Copernicus) con AEMET
- Más años de backfill si interesa serie larga
- Análisis comparativo con normales 1991-2020 (anomalías vs clima histórico)
- Extensión a otros países europeos vía MeteoStat o Copernicus

## Comandos útiles

```bash
cd aemet-temperaturas

# Reconstruir la web entera (el orden importa: es el de construir-web.yml)
python scripts/generar_gif.py
python scripts/estudio_colores.py
python scripts/generar_calculadora.py     # escribe ../docs/ completo
python scripts/generar_pagina_mapa.py

# Análisis (regeneran el ranking del que vive la web)
python scripts/analisis_refugios_nocturnos.py
python scripts/analisis_refugios.py

# Backfill de un rango
python scripts/backfill_historico.py --desde 2024-01-01 --hasta 2024-12-31

# Una estación concreta
python scripts/evolucion_estacion.py --buscar "MOSQUERUELA"
python scripts/generar_informe_lead.py --estacion 8293X
python scripts/exportar_excel_estacion.py --estacion 8293X

# El parte, sin clave de AEMET (datos sintéticos)
python scripts/parte_nocturno.py --demo

# Ver el HTML generado
xdg-open ../docs/index.html   # Linux
open ../docs/index.html       # macOS
start ..\docs\index.html      # Windows
```

## Cómo trabajar conmigo (Claude Code)

- **No tocar nada de `docs/` a mano** — se regenera entero por script. Un cambio manual se pierde en la siguiente ejecución del workflow.
- **Editar el generador, no la salida.** Casi todo el HTML del sitio vive dentro de `generar_calculadora.py`.
- **No commitear claves API.** Solo secrets de GitHub.
- **Antes de añadir un análisis nuevo**: comprobar que las métricas no se solapan con las existentes; preferir extender un script existente a crear uno nuevo.
- **Antes de crear un script nuevo**: mirar si ya existe uno con ese nombre y un sufijo de fecha (ver deuda técnica).
- **Cambios en workflows**: probar con `workflow_dispatch` manual antes de fiarse del cron.
- **Si una decisión técnica es controvertida** (p. ej. cambiar de matplotlib a plotly, o meter una librería JS): preguntar antes de migrar.
