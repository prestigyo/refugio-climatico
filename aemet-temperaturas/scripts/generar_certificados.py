#!/usr/bin/env python3
"""
Certificados "Refugio Climático de España 2026" para ayuntamientos.

Genera un diploma PNG por cada una de las 25 estaciones de AEMET con menos
noches tropicales de España (nt < 1, desempate por altitud: el mismo orden
que publica /ranking-noches-tropicales/). Pensados para enviarse por email a
los ayuntamientos: cada acierto es un backlink institucional y prensa local.

Salida: docs/certificados/certificado-{slug}.png  (1600x1131, ~A4 apaisado)
        (quedan servidos en nochetropical.es/certificados/... para enlazar)

Requiere: Pillow. Uso: python scripts/generar_certificados.py
"""
from __future__ import annotations

import json

from PIL import Image, ImageDraw, ImageFont

import generar_calculadora as g

# Paleta del sitio
BG, PANEL, LINE = "#161009", "#241b11", "#3a2c1c"
PAPER, MUTED, TEJA, TEJA2, VERDE = "#efe6d6", "#b3a48c", "#d9744e", "#e89a73", "#8fb07a"

W, H = 1600, 1131
OUT_DIR = g.DOCS_DIR / "certificados"
TOP_N = 25

# Serif para el nombre del pueblo, sans para el resto. Rutas de CI (Ubuntu,
# DejaVu) y de Windows (pruebas locales), en orden de preferencia.
_SERIF = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
          "C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/georgia.ttf",
          "DejaVuSerif-Bold.ttf"]
_SANS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf"]
_SANS_R = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
           "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"]


