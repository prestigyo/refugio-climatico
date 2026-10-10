# refugio-climatico — contexto del proyecto para Claude Code

> Última revisión: 2026-10-10. Este fichero no se actualiza solo: si cambias la
> estructura, añades un workflow o publicas una sección nueva, actualízalo en el
> mismo commit.

## Qué es esto

Sistema automatizado que descarga datos meteorológicos de AEMET y los analiza para identificar **refugios climáticos nocturnos** en España — pueblos donde se sigue durmiendo bien en verano.

Lo público ya **no** es solo una calculadora: es un sitio entero, **https://nochetropical.es** (GitHub Pages sirviendo `docs/`, dominio propio vía `docs/CNAME`), con reportaje scrollytelling, calculadora, 52 landings provinciales, mapa interactivo de ~848 estaciones, un parte diario que se autopublica en X, certificados para ayuntamientos y varias landings temáticas.

Objetivo a corto plazo: **lanzamiento mediático**. La audiencia son periodistas españoles.

## Estructura del repo

```
refugio-climatico/
├── .gitignore                # solo bytecode (__pycache__/, *.pyc) y restos del SO
├── .github/workflows/        # 12 workflows (ver tabla abajo)
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
| `generar_calculadora.py` (9.300 líneas, el núcleo) | `index.html` (reportaje + calculadora), las **52 landings de provincia**, `ranking-noches-tropicales/`, `prensa/`, `metodologia/`, `confortometro/`, `observatorio-del-descanso/`, `ola-de-calor/`, `la-espana-que-nunca-se-colorea/`, `refugios-climaticos-naturales-cerca-de-mi/`, `refugios-y-espana-vaciada/`, `hoteles-refugio-climatico/`, `tu-hotel/`, `tu-pueblo/`, `dormir-con-calor/`, `dormir-con-manta-en-verano/`, `vacaciones-sin-calor/`, `informes/`, `estudios/`, `en/` (versión inglesa: `en/best-climate-in-spain-year-round/`, `en/find-your-winter-address/` + `en/winter-stations.json`, `en/mild-winter/` y una página por sello, `en/winter-in-spain-long-stay/`), `badges/`, `sitemap.xml`, `robots.txt`, `favicon.svg`, `.nojekyll`, `CNAME` |
| `generar_miniaturas.py` | `miniaturas/<slug-provincia>.png` (1200×1200, la que usa Google) y `miniaturas/<slug-provincia>-og.png` (1200×630, la de redes) — silueta de la provincia + sus estaciones coloreadas + la cifra grande. Además las **7 páginas en inglés** (`miniaturas/en-*.png`), con España entera y sus 857 estaciones: ahí **el color codifica temperatura, nunca juicio** — en las de verano rojo = noche caliente (`color_nt`), en las de invierno azul = noche helada (`color_helada`), y en la de la herramienta de estancia azul = semanas sin un día que llegue a 18 °C (`color_sin_terraza`, sobre `estancia_por_ventana.csv`). Por eso el mismo tono cálido es malo en verano y bueno en invierno: la escala dice cuánto calor hace y es la estación del año la que decide si conviene. También `miniaturas/indice.json`, que dice qué provincias llevan mapa: lo lee `generar_calculadora.py` para escribir un `alt` que describa la imagen de verdad (Ceuta y Melilla no llevan silueta). **Tiene que correr ANTES que `generar_calculadora.py`**, y así está en el workflow |
| `generar_calculadora.py` (descargas) | Copia a `datos/` los CSV de análisis que respaldan las fichas `Dataset`: `refugios_nocturnos_ranking.csv`, `horas_dormibles.csv`, `invierno_por_estacion.csv`, `invierno_por_temporada.csv` (1,1 MB). `tendencia_estaciones.csv` se copió a mano, porque su página también se mantiene a mano. Sin ellos las fichas irían sin `distribution` |
| `generar_pagina_mapa.py` | `mapa-estaciones/index.html` — mapa interactivo, provincias y puntos proyectados en Python con la misma `project()`, sin librerías JS |
| `generar_gif.py` | `ola-minimas.gif`, `ola-maximas.gif`, `ola-dia-noche.gif`, `ola-dia-noche-vertical.gif`, `ola-canarias-minimas.gif`, `og.png`. **Por EDICIÓN**: solo los mapas del año del más reciente, o los de `--anio` / `--desde` / `--hasta` |
| `estudio_colores.py` | `estudios/*.png` + `estudios/estudio-datos.json` |
| `generar_certificados.py` | `certificados/index.html` + `certificados/<slug>/` (una página por estación certificada), `certificados/certificado-<slug>.png` (25 diplomas para ayuntamientos) y `badges/pueblo-<slug>.svg` y `badges/pueblo-<slug>-claro.svg` (el sello del pueblo en sus dos temas, para que el alojamiento incruste en su web el que le pegue al fondo) |
| `generar_calendario_datos.py` | `datos/<slug-provincia>.json` (calendario de calor que carga la calculadora bajo demanda) |
| `analisis_invierno.py` | `estudios/invierno-datos.json` (cifras de `/en/best-climate-in-spain-year-round/` y la lista del sello Mild Winter) + `en/winter-stations.json` (las 828 estaciones que consume la herramienta) |
| `analisis_estancia.py` | `en/stays/stations.json` (catálogo) + `en/stays/<mes>-<días>.json` (60 ventanas: 12 meses de llegada × 5 duraciones, con el valor de **cada año** por separado). De ahí vive `/en/find-your-winter-address/`. 7,2 MB en disco; por la red son 16-36 KB, que es lo que descarga el visitante de una ventana |
| `analisis_curva_nocturna.py` | `estudios/horas-datos.json` (las cifras de la landing `/cuantas-horas-se-duerme-en-verano/`, que arma `generar_calculadora.py`) |
| `generar_presskit.py` | `prensa/kit/index.html` — dosier de prensa de dos A4, pensado para imprimirse o guardarse en PDF. **Lee las cifras de los ficheros de análisis en cada ejecución**, para que un PDF estático no se quede viejo: por eso es **el último paso de `construir-web.yml`** y no un workflow aparte. Lleva `noindex`, así que el filtro `_es_noindex()` lo deja fuera del sitemap; sus URLs van en `<a>` con la dirección a la vista, que es lo único que sirve a la vez en papel y en pantalla. No necesita pandas —`csv` y `statistics`— para no engordar la instalación del build diario |
| `parte_nocturno.py` | `parte/index.html`, `parte/parte.txt`, `parte/parte.json` |

**`generar_calculadora.py` es además un módulo compartido**: varios scripts hacen `import generar_calculadora as g` para reutilizar `PROVINCIAS`, `slug()`, `RANKING_CSV`, `DOCS_DIR` (lo hacen `generar_certificados.py`, `generar_calendario_datos.py`, `generar_informe_lead.py`, `publicar_x.py`). Si tocas esos nombres, rompes a los demás.

## Workflows

| Workflow | Cuándo | Qué hace |
|---|---|---|
| `main.yml` | cron 10:30 UTC | `descarga_aemet.py` (mapas PNG) + `descarga_datos.py` (OpenData) |
| `construir-web.yml` | cron 11:00 UTC + push a los generadores + manual | Reconstruye **toda** la web: estudios → miniaturas → calculadora → mapa → **dosier de prensa**. **Ya no genera los GIFs** (2026-10-07) |
| `parte-nocturno.yml` | cron 07:15 UTC (+ 08:50 de red de seguridad) | `parte_nocturno.py` (parte + **archivo horario**) + `publicar_x.py` |
| `actualizar-gifs.yml` | **cron 11:00 UTC de abril a octubre** (`0 11 * 4-10 *`) + manual con año/recorte | Solo `generar_gif.py`. Fuera de temporada no dispara; el botón «Run workflow» funciona los 365 días |
| `datos-calendario.yml` | lunes 05:00 UTC | `generar_calendario_datos.py` |
| `analisis.yml` | mensual (día 1, 06:00 UTC) | `analisis_refugios.py` + `analisis_refugios_nocturnos.py` |
| `estudio-horario.yml` | lunes 04:00 UTC + manual | `analisis_curva_nocturna.py` (rehace `docs/estudios/horas-datos.json`; la landing la construye el build de las 11:00) |
| `estudio-invierno.yml` | día 1 de cada mes, 08:00 UTC + manual | `analisis_invierno.py` (rehace `docs/estudios/invierno-datos.json`; corre tras `analisis.yml`, que rehace `noches_por_anio.csv`) |
| `estudio-estancia.yml` | día 1 de cada mes, 09:00 UTC + manual | `analisis_estancia.py` (rehace `docs/en/stays/`; va tras `estudio-invierno.yml` y antes del build de las 11:00). **Grupo propio**, por lo del `commit-docs` |
| `pitch.yml` | manual (desplegable `tipo` + campo `provincia`) | `generar_pitch.py`. **No commitea nada** y tiene permisos de solo lectura: el correo sale en el registro de la ejecución, para copiar desde el navegador. Existe porque el script imprime en pantalla y el proyecto se maneja desde la web de GitHub, donde no hay pantalla |
| `certificados.yml` | manual | `generar_certificados.py` |
| `evolucion.yml` | manual (input `buscar`) | `evolucion_estacion.py` para una estación |
| `backfill.yml` | manual | `backfill_historico.py` |
| `normales.yml` | manual | `descarga_normales.py` (una sola vez) |

Los workflows que escriben en `docs/` comparten `concurrency: group: commit-docs` para no pisarse, y el push reintenta con `pull --rebase --autostash` hasta 5 veces.

**Cuidado con `commit-docs`**: GitHub solo guarda **una** ejecución en cola por grupo, y cuando llega otra **cancela la que esperaba**, aunque `cancel-in-progress` sea `false`. Un workflow esporádico metido en ese grupo se queda en la cola detrás de `construir-web` y muere sin arrancar (cero jobs). Le pasó a `estudio-invierno.yml` el 2026-09-24. Por eso `archivo-horario.yml`, `estudio-horario.yml`, `estudio-invierno.yml` y `estudio-estancia.yml` tienen **grupo propio**: escriben ficheros que no toca nadie más, y la colisión real en el push ya la resuelve el reintento con rebase.

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
- **Para una estancia larga manda la RACHA, no la mediana.** `/en/winter-in-spain-long-stay/`
  usa `racha_sin_terraza_max` —el tramo más largo sin un solo día que llegara a 18 °C— y no
  la usa ninguna otra página. La mediana nacional son **90 días en península y Baleares**
  frente a **8 en Canarias**: en medio país puedes pasar casi toda una estancia de tres
  meses sin una tarde para sentarte fuera. Para una semana da igual; para noventa días es lo
  único que no puedes esperar a que pase. **Ojo al filtrar**: sin el tope de calefacción
  (≤45 noches bajo 10 °C) la tabla colaba Torre-Pacheco (111), Murcia (105) y Salobreña (98)
  por tener la racha corta — una racha buena con noches frías no sirve a quien paga la
  calefacción tres meses. Con los tres filtros quedan **ocho estaciones en toda la península
  y Baleares**.
- **Los GIFs son una EDICIÓN anual, no un acumulador.** `generar_gif.py` hacía `glob` de
  todo lo que hubiera en `images/` y los metía todos, así que la animación crecía sola
  hacia el otoño: el 6 de octubre de 2026 el último fotograma de «la ola de calor» —el que
  se queda 1,7 s, el doble que los demás— era un mapa templado en el que no pasa nada.
  Ahora la ventana por defecto es **del 15 de abril al 31 de octubre del año del mapa más
  reciente** (no el año de hoy: en enero la edición que toca sigue siendo la del verano
  pasado), y se puede recortar con `--desde/--hasta`. En 2027 pasará solo a 2027 y el
  historial de 2026 se queda en `images/`, regenerable con `--anio 2026`.
  **Las fechas están medidas, no elegidas**: sobre 2017-2025, el 5 % de las estaciones
  pasa de 30 °C del 3 de mayo al 25 de octubre de mediana, y el 20 % ya lo hacía el 26 de
  abril en el año más amplio. Valencia **nunca ha tenido menos de 6 días de 30 °C en mayo**
  (15 en 2022) y tiene 15 días de 25 °C en octubre; en noviembre, uno. Y ojo con lo que se
  mira para decidir: en octubre el mapa de MÍNIMAS está vacío pero el de MÁXIMAS marca
  22-28 °C en media España — dar octubre por muerto mirando solo las mínimas fue un error.
  **Lo que NO se para es la descarga**: los 8 PNG diarios son 181 KB, AEMET los borra y no
  se pueden recuperar. Es el mismo argumento del archivo horario. Se para la animación.
- **La divulgación de afiliación va JUNTO al enlace, no en el pie.** El sitio monetiza con
  Booking vía CJ (`cj_deeplink()`, `CJ_PID`). Cada enlace lleva `rel="sponsored nofollow
  noopener"` y, al lado, el texto de `DIVULGACION_AFILIADO` — que vive en **un solo sitio**
  para que el directorio y las 32 fichas digan lo mismo. Lo exigen la LSSI (art. 20) y los
  términos de CJ y Booking, y además es lo que sostiene la premisa del sitio: un botón de
  comisión sin declarar en la ficha de un hotel que tú mismo certificas es justo lo que un
  periodista usaría para desmontarte. **Solo se emite si hay enlace de afiliado**: en las
  fichas sin `slug_booking` el botón va a la web del alojamiento y declarar una comisión
  que no existe sería falso.

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
- **Google NO usa SVG como miniatura de resultado** — ni en la búsqueda ni en Imágenes.
  Daba igual que los 219 sellos de pueblo y los 67 de Mild Winter fueran `<img src=".svg">`:
  a efectos de miniatura esas páginas no tenían imagen. Solo cuenta un ráster (PNG/JPEG/WebP)
  dentro de un `<img>` VISIBLE en el cuerpo. El `og:image` no basta: Google elige de lo que ve
  en la página, no del `<head>`.
- **Un `og:image` compartido no lo elige Google.** 369 páginas declaraban el mismo `og.png`:
  con eso no hay forma de que asocie la imagen a ninguna en concreto, así que no ponía
  ninguna. Tiene que ser distinta por página.
- **La miniatura del resultado se recorta CUADRADA**; el `og:image` de redes es 1,91:1. Son
  dos formatos incompatibles y por eso `generar_miniaturas.py` escribe los dos. Un 1200×630
  usado como miniatura pierde casi la mitad por los lados.
- **A tamaño real de miniatura (~92 px en escritorio) no se lee NADA.** Solo sobreviven la
  silueta y una cifra grande. Todo lo demás de la composición es para cuando se ve entera.
- **`Image.quantize()` rompe los degradados** en un escalón duro (medido: un salto de 9
  niveles a media altura) y el dither no lo arregla. Para reducir peso hay que usar
  `convert("P", palette=Image.ADAPTIVE, colors=256)`, que sí lo conserva: deja los PNG
  en el 37 % sin artefactos (13,4 MB → 5,2 MB en las 104 miniaturas).
- **Un islote remoto estira el encuadre de la provincia y la deja diminuta.** El encuadre
  sale de la caja envolvente, así que **Isla de Alborán** (0,7 km² a 90 km de la costa, sin
  estación) doblaba la caja de Almería: de 1,21×0,8° a 1,21×1,98°, y la silueta se dibujaba
  a 308 px dentro de una caja de 1.060. `anillos_utiles()` descarta un anillo solo si es
  despreciable (<0,5 % del área del mayor) **y** no tiene ninguna estación dentro; Menorca,
  Ibiza, Lanzarote y Fuerteventura están muy por encima y se quedan. Afecta a 28 provincias.
  De paso Ceuta baja de 0,92° a 0,08° —sus 0,92 eran islotes— y pasa al formato sin mapa,
  igual que Melilla.
- **En la miniatura cuadrada el reparto va anclado de ABAJO ARRIBA** (pie → línea de altitud
  → nombre de la estación → fila de la cifra → y el mapa se queda con lo que sobre). Así el
  nombre de la estación dispone del ancho entero: hay muchos largos o compuestos
  («La Póveda de Soria, Barriomartín», «Vélez Blanco - Topares») que en media columna se
  encogían hasta no leerse. La apaisada mantiene dos columnas porque en 630 px de alto no
  cabe ese reparto.
- **`textbbox()` se come los espacios de los extremos**: encadenar trozos de texto con
  fuentes distintas medidos así los pega unos a otros. Para eso está `avance()`, con
  `textlength()`.
- **El umbral de la hamburguesa hay que MEDIRLO, no elegirlo bonito.** Estaba en 960 px
  porque es un número redondo, pero el menú español necesita 982 px de ventana para sus
  754 px de pestañas: entre 961 y 976 px las últimas entradas se recortaban en las ~400
  páginas, y `overflow-x:auto` recorta **sin avisar** (ni desborda la página, ni sale
  barra, ni falla nada). El menú inglés era peor: siete pestañas más la lupa piden 899 px
  y en una banda de 1.100 solo quedan 803 —48 de relleno, 160 del logotipo, 40 de huecos
  y 49 del chip «ES»—, así que faltaban 96 px **en todos los anchos de escritorio**,
  también a 1.600. Hoy: fila a partir de 1.024 px (español) y de 1.260 (inglés, con la
  banda ensanchada a 1.260), panel por debajo. La comprobación es un barrido con
  Playwright mirando `scrollWidth > clientWidth`; a ojo no se ve.
- **`.nav-e` la comparten el menú inglés y el escueto español**, así que no sirve para
  distinguirlos: el inglés lleva además `.nav-en`, y sus reglas van con `nav.nav-e.nav-en`.
- **El panel absoluto se posiciona contra la CAJA DE RELLENO de `.in`**, no contra el
  botón: con `right:0` sobresalía 24 px por fuera de la hamburguesa que lo abre.
- **El CSS móvil compartido rotulaba la lupa en español** («Buscar en la web») dentro del
  panel de las ocho páginas inglesas. Cualquier regla con `content:` que viaje en el CSS
  común necesita su contrapartida en `.nav-en`.
- **Si el estado vive en el hash, un enlace nuevo tiene que BORRAR el anterior.** La
  herramienta de estancia guarda mes, duración, los cinco umbrales y la región en la URL.
  Al navegar de un enlace con `t=12` a otro sin `t`, el límite viejo seguía puesto: el
  segundo enlace enseñaba una lista distinta según vinieras de otro o lo abrieras recién,
  y la promesa de «dos personas con el mismo enlace ven lo mismo» se caía. En `hashchange`
  hay que reiniciar umbrales, región y orden ANTES de leer el hash. No se ve probando
  enlaces de uno en uno en pestañas limpias — solo navegando entre ellos.
- **El ancho mínimo de una tabla lo fijan las cabeceras con `white-space:nowrap`.** No baja
  de ahí por mucho que aprietes la letra o el relleno: 311 px en la tabla de la herramienta,
  con una caja de 250 en una pantalla de 320. Y un solo nombre largo («Las Palmas de Gran
  Canaria, Pl. de la Feria») ensancha la tabla entera si la primera columna no parte palabra
  — pasaba solo en febrero y solo a 480 px, que es justo como se escapan estas cosas.
- **Los cortes de una escala de color salen del reparto real, no de números redondos.**
  En el peor tramo sin terraza de una estancia de tres meses la MEDIANA son 63 días y
  más del 10 % del país no tiene ni uno en los 90: con cortes regulares (0-20-40-60-90)
  medio mapa quedaba del mismo tono. `color_sin_terraza()` usa 0-15-35-63-90.
- **`inyectar_miniatura` parcheaba `Article.image` y las herramientas declaran
  `WebApplication`**, así que las dos inglesas se quedaban sin `image` en su JSON-LD
  mientras las landings sí lo llevaban. Ahora parchea los dos tipos.
- **Un generador que no encuentra datos no debe ESCRIBIR igualmente.** `og_image()` pintaba
  el `og.png` sin mapa cuando la edición salía vacía: 33 KB en vez de 250, sin error ni
  aviso, sobre la imagen social de 317 páginas. No reventaba nada — solo dejaba el sitio
  peor. Ahora sale sin tocar el fichero.
- **El shell de Actions lleva `-e`**, así que `[ -n "$X" ] && ARGS=…` como última orden de
  una línea aborta el paso cuando el test da falso. Con los campos de `workflow_dispatch`
  vacíos —el caso del cron— fallaba siempre. Usar `if … then … fi`.
- **El plazo de `getCurrentPosition` incluye el diálogo del permiso.** El reloj del
  `timeout` empieza a contar en la LLAMADA, no cuando el usuario concede el permiso,
  así que el diálogo del navegador se come el presupuesto. Con los 8-9 s que había,
  la **primera** vez en un móvil se agotaba entre leer el diálogo y conseguir un
  arreglo en frío (5-20 s por GPS) y saltaba el error; la segunda vez el permiso ya
  estaba dado y el sistema tenía una posición reciente, así que respondía al
  instante. Síntoma exacto: **no va a la primera y sí a la segunda**. Reproducido con
  Playwright sustituyendo el proveedor de posición por uno lento.
  Hoy las cuatro páginas con botón de ubicación piden
  `{enableHighAccuracy:false,timeout:25000,maximumAge:300000}`. **La pieza que lo
  arregla es `maximumAge`**, no el `timeout`: acepta la posición de hasta cinco
  minutos que es justo la que hacía funcionar el segundo intento, y cinco minutos no
  mueven un puesto en un ranking de pueblos a decenas de km. `enableHighAccuracy`
  se queda en **false** a propósito: el GPS fino tarda mucho más y aquí la red de
  wifi/móvil da de sobra.
- **Un fallo de ubicación no es «permiso denegado».** Los cinco manejadores decían
  «(¿permiso denegado?)» pasara lo que pasara, así que el caso más frecuente
  —agotarse el plazo con el permiso **recién concedido**— acusaba al usuario de algo
  que no había hecho, y encima aconsejaba lo peor: «elige a mano», cuando lo que
  funciona es volver a pulsar. Hay que mirar `e.code`: 1 permiso, 2 posición no
  disponible, 3 plazo agotado. En la página bilingüe de heladas son `T.geoNeg`,
  `T.geoTarda` y `T.falloGeo`, con sus dos idiomas.
- **Una miniatura CUADRADA con `width:100%` ocupa el ancho entero × la misma altura.**
  `inyectar_miniatura()` mete el PNG de 1200×1200 en el cuerpo de las 8 páginas
  inglesas. Sin tope, en `/en/frost-free-towns-spain/` se pintaba a **1600×1600** en
  una ventana de 1600 —de borde a borde y **1,8 pantallas de alto**— porque su
  contenedor no tiene `max-width`; otras tres a 1132. Las 52 provinciales llevan el
  mismo CSS y salían bien (540) solo porque su columna sí lo tiene: el defecto no
  estaba en el CSS de la figura sino en confiar en el contenedor. Hoy
  `figure.mini{max-width:540px;margin:26px auto 0}` las iguala. El fichero sigue
  siendo de 1200 px y los atributos `width`/`height` también, que es lo que mira
  Google: solo se limita cómo se pinta. Se mide con Playwright, no a ojo.
- **IndexNow solo avisa de lo que CAMBIÓ ese día, y eso deja fuera lo nunca rastreado.**
  El aviso diario manda las URLs cuyo contenido cambió —correcto: avisar del sitio
  entero a diario es lo que estos buscadores consideran abuso—. Pero una página que
  Bing «descubrió y no rastreó» no cambia nunca, así que **no se la vuelve a**
  **anunciar jamás**. El 2026-10-10 el build decía `indexnow: sin avisos que mandar`
  con `0 con contenido nuevo hoy`. Para eso está
  `python scripts/generar_calculadora.py --indexnow-todo`, que manda el sitemap
  entero; **a mano, nunca en el cron**. La guardia de >200 URLs sigue activa en el
  modo diario y el tope de 10.000 es el del propio protocolo.
- **Un fragmento (`#m=11&d=90`) NO es una URL distinta para un rastreador.** Se
  descarta antes de pedir la página, así que inspeccionar en Bing una URL con
  fragmento y leer «Discovered but not crawled» no indica ningún defecto: no hay
  recurso que rastrear ahí. La herramienta de estancia enlaza cinco presets con
  hash, y de ahí salen esos descubrimientos. Antes de tocar nada, comprobar la URL
  **sin** fragmento: canonical a sí misma, `index, follow`, en el sitemap y permitida
  por robots.txt. Si todo eso está (lo estaba), lo que queda es presupuesto de
  rastreo del buscador, no código.
- **Una tabla ancha arrastra la PÁGINA entera si no rueda por dentro.** Barrido con
  Playwright a 360 px: **38 páginas de 473** se arrastraban en horizontal, 31 de ellas
  por la tabla (la de «dónde dormir» pide 471 px). Se envuelven en
  `<div class="twrap">` con `overflow-x:auto` —la clase que ya usaban las inglesas— y
  `overscroll-behavior-x:contain`, que evita que el gesto se escape al navegador y
  dispare el «atrás» del móvil al llegar al borde. Quedan 3, y son **partes
  archivados que ningún script regenera**: su HTML está congelado.
  **Ojo al barrer**: reutilizar una pestaña de Playwright para 500 páginas da
  falsos negativos —las de certificado y hotel redirigen, y esa navegación aborta la
  carga siguiente con «Execution context was destroyed»—. Se saldían 330 páginas sin
  avisar, y `vacaciones-sin-calor` desapareció de la lista estando rota. Pestaña
  nueva por página.
- **El traductor de Chrome se inventa los topónimos si no se lo impides.** En las
  páginas inglesas leídas con traducción automática, **«A Capela» salía «Una capa»**,
  «A Guía» «Una guía», «A Bola» «La Bola» y «A Guarda» «La Guarda». En un sitio cuya
  premisa es que cada cifra sale de una estación medida, un nombre de pueblo
  inventado la desmonta entera. Se marca `translate="no"` en la celda del nombre;
  **el atributo se hereda**, así que en el listado por provincia basta ponerlo en el
  `<div class="grupo">` para cubrir los cientos de nombres de dentro. Lo llevan ya
  las tablas de municipios, estación y provincia de las páginas inglesas, las `.loc`
  y el sello Mild Winter. **Lo que NO se marca son titulares, párrafos y cabeceras**:
  esos sí deben traducirse. Comprobación: recorrer el árbol como hace el traductor
  —parando en cada `translate="no"`— y contar nodos protegidos frente a traducibles;
  en `/en/frost-free-towns-spain/` salen 352 protegidos y 1.102 traducibles.
- **El archivo del parte se veía «detenido» sin estarlo.** El índice de `/parte/`
  enlazaba `[-12:]`, los doce últimos. Con 96 partes publicados eso dejaba 84
  invisibles: existían, se servían y eran **alcanzables** —cada parte fechado lleva
  su propia lista de 12, congelada en su día, así que encadenando hacia atrás se
  llega a todos—, pero subía a siete saltos llegar a agosto. Por eso el revisor de
  enlaces **no los marcaba como huérfanos** y por eso desde fuera parecía que el
  parte se había parado en septiembre. Hoy se listan todos en un `<details>`
  agrupados por mes (solo el número del día dentro del grupo): un verano entero
  cabe en 343 px de alto a 360 px de ancho.
  **Moraleja**: «no se ve» y «no existe» son diagnósticos distintos, y un clon
  local viejo los confunde. Antes de dar por roto algo que produce un workflow,
  comprobarlo contra `main`, no contra el clon de la sesión: aquí el clon mostraba
  18 huecos en el parte y 16 días perdidos del archivo horario que en `main` no
  existían.
- **Pillow no antialiasa polígonos**: se dibuja a 3× y se reduce con `LANCZOS`.
- **`spain-provinces.geojson` no es topológicamente limpio**: provincias vecinas no comparten vértices, así que no se pueden unir polígonos por tramos (por eso `generar_silueta.py` rasteriza y traza el contorno).
- **DOS provincias vienen escritas de dos formas en el catálogo de AEMET**, en
  `datos/estaciones.csv` y por tanto en `analisis/refugios_nocturnos_ranking.csv`:
  **Santa Cruz de Tenerife** («SANTA CRUZ DE TENERIFE» 19 / «STA. CRUZ DE TENERIFE» 19)
  y **Baleares** («BALEARES» 33 / «ILLES BALEARS» 11). Cualquier agrupación por provincia
  que no las unifique las parte por la mitad y calcula contrastes falsos: Baleares salía
  con 13 estaciones y un salto de 73,8 en vez de 44 y 78,9. **El síntoma que lo delata es
  contar 54 provincias donde España tiene 52** — si un listado por provincia no da 52,
  hay un duplicado. `generar_pitch.py` lo arregla con `EQUIVALENTES` más la regla
  «Sta.» → «Santa»; conviene comprobar si otros agrupamientos lo hacen.
- **`.title()` de Python escribe «Santa Cruz De Tenerife»** — pone en mayúscula las
  preposiciones. En un titular o en el asunto de un correo canta. Para topónimos
  castellanos hace falta bajar de, del, la, las, los, y, el (salvo si abren el nombre).
- **Ids duplicados en `lugares.csv` mezclan votos de pueblos distintos** en el Observatorio. `generar_lugares.py` ya lo arregló (barrios de Madrid/Barcelona renombrados como «Salamanca (Madrid)»); no reintroducir duplicados.
- **Las normales 1991-2020 se descargaron** pero el cruce salió con `tmax_normal_verano` vacío — bug pendiente.

## Deuda técnica conocida

- **7 copias con fecha de `generar_calculadora.py`** en `scripts/` (`22-07-2026`, `23-07-26`, `26-07-26`, `29-07-26`, `-21-07-26`, `(26)`, `respaldo`) + una de `estudio_colores.py`. La buena es la que no lleva sufijo: es la que ejecutan los workflows. Las demás son ~2 MB de ruido y confunden las búsquedas.
- **`aemet-temperaturas/generar_gif.py`** existe además de `scripts/generar_gif.py` y **difiere**. Los workflows usan el de `scripts/`.
- **`README.md` está desfasado**: describe solo el archivo de mapas y apunta a `descarga-diaria.yml`, que ya no existe en `.github/`.
- ~~`actualizar-gifs.yml` y `construir-web.yml` generan los dos los GIFs~~ **RESUELTO (2026-10-07)**:
  `construir-web.yml` ya no los genera ni se dispara al tocar `generar_gif.py`. Era peor que
  redundante: al estar en los `paths` del build, **cada push a un generador reescribía 22 MB
  de GIFs**. Medido: 7 versiones de los cinco ficheros ocupan 152 MB de historial, ~22 MB al día.
- **El escaneo de `docs/` llega a 3 niveles** (`*/*/*/index.html`) en sitemap, revisor
  de enlaces y buscador. Estaba en 2 y las 67 páginas de `en/mild-winter/<slug>/` se
  quedaban fuera de los tres sin que nada avisara. Si algún día hay páginas a 4, hay que
  tocar los tres sitios.
- **Una sección nueva no puede tumbar el build.** Cada bloque de `main()` que depende
  de un JSON tiene que comprobar que la clave está (`.get()`) y omitirse con un mensaje
  si falta, como hacen los estudios. El sello Mild Winter hacía `dos_caras["sello"]` y
  reventó `construir-web` entero con `KeyError` cuando el JSON de producción aún no
  traía esa clave: 400 páginas sin publicar por una sección nueva. Y al revés, **un dato
  que falta NO es un cero**: poner valores por defecto hizo que la landing publicara
  «0 station-seasons across 0 years» como si fuera un hallazgo. O está el dato, o no
  está el párrafo.
- **Una ficha `Dataset` sin `distribution` no es un dataset descargable.** `Dataset` da
  acceso a **Google Dataset Search**, un vertical aparte donde buscan investigadores y
  periodistas de datos. Pero sin `distribution` (un `DataDownload` con `contentUrl`) la
  ficha dice QUÉ hay y no DÓNDE, así que sale como mención y no como descarga. 58 de las
  60 estaban así; hoy están las **60**. Las 52 provinciales apuntan ya a su `datos.csv`, que la página enlazaba
  desde siempre; las de estudio, a los CSV que ahora se copian a `docs/datos/`.
  **Nunca declarar una URL que no exista**: Google la rastrea, no la encuentra y descarta
  el dataset entero — por eso `descarga()` devuelve `{}` y no un campo vacío cuando falta
  el fichero.
- **Nada de `aggregateRating`, y por eso tampoco `offers`.** Las cinco páginas con
  `WebApplication` (portada, confortómetro, observatorio, refugios-cerca-de-mi y la
  herramienta inglesa) llevaban un `Offer` de 0 €. Ese precio ficticio es lo que hace
  que Google evalúe la entidad como ficha de «Software App», cuyo rich result **exige**
  `aggregateRating` — de ahí el aviso «falta el campo aggregateRating». Ese campo son
  valoraciones reales de usuarios con su recuento: aquí no hay ninguna, así que ponerlo
  sería inventarse reseñas. Va contra las normas de datos estructurados de Google y
  contra la premisa del sitio. Se quitó el `offers`; `WebApplication` se queda porque es
  cierto.
- **Quedan 317 páginas compartiendo `og.png`** (las 52 provinciales ya no). Los 219
  certificados y los 67 Mild Winter tienen `og:image` propio pero **apuntando a un SVG**,
  que no vale ni para Google ni para WhatsApp: hay que rasterizar esos sellos.
- **Los 26 diplomas PNG de certificado no están en un `<img>`** en su propia página, solo
  como `href` de descarga y como `og:image`. Google puntúa mucho más una imagen que el
  visitante ve de verdad.
- **`/aumento-noches-tropicales-espana/` SE MANTIENE A MANO**, y es la única del sitio.
  Está publicada y enlazada desde el menú —y por tanto desde **308 páginas**— y en el
  sitemap, pero **ningún script del repo la escribe**: `generar_calculadora.py` solo la
  enlaza y `analisis_tendencia.py` solo produce `datos/tendencia_resumen.json`. Sobrevive
  porque `git add docs` nunca borra.
  **La regla «no tocar `docs/` a mano» no aplica aquí**, y conviene entender por qué: esa
  regla existe porque un cambio manual se pierde en el siguiente build. A esta página no
  la reconstruye nadie, así que no se pierde. Editarla a mano es lo correcto **mientras
  siga sin generador**.
  Decidido (2026-10-02): se trata como **estudio con edición anual**. Lleva el antetítulo
  «Estudio 2026», una nota de edición visible diciendo que las cifras son del análisis de
  agosto de 2026 y que se rehará al cerrar el verano de 2027, y la fecha y los scripts en
  metodología. Con fecha encima, que las cifras estén congeladas deja de ser un defecto.
  Por eso tampoco se meten `analisis_tendencia.py` ni `analisis_gradiente.py` en ningún
  cron: se ejecutan cuando toca rehacer la edición.
  **Pendiente, sin prisa**: mover su HTML a `generar_calculadora.py` como constante
  `PAGINA_TENDENCIA` (igual que las ~30 `PAGINA_*` que ya hay) cambiando `<nav>` y pie por
  `__NAV__` y `__FOOTER__`. El HTML ya fechado es exactamente el literal que entra, así
  que el trabajo a mano NO se tira. Hasta entonces, cualquier cambio en el menú o el pie
  del sitio **no llega a esta página**: hay que replicarlo a mano.
- **La cifra de una miniatura tiene que ser la que esa página YA publica.** Las inglesas
  llevan cada una su número (`PAGINAS_EN` en `generar_miniaturas.py`, con la columna
  `fuente` diciendo de dónde sale). La de `/en/spains-mildest-winters/` arrancó diciendo
  «0 frost nights in Alicante» —cierto, pero la página titula con otra métrica y otras
  ciudades: 10,3 noches a 5 °C en Málaga frente a 101,8 en Madrid—. Quien pulsa desde la
  miniatura aterriza en algo que no cuadra. Solo se vio al RENDERIZAR la página.
  **La comprobación automática se daba por hecha aquí pero NO existía en el código**;
  está desde 2026-10-07 en `cifra_en_su_pagina()` (`generar_miniaturas.py`), y a la
  primera ejecución cazó otras dos: la herramienta seguía diciendo «828 weather
  stations, nine winters» cuando ya no era un filtro de invierno, y
  `/en/frost-free-towns-spain/` decía «414 pueblos sin una helada en nueve inviernos»
  —puede ser cierto en el JSON, pero la página cuenta invierno a invierno y su cifra
  es otra (845 en 2025/26)—. Avisa y sigue: una miniatura vieja publicada es mala,
  tumbar el build por un aviso es peor. Iguala la coma decimal española con el punto
  inglés, o saltaría con razón aparente en «10,3».
- **`docs/en/stays/` son 7,2 MB** (60 ventanas × ~120 KB + catálogo) sobre los 90 MB que
  ya pesaba `docs/`. Por la red el visitante solo baja la ventana que pide (16-36 KB con
  gzip, que es lo que sirve Pages) más 13 KB de catálogo, así que el coste es de repo, no
  de página. Si algún día molesta, lo que sobra son las ventanas largas: para 90 y 182 días
  la frecuencia por años aporta menos que la mediana y el peor tramo.
- **`docs/en/winter-stations.json` ya no lo lee nadie.** Lo sigue escribiendo
  `analisis_invierno.py` y lo sigue commiteando `estudio-invierno.yml`, pero la herramienta
  pasó a `en/stays/`. Son 48 KB muertos; quitarlo es tocar los dos sitios a la vez.
- **Hay un segundo `CLAUDE.md` en `aemet-temperaturas/`**, de 2026-08-09, que describe 10
  workflows y ni la mitad de las páginas. El bueno es el de la raíz. Confunde a cualquiera
  —persona o modelo— que entre por esa carpeta.
- **El formato apaisado (1200×630) de las 8 inglesas desperdicia más de media imagen.**
  `componer_en()` da al mapa una caja de todo el ancho pero poca altura, y `dibujar_espana`
  encaja por el lado que limita: en 630 px de alto el mapa sale de ~290 px de ancho y deja
  dos franjas vacías. Es el `og:image`, o sea lo que se ve al compartir en WhatsApp o X.
  Arreglarlo es rehacer el reparto apaisado (mapa a un lado, texto al otro) y toca las ocho.
- **5 páginas declaran `dateModified` = día del build**, así que dicen que cambiaron hoy
  cada vez que corre `construir-web`, cambie su contenido o no. Son las que usan
  `iso_tz(date.today().isoformat())` en su JSON-LD (líneas 10852, 13379, 13686,
  14494 y 17056 de `generar_calculadora.py`): `dormir-con-manta-en-verano`,
  `hoteles-refugio-climatico`, `en/coolest-towns-spain`, `en/spains-mildest-winters`
  y `en/winter-in-spain-long-stay`. Las demás llevan una fecha explícita.
  **Es el mismo error que ya se arregló en el sitemap** —«un sitemap donde todo
  cambió ayer es un sitemap que Google acaba ignorando»— pero en los datos
  estructurados, y aquí es peor porque los dos se contradicen: el sitemap de esas
  cinco dice `2026-10-02` (su huella real en `lastmod.json`) mientras la página
  dice hoy. Detectado el 2026-10-10 porque un build de prueba movió sus cinco
  fechas de `2026-10-07` a `2026-10-10` sin tocar una sola palabra del contenido.
  **El arreglo no es copiar `_fecha_de()` tal cual**: la huella se calcula del HTML
  ya escrito, así que la fecha no se puede conocer mientras se escribe la página.
  Hay que parchear el JSON-LD en una segunda pasada, como hace `inyectar_miniatura`.
- **`TEMPLATE` es código muerto: 652 líneas y 41 KB.** Era la portada vieja; hoy la
  escribe `construir_pagina_beta()` y el único sitio que menciona `TEMPLATE` es un
  comentario que dice que se queda «como referencia por si portamos piezas». El
  riesgo no es el peso, es **confundir al que busca**: lleva su propio botón
  `id="geo"` con `getCurrentPosition`, sus propios estilos y su propia
  calculadora, así que un `grep` de cualquiera de esas cosas da seis resultados
  cuando solo cinco se ejecutan. Pasó el 2026-10-10 arreglando la geolocalización:
  parche aplicado a seis sitios, uno de ellos inerte. Si de verdad se quiere la
  referencia, que viva en un fichero aparte y no dentro del núcleo.
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
- `datos/horarias/AAAA/*.csv.gz` — lecturas horarias de ~856 estaciones, desde 2026-08-29.
  **Desde el 2026-09-02 cubre las 24 HORAS**, no solo la noche: al entrar el segundo cron
  el fichero diario pasó de ~100 KB a ~185 KB. 733 de 856 estaciones traen el día completo
  y la cobertura por campo es del 97-99 %. Es lo único que permite responder «cuántas
  HORAS estuvo la noche por debajo de 20°», frente a «cuánto bajó en el punto más frío»
  de los diarios — y ahora también la mitad diurna (isla de calor, amplitud real).
  Ojo: el 2026-09-04 le faltan las horas 01-12 UTC (ejecución perdida, irrecuperable).
- `datos/gradiente_nocturno.json` + `pares_estaciones.csv` — gradiente térmico nocturno
- `datos/tendencia_estaciones.csv` + `tendencia_resumen.json` — tendencia de noches tropicales
- `datos/estaciones_termicas.csv` + `estaciones_termicas.json` — estaciones del año térmicas
- `analisis/refugios_nocturnos_ranking.csv` — **la fuente de verdad de la web**; todo `docs/` se construye a partir de él
- `analisis/noches_por_anio.csv` — una fila por estación y **año natural completo** (no por
  verano): noches tropicales del año y las que caen en jun-ago, noches >22 y >25, racha
  máxima, mínima más baja y más alta con su fecha, P95, y primera y última noche tropical.
  Es la tabla sin medias y sin ventana astronómica.
- `analisis/curva_nocturna.csv` — una fila por **noche y estación** (ventana local 23:00-07:00):
  tipo de noche, forma de la curva, horas bajo 20/18/16 °C, hora del cruce de cada umbral y
  la serie hora a hora. Lo escribe `analisis_curva_nocturna.py` desde `datos/horarias/`.
- `analisis/horas_dormibles.csv` — el anterior colapsado **por estación**: mediana, peor y
  mejor de horas bajo 20°, noches sin un solo respiro y hora típica del cruce. Mediana y
  peor valor, nunca media: promediar una noche infernal con una buena inventa una templada.
- `analisis/invierno_por_temporada.csv` — una fila por estación y **temporada de
  invierno** (1 nov – 31 mar, etiquetada por el año de inicio): noches de calefacción
  (<10°), noches frías (<5°), heladas, días de terraza (tmax ≥18°), días de lluvia,
  rachas consecutivas, P05 de tmin y extremos con fecha. Lo escribe `analisis_invierno.py`.
- `analisis/invierno_por_estacion.csv` — el anterior por estación: mediana, peor y mejor
  temporada con su año, racha máxima sin terraza, temporadas sin una sola helada.
- `analisis/estancia_por_ventana.csv` — una fila por estación, **mes de llegada** y
  **duración** (7/14/30/90/182 días): mediana de días de terraza, noches de calefacción,
  heladas, tropicales y días de lluvia dentro de esa ventana, más el peor tramo sin un
  solo día de terraza. Lo escribe `analisis_estancia.py`. La ventana arranca el **día 1**
  del mes y un año solo cuenta si AEMET midió el 90 % de sus días.
- `analisis/noches_por_estacion.csv` — resumen por estación con **extremos, no promedios**:
  peor año y cuál fue, mejor año, último año, racha máxima real de la serie, P95, peor noche
  con fecha, y cuántas noches tropicales al año se pierden por mirar solo jun-ago

## Hallazgos clave del análisis hasta ahora

- Los **refugios nocturnos garantizados** son pueblos de montaña interior 600-1500 m, climas continentales secos: Sanabria, Puerto del Pico, Rascafría, Benasque, Vall de Boí, Beariz, Reinosa, Isaba...
- La **costa mediterránea** es de los PEORES sitios de España para dormir en verano: Palma, Cartagena, Capdepera con rachas de **86 noches tropicales consecutivas**.
- **La ventana jun-ago descarta el 21,4 % de las noches tropicales** del histórico.
  Septiembre (13,9 % del total) tiene MÁS que junio (12,1 %). En Canarias no captura
  ni la mitad: Hierro Aeropuerto publica 83 noches/año y tiene **170**; en 2023 tuvo
  204, del 3 de enero al 20 de diciembre, con una **racha real de 161 seguidas**.
  Comprobado que la ventana NO se está desplazando de forma detectable (R² de 0,01 a
  0,11 en nueve años): no es una deriva futura, ya está fuera. Los refugios apenas
  cambian —solo 2 de 192 pierden el criterio de <1 noche/año contando el año entero—;
  lo que está mal medido es el contraste, y en nuestra contra: los sitios malos son
  mucho peores de lo que publicamos.
- El **interior de Gran Canaria** (Tejeda, San Bartolomé de Tirajana) es el peor sitio de España para dormir, peor que la costa andaluza, por efecto foehn.
- **Alcalá de la Selva** (Teruel, sierra de Gúdar) tiene **0,5 noches tropicales/año** vs **72/año** en Valencia capital. Ratio 180:1.
- **La mínima no dice cuánto se duerme.** Con 22 noches horarias y 16.733 noches-estación:
  entre las noches cuya mínima fue de 19 °C, las horas por debajo de 20° van **de 1 a 9**
  (mediana 3; el 64 % se queda en 1-3 h). Con mínima de 18°, de 1 a 9 (mediana 5). Es decir:
  dos pueblos con la misma mínima publicada pueden haber tenido noches opuestas. Lo que
  decide es **a qué hora se cruza**: el 42 % de las noches ya empieza por debajo de 20° a
  las 23:00 —el único grupo con la noche entera fresca— y el 24,5 % no cruza nunca. Cruzar
  a las 05:00 equivale a no cruzar. Mediana nacional: 7,5 h de 9 bajo 20°, pero solo 4,5 h
  bajo 18°. **31 estaciones no bajaron de 20° ni una hora en ninguna de las 22 noches**
  (Cabo de Gata, Capdepera, Cádiz, y media Canarias).
- **La duración de la estancia cambia la respuesta, no solo la confianza.** Llegando el
  1 de noviembre a Huelva: una quincena da **14 días de terraza de 14**; tres meses dan
  **53 de 90, con un tramo de 25 días seguidos sin ninguno** y 60 noches de calefacción.
  Sevilla: 14 de 14 y luego 44 de 90 con **32 días seguidos**. Con quince días no se
  distinguen —todo el sur da 14 de 14—; con noventa, el orden se da la vuelta. Medido con
  el mismo filtro (terrazas en el 86 % de los días, calefacción como mucho un tercio),
  **117 estaciones de península valen para la quincena y exactamente 1 para el trimestre**
  (El Ejido, y solo cumplió 2 de sus 6 años). Es el argumento de `/en/find-your-winter-address/`.
- **La mediana dice cómo suele ir; tú solo vienes una vez.** Punta Galea tiene mediana de
  **0 noches tropicales** en una quincena de julio y en uno de los nueve años tuvo **9 de
  14**. Por eso la herramienta publica además en cuántos de los años medidos habrían
  cumplido TODOS los umbrales a la vez, y no solo la mediana.
- **El invierno suave y el verano dormible son incompatibles en la península.**
  Cruzando las dos series (837 estaciones), la correlación de Spearman entre noches de
  calefacción en invierno y noches tropicales en verano es **−0,70**. En península lo que
  se puede pedir es: verano de 0-1 noches tropicales → Estaca de Bares, pero **75 noches
  de calefacción** y 14 días de terraza; invierno de 4-9 noches de calefacción → Cabo de
  Gata o Ceuta, pero **77 y 59 noches tropicales**. Málaga: 24 noches de calefacción y
  78,7 tropicales. **Solo dos estaciones de España cumplen las dos cosas** (≤40 calefacción
  y ≤5 tropicales) y las dos son canarias: **San Andrés y Sauces** (La Palma, 362 m: 0
  noches de calefacción, 3,2 tropicales — pero 51 días de lluvia y solo 104 de terraza) y
  **Tías** (Lanzarote, 376 m: 3 y 4,3, con 121 días de terraza y 18 de lluvia). Mención
  aparte para **Lomo del Balo** (Tenerife): 0 calefacción, 144 días de terraza, 10 de
  lluvia, con 5-15 tropicales.
- **En invierno no hay meses hombro.** Noviembre y marzo son el 40,4 % de los días de la
  temporada y se llevan el 37,2 % de las noches de calefacción (×0,92 su cuota): el frío
  general no se concentra en dic-feb. La helada sí (22,8 %, ×0,56). Es lo contrario de lo
  que pasa en verano con jun-ago, y desmonta la idea de que noviembre y marzo sean
  templados. **155 estaciones no han tenido una sola helada** en ninguna temporada.
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
- ~~Press kit PDF de 2 páginas~~ **HECHO (2026-10-09)**: `generar_presskit.py` →
  `/prensa/kit/`, dos A4 que se guardan en PDF desde el navegador. Y
  `generar_pitch.py`, que escribe el correo de presentación con la cifra de CADA
  provincia — el contraste de dentro de una provincia (Valencia: Utiel 1,0 contra
  Miramar 77,1) es mejor titular local que cualquier cifra nacional.
- Lista de ~20-25 periodistas españoles (clima/medio ambiente, nacionales + regionales)
- Plan de lanzamiento coordinado
- Envío de los certificados a los ayuntamientos (backlinks institucionales + prensa local)

**Pendiente inmediato — archivo horario (acordado el 2026-08-29):**
- ~~Primer ensayo con las noches acumuladas~~ **HECHO (2026-09-23)**: `analisis_curva_nocturna.py`
  sobre 22 noches completas de 26 archivadas. Ver el hallazgo «la mínima no dice cuánto se
  duerme» más arriba.
- ~~Llevarlo a la web~~ **HECHO (2026-09-23)**: landing `/cuantas-horas-se-duerme-en-verano/`,
  con `estudio-horario.yml` semanal refrescando las cifras. **Cuidado con el encuadre**: son
  22 noches de final de verano, no un año. La página lo dice; cualquier cifra que se saque de
  ahí a otra página tiene que decirlo también. Las tarjetas por provincia esperan a tener un
  verano entero: hoy dirían «así fueron estas 22 noches», no «así es este pueblo».
- ~~**Rediseñar los cron para cubrir la noche**~~ **HECHO**: `archivo-horario.yml` con
  cron a 23:30, 02:30 y 05:30 UTC, más el 07:15 del parte. Cuatro pasadas: dos cubren la
  ventana de sueño entera y dos a trozos. Contexto original de la decisión:
- ~~**Rediseñar los cron para cubrir la noche, no solo duplicarla.**~~ Los dos actuales
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
python scripts/estudio_colores.py
python scripts/generar_miniaturas.py      # ANTES que la calculadora
python scripts/generar_calculadora.py     # escribe ../docs/ completo
python scripts/generar_pagina_mapa.py
python scripts/generar_presskit.py        # el dosier, con las cifras de hoy

# Los GIFs van aparte desde 2026-10-07: ya no son parte del build, y su
# workflow solo corre de junio a septiembre.
python scripts/generar_gif.py                          # temporada cálida del año más reciente
python scripts/generar_gif.py --anio 2026              # rehacer una edición pasada
python scripts/generar_gif.py --desde 2026-06-01 --hasta 2026-09-30

# Prensa: dosier y correos de presentación
python scripts/generar_presskit.py                       # escribe docs/prensa/kit/
python scripts/generar_pitch.py --provincia Teruel       # correo regional
python scripts/generar_pitch.py --tipo nacional          # correo a sección de clima
python scripts/generar_pitch.py --tipo datos             # correo a unidad de datos
python scripts/generar_pitch.py --listar                 # provincias por contraste

# Ventanas de estancia (mes x duración) — rehace docs/en/stays/
python scripts/analisis_estancia.py
python scripts/analisis_estancia.py --sin-json   # solo el CSV, sin tocar docs/

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
