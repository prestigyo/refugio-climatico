#!/usr/bin/env python3
"""
El press kit: dos páginas para un periodista con prisa.

Escribe docs/prensa/kit/ — una página pensada para IMPRIMIRSE o guardarse en
PDF desde el navegador (Ctrl+P), no para navegarse. Por eso lleva su propio
CSS de impresión, sin menú ni pie, y cabe en dos hojas A4.

POR QUÉ UNA PÁGINA Y NO UN PDF SUBIDO A MANO. Un PDF estático se queda viejo
el día que cambia una cifra, y aquí las cifras se recalculan solas cada mes.
Esta página LEE los ficheros de análisis en cada ejecución, así que lo que
dice es lo que dicen los datos hoy. La regla del proyecto —nada publicado que
no salga de un script— no es burocracia: es lo que impide mandarle a un
periodista un número que ya no es verdad.

QUÉ LLEVA, y por qué en este orden. Un periodista de clima recibe muchos
dosieres. Lo que decide si te hace caso no son las cifras, es si puede
fiarse de ellas y comprobarlas en cinco minutos:

  1. Qué es esto y de dónde salen los datos (AEMET, abiertos, citables).
  2. Las cifras, CADA UNA con el fichero del que sale.
  3. Lo que no ha publicado nadie — el gancho.
  4. Qué puede descargar y usar, con URL.
  5. LAS LIMITACIONES, literales del propio análisis. Esto es lo que
     distingue un dosier de una nota de prensa: decirle por adelantado qué
     NO puede afirmar con estos datos. Diez veranos no son una tendencia
     climática y no permiten atribuir nada al cambio climático; va escrito.
  6. Contacto.

Uso:
    python scripts/generar_presskit.py
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from datetime import date
from pathlib import Path

# SIN pandas a propósito: este script corre dentro de construir-web.yml, que
# instala solo pillow y numpy porque ningún otro generador necesita más. Meter
# pandas en la construcción diaria por cuatro medianas y dos sumas sería pagar
# la instalación todos los días para nada. Con csv y statistics basta.

ROOT = Path(__file__).resolve().parent.parent
ANALISIS = ROOT / "analisis"
DATOS = ROOT / "datos"
DOCS = ROOT.parent / "docs"
SITIO = "https://nochetropical.es"


def url(ruta: str = "") -> str:
    """La URL, escrita a la vista y además pulsable.

    El dosier se lee de dos maneras que se excluyen si se elige una sola:
    IMPRESO —o guardado en PDF—, donde la dirección tiene que estar escrita
    porque el papel no se pulsa, y EN EL NAVEGADOR en /prensa/kit/, donde un
    periodista da por hecho que puede pulsarla. Estaban las siete como texto
    plano, o sea resuelto solo el primer caso. Un <a> cuyo texto es la propia
    URL resuelve los dos: en papel se lee, en pantalla se pulsa, y no hay que
    repetir la dirección entre paréntesis.
    """
    return f'<a class="mono" href="{SITIO}{ruta}">{SITIO}{ruta}</a>'


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def num(x: float, dec: int = 0) -> str:
    """Cifra en castellano: punto de millar, coma decimal."""
    s = f"{x:,.{dec}f}"
    return s.replace(",", " ").replace(".", ",")


def cifras() -> dict:
    """Todas las cifras del kit, leídas de su fichero. Si falta alguno, se
    para: un dosier con un hueco es peor que no mandarlo."""
    faltan = [f for f in ("analisis/refugios_nocturnos_ranking.csv",
                          "analisis/noches_por_estacion.csv",
                          "analisis/horas_dormibles.csv",
                          "datos/tendencia_resumen.json",
                          "datos/gradiente_nocturno.json")
              if not (ROOT / f).exists()]
    if faltan:
        sys.exit("Faltan ficheros de análisis: " + ", ".join(faltan))

    def leer(ruta: Path) -> list[dict]:
        with ruta.open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def flot(fila: dict, campo: str) -> float:
        try:
            return float(fila.get(campo, "") or 0)
        except ValueError:
            return 0.0

    r = leer(ANALISIS / "refugios_nocturnos_ranking.csv")
    n = leer(ANALISIS / "noches_por_estacion.csv")
    h = leer(ANALISIS / "horas_dormibles.csv")
    t = json.loads((DATOS / "tendencia_resumen.json").read_text("utf-8"))
    g = json.loads((DATOS / "gradiente_nocturno.json").read_text("utf-8"))

    def una(patron: str) -> tuple[str, float]:
        for fila in r:
            if patron in str(fila["nombre"]).upper():
                return str(fila["nombre"]).title(), flot(fila, "noches_trop_anio")
        return patron.title(), float("nan")

    total = sum(flot(x, "noches_trop_anio_medio") for x in n)
    fuera = sum(flot(x, "noches_fuera_jja_anio") for x in n)
    alt = t["por_altitud"]
    return {
        "estaciones": len(r),
        "anio_ini": t["periodo"]["anio_ini"], "anio_fin": t["periodo"]["anio_fin"],
        "bajo_una": sum(1 for x in r if flot(x, "noches_trop_anio") < 1),
        "cero": sum(1 for x in r if flot(x, "noches_trop_anio") == 0),
        "frio": una("CEDRILLAS"), "calor": una("VALENCIA AEROPUERTO"),
        "pct_fuera": fuera / total * 100,
        "suben": t["global"]["n_suben"], "bajan": t["global"]["n_bajan"],
        "n_tendencia": t["estaciones"]["validas"],
        "llano": alt["<200"]["pendiente_media"],
        "montana": alt["800-1200"]["pendiente_media"],
        "gradiente": g["global"]["descenso_c_por_100m"],
        "gradiente_r2": g["global"]["r2"],
        "pares": g["global"]["n_pares"], "inversiones": g["n_inversiones_puras"],
        "h_estaciones": len(h),
        "h_noches": int(statistics.median(flot(x, "noches") for x in h)),
        "h20": statistics.median(flot(x, "h20_mediana") for x in h),
        "h18": statistics.median(flot(x, "h18_mediana") for x in h),
        "h_nunca": sum(1 for x in h if flot(x, "h20_mejor") == 0),
        "limitaciones": t["limitaciones"],
    }


CSS = """
:root{--tinta:#1a1208;--suave:#6b5b45;--teja:#b5502a;--linea:#d8ccb8;
      --papel:#fdfbf7;--caja:#f4efe5}
*{margin:0;padding:0;box-sizing:border-box}
body{background:#8a7f6d;font:15px/1.55 Lora,Georgia,serif;color:var(--tinta);
     padding:26px 14px}
.hoja{background:var(--papel);max-width:830px;margin:0 auto 24px;
      padding:46px 54px 40px;box-shadow:0 10px 36px rgba(0,0,0,.26)}
h1{font:700 30px/1.15 Fraunces,Georgia,serif;margin:0 0 8px;letter-spacing:-.01em}
h2{font:700 16px/1.3 Fraunces,Georgia,serif;margin:28px 0 10px;color:var(--teja);
   text-transform:uppercase;letter-spacing:.07em;font-size:12.5px}
h3{font:700 16.5px/1.35 Fraunces,Georgia,serif;margin:16px 0 3px}
p{margin:0 0 11px}
a{color:var(--teja)}
.kick{font:600 11px/1 system-ui,sans-serif;letter-spacing:.16em;
      text-transform:uppercase;color:var(--suave);margin-bottom:14px}
.entrada{font-size:17px;line-height:1.55;color:#2e2316;margin-bottom:4px}
.regla{height:3px;background:var(--teja);width:74px;margin:16px 0 22px}
.rej{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0 6px}
.dato{background:var(--caja);border-left:3px solid var(--teja);padding:11px 13px}
/* SOLO el primer <b> es la cifra gigante. Sin `>b:first-child`, cualquier
   negrita del texto de apoyo heredaba el tamaño de titular y la tarjeta se
   leía como si tuviera tres cifras. */
.dato>b:first-child{display:block;font:700 25px/1.05 Fraunces,Georgia,serif;
                    color:var(--teja)}
.dato span{display:block;font-size:12.5px;line-height:1.42;margin-top:4px}
.dato span b{font-weight:600;color:inherit;font-family:inherit;font-size:inherit}
.dato i{display:block;font:400 10.5px/1.3 system-ui,sans-serif;color:var(--suave);
        font-style:normal;margin-top:6px}
ul{margin:0 0 12px 18px}
li{margin-bottom:6px}
.aviso{background:#fbf4e8;border:1px solid #e3cfa8;padding:14px 16px;
       font-size:13.2px;line-height:1.55}
.aviso b{color:#8a5a12}
.pie{border-top:1px solid var(--linea);margin-top:26px;padding-top:12px;
     font-size:12px;color:var(--suave);display:flex;justify-content:space-between;
     gap:14px;flex-wrap:wrap}
.mono{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:12px}
.imprimir{position:fixed;top:14px;right:16px;background:var(--teja);color:#fff;
          border:0;border-radius:999px;padding:11px 20px;font:600 14px system-ui,
          sans-serif;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.3)}
@media(max-width:700px){.rej{grid-template-columns:1fr 1fr}.hoja{padding:30px 22px}}
/* Por debajo de 420 px no caben dos columnas: medido, el dosier se arrastraba
   de lado en una ventana de 360 (437 px de scroll). Una sola columna. */
@media(max-width:420px){.rej{grid-template-columns:1fr}.hoja{padding:24px 16px}}
@media print{
  @page{size:A4;margin:14mm 15mm}
  body{background:#fff;padding:0;font-size:10.2pt;line-height:1.42}
  .hoja{box-shadow:none;max-width:none;margin:0;padding:0;background:#fff}
  .imprimir{display:none}
  h1{font-size:21pt}h2{font-size:9pt;margin:13pt 0 5pt}h3{font-size:11pt}
  .entrada{font-size:11pt}
  .dato>b:first-child{font-size:15pt}.dato span{font-size:8.6pt}.dato i{font-size:7.2pt}
  .rej{gap:7pt}.dato{padding:6pt 8pt}
  .salto{break-before:page}
  .aviso{font-size:8.8pt;padding:8pt 10pt}
  a.mono{color:var(--tinta);text-decoration:none}
  p,li{orphans:3;widows:3}
}
"""


def html(c: dict) -> str:
    hoy = date.today()
    fecha = f"{hoy.day} de {MESES[hoy.month-1]} de {hoy.year}"
    veranos = c["anio_fin"] - c["anio_ini"] + 1
    frio_n, frio_v = c["frio"]
    calor_n, calor_v = c["calor"]

    dato = (lambda v, txt, fuente:
            f'<div class="dato"><b>{v}</b><span>{txt}</span>'
            f'<i>{fuente}</i></div>')

    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dosier de prensa · NocheTropical.es</title>
<meta name="robots" content="noindex">
<meta name="description" content="Dosier de prensa de NocheTropical.es: {c['estaciones']} estaciones de AEMET, {veranos} veranos, dónde se duerme fresco en España y dónde no.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,700&family=Lora:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body>
<button class="imprimir" onclick="window.print()">Guardar en PDF</button>

<div class="hoja">
  <div class="kick">Dosier de prensa · {fecha}</div>
  <h1>Dónde se duerme fresco en España, y dónde no</h1>
  <p class="entrada"><b>NocheTropical.es</b> analiza {veranos} veranos de datos
  abiertos de AEMET ({c['anio_ini']}&#8211;{c['anio_fin']}) en
  <b>{c['estaciones']} estaciones</b> para responder una pregunta que el
  termómetro del telediario no responde: cuántas noches al año no se baja de
  20&nbsp;°C, y en qué pueblos no pasa nunca.</p>
  <div class="regla"></div>

  <h2>Las cifras</h2>
  <div class="rej">
    {dato(num(c['bajo_una']), 'estaciones no llegan a <b>una</b> noche tropical al año. De ellas, ' + num(c['cero']) + ' no han tenido ninguna.', 'refugios_nocturnos_ranking.csv')}
    {dato(f"{num(frio_v,1)} vs {num(calor_v,1)}", f'noches tropicales al año en <b>{frio_n}</b> (Teruel) frente a <b>{calor_n}</b>. Mismo país, dos veranos.', 'refugios_nocturnos_ranking.csv')}
    {dato(f"{num(c['pct_fuera'],1)}&nbsp;%", 'de las noches tropicales caen <b>fuera de junio-agosto</b>, la ventana con la que se suele medir el verano.', 'noches_por_estacion.csv')}
    {dato(f"{num(c['suben'])}/{num(c['n_tendencia'])}", f"estaciones con más noches tropicales que hace {veranos} años. Bajan {num(c['bajan'])}.", 'tendencia_resumen.json')}
    {dato(f"+{num(c['llano'],1)} vs +{num(c['montana'],1)}", 'noches más al año por debajo de 200&nbsp;m frente a entre 800 y 1.200&nbsp;m. <b>La brecha se abre.</b>', 'tendencia_resumen.json')}
    {dato(f"{num(c['gradiente'],2)}&nbsp;°C", f"es lo que baja la mínima por cada 100&nbsp;m de altitud — no los 0,6 del manual. R²&nbsp;=&nbsp;{num(c['gradiente_r2'],2)} sobre {c['pares']} pares.", 'gradiente_nocturno.json')}
  </div>

  <h2>Tres cosas que no ha publicado nadie</h2>

  <h3>1. Medimos el verano con la ventana equivocada</h3>
  <p>Los resúmenes estivales suelen contar de junio a agosto. Esa ventana deja
  fuera el <b>{num(c['pct_fuera'],1)}&nbsp;%</b> de las noches tropicales del
  histórico, y septiembre acumula más que junio. No es una deriva futura: ya
  está ocurriendo, y juega en contra del dato publicado — los sitios malos son
  peores de lo que dicen las cifras al uso.</p>

  <h3>2. La mínima no dice cuánto se duerme</h3>
  <p>AEMET borra la observación horaria a las pocas horas y no publica
  histórico, así que este proyecto la <b>archiva desde agosto de 2026</b>: hoy
  son {num(c['h_estaciones'])} estaciones con una mediana de {c['h_noches']}
  noches completas. Con ese dato se ve lo que una mínima esconde: dos pueblos
  con el mismo mínimo publicado pueden haber tenido noches opuestas, porque lo
  que decide es <b>a qué hora se cruza el umbral</b>. De nueve horas de noche,
  la mediana nacional son <b>{num(c['h20'],1)}&nbsp;h</b> por debajo de
  20&nbsp;°C, pero solo <b>{num(c['h18'],1)}&nbsp;h</b> por debajo de 18.
  En <b>{num(c['h_nunca'])}</b> estaciones ni la mejor noche del archivo bajó
  de 20&nbsp;°C ni una sola hora.</p>

  <h3>3. La altitud no te salva por sí sola</h3>
  <p>El gradiente nocturno real medido entre pares de estaciones cercanas es de
  <b>{num(c['gradiente'],2)}&nbsp;°C por cada 100&nbsp;m</b>, bastante menos que
  el valor de manual. Y en <b>{c['inversiones']} de {c['pares']} pares</b> el
  pueblo alto duerme <i>peor</i> que el bajo: el aire frío se acumula en el
  fondo del valle. Subir a la sierra no garantiza nada; hay que mirar la
  estación.</p>

  <div class="pie">
    <span>NocheTropical.es · Ramón J. Lowesting</span>
    {url()}
  </div>
</div>

<div class="hoja salto">
  <h2>Qué podéis usar</h2>
  <p>Todo el material es reutilizable citando <b>«Fuente: AEMET ·
  NocheTropical.es»</b>. Los datos originales son de AEMET y están bajo su
  licencia de datos abiertos.</p>
  <ul>
    <li><b>Sala de prensa</b>, con titulares sugeridos, mapas en alta y GIFs
      listos para publicar: {url("/prensa/")}</li>
    <li><b>Los datos en bruto</b>, en CSV descargable desde cada página y desde
      {url("/metodologia/")}</li>
    <li><b>Mapa interactivo</b> de las {c['estaciones']} estaciones:
      {url("/mapa-estaciones/")}</li>
    <li><b>Ficha por provincia</b> — hay una por cada una de las 52, con su
      ranking y su CSV: {url("/teruel/")},
      {url("/valencia/")}&#8230;</li>
    <li><b>Informe a medida</b> de cualquier estación o municipio, si lo
      necesitáis para una pieza concreta. Se genera en el día.</li>
  </ul>

  <h2>Cómo está hecho</h2>
  <ul>
    <li><b>Noche tropical</b>: aquella cuya temperatura mínima no baja de
      20&nbsp;°C. Se cuenta sobre los valores climatológicos diarios de AEMET
      OpenData, estación por estación.</li>
    <li><b>Nada interpolado.</b> Cada cifra sale de un termómetro real. Si un
      pueblo no tiene estación, se dice de cuál es el dato y a qué distancia
      está — no se inventa un valor para el municipio.</li>
    <li><b>Sin medias cuando la media engaña.</b> Se usan medianas, percentiles,
      rachas consecutivas y conteos por umbral. Promediar un verano infernal
      con uno suave inventa un verano templado que no existió.</li>
    <li><b>Reproducible.</b> Todo el proceso es código abierto: cualquiera puede
      ejecutarlo y obtener las mismas cifras. Este dosier las lee de los
      ficheros de análisis cada vez que se genera.</li>
  </ul>

  <h2>Lo que estos datos NO dicen</h2>
  <div class="aviso">
    <p><b>Esto no es una tendencia climática y no permite atribuir nada al
    cambio climático.</b> {c['limitaciones']}</p>
    <p style="margin-bottom:0">Lo decimos antes de que lo preguntéis porque es
    la diferencia entre un dato publicable y uno que no lo es. Aquí no se
    publica ninguna cifra que no se haya podido comprobar en la fuente: si
    alguna no aparece en el sitio, suele ser por eso.</p>
  </div>

  <h2>Contacto</h2>
  <p>Ramón J. Lowesting &#183; proyecto <b>Refugio Climático</b><br>
  Formulario de prensa y contacto directo en
  {url("/prensa/")}<br>
  Disponible para entrevistas, datos a medida y comprobación de cifras.</p>

  <div class="pie">
    <span>Dosier generado el {fecha} · las cifras se recalculan con cada
      actualización del análisis</span>
    {url("/prensa/kit/")}
  </div>
</div>
</body></html>
"""


def main() -> int:
    c = cifras()
    destino = DOCS / "prensa" / "kit"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "index.html").write_text(html(c), encoding="utf-8")
    print("Dosier de prensa")
    print(f"   {destino.relative_to(DOCS.parent)}/index.html")
    print(f"   {c['estaciones']} estaciones · {c['anio_ini']}-{c['anio_fin']} · "
          f"{c['bajo_una']} por debajo de una noche al año")
    print(f"   fuera de jun-ago: {c['pct_fuera']:.1f} % · suben {c['suben']} "
          f"de {c['n_tendencia']}, bajan {c['bajan']}")
    print(f"   archivo horario: {c['h_estaciones']} estaciones, "
          f"{c['h20']:.1f} h bajo 20° de 9 (mediana)")
    print("   Para el PDF: abrir la página y pulsar «Guardar en PDF» (Ctrl+P)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
