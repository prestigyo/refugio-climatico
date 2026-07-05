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


def dibujar_certificado(e: dict) -> Image.Image:
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
    centrado(d, 306, espaciado("TOP 25 · 2026"), fuente(_SANS_R, 24), MUTED)

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

    centrado(d, 850, "Una de las 25 estaciones de España donde mejor se duerme en verano,",
             fuente(_SANS_R, 29), PAPER)
    centrado(d, 894, "según el análisis de 848 estaciones y diez veranos de datos abiertos.",
             fuente(_SANS_R, 29), PAPER)

    d.line([(120, 985), (W - 120, 985)], fill=LINE, width=2)
    centrado(d, 1008, "nochetropical.es   ·   Datos: AEMET OpenData   ·   CC BY 4.0",
             fuente(_SANS_R, 24), MUTED)
    return im


# ---------------------------------------------------------------------------
# Página del certificado: enlace compartible en el dominio (el og:image ES el
# diploma, así que al pegarlo en WhatsApp/X se ve el certificado) + descarga.
# ---------------------------------------------------------------------------

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
    '.cert img{width:100%;height:auto;display:block}'
    '.acciones{display:flex;flex-wrap:wrap;gap:10px;margin:6px 0 26px}'
    '.acciones a,.acciones button{border:1px solid var(--teja);color:var(--teja2);background:transparent;'
    'font-weight:700;font-size:14px;padding:11px 18px;border-radius:10px;cursor:pointer;text-decoration:none}'
    '.acciones a.pri{background:var(--teja);color:#1a1209}'
    '.acciones a:hover,.acciones button:hover{background:var(--teja);color:#1a1209;text-decoration:none}'
    '.verifica{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);'
    'border-radius:14px;padding:18px 20px;margin:0 0 26px;font-size:14px;color:var(--muted)}'
    '.verifica b{color:#e7dcc8}.verifica .t{font:600 11px/1 var(--fb);letter-spacing:.14em;'
    'text-transform:uppercase;color:var(--teja);margin-bottom:8px}'
    'footer{border-top:1px solid var(--line);padding:26px 0 60px;color:#82745d;font-size:12.5px}'
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
<meta name="robots" content="index,follow,max-image-preview:large">
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
<style>__CSS__</style>
</head>
<body>
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__SITE__/">Refugio Climático</a> · <a href="__SITE__/certificados/">Certificados</a> · __LOC__</nav>
  <div class="kick">Certificado digital · Top 25 · 2026</div>
  <h1>__LOC__, Refugio Climático de España</h1>
  <p class="intro">La estación de AEMET de <b>__LOC__</b> (__PROV__, __ALT__ m) registra <b>__NT__ noches tropicales al año</b> de media en los veranos 2017–2026: está entre las <b>25 de España donde mejor se duerme en verano</b>, de las 848 analizadas.</p>
</div></header>

<section><div class="wrap">
  <figure class="cert"><img src="../certificado-__SLUG__.png" width="1600" height="1131" alt="Certificado Refugio Climático de España 2026 de __LOC__"></figure>

  <div class="acciones">
    <a class="pri" href="../certificado-__SLUG__.png" download>⬇ Descargar el certificado (PNG)</a>
    <button id="copiar">Copiar enlace</button>
    <a id="wa" href="#" target="_blank" rel="noopener">WhatsApp</a>
    <a id="tw" href="#" target="_blank" rel="noopener">X / Twitter</a>
  </div>

  <div class="verifica">
    <div class="t">Cómo verificar este certificado</div>
    Una <b>noche tropical</b> es aquella en que la mínima no baja de 20&nbsp;°C. El dato procede de los valores climatológicos diarios de <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a> (veranos 2017–2026) medidos en la estación de __LOC__. Puede contrastarse en el <a href="__SITE__/ranking-noches-tropicales/">ranking nacional</a> y en la página de <a href="__SITE__/__PROVSLUG__/">__PROV__</a>. El certificado es de uso libre citando la fuente (CC&nbsp;BY&nbsp;4.0).
  </div>
</div></section>

<footer><div class="wrap">
  Proyecto <a href="__SITE__/">Refugio Climático · nochetropical.es</a> · Datos: AEMET OpenData · <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">CC&nbsp;BY&nbsp;4.0</a>
</div></footer>

