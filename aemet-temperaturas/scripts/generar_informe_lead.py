#!/usr/bin/env python3
"""
Genera el INFORME de zona que promete el formulario de leads ("Quiero el
informe + alertas de calor"): un HTML autocontenido, listo para adjuntar por
correo, con el dato de la estación consultada, su contexto provincial y
nacional, y los refugios climáticos más cercanos.

Lee   : aemet-temperaturas/analisis/refugios_nocturnos_ranking.csv
Escribe: aemet-temperaturas/analisis/informes/informe-<slug>.html

Uso:
    python scripts/generar_informe_lead.py --estacion 8293X
    python scripts/generar_informe_lead.py --buscar xativa

Reproducible: mismo CSV -> mismo informe. Tipografías Fraunces + Lora y
paleta cálida, según las convenciones de informes del proyecto.
"""
from __future__ import annotations

import argparse
import math
from datetime import date
from pathlib import Path

import generar_calculadora as g


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


PLANTILLA = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Informe de noches tropicales · __LOC__ (__PROV__)</title>
<meta name="robots" content="noindex, follow">
<link rel="canonical" href="__SITE__/informes/__SLUG__/">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&family=Lora:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">
<style>
 :root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--verde:#8fb07a;--rojo:#cf6b54;--fd:"Fraunces",Georgia,serif;--fb:"Lora",Georgia,serif;--fm:ui-monospace,monospace}
 *{margin:0;padding:0;box-sizing:border-box}
 body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.65;-webkit-font-smoothing:antialiased}
 .wrap{max-width:720px;margin:0 auto;padding:0 24px}
 a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}
 header{padding:36px 0 8px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}
 .kick{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--teja);font-weight:600;margin-bottom:12px}
 h1{font-family:var(--fd);font-weight:900;font-size:clamp(30px,6vw,44px);line-height:1.06}
 h1 em{font-style:italic;color:var(--teja2)}
 .fecha{color:var(--muted);font-size:13.5px;margin-top:12px}
 section{padding:26px 0}
 h2{font-family:var(--fd);font-weight:700;font-size:clamp(20px,3.6vw,25px);margin:0 0 12px}
 p{color:var(--muted);font-size:15.5px;margin:0 0 14px}
 p b{color:var(--paper)}
 .dato{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:18px;padding:26px;text-align:center;margin:18px 0}
 .dato .big{font-family:var(--fm);font-weight:700;font-size:clamp(44px,10vw,64px);line-height:1;color:__COLBANDA__}
 .dato .lbl{color:var(--muted);font-size:14px;margin-top:6px}
 .v{display:inline-block;font-weight:600;font-size:12px;padding:6px 12px;border-radius:999px;margin-top:12px;color:__COLBANDA__;background:__BGBANDA__;letter-spacing:.06em;text-transform:uppercase}
 table{width:100%;border-collapse:collapse;font-size:14.5px;margin:8px 0}
 th,td{text-align:left;padding:10px 10px;border-bottom:1px solid var(--line)}
 th{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
 th.r,td.n{text-align:right}
 td.n{font-family:var(--fm);font-weight:700}
 td.loc{font-weight:600}
 .descarga{display:inline-block;background:var(--teja);color:#1a1209;font-weight:700;padding:12px 20px;border-radius:11px;font-family:var(--fb);margin:6px 0}
 .descarga:hover{background:var(--teja2);text-decoration:none}
 .metodo{border-left:3px solid var(--teja);background:var(--bg2);border-radius:0 12px 12px 0;padding:16px 18px;margin-top:8px}
 .metodo p{font-size:13.5px;margin:0}
 __NAVCSS__
 __FOOTERCSS__
</style>
</head>
<body>
__NAV__
<header><div class="wrap">
  <div class="kick">Informe de zona · nochetropical.es</div>
  <h1>¿Se duerme bien en <em>__LOC__</em>?</h1>
  <p class="fecha">__PROV__ · estación de AEMET a __ALT__ m de altitud · elaborado en __FECHA__ con datos de los veranos 2017–2026</p>
</div></header>

<section><div class="wrap">
  <div class="dato">
    <div class="big">__NT__</div>
    <div class="lbl">noches tropicales al año, de media (mínima que no baja de 20&nbsp;°C)</div>
    <span class="v">__BANDA__</span>
  </div>
  <p>__LECTURA__</p>
  <p>En el conjunto de España, la estación de __LOC__ registra más calor nocturno que el <b>__PCT__&nbsp;%</b> de las __TOTAL__ estaciones de AEMET analizadas. Además de las noches tropicales, suma <b>__NE__ noches ecuatoriales</b> al año (mínima que no baja de 25&nbsp;°C), y su temperatura mínima media de verano es de <b>__TMIN__&nbsp;°C</b>.</p>
</div></section>

<section><div class="wrap">
  <h2>Tu provincia, en contexto</h2>
  <p>__CONTEXTO_PROV__</p>
  <table>
    <thead><tr><th>Estación (__PROV__)</th><th class="r">Altitud</th><th class="r">Noches trop./año</th></tr></thead>
    <tbody>__TABLA_PROV__</tbody>
  </table>
</div></section>

<section><div class="wrap">
  <h2>Tus refugios climáticos más cercanos</h2>
  <p>Estaciones de AEMET con <b>menos de 1 noche tropical al año</b> — donde la noche refresca con fiabilidad incluso en pleno verano — ordenadas por distancia en línea recta desde __LOC__:</p>
  <table>
    <thead><tr><th>Refugio</th><th>Provincia</th><th class="r">Altitud</th><th class="r">Distancia</th></tr></thead>
    <tbody>__TABLA_REF__</tbody>
  </table>
  <p>La ruta y el detalle de cada uno, en <a href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/">nochetropical.es/refugios-climaticos-naturales-cerca-de-mi</a>.</p>
</div></section>

<section><div class="wrap">
  <h2>Los datos, día a día</h2>
  <p>Descárgate los <b>__NDIAS__ días</b> de datos diarios de esta estación (mínima, máxima, media y precipitación, 2017–2026) más un resumen anual calculado, en una hoja de cálculo:</p>
  <a class="descarga" href="datos.xlsx" download>⬇ Descargar los 10 años en Excel</a>
</div></section>

<section><div class="wrap">
  <h2>Sigue tu zona</h2>
  <p>· El mapa completo de tu provincia: <a href="__SITE__/__SLUGPROV__/">nochetropical.es/__SLUGPROV__</a><br>
  · La ola de calor, día a día: <a href="__SITE__/ola-de-calor/">nochetropical.es/ola-de-calor</a><br>
  · Vota cómo se siente tu zona en <b>el Confortómetro</b>, nuestro estudio participativo: <a href="__SITE__/confortometro/">nochetropical.es/confortometro</a><br>
  · Destinos frescos medidos por AEMET: <a href="__SITE__/dormir-con-manta-en-verano/">nochetropical.es/dormir-con-manta-en-verano</a></p>
  <div class="metodo"><p><b>Metodología.</b> Una noche tropical es aquella en que la temperatura mínima no baja de 20&nbsp;°C; una ecuatorial, de 25&nbsp;°C. Datos diarios de AEMET OpenData, veranos (junio–agosto) de 2017 a 2026, para estaciones con al menos 3 veranos y 60 días de mínima por verano. El dato es de la estación, no del municipio entero: en zonas de montaña la noche cambia mucho en pocos kilómetros. Distancias en línea recta.</p></div>
</div></section>

__FOOTER__
</body>
</html>
"""


def construir_informe(est: dict, estaciones: list, total: int, ndias: int) -> str:
    site = g.SITE_URL.rstrip("/")
    banda, col, bg = g.bandas_py(est["nt"])
    pct = round(100 * sum(1 for e in estaciones if e["nt"] < est["nt"]) / total)
    misma_prov = sorted((e for e in estaciones if e["prov"] == est["prov"]),
                        key=lambda x: x["nt"])
    mejor, peor = misma_prov[0], misma_prov[-1]

    if est["nt"] >= 30:
        lectura = (f"El termómetro lo dice claro: en <b>{est['loc']}</b>, más de un tercio de las "
                   f"noches de verano no baja de los 20&nbsp;°C. Son noches en las que el cuerpo "
                   f"no descansa del todo — y la buena noticia es que a poca distancia hay zonas "
                   f"donde eso prácticamente no ocurre nunca.")
    elif est["nt"] >= 10:
        lectura = (f"En <b>{est['loc']}</b> el verano se nota de noche, aunque sin llegar a los "
                   f"registros de la costa: hay margen para dormir bien muchas noches, y "
                   f"alternativas frescas cerca para las peores rachas.")
    else:
        lectura = (f"Enhorabuena: <b>{est['loc']}</b> está entre las zonas donde mejor se duerme "
                   f"en verano. Las noches tropicales son la excepción, no la regla.")

    contexto = (f"De la más fresca a la más calurosa, así queda {est['prov']}: en "
                f"<b>{mejor['loc']}</b> ({g.miles(mejor['alt'])} m) se cuentan "
                f"{g.ntfmt(mejor['nt'])} noches tropicales al año, mientras que "
                f"<b>{peor['loc']}</b> llega a {g.ntfmt(peor['nt'])}. "
                f"Tu estación, <b>{est['loc']}</b>, ocupa el puesto "
                f"{[e['id'] for e in misma_prov].index(est['id']) + 1} de {len(misma_prov)} "
                f"en la provincia.")

    filas_prov = []
    for e in misma_prov[:3] + ([est] if est["nt"] > misma_prov[2]["nt"] else []):
        marca = " ← tu zona" if e["id"] == est["id"] else ""
        filas_prov.append(
            f'<tr><td class="loc">{e["loc"]}{marca}</td>'
            f'<td class="n">{g.miles(e["alt"])} m</td>'
            f'<td class="n">{g.ntfmt(e["nt"])}</td></tr>')

    refugios = sorted((e for e in estaciones if e["nt"] < 1),
                      key=lambda e: haversine_km(est["lat"], est["lon"], e["lat"], e["lon"]))
    filas_ref = []
    for e in refugios[:6]:
        km = haversine_km(est["lat"], est["lon"], e["lat"], e["lon"])
        filas_ref.append(
            f'<tr><td class="loc">{e["loc"]}</td><td>{e["prov"]}</td>'
            f'<td class="n">{g.miles(e["alt"])} m</td>'
            f'<td class="n">{km:.0f} km</td></tr>')

    sl = g.slug(est["loc"])
    return (PLANTILLA
            .replace("__NAVCSS__", g.CSS_NAV_ESCUETO)
            .replace("__FOOTERCSS__", g.CSS_FOOTER_ESCUETO)
            .replace("__NAV__", g.nav_escueto_html(site))
            .replace("__FOOTER__", g.footer_escueto_html(
                site, "Informe reproducible, generado por script a partir de datos públicos de AEMET"))
            .replace("__SLUG__", sl)
            .replace("__LOC__", est["loc"])
            .replace("__PROV__", est["prov"])
            .replace("__ALT__", g.miles(est["alt"]))
            .replace("__FECHA__", g.fecha_es(date.today()))
            .replace("__NT__", g.ntfmt(est["nt"]))
            .replace("__NE__", g.ntfmt(est["ne"]))
            .replace("__TMIN__", f"{est.get('tmin_media', 0):.1f}" if est.get("tmin_media") else "—")
            .replace("__BANDA__", banda)
            .replace("__COLBANDA__", col)
            .replace("__BGBANDA__", bg)
            .replace("__PCT__", str(pct))
            .replace("__TOTAL__", str(total))
            .replace("__LECTURA__", lectura)
            .replace("__CONTEXTO_PROV__", contexto)
            .replace("__TABLA_PROV__", "".join(filas_prov))
            .replace("__TABLA_REF__", "".join(filas_ref))
            .replace("__SLUGPROV__", g.slug(est["prov"]))
            .replace("__NDIAS__", g.miles(ndias))
            .replace("__SITE__", site))


def main() -> int:
    ap = argparse.ArgumentParser(description="Informe de zona para un lead")
    ap.add_argument("--estacion", help="indicativo AEMET (p. ej. 8293X)")
    ap.add_argument("--buscar", help="texto a buscar en el nombre de estación")
    args = ap.parse_args()
    if not args.estacion and not args.buscar:
        ap.error("indica --estacion o --buscar")

    estaciones, total = g.cargar_estaciones()
    # tmin media de verano: está en el CSV pero cargar_estaciones no la trae;
    # se relee aquí sin duplicar el parseo del resto de campos.
    import csv as _csv
    tmins = {f["indicativo"]: float(f["tmin_media_verano"])
             for f in _csv.DictReader(g.RANKING_CSV.open(encoding="utf-8"))
             if f.get("tmin_media_verano")}
    for e in estaciones:
        e["tmin_media"] = tmins.get(e["id"])

    if args.estacion:
        sel = [e for e in estaciones if e["id"] == args.estacion.upper()]
    else:
        clave = g.clave_orden(args.buscar)
        sel = [e for e in estaciones if clave in g.clave_orden(e["loc"])]
    if not sel:
        raise SystemExit("No encuentro esa estación en el ranking.")
    if len(sel) > 1:
        print("Varias coinciden; uso la primera:")
        for e in sel:
            print(f"  {e['id']}  {e['loc']} ({e['prov']})")
    est = sel[0]

    # Publicado bajo docs/informes/<slug>/ (noindex, fuera del sitemap): una
    # URL limpia y compartible por lead, con su Excel de 10 años al lado.
    import exportar_excel_estacion as xl
    site = g.SITE_URL.rstrip("/")
    sl = g.slug(est["loc"])
    carpeta = g.REPO_ROOT / "docs" / "informes" / sl
    carpeta.mkdir(parents=True, exist_ok=True)
    _, _, ndias = xl.exportar(est["id"], carpeta / "datos.xlsx")
    (carpeta / "index.html").write_text(
        construir_informe(est, estaciones, total, ndias), encoding="utf-8")
    # Refresca la consola interna (docs/informes/index.html) para que liste ya
    # el informe nuevo. La consola la posee generar_calculadora.
    (g.REPO_ROOT / "docs" / "informes" / "index.html").write_text(
        g.construir_consola_informes(estaciones, site), encoding="utf-8")
    print(f"OK -> {carpeta / 'index.html'}")
    print(f"   {site}/informes/{sl}/")
    print(f"   {est['loc']} ({est['prov']}): {est['nt']} noches trop/año · {ndias} días en Excel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