def fuente(rutas: list[str], size: int) -> ImageFont.FreeTypeFont:
    for r in rutas:
        try:
            return ImageFont.truetype(r, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def centrado(d: ImageDraw.ImageDraw, y: float, txt: str,
             fnt: ImageFont.FreeTypeFont, fill: str) -> float:
    b = d.textbbox((0, 0), txt, font=fnt)
    d.text(((W - (b[2] - b[0])) / 2 - b[0], y), txt, font=fnt, fill=fill)
    return y + (b[3] - b[1])


def espaciado(txt: str) -> str:
    """Tracking manual: 'REFUGIO' -> 'R E F U G I O' (PIL no tiene tracking)."""
    return "  ".join(" ".join(p) for p in txt.split(" "))


def dibujar_certificado(e: dict, top25: bool = False) -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    # Marco doble: línea exterior + filete teja interior
    d.rectangle([40, 40, W - 40, H - 40], outline=LINE, width=3)
    d.rectangle([56, 56, W - 56, H - 56], outline=TEJA, width=2)

    # Luna creciente (el favicon del proyecto, a lo grande)
    cx, cy, r = W // 2, 165, 52
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PAPER)
    d.ellipse([cx - r + 26, cy - r - 14, cx + r + 26, cy + r - 14], fill=BG)
    d.ellipse([cx + 30, cy - 34, cx + 44, cy - 20], fill=TEJA)

    centrado(d, 250, espaciado("REFUGIO CLIMÁTICO DE ESPAÑA"),
             fuente(_SANS, 34), TEJA2)
    centrado(d, 306, espaciado("TOP 25 · 2026" if top25 else "CERTIFICADO · 2026"),
             fuente(_SANS_R, 24), MUTED)

    # Nombre de la localidad (encoge hasta caber)
    nombre = e["loc"]
    size = 118
    fnt = fuente(_SERIF, size)
    while d.textbbox((0, 0), nombre, font=fnt)[2] > W - 260 and size > 48:
        size -= 6
        fnt = fuente(_SERIF, size)
    centrado(d, 396, nombre, fnt, PAPER)

    centrado(d, 560, f"Provincia de {e['prov']}  ·  {g.miles(e['alt'])} m de altitud",
             fuente(_SANS_R, 30), MUTED)

    d.line([(W // 2 - 90, 640), (W // 2 + 90, 640)], fill=TEJA, width=3)

    nt = "0,0" if e["nt"] == 0 else f"{e['nt']:.1f}".replace(".", ",")
    centrado(d, 676, f"{nt} noches tropicales al año", fuente(_SANS, 56), VERDE)
    centrado(d, 762, "media de los veranos 2017–2026, medida en su estación de AEMET",
             fuente(_SANS_R, 26), MUTED)

    if top25:
        centrado(d, 850, "Una de las 25 estaciones de España donde mejor se duerme en verano,",
                 fuente(_SANS_R, 29), PAPER)
        centrado(d, 894, "según el análisis de 848 estaciones y diez veranos de datos abiertos.",
                 fuente(_SANS_R, 29), PAPER)
    else:
        centrado(d, 850, "Refugio climático acreditado: aquí la noche fresca la fabrica la geografía,",
                 fuente(_SANS_R, 29), PAPER)
        centrado(d, 894, "según el análisis de 848 estaciones y diez veranos de datos abiertos.",
                 fuente(_SANS_R, 29), PAPER)

    d.line([(120, 985), (W - 120, 985)], fill=LINE, width=2)
    centrado(d, 1008, "nochetropical.es   ·   Datos: AEMET OpenData   ·   CC BY 4.0",
             fuente(_SANS_R, 24), MUTED)
    return im


# ---------------------------------------------------------------------------
# El CERTIFICADO IMPRIMIBLE es un SVG claro y elegante embebido en la página:
# tinta mínima (fondo papel, texto oscuro), soporta fotocopia en B/N, y el
# visitante lo imprime o guarda en PDF bajo demanda (sin pre-generar PNGs).
# Solo el Top 25 lleva además su tarjeta PNG (para la vista previa al
# compartir el enlace por WhatsApp/X en la campaña de ayuntamientos).
# ---------------------------------------------------------------------------

# Tinta sobre papel: la paleta clara del diploma impreso.
P_PAPEL, P_TINTA, P_SUAVE = "#faf5ea", "#241809", "#8a7a5f"
P_TEJA, P_VERDE, P_MARCO = "#c05a2e", "#4a7a3a", "#c9b99a"


def svg_certificado(e: dict, top25: bool) -> str:
    """Diploma vectorial claro (1600x1131). Usa las fuentes de la página."""
    nombre = e["loc"]
    tam = min(118, max(48, int(1400 / max(len(nombre), 1) / 0.62)))
    nt = "0,0" if e["nt"] == 0 else f"{e['nt']:.1f}".replace(".", ",")
    nivel = "TOP 25 · 2026" if top25 else "CERTIFICADO · 2026"
    linea = ("Una de las 25 estaciones de España donde mejor se duerme en verano,"
             if top25 else
             "Refugio climático acreditado: aquí la noche fresca la fabrica la geografía,")
    fs, fd = '-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif', 'Fraunces,Georgia,serif'
    return f'''<svg viewBox="0 0 1600 1131" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Certificado Refugio Climático de España 2026 de {nombre}">
<rect width="1600" height="1131" fill="{P_PAPEL}"/>
<rect x="40" y="40" width="1520" height="1051" fill="none" stroke="{P_MARCO}" stroke-width="3"/>
<rect x="58" y="58" width="1484" height="1015" fill="none" stroke="{P_TEJA}" stroke-width="1.5"/>
<circle cx="800" cy="163" r="52" fill="{P_TINTA}"/>
<circle cx="828" cy="148" r="50" fill="{P_PAPEL}"/>
<circle cx="842" cy="128" r="8" fill="{P_TEJA}"/>
<text x="800" y="286" text-anchor="middle" font-family="{fs}" font-weight="700" font-size="34" letter-spacing="10" fill="{P_TEJA}">REFUGIO CLIMÁTICO DE ESPAÑA</text>
<text x="800" y="336" text-anchor="middle" font-family="{fs}" font-size="23" letter-spacing="7" fill="{P_SUAVE}">{nivel}</text>
<text x="800" y="500" text-anchor="middle" font-family="{fd}" font-weight="900" font-size="{tam}" fill="{P_TINTA}">{nombre}</text>
<text x="800" y="576" text-anchor="middle" font-family="{fs}" font-size="30" fill="{P_SUAVE}">Provincia de {e["prov"]}  ·  {g.miles(e["alt"])} m de altitud</text>
<line x1="710" y1="630" x2="890" y2="630" stroke="{P_TEJA}" stroke-width="3"/>
<text x="800" y="712" text-anchor="middle" font-family="{fs}" font-weight="700" font-size="56" fill="{P_VERDE}">{nt} noches tropicales al año</text>
<text x="800" y="768" text-anchor="middle" font-family="{fs}" font-size="26" fill="{P_SUAVE}">media de los veranos 2017–2026, medida en su estación de AEMET</text>
<text x="800" y="866" text-anchor="middle" font-family="{fs}" font-size="29" fill="{P_TINTA}">{linea}</text>
<text x="800" y="908" text-anchor="middle" font-family="{fs}" font-size="29" fill="{P_TINTA}">según el análisis de 848 estaciones y diez veranos de datos abiertos.</text>
<line x1="120" y1="985" x2="1480" y2="985" stroke="{P_MARCO}" stroke-width="2"/>
<text x="800" y="1030" text-anchor="middle" font-family="{fs}" font-size="24" fill="{P_SUAVE}">nochetropical.es   ·   Datos: AEMET OpenData   ·   CC BY 4.0</text>
</svg>'''

_CSS_CERT = (
    ':root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;'
    '--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--verde:#8fb07a;'
    '--fd:"Fraunces",Georgia,serif;--fb:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;'
    '--fm:"JetBrains Mono",monospace}'
    '*{margin:0;padding:0;box-sizing:border-box}'
    'body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.65;-webkit-font-smoothing:antialiased}'
    '.wrap{max-width:860px;margin:0 auto;padding:0 22px}'
    'a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}'
    'header.h{padding:44px 0 10px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}'
    '.crumb{font-size:13px;color:var(--muted)}.crumb a{color:var(--muted)}'
    '.kick{font:600 12px/1 var(--fb);letter-spacing:.15em;text-transform:uppercase;color:var(--teja);margin:16px 0 10px}'
    'h1{font-family:var(--fd);font-weight:900;font-size:clamp(26px,5.2vw,40px);line-height:1.1;letter-spacing:-.01em}'
    '.intro{color:#e7dcc8;font-size:clamp(15.5px,2.4vw,17.5px);margin:14px 0 0;max-width:62ch}.intro b{color:var(--paper)}'
    '.cert{margin:26px 0 14px;border:1px solid var(--line);border-radius:14px;overflow:hidden}'
    '.cert svg{width:100%;height:auto;display:block}'
    '.cert svg text{-webkit-font-smoothing:antialiased}'
    '@media print{@page{size:A4 landscape;margin:8mm}'
    'body{background:#fff}'
    'header.h,.acciones,.verifica,footer,.nav-e,.crumb,.kick,h1,.intro{display:none!important}'
    '.cert{margin:0;border:none;border-radius:0}}'
    '.acciones{display:flex;flex-wrap:wrap;gap:10px;margin:6px 0 26px}'
    '.acciones a,.acciones button{border:1px solid var(--teja);color:var(--teja2);background:transparent;'
    'font-weight:700;font-size:14px;padding:11px 18px;border-radius:10px;cursor:pointer;text-decoration:none}'
    '.acciones a.pri{background:var(--teja);color:#1a1209}'
    '.acciones a:hover,.acciones button:hover{background:var(--teja);color:#1a1209;text-decoration:none}'
    '.verifica{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);'
    'border-radius:14px;padding:18px 20px;margin:0 0 26px;font-size:14px;color:var(--muted)}'
    '.verifica b{color:#e7dcc8}.verifica .t{font:600 11px/1 var(--fb);letter-spacing:.14em;'
    'text-transform:uppercase;color:var(--teja);margin-bottom:8px}'
    '.sigue{font-size:14.5px;color:var(--muted);margin:0 0 30px;max-width:70ch;line-height:1.7}'
    '.sigue a{font-weight:600}'
    'footer{border-top:1px solid var(--line);padding:26px 0 60px;color:#9a8a6f;font-size:12.5px}'
    'footer a{color:#9a8a6f}'
)

PAGINA_CERT = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__LOC__, Refugio Climático de España 2026 (certificado) | Noche Tropical</title>
<meta name="description" content="Certificado digital: la estación de AEMET de __LOC__ (__PROV__) está entre las 25 de España con menos noches tropicales — __NT__ al año de media (2017–2026). Verificable y descargable.">
<link rel="canonical" href="__URL__">
<meta name="robots" content="__ROBOTS__">
<meta property="og:type" content="article">
<meta property="og:title" content="__LOC__, Refugio Climático de España 2026">
<meta property="og:description" content="__NT__ noches tropicales al año de media (AEMET, 2017–2026). Entre los 25 mejores refugios climáticos de España.">
<meta property="og:url" content="__URL__">
<meta property="og:image" content="__PNG__">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__PNG__">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900&family=JetBrains+Mono:wght@700&display=swap" rel="stylesheet">
<style>__CSS__ __NAVCSS__ __FOOTERCSS__</style>
</head>
<body>
__NAV__
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__SITE__/">Refugio Climático</a> · <a href="__SITE__/certificados/">Certificados</a> · __LOC__</nav>
  <div class="kick">Certificado digital · __NIVEL__ · 2026</div>
  <h1>__LOC__, Refugio Climático de España</h1>
  <p class="intro">La estación de AEMET de <b>__LOC__</b> (__PROV__, __ALT__ m) registra <b>__NT__ noches tropicales al año</b> de media en los veranos 2017–2026: __CLAIM__. Un <b>refugio climático natural</b>: aquí las noches frescas las fabrica la geografía —altitud, aire seco, cielo limpio—, no el aire acondicionado.</p>
</div></header>

<section><div class="wrap">
  <figure class="cert">__SVG__</figure>

  <div class="acciones">
    <button class="pri" id="imprimir">🖨 Imprimir / guardar en PDF</button>__BTN_PNG__
    <button id="copiar">Copiar enlace</button>
    <a id="wa" href="#" target="_blank" rel="noopener">WhatsApp</a>
    <a id="tw" href="#" target="_blank" rel="noopener">X / Twitter</a>
  </div>

  <div class="verifica">
    <div class="t">Por qué se otorga este certificado</div>
    Se certifica como <b>Refugio Climático de España</b> a las estaciones de AEMET con <b>menos de una noche tropical al año</b> de media en los últimos diez veranos (2017–2026) — una <b>noche tropical</b> es aquella en que la mínima no baja de 20&nbsp;°C. Lo consiguen <b>218 de las 848</b> estaciones analizadas; el <b>Top 25</b> reúne, de entre ellas, las de mayor altitud. El dato de __LOC__ procede de los valores climatológicos diarios de <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a> y puede contrastarse en el <a href="__SITE__/ranking-noches-tropicales/">ranking nacional</a> y en la página de <a href="__SITE__/__PROVSLUG__/">__PROV__</a>. Certificado de uso libre citando la fuente (CC&nbsp;BY&nbsp;4.0).
  </div>

  <p class="sigue">Sigue explorando: mira <a href="__SITE__/__PROVSLUG__/">cómo se duerme en el resto de __PROV__</a>, <a href="__SITE__/ranking-noches-tropicales/">el ranking nacional de noches tropicales</a>, <a href="__SITE__/dormir-con-manta-en-verano/">los pueblos de España donde se duerme con manta en agosto</a> o <a href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/">el refugio climático más cercano a ti</a>. Y vota cómo se siente tu zona en <a href="__SITE__/confortometro/">el Confortómetro</a>.</p>
</div></section>

__FOOTER__

<script>
const URL_CERT="__URL__";
const TXT="«__LOC__» es un refugio climático certificado de España: __NT__ noches tropicales al año (AEMET, 2017–2026) 🌙 "+URL_CERT;
document.getElementById("imprimir").addEventListener("click",()=>window.print());
document.getElementById("copiar").addEventListener("click",e=>{navigator.clipboard?.writeText(URL_CERT);e.target.textContent="¡Copiado!";setTimeout(()=>e.target.textContent="Copiar enlace",1500);});
document.getElementById("wa").href="https://wa.me/?text="+encodeURIComponent(TXT);
document.getElementById("tw").href="https://twitter.com/intent/tweet?text="+encodeURIComponent(TXT);
</script>
</body>
</html>
"""


def construir_pagina_cert(e: dict, site: str, top25: bool = False,
                          n_total: int = 218) -> str:
    sl = g.slug(e["loc"])
    url = f"{site}/certificados/{sl}/"
    # Solo el Top 25 tiene tarjeta PNG pre-generada (para la vista previa al
    # compartir); el resto usa la imagen genérica del sitio.
    png = (f"{site}/certificados/certificado-{sl}.png" if top25 else f"{site}/og.png")
    btn_png = (f'\n    <a href="../certificado-{sl}.png" download>⬇ Descargar imagen (PNG)</a>'
               if top25 else "")
    nt = "0,0" if e["nt"] == 0 else f"{e['nt']:.1f}".replace(".", ",")
    nivel = "Top 25" if top25 else "Refugio acreditado"
    claim = ("está entre las <b>25 de España donde mejor se duerme en verano</b>, "
             "de las 848 analizadas" if top25 else
             f"un <b>refugio climático acreditado</b> — solo {n_total} de las 848 "
             "estaciones analizadas lo consiguen")
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Certificados", "item": site + "/certificados/"},
            {"@type": "ListItem", "position": 3, "name": e["loc"], "item": url}]},
        {"@type": "Article",
         "headline": f"{e['loc']}, Refugio Climático de España 2026",
         "description": f"Certificado: {nt} noches tropicales al año de media (AEMET, 2017–2026).",
         "image": png,
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "publisher": {"@type": "Organization", "name": "Refugio Climático",
                       "logo": {"@type": "ImageObject", "url": site + "/favicon.svg"}},
         "datePublished": "2026-07-06", "dateModified": "2026-07-06",
         "mainEntityOfPage": url}]}, ensure_ascii=False)
    # Solo el Top 25 se indexa; el resto de certificados individuales son finos
    # (una página casi calcada por estación) y van a noindex para no lastrar la
    # calidad media del sitio ante Google.
    robots = "index,follow,max-image-preview:large" if top25 else "noindex,follow"
    return (PAGINA_CERT
            .replace("__SCHEMA__", schema)
            .replace("__CSS__", _CSS_CERT)
            .replace("__NAVCSS__", g.CSS_NAV_ESCUETO)
            .replace("__FOOTERCSS__", g.CSS_FOOTER_ESCUETO)
            .replace("__NAV__", g.nav_escueto_html(site))
            .replace("__FOOTER__", g.footer_escueto_html(site))
            .replace("__ROBOTS__", robots)
            .replace("__URL__", url)
            .replace("__SLUG__", sl)
            .replace("__NIVEL__", nivel)
            .replace("__CLAIM__", claim)
            .replace("__SVG__", svg_certificado(e, top25))
            .replace("__BTN_PNG__", btn_png)
            .replace("__PNG__", png)
            .replace("__LOC__", e["loc"])
            .replace("__PROVSLUG__", g.slug(e["prov"]))
            .replace("__PROV__", e["prov"])
            .replace("__ALT__", g.miles(e["alt"]))
            .replace("__NT__", nt)
            .replace("__SITE__", site))


def construir_indice(top: list[dict], todos: list[dict], site: str) -> str:
    filas = "".join(
        f'<li><a href="{site}/certificados/{g.slug(e["loc"])}/"><b>{e["loc"]}</b>'
        f'<span>{e["prov"]} · {g.miles(e["alt"])} m</span></a></li>'
        for e in top)
    # El resto, compactos y agrupados por provincia (indexables y navegables).
    resto = [e for e in todos if e not in top]
    por_prov: dict[str, list[dict]] = {}
    for e in resto:
        por_prov.setdefault(e["prov"], []).append(e)
    grupos = "".join(
        f'<div class="grupo"><b>{prov}</b> ' + " · ".join(
            f'<a href="{site}/certificados/{g.slug(e["loc"])}/">{e["loc"]}</a>'
            for e in sorted(lst, key=lambda x: g.clave_orden(x["loc"]))) + "</div>"
        for prov, lst in sorted(por_prov.items(), key=lambda kv: g.clave_orden(kv[0])))
    css = _CSS_CERT + (
        'ul.lista{list-style:none;padding:0;margin:22px 0;display:grid;'
        'grid-template-columns:1fr 1fr;gap:10px}'
        'ul.lista a{display:block;background:linear-gradient(180deg,var(--bg2),var(--panel));'
        'border:1px solid var(--line);border-radius:12px;padding:13px 16px;color:var(--paper);font-size:15px}'
        'ul.lista a:hover{border-color:var(--teja);text-decoration:none}'
        'ul.lista span{display:block;color:var(--muted);font-size:12.5px;margin-top:2px}'
        'h2{font-family:var(--fd);font-weight:700;font-size:clamp(20px,3.6vw,26px);margin:34px 0 6px}'
        '.grupo{font-size:13.5px;color:var(--muted);padding:9px 0;border-bottom:1px solid var(--line);line-height:1.8}'
        '.grupo b{color:#e7dcc8;margin-right:6px}'
        '@media(max-width:560px){ul.lista{grid-template-columns:1fr}}'
        + g.CSS_NAV_ESCUETO + g.CSS_FOOTER_ESCUETO)
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Certificados",
             "item": site + "/certificados/"}]}]}, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Los 25 Refugios Climáticos de España certificados (2026) | Noche Tropical</title>
<meta name="description" content="Los 25 lugares de España con menos noches tropicales, certificados con 10 veranos de datos de AEMET. Certificados digitales verificables y descargables.">
<link rel="canonical" href="{site}/certificados/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:type" content="website">
<meta property="og:title" content="Los 25 Refugios Climáticos de España certificados (2026)">
<meta property="og:description" content="Los 25 lugares con menos noches tropicales, certificados con datos de AEMET.">
<meta property="og:url" content="{site}/certificados/">
<meta property="og:image" content="{site}/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{site}/og.png">
<link rel="icon" type="image/svg+xml" href="{site}/favicon.svg">
<script type="application/ld+json">{schema}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900&family=JetBrains+Mono:wght@700&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
{g.nav_escueto_html(site)}
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="{site}/">Refugio Climático</a> · Certificados</nav>
  <div class="kick">Certificados digitales · Top 25 · 2026</div>
  <h1>Los 25 Refugios Climáticos de España</h1>
  <p class="intro">Las 25 estaciones de AEMET con menos noches tropicales del país (veranos 2017–2026, 848 estaciones analizadas). Cada certificado es verificable, descargable y de uso libre citando la fuente.</p>
</div></header>
<section><div class="wrap">
  <ul class="lista">{filas}</ul>
  <h2>Todos los refugios certificados ({len(todos)})</h2>
  <p class="intro" style="font-size:15px;margin:4px 0 14px">Cada uno de estos lugares registra <b>menos de una noche tropical al año</b> de media (2017–2026) y tiene su certificado digital, verificable y descargable.</p>
  {grupos}
  <div class="verifica"><div class="t">Cómo se otorga</div>
  Una <b>noche tropical</b> es aquella en que la mínima no baja de 20&nbsp;°C. Se certifica a las estaciones con <b>menos de una noche tropical al año</b> de media (2017–2026): lo logran <b>218 de las 848</b> analizadas. Este Top 25 reúne, de entre ellas, las de mayor altitud. Solo podemos certificar donde hay estación de AEMET con datos suficientes: que un pueblo no aparezca no significa que no sea un refugio — significa que aún no podemos medirlo. Datos: <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a> · <a href="{site}/ranking-noches-tropicales/">ranking completo</a>.</div>
</div></section>
{g.footer_escueto_html(site)}
</body>
</html>
"""


def main() -> int:
    estaciones, _ = g.cargar_estaciones()
    # Se certifica a TODAS las estaciones con <1 noche tropical/año de media;
    # las 25 de mayor altitud llevan además el distintivo "Top 25".
    todos = sorted([e for e in estaciones if e["nt"] < 1],
                   key=lambda x: (x["nt"], -x["alt"]))
    top = todos[:TOP_N]
    site = g.SITE_URL.rstrip("/")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    vistos: set[str] = set()   # un certificado por localidad (Oviedo tiene 2 estaciones)
    for e in todos:
        if g.slug(e["loc"]) in vistos:
            continue
        vistos.add(g.slug(e["loc"]))
        es_top = e in top
        sl = g.slug(e["loc"])
        if es_top:   # tarjeta PNG solo para el Top 25 (campaña de ayuntamientos)
            dibujar_certificado(e, True).save(OUT_DIR / f"certificado-{sl}.png",
                                              optimize=True)
        carpeta = OUT_DIR / sl
        carpeta.mkdir(exist_ok=True)
        (carpeta / "index.html").write_text(
            construir_pagina_cert(e, site, es_top, len(todos)), encoding="utf-8")
    (OUT_DIR / "index.html").write_text(construir_indice(top, todos, site),
                                        encoding="utf-8")
    print(f"OK -> {len(todos)} certificados (PNG + página; {len(top)} Top 25) "
          f"+ índice en {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
