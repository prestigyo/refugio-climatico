#!/usr/bin/env python3
"""
Genera docs/mapa-estaciones/index.html: el MAPA INTERACTIVO.

Un mapa político de España (contornos de las 52 provincias) con las ~848
estaciones de AEMET como puntos coloreados por noches tropicales. Al pasar el
ratón (o tocar en móvil) sobre un punto aparece un popup con sus datos y un
enlace a la landing provincial.

Clave del diseño: los contornos de las provincias Y los puntos se dibujan en
Python con la MISMA proyección (project()), así que los puntos caen clavados
sobre su provincia, por construcción. Sin librerías JS (ni Leaflet ni nada):
HTML + CSS + JS vanilla. Es una página complementaria; no toca la portada ni
las landings (solo se enlaza desde ellas).

Lee  : aemet-temperaturas/analisis/refugios_nocturnos_ranking.csv (vía generar_calculadora)
       aemet-temperaturas/datos/spain-provinces.geojson
Escribe: docs/mapa-estaciones/index.html

Uso:
    python scripts/generar_pagina_mapa.py
"""
from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

import generar_calculadora as g  # datos, slug, paleta, rutas, helpers


GEOJSON = next((p for p in [g.AEMET_DIR / "datos" / "spain-provinces.geojson",
                            g.REPO_ROOT / "_mapa" / "spain-provinces.geojson"]
                if p.exists()), g.AEMET_DIR / "datos" / "spain-provinces.geojson")
OUT = g.DOCS_DIR / "mapa-estaciones" / "index.html"
SITE = g.SITE_URL.rstrip("/")


# --- Proyección y color: PORTADAS EXACTAS de la portada (generar_calculadora) ---
def project(lat: float, lon: float) -> tuple[float, float]:
    if lat < 31:  # Canarias -> recuadro inferior izquierdo
        x = (lon - (-18.3)) / ((-13.2) - (-18.3))
        y = (29.6 - lat) / (29.6 - 27.5)
        return (55 + x * 200, 590 + y * 95)
    x = (lon - (-9.6)) / (4.6 - (-9.6))
    y = (44.2 - lat) / (44.2 - 35.8)
    return (70 + x * 640, 35 + y * 545)


def color_nt(nt: float) -> str:
    stops = [(0, (134, 176, 196)), (18, (217, 160, 94)),
             (36, (207, 75, 52)), (60, (150, 30, 20))]
    c = stops[0][1]
    for i in range(len(stops) - 1):
        a, ca = stops[i]
        b, cb = stops[i + 1]
        if nt <= b:
            t = max(0.0, (nt - a) / (b - a))
            c = tuple(round(ca[k] + (cb[k] - ca[k]) * t) for k in range(3))
            break
        c = cb
    return f"rgb({c[0]},{c[1]},{c[2]})"


# --- Contornos de provincias: GeoJSON (lon/lat reales) -> paths SVG proyectados ---
def construir_provincias() -> str:
    gj = json.loads(GEOJSON.read_text(encoding="utf-8"))
    paths = []
    for ft in gj["features"]:
        geom = ft["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        d = []
        for poly in polys:
            for ring in poly:
                pts, last = [], None
                for lon, lat in ring:
                    x, y = project(lat, lon)
                    p = (round(x), round(y))          # redondeo a píxel: simplifica
                    if p != last:
                        pts.append(p)
                        last = p
                if len(pts) >= 3:
                    d.append("M" + " ".join(f"{x},{y}" for x, y in pts) + "Z")
        if d:
            paths.append('<path d="' + "".join(d) + '"/>')
    return "\n".join(paths)


# --- Puntos: una estación = un círculo con sus datos en data-* ---
def construir_circulos(estaciones: list[dict]) -> str:
    out = []
    # de más caluroso a más fresco: los refugios quedan dibujados ENCIMA
    for e in sorted(estaciones, key=lambda x: -x["nt"]):
        x, y = project(e["lat"], e["lon"])
        out.append(
            f'<circle class="st" cx="{x:.1f}" cy="{y:.1f}" r="3.3" fill="{color_nt(e["nt"])}" '
            f'data-n="{html.escape(e["loc"])}" data-p="{html.escape(e["prov"])}" '
            f'data-s="{g.slug(e["prov"])}" data-a="{e["alt"]}" '
            f'data-nt="{e["nt"]}" data-ne="{e["ne"]}" data-r="{e["rank"]}"/>'
        )
    return "\n".join(out)


def construir_schema(fecha_iso: str) -> str:
    url = SITE + "/mapa-estaciones/"
    desc = ("Mapa interactivo de las 848 estaciones de AEMET de España coloreadas por "
            "noches tropicales (noches con mínima ≥ 20 °C). Pulsa cualquier punto para "
            "ver sus datos. Veranos 2017–2026.")
    schema = {"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "El mapa interactivo", "item": url}]},
        {"@type": "Article",
         "headline": "El mapa interactivo de los refugios climáticos de España",
         "description": desc,
         "image": SITE + "/og.png",
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "publisher": {"@type": "Organization", "name": "Refugio Climático",
                       "logo": {"@type": "ImageObject", "url": SITE + "/favicon.svg"}},
         "datePublished": g.FECHA_PUBLICACION_LANDINGS,
         "dateModified": fecha_iso,
         "mainEntityOfPage": url}]}
    return json.dumps(schema, ensure_ascii=False)


TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>El mapa interactivo de los refugios climáticos de España | Refugio Climático</title>
<meta name="description" content="Mapa interactivo de las 848 estaciones de AEMET coloreadas por noches tropicales. Pulsa cualquier punto y descubre dónde se duerme fresco en España. Veranos 2017–2026.">
<link rel="canonical" href="__SITE__/mapa-estaciones/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:type" content="article">
<meta property="og:title" content="El mapa interactivo de los refugios climáticos de España">
<meta property="og:description" content="Pulsa cualquier punto y descubre dónde se duerme fresco en España. 848 estaciones de AEMET, veranos 2017–2026.">
<meta property="og:url" content="__SITE__/mapa-estaciones/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="El mapa interactivo de los refugios climáticos de España">
<meta name="twitter:description" content="Pulsa cualquier punto y descubre dónde se duerme fresco en España.">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<script type="application/ld+json">__SCHEMA__</script>
<style>
 :root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--fd:"Fraunces",Georgia,serif;--fb:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--fm:"JetBrains Mono",monospace}
 *{box-sizing:border-box}
 html{-webkit-text-size-adjust:100%}
 body{margin:0;background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.6;-webkit-font-smoothing:antialiased}
 a{color:var(--teja2)}
 .wrap{max-width:880px;margin:0 auto;padding:0 1.1rem}
 .crumb{font-family:var(--fm);font-size:.72rem;letter-spacing:.04em;color:var(--muted);text-transform:uppercase;padding:1.1rem 0 .2rem}
 .crumb a{color:var(--muted);text-decoration:none}
 .crumb a:hover{color:var(--teja2)}
 h1{font-family:var(--fd);font-weight:900;font-size:clamp(1.7rem,5.2vw,2.8rem);line-height:1.08;letter-spacing:-.01em;margin:.5rem 0 .4rem}
 .lead{font-size:1.05rem;color:#e7dcc8;max-width:42rem;margin:0 0 1.1rem}
 .tools{display:flex;flex-wrap:wrap;gap:.7rem;align-items:center;margin:.6rem 0 1rem}
 .buscador{flex:1 1 220px;min-width:0}
 .buscador input{width:100%;background:var(--bg2);border:1px solid var(--line);border-radius:10px;color:var(--paper);font-family:var(--fb);font-size:.95rem;padding:.55rem .8rem}
 .buscador input:focus{outline:none;border-color:var(--teja)}
 .cont{font-family:var(--fm);font-size:.78rem;color:var(--muted);white-space:nowrap}
 .mapwrap{position:relative;background:linear-gradient(180deg,#12100c,#0e0b07);border:1px solid var(--line);border-radius:16px;padding:.4rem;overflow:hidden}
 svg#mapa{width:100%;height:auto;display:block;touch-action:manipulation}
 .provincias path{fill:#221a10;stroke:#5b4730;stroke-width:.6;stroke-linejoin:round}
 .inset{fill:none;stroke:#4a3a26;stroke-width:.7;stroke-dasharray:3 3}
 circle.st{stroke:#120d07;stroke-width:.35;cursor:pointer;transition:r .08s ease}
 circle.st:hover{r:5.6;stroke:var(--paper);stroke-width:.9}
 .pop{position:absolute;z-index:30;display:none;width:228px;background:linear-gradient(180deg,var(--panel),var(--bg2));border:1px solid #54402a;border-radius:13px;padding:.7rem .85rem .85rem;box-shadow:0 14px 36px rgba(0,0,0,.55)}
 .pop .x{position:absolute;top:2px;right:6px;background:none;border:none;color:var(--muted);font-size:1.25rem;line-height:1;cursor:pointer;padding:.2rem}
 .pop .x:hover{color:var(--paper)}
 .pl{font-family:var(--fd);font-weight:600;font-size:1.08rem;line-height:1.15;padding-right:1rem;margin-bottom:.1rem}
 .pm{font-family:var(--fm);font-size:.74rem;color:var(--muted);margin-bottom:.5rem}
 .pb{display:flex;align-items:baseline;gap:.4rem;margin-bottom:.15rem}
 .pn{font-family:var(--fm);font-weight:700;font-size:1.55rem}
 .pbu{font-size:.8rem;color:#e7dcc8}
 .pr{font-size:.76rem;color:var(--muted);margin-bottom:.55rem}
 .pa{display:inline-block;font-family:var(--fm);font-size:.8rem;font-weight:700;color:var(--teja2);text-decoration:none;border-bottom:1px solid rgba(232,154,115,.4)}
 .pa:hover{border-color:var(--teja2)}
 .leyenda{display:flex;align-items:center;gap:.6rem;margin:.9rem 0 .2rem;font-family:var(--fm);font-size:.72rem;color:var(--muted)}
 .barra{flex:1;height:11px;border-radius:6px;background:linear-gradient(90deg,rgb(134,176,196),rgb(217,160,94),rgb(207,75,52),rgb(150,30,20))}
 .ayuda{font-size:.9rem;color:var(--muted);margin:.7rem 0 0}
 .ayuda b{color:#e7dcc8;font-weight:600}
 .sigue{margin:2rem 0 0;padding:1.1rem 1.2rem;background:var(--bg2);border:1px solid var(--line);border-radius:12px}
 .sigue h2{font-family:var(--fd);font-weight:600;font-size:1.05rem;color:var(--paper);margin:0 0 .5rem}
 .sigue p{font-size:.92rem;line-height:1.65;color:var(--muted);margin:0 0 .5rem}
 .sigue p:last-child{margin:0}
 .sigue b{color:#e7dcc8;font-weight:600}
 footer{border-top:1px solid var(--line);margin-top:2.2rem;padding:1.3rem 0 2.4rem;color:var(--muted);font-size:.82rem}
 footer a{color:var(--muted)}
 .volver{font-family:var(--fm);font-size:.8rem}
 @media(max-width:560px){.lead{font-size:1rem}.cont{width:100%}}
</style>
</head>
<body>
<div class="wrap">
  <div class="crumb"><a href="__SITE__/">Refugio Climático</a> · El mapa interactivo</div>
  <h1>El mapa de los refugios climáticos de España</h1>
  <p class="lead">Las <b>848 estaciones de AEMET</b>, una a una, sobre el mapa. El color dice cuántas <b>noches tropicales</b> (mínima ≥ 20 °C) sufre cada una al año. Pasa el ratón —o toca en el móvil— sobre cualquier punto para ver sus datos y abrir su provincia.</p>

  <div class="tools">
    <div class="buscador"><input id="buscar" type="search" placeholder="Buscar estación o provincia…" autocomplete="off" aria-label="Buscar estación o provincia"></div>
    <div class="cont" id="cont">__TOTAL__ estaciones</div>
  </div>

  <div class="mapwrap" id="mapwrap">
    <svg id="mapa" viewBox="0 0 760 700" role="img" aria-label="Mapa de las estaciones de AEMET de España según noches tropicales">
      <g class="provincias">
__PROVINCIAS__
      </g>
      <rect class="inset" x="50" y="585" width="210" height="105" rx="4"/>
      <g class="puntos">
__CIRCULOS__
      </g>
    </svg>
    <div class="pop" id="pop">
      <button class="x" aria-label="Cerrar">×</button>
      <div class="pl"></div>
      <div class="pm"></div>
      <div class="pb"><span class="pn"></span> <span class="pbu">noches tropicales/año</span></div>
      <div class="pr"></div>
      <a class="pa" href="#"></a>
    </div>
  </div>

  <div class="leyenda"><span>se duerme fresco</span><span class="barra"></span><span>no refresca</span></div>
  <p class="ayuda"><b>Verde</b> = duerme tapadito todo el verano · <b>Rojo</b> = se suda. Pulsa cualquier punto para ver los detalles. El recuadro de abajo a la izquierda son las <b>Canarias</b>.</p>

  <div class="sigue">
    <h2>Y cuando llega la ola de calor, ¿aguantan?</h2>
    <p>Este mapa es la <b>media de diez veranos</b>: sirve para saber dónde se duerme fresco un año normal. Para ver qué pasa en el peor momento está el <a href="__SITE__/ola-de-calor/">mapa de la ola de calor en España</a>, animado con los mapas de temperaturas de AEMET: las máximas de cada día y las mínimas de cada noche, un fotograma por jornada. Los refugios de verdad son los que ahí <b>ni se vuelven rojos de día ni pierden el azul de noche</b>.</p>
    <p>Y si lo que quieres es lo práctico: mira <a href="__SITE__/refugios-cerca/">qué refugios climáticos tienes cerca de ti</a>, ordenados por distancia.</p>
  </div>

  <footer>
    <p class="volver"><a href="__SITE__/">← Volver a la portada</a></p>
    <p>Fuente: <b>AEMET</b> (OpenData). Noches tropicales medidas en verano (jun–ago), veranos 2017–2026. Datos abiertos bajo <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">CC BY 4.0</a>. Actualizado en <time datetime="__FECHA_ISO__">__FECHA_TXT__</time>.</p>
  </footer>
</div>

<script>
const SITE="__SITE__", TOTAL=__TOTAL__;
const $=s=>document.querySelector(s);
const wrap=$("#mapwrap"), pop=$("#pop"), sts=[...document.querySelectorAll(".st")];
const norm=s=>s.normalize("NFD").replace(/\p{Diacritic}/gu,"").toLowerCase();
const ntTxt=n=>n<1?"<1":(n<10?n.toFixed(1):Math.round(n));
const neTxt=n=>n<1?"<1":Math.round(n);

let pinned=false, ht;
function show(c){
  const d=c.dataset;
  pop.querySelector(".pl").textContent=d.n;
  pop.querySelector(".pm").textContent=d.p+" · "+Number(d.a).toLocaleString("es")+" m";
  const pn=pop.querySelector(".pn"); pn.textContent=ntTxt(+d.nt); pn.style.color=c.getAttribute("fill");
  pop.querySelector(".pr").textContent="Puesto "+d.r+" de "+TOTAL+" · "+neTxt(+d.ne)+" noches ecuatoriales/año";
  const a=pop.querySelector(".pa"); a.href=SITE+"/"+d.s+"/"; a.textContent="Ver "+d.p+" →";
  pop.style.display="block";
  const cr=c.getBoundingClientRect(), wr=wrap.getBoundingClientRect();
  const pw=pop.offsetWidth, ph=pop.offsetHeight;
  let left=cr.left-wr.left+cr.width/2-pw/2;
  let top=cr.top-wr.top-ph-10;
  left=Math.max(6,Math.min(left,wrap.clientWidth-pw-6));
  if(top<6) top=cr.top-wr.top+cr.height+10;
  pop.style.left=left+"px"; pop.style.top=top+"px";
}
function hide(){pinned=false; pop.style.display="none";}
function sched(){clearTimeout(ht); ht=setTimeout(()=>{if(!pinned)pop.style.display="none";},250);}

sts.forEach(c=>{
  c.addEventListener("pointerover",()=>{if(c.style.pointerEvents==="none")return; clearTimeout(ht); pinned=false; show(c);});
  c.addEventListener("pointerout",sched);
  c.addEventListener("click",e=>{e.stopPropagation(); pinned=true; show(c);});
});
pop.addEventListener("pointerover",()=>clearTimeout(ht));
pop.addEventListener("pointerout",sched);
pop.addEventListener("click",e=>e.stopPropagation());
pop.querySelector(".x").addEventListener("click",e=>{e.stopPropagation(); hide();});
document.addEventListener("click",hide);

const buscar=$("#buscar"), cont=$("#cont");
buscar.addEventListener("input",()=>{
  const q=norm(buscar.value.trim()); let v=0;
  sts.forEach(c=>{
    const m=!q||norm(c.dataset.n+" "+c.dataset.p).includes(q);
    c.style.opacity=m?"":"0.08"; c.style.pointerEvents=m?"":"none";
    if(m)v++;
  });
  cont.textContent = q ? (v+" de "+TOTAL+" estaciones") : (TOTAL+" estaciones");
});
</script>
</body>
</html>
"""


def main() -> int:
    estaciones, total = g.cargar_estaciones()
    fecha = date.fromtimestamp(g.RANKING_CSV.stat().st_mtime)
    fecha_iso = fecha.isoformat()
    fecha_txt = g.fecha_es(fecha)

    html_out = (TEMPLATE
                .replace("__SCHEMA__", construir_schema(fecha_iso))
                .replace("__PROVINCIAS__", construir_provincias())
                .replace("__CIRCULOS__", construir_circulos(estaciones))
                .replace("__TOTAL__", str(total))
                .replace("__FECHA_ISO__", fecha_iso)
                .replace("__FECHA_TXT__", fecha_txt)
                .replace("__SITE__", SITE))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html_out, encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"OK -> {OUT} ({total} estaciones, {kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
