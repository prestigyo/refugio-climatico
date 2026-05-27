# Archivo diario de mapas de temperaturas de AEMET

Repositorio que automatiza la descarga diaria de los mapas de temperaturas
máximas y mínimas publicados por AEMET para Península/Baleares y Canarias,
acumulando un histórico para análisis posteriores (zonas refugio climático,
evolución estacional, comparación predicción vs realidad…).

Fuente: <https://www.aemet.es/es/eltiempo/prediccion/temperaturas>

## Qué se descarga

Para cada zona se guarda una imagen PNG al día:

| Zona              | Tipos                                                        |
|-------------------|--------------------------------------------------------------|
| `peninsula`       | `maxima`, `minima`, `variacionmax`, `variacionmin`           |
| `canarias`        | `maxima`, `minima`                                           |

Ruta de los ficheros: `images/<zona>/<tipo>/YYYY-MM-DD.png`.

Además, cada descarga se registra en `metadata.csv` con: fecha, URL de origen,
hash SHA-256, tamaño y estado, lo que permite reconstruir series y detectar
huecos.

## Cómo funciona

`scripts/descarga_aemet.py` hace lo siguiente:

1. Abre la página HTML correspondiente a cada combinación zona/tipo.
2. Localiza el `<img>` que apunta a
   `/imagenes_d/eltiempo/prediccion/temperaturas/...png` (la URL incluye un
   timestamp que cambia con cada pasada del modelo, por eso **no se construye
   a mano**, se lee de la página).
3. Descarga el PNG y lo guarda con el nombre `YYYY-MM-DD.png`. Si ya existe
   no lo sobrescribe (idempotente).
4. Añade una fila al `metadata.csv`.

La GitHub Action `.github/workflows/descarga-diaria.yml` lo ejecuta todos los
días a las **10:30 UTC** (≈ 12:30 hora peninsular, después de que AEMET
publique los mapas definitivos del día) y hace `commit & push` de los cambios.

## Despliegue paso a paso

1. Crea un repositorio nuevo en GitHub (público o privado, da igual).
2. Copia todos los ficheros de este proyecto en la raíz.
3. `git add . && git commit -m "Init" && git push`.
4. Ve a la pestaña **Actions** del repo y habilita workflows si te lo pide.
5. Pulsa "Run workflow" la primera vez para verificar que funciona. A partir
   de ahí se ejecuta solo cada día.

No hace falta ninguna clave ni secret: AEMET sirve los mapas públicamente.

## Ejecución manual local

```bash
pip install -r requirements.txt
python scripts/descarga_aemet.py
```

## Consideraciones importantes

- **Licencia de los datos**: AEMET permite la reutilización citando la
  autoría. Añade en cualquier estudio/publicación: *"Fuente: AEMET"*. Más
  info: <https://www.aemet.es/es/nota_legal>.
- **Frecuencia**: una descarga al día es uso razonable; no aumentes la cron
  porque los mapas no cambian más a menudo.
- **El timestamp de la URL**: la imagen del día de hoy se publica como
  `YYYYMMDD00+024_ww_btmxp0d1.png` (predicción a +24h desde las 00:00 UTC).
  Eso explica por qué la URL incluye `+024` y por qué a las 06:00 puede no
  estar todavía la del día.

## ⚠️ Para un estudio serio: usa también la API OpenData de AEMET

Los mapas PNG son **excelentes para visualización**, pero para un estudio
cuantitativo de "zonas refugio climático" lo ideal es trabajar con datos
numéricos. AEMET ofrece gratis su API oficial **AEMET OpenData**:

- Portal: <https://opendata.aemet.es/centrodedescargas/inicio>
- Solicitas una API key por email (gratis, en segundos).
- Endpoints útiles para tu caso:
  - `/api/valores/climatologicos/diarios/datos/...` → tmin/tmax diarios por
    estación.
  - `/api/valores/climatologicos/normales/estacion/...` → valores normales
    (climatología 1991-2020) para comparar.
  - `/api/prediccion/especifica/municipio/diaria/{municipio}` → predicciones
    municipales.

Tener tmin/tmax por estación en CSV permite calcular cosas que en una imagen
son imposibles: anomalías respecto a la normal climática, conteo de noches
tropicales (>20 °C) y noches ecuatoriales (>25 °C), persistencia de olas de
calor, etc. — que son los indicadores habituales para identificar refugios
climáticos.

Si te interesa, puedo ampliarte este mismo repo con un segundo script que
baje también el CSV diario de estaciones vía OpenData.

## Estructura del repositorio

```
.
├── .github/workflows/descarga-diaria.yml   # Cron diario
├── scripts/descarga_aemet.py               # Scraper principal
├── images/
│   ├── peninsula/{maxima,minima,variacionmax,variacionmin}/YYYY-MM-DD.png
│   └── canarias/{maxima,minima}/YYYY-MM-DD.png
├── metadata.csv                            # Log de descargas
├── requirements.txt
└── README.md
```