<script>
const URL_CERT="__URL__";
const TXT="«__LOC__» está entre los 25 mejores refugios climáticos de España: __NT__ noches tropicales al año (AEMET, 2017–2026) 🌙 "+URL_CERT;
document.getElementById("copiar").addEventListener("click",e=>{navigator.clipboard?.writeText(URL_CERT);e.target.textContent="¡Copiado!";setTimeout(()=>e.target.textContent="Copiar enlace",1500);});
document.getElementById("wa").href="https://wa.me/?text="+encodeURIComponent(TXT);
document.getElementById("tw").href="https://twitter.com/intent/tweet?text="+encodeURIComponent(TXT);
</script>
</body>
</html>
"""


def construir_pagina_cert(e: dict, site: str) -> str:
    sl = g.slug(e["loc"])
    url = f"{site}/certificados/{sl}/"
    png = f"{site}/certificados/certificado-{sl}.png"
    nt = "0,0" if e["nt"] == 0 else f"{e['nt']:.1f}".replace(".", ",")
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
    return (PAGINA_CERT
            .replace("__SCHEMA__", schema)
            .replace("__CSS__", _CSS_CERT)
            .replace("__URL__", url)
            .replace("__SLUG__", sl)
            .replace("__PNG__", png)
            .replace("__LOC__", e["loc"])
            .replace("__PROVSLUG__", g.slug(e["prov"]))
            .replace("__PROV__", e["prov"])
            .replace("__ALT__", g.miles(e["alt"]))
            .replace("__NT__", nt)
            .replace("__SITE__", site))


def construir_indice(top: list[dict], site: str) -> str:
    filas = "".join(
        f'<li><a href="{site}/certificados/{g.slug(e["loc"])}/"><b>{e["loc"]}</b>'
        f'<span>{e["prov"]} · {g.miles(e["alt"])} m</span></a></li>'
        for e in top)
    css = _CSS_CERT + (
        'ul.lista{list-style:none;padding:0;margin:22px 0;display:grid;'
        'grid-template-columns:1fr 1fr;gap:10px}'
        'ul.lista a{display:block;background:linear-gradient(180deg,var(--bg2),var(--panel));'
        'border:1px solid var(--line);border-radius:12px;padding:13px 16px;color:var(--paper);font-size:15px}'
        'ul.lista a:hover{border-color:var(--teja);text-decoration:none}'
        'ul.lista span{display:block;color:var(--muted);font-size:12.5px;margin-top:2px}'
        '@media(max-width:560px){ul.lista{grid-template-columns:1fr}}')
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
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="{site}/">Refugio Climático</a> · Certificados</nav>
  <div class="kick">Certificados digitales · Top 25 · 2026</div>
  <h1>Los 25 Refugios Climáticos de España</h1>
  <p class="intro">Las 25 estaciones de AEMET con menos noches tropicales del país (veranos 2017–2026, 848 estaciones analizadas). Cada certificado es verificable, descargable y de uso libre citando la fuente.</p>
</div></header>
<section><div class="wrap">
  <ul class="lista">{filas}</ul>
  <div class="verifica"><div class="t">Metodología</div>
  Una <b>noche tropical</b> es aquella en que la mínima no baja de 20&nbsp;°C. Selección: estaciones con menos de una noche tropical al año de media, ordenadas por altitud. Datos: <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a> · <a href="{site}/ranking-noches-tropicales/">ranking completo</a>.</div>
</div></section>
<footer><div class="wrap">
  Proyecto <a href="{site}/">Refugio Climático · nochetropical.es</a> · Datos: AEMET OpenData · <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">CC&nbsp;BY&nbsp;4.0</a>
</div></footer>
</body>
</html>
"""


def main() -> int:
    estaciones, _ = g.cargar_estaciones()
    top = sorted([e for e in estaciones if e["nt"] < 1],
                 key=lambda x: (x["nt"], -x["alt"]))[:TOP_N]
    site = g.SITE_URL.rstrip("/")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for i, e in enumerate(top, 1):
        sl = g.slug(e["loc"])
        dibujar_certificado(e).save(OUT_DIR / f"certificado-{sl}.png", optimize=True)
        carpeta = OUT_DIR / sl
        carpeta.mkdir(exist_ok=True)
        (carpeta / "index.html").write_text(construir_pagina_cert(e, site), encoding="utf-8")
        print(f"{i:2d}. {e['loc']} ({e['prov']}) -> /certificados/{sl}/")
    (OUT_DIR / "index.html").write_text(construir_indice(top, site), encoding="utf-8")
    print(f"OK -> {len(top)} certificados (PNG + página) + índice en {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
