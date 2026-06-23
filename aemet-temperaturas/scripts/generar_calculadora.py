#!/usr/bin/env python3
"""
Genera el reportaje público "El mapa del calor que no te deja dormir" +
la calculadora "¿Se duerme bien en tu pueblo?", a partir del ranking nocturno
ya calculado.

Lee  : aemet-temperaturas/analisis/refugios_nocturnos_ranking.csv
Escribe: docs/index.html  (autocontenido, sin dependencias externas de datos)

El reportaje es scrollytelling: hero -> el contraste -> el mapa de las ~848
estaciones (dibujado desde los datos) -> la calculadora real (Provincia ->
Estación, o geolocalización). Todos los datos son medidos (AEMET OpenData);
no se interpola ni se estima nada.

Idempotente y regenerable: vuelve a ejecutarlo cuando cambie el ranking.

Uso:
    python scripts/generar_calculadora.py
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from datetime import date
from pathlib import Path


def clave_orden(texto: str) -> str:
    """Clave de ordenación insensible a acentos (Cáceres antes que Ciudad Real)."""
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def slug(texto: str) -> str:
    """'A Coruña' -> 'a-coruna', 'Illes Balears' -> 'illes-balears'."""
    base = clave_orden(texto)
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


# ---------------------------------------------------------------------------
# Rutas (este script vive en aemet-temperaturas/scripts/)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
AEMET_DIR = SCRIPT_DIR.parent                 # aemet-temperaturas/
REPO_ROOT = AEMET_DIR.parent                  # raíz del repo
RANKING_CSV = AEMET_DIR / "analisis" / "refugios_nocturnos_ranking.csv"
DOCS_DIR = REPO_ROOT / "docs"                 # GitHub Pages sirve /docs en raíz
OUT_HTML = DOCS_DIR / "index.html"

# URL pública del sitio, sin barra final. Cámbiala si pasas a dominio propio.
SITE_URL = "https://prestigyo.github.io/refugio-climatico"

# URL /exec del Apps Script que recibe los leads (ver apps_script_refugio.gs).
# Déjalo vacío hasta desplegar el backend: el formulario funcionará igual y
# volcará el lead a la consola hasta que pegues aquí la URL real.
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbws_0q0zwYdFNh_NAvA-mAJYH0Jkrg9d0dkFurITnYdHFR3kx8GbeqC8u9YI_PCQpuJ/exec"

# Modo prensa: en True la página se presenta como proyecto de datos neutral
# (capta solo "informe + alertas de calor" y "soy periodista"; sin compra/venta
# ni enlaces comerciales). Ponlo en False para activar el modo comercial.
MODO_PRENSA = True

# Correcciones de nombres de estación (AEMET los guarda sin acentos). Clave =
# indicativo. Solo hace falta para los nombres que se muestran destacados.
CORRECCIONES = {
    "C623I": "San Bartolomé de Tirajana",
}

# ---------------------------------------------------------------------------
# Normalización de provincias (el CSV trae duplicados y sin acentos)
# ---------------------------------------------------------------------------
PROVINCIAS = {
    "A CORUÑA": "A Coruña", "ALBACETE": "Albacete", "ALICANTE": "Alicante",
    "ALMERIA": "Almería", "ARABA/ALAVA": "Araba/Álava", "ASTURIAS": "Asturias",
    "AVILA": "Ávila", "BADAJOZ": "Badajoz", "BALEARES": "Illes Balears",
    "ILLES BALEARS": "Illes Balears", "BARCELONA": "Barcelona",
    "BIZKAIA": "Bizkaia", "BURGOS": "Burgos", "CACERES": "Cáceres",
    "CADIZ": "Cádiz", "CANTABRIA": "Cantabria", "CASTELLON": "Castellón",
    "CEUTA": "Ceuta", "CIUDAD REAL": "Ciudad Real", "CORDOBA": "Córdoba",
    "CUENCA": "Cuenca", "GIPUZKOA": "Gipuzkoa", "GIRONA": "Girona",
    "GRANADA": "Granada", "GUADALAJARA": "Guadalajara", "HUELVA": "Huelva",
    "HUESCA": "Huesca", "JAEN": "Jaén", "LA RIOJA": "La Rioja",
    "LAS PALMAS": "Las Palmas", "LEON": "León", "LLEIDA": "Lleida",
    "LUGO": "Lugo", "MADRID": "Madrid", "MALAGA": "Málaga", "MELILLA": "Melilla",
    "MURCIA": "Murcia", "NAVARRA": "Navarra", "OURENSE": "Ourense",
    "PALENCIA": "Palencia", "PONTEVEDRA": "Pontevedra", "SALAMANCA": "Salamanca",
    "SANTA CRUZ DE TENERIFE": "Santa Cruz de Tenerife",
    "STA. CRUZ DE TENERIFE": "Santa Cruz de Tenerife", "SEGOVIA": "Segovia",
    "SEVILLA": "Sevilla", "SORIA": "Soria", "TARRAGONA": "Tarragona",
    "TERUEL": "Teruel", "TOLEDO": "Toledo", "VALENCIA": "Valencia",
    "VALLADOLID": "Valladolid", "ZAMORA": "Zamora", "ZARAGOZA": "Zaragoza",
}

# Conectores que van en minúscula dentro de un nombre (salvo si es la 1ª palabra)
MINUSCULAS = {"de", "del", "la", "las", "los", "el", "y", "e", "o", "u",
              "da", "do", "dos", "das", "i", "a", "lo"}


def titular(nombre: str) -> str:
    """Pasa 'NAUT ARAN, ARTIES ' -> 'Naut Aran, Arties' respetando acentos,
    guiones, comas y paréntesis, y dejando los conectores en minúscula."""
    nombre = re.sub(r"\s+", " ", nombre.strip())

    def cap(palabra: str, primera: bool) -> str:
        if not palabra:
            return palabra
        if not primera and palabra.lower() in MINUSCULAS:
            return palabra.lower()
        return palabra[0].upper() + palabra[1:].lower()

    out = []
    tokens = re.split(r"([ \-/(,.])", nombre)
    primera = True
    for tok in tokens:
        if tok in {" ", "-", "/", "(", ",", "."}:
            out.append(tok)
            continue
        out.append(cap(tok, primera))
        if tok:
            primera = False
    return "".join(out).strip()


def cargar_estaciones() -> tuple[list[dict], int]:
    if not RANKING_CSV.exists():
        raise SystemExit(
            f"No encuentro el ranking: {RANKING_CSV}\n"
            "Ejecuta antes scripts/analisis_refugios_nocturnos.py."
        )
    filas = list(csv.DictReader(RANKING_CSV.open(encoding="utf-8")))
    total = len(filas)
    estaciones = []
    for f in filas:
        prov_raw = f["provincia"].strip().upper()
        provincia = PROVINCIAS.get(prov_raw, titular(prov_raw))
        ind = f["indicativo"]
        estaciones.append({
            "id": ind,
            "loc": CORRECCIONES.get(ind, titular(f["nombre"])),
            "prov": provincia,
            "alt": int(round(float(f["altitud_m"]))),
            "nt": round(float(f["noches_trop_anio"]), 1),
            "ne": round(float(f["noches_ecua_anio"]), 1),
            "rank": int(float(f["rank"])),
            "lat": round(float(f["lat"]), 4),
            "lon": round(float(f["lon"]), 4),
            "anios": round(float(f["n_anios"]), 1),
        })
    return estaciones, total


def _slim(e: dict) -> dict:
    return {"loc": e["loc"], "prov": e["prov"], "alt": e["alt"], "nt": e["nt"]}


def construir_datos(estaciones: list[dict], total: int) -> dict:
    # Agrupa por provincia, ordena localidades alfabéticamente (sin acentos)
    provincias: dict[str, list[dict]] = {}
    for e in estaciones:
        provincias.setdefault(e["prov"], []).append(e)
    for lista in provincias.values():
        lista.sort(key=lambda x: clave_orden(x["loc"]))
    provincias = dict(sorted(provincias.items(), key=lambda kv: clave_orden(kv[0])))

    mejor = min(estaciones, key=lambda x: x["rank"])
    peor = max(estaciones, key=lambda x: x["nt"])
    # Ancla "horno": la estación de la ciudad de Valencia más calurosa
    val_city = [e for e in estaciones
                if "valencia" in e["loc"].lower() and e["prov"] == "Valencia"]
    valencia = max(val_city, key=lambda x: x["nt"]) if val_city else None

    # Contraste del reportaje: un refugio de la sierra de Gúdar (Teruel) frente
    # al "horno" mediterráneo. Si no hay estación de Gúdar, caemos al mejor.
    teruel = [e for e in estaciones if e["prov"] == "Teruel"]
    refugio = next((e for e in teruel if "cedrillas" in e["loc"].lower()), None)
    if refugio is None and teruel:
        refugio = min(teruel, key=lambda x: (x["nt"], -x["alt"]))
    if refugio is None:
        refugio = mejor
    horno = valencia or peor

    # Caso foehn: la estación de altura más caliente del interior de Gran Canaria
    # (el efecto foehn es un fenómeno canario: el aire baja de la cumbre y se
    # recalienta). Restringido a Las Palmas para no confundirlo con el calor de
    # valle de la península (p.ej. Cazorla).
    altas_gc = [e for e in estaciones if e["prov"] == "Las Palmas" and e["alt"] >= 700]
    foehn = max(altas_gc, key=lambda x: x["nt"]) if altas_gc else peor

    # Barras "refugios e infiernos": top/bottom por noches tropicales, máximo
    # una estación por provincia para que la lista tenga variedad geográfica.
    def seleccionar(key, n=8):
        vistos: dict[str, int] = {}
        out = []
        for e in sorted(estaciones, key=key):
            if vistos.get(e["prov"], 0) >= 1:
                continue
            vistos[e["prov"]] = 1
            out.append(_slim(e))
            if len(out) >= n:
                break
        return out
    refugios = seleccionar(lambda x: (x["nt"], -x["alt"]))
    infiernos = seleccionar(lambda x: -x["nt"])

    return {
        "meta": {
            "total": total,
            "fuente": "AEMET OpenData",
            "verano": "jun–ago",
            "mejor": _slim(mejor),
            "peor": _slim(peor),
            "valencia": ({"loc": valencia["loc"], "nt": valencia["nt"]}
                         if valencia else None),
            "contraste": {"refugio": _slim(refugio), "horno": _slim(horno)},
            "foehn": _slim(foehn),
            "refugios": refugios,
            "infiernos": infiernos,
        },
        "provincias": provincias,
    }


def construir_schema(datos: dict, site: str) -> dict:
    """Datos estructurados JSON-LD: Dataset + WebApplication + FAQPage + WebSite.
    Para resultados enriquecidos en Google y para que la IA cite la fuente."""
    m = datos["meta"]
    mejor, peor, foehn = m["mejor"], m["peor"], m["foehn"]
    faq = [
        ("¿Qué es una noche tropical?",
         "Una noche tropical es aquella en la que la temperatura mínima no baja de "
         "20 °C. Es el indicador que mejor refleja si se descansa bien en verano."),
        ("¿Dónde se duerme mejor en verano en España?",
         f"En las sierras del interior. Estaciones como {mejor['loc']} ({mejor['prov']}) "
         "registran prácticamente cero noches tropicales al año, frente a la costa "
         "mediterránea y las islas."),
        ("¿Cuál es el peor sitio de España para dormir en verano?",
         f"La costa mediterránea y las islas. {peor['loc']} ({peor['prov']}) llega a unas "
         f"{round(peor['nt'])} noches tropicales al año: casi todo el verano sin que la "
         "temperatura baje de 20 °C."),
        ("¿Por qué hace tanto calor de noche en la montaña de Gran Canaria?",
         "Por el efecto foehn: el aire baja de la cumbre, se comprime y se recalienta. "
         f"En {foehn['loc']}, a {foehn['alt']} m de altitud, se cuentan unas "
         f"{round(foehn['nt'])} noches tropicales al año, más que en muchos pueblos de costa."),
    ]
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Dataset",
                "name": "Noches tropicales en España (AEMET, 2017–2026)",
                "description": (
                    f"Número de noches tropicales (temperatura mínima ≥ 20 °C) al año en "
                    f"{m['total']} estaciones meteorológicas de AEMET, veranos de 2017 a 2026. "
                    "Identifica los refugios climáticos donde mejor se duerme en verano."),
                "url": site + "/",
                "creator": {"@type": "Person", "name": "Ramón J. Lowesting"},
                "isBasedOn": "https://opendata.aemet.es",
                "temporalCoverage": "2017/2026",
                "spatialCoverage": {"@type": "Place", "name": "España"},
                "keywords": ["noches tropicales", "ola de calor", "refugio climático",
                             "AEMET", "temperatura mínima", "clima España"],
            },
            {
                "@type": "WebApplication",
                "name": "Calculadora de noches tropicales por pueblo",
                "url": site + "/",
                "applicationCategory": "ReferenceApplication",
                "operatingSystem": "Web",
                "browserRequirements": "Requires JavaScript",
                "description": ("Elige tu provincia y la estación más cercana y descubre cuántas "
                                "noches tropicales sufre tu pueblo al año y si es un refugio climático."),
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"},
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q,
                     "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faq
                ],
            },
            {
                "@type": "WebSite",
                "name": "Refugio Climático",
                "url": site + "/",
                "inLanguage": "es-ES",
                "publisher": {"@type": "Person", "name": "Ramón J. Lowesting"},
            },
        ],
    }


# ---------------------------------------------------------------------------
# Plantilla HTML (autocontenida). Los datos se inyectan en __DATA__.
# ---------------------------------------------------------------------------
TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>El mapa del calor que no te deja dormir · Refugio Climático</title>
<meta name="description" content="Reportaje con 10 veranos de datos de AEMET: dónde se duerme fresco en España y dónde se suda hasta el amanecer. Y la calculadora de tu pueblo.">
<meta property="og:title" content="El mapa del calor que no te deja dormir">
<meta property="og:description" content="848 estaciones, diez veranos de AEMET. ¿Cuántas noches tropicales aguanta tu pueblo?">
<meta property="og:type" content="website">
<link rel="canonical" href="__SITE_URL__/">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:url" content="__SITE_URL__/">
<meta property="og:site_name" content="Refugio Climático">
<meta property="og:locale" content="es_ES">
<meta property="og:image" content="__SITE_URL__/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="El mapa del calor que no te deja dormir">
<meta name="twitter:description" content="848 estaciones, diez veranos de AEMET. ¿Cuántas noches tropicales aguanta tu pueblo?">
<meta name="twitter:image" content="__SITE_URL__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE_URL__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,900;1,9..144,400;1,9..144,600&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#161009; --bg2:#1f1810; --panel:#241b11; --line:#3a2c1c;
    --paper:#efe6d6; --muted:#b3a48c; --teja:#d9744e; --teja2:#e89a73;
    --teal:#96b6c4; --verde:#8fb07a; --rojo:#cf6b54;
    --fd:"Fraunces",Georgia,serif; --fb:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    --fm:"JetBrains Mono",ui-monospace,monospace;
  }
  *{margin:0;padding:0;box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.6;
    -webkit-font-smoothing:antialiased;overflow-x:hidden}
  .wrap{max-width:min(92vw,1080px);margin:0 auto;padding:0 22px}
  .kicker{font:600 12px/1 var(--fb);letter-spacing:.18em;text-transform:uppercase;color:var(--teja)}
  h2.st{font-family:var(--fd);font-weight:900;font-size:clamp(26px,5.5vw,40px);line-height:1.06;
    letter-spacing:-.01em;margin:0 0 6px}
  h2.st em{font-style:italic;color:var(--teja2)}
  .lead{color:var(--muted);font-size:clamp(15px,2.4vw,17px);margin:14px 0 0;max-width:720px}
  .num{font-family:var(--fm);font-weight:700;letter-spacing:-.02em}
  .reveal{opacity:0;transform:translateY(26px);transition:opacity .8s ease,transform .8s cubic-bezier(.22,1,.36,1)}
  .reveal.in{opacity:1;transform:none}
  section{padding:clamp(70px,11vw,130px) 0}
  .secnum{font:600 12px/1 var(--fb);letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-bottom:18px}

  /* HERO */
  .hero{min-height:100svh;display:flex;flex-direction:column;justify-content:center;
    padding:60px 0 40px;position:relative;
    background:radial-gradient(130% 90% at 50% -10%,#2a1d10 0%,var(--bg) 55%)}
  .hero h1{font-family:var(--fd);font-weight:900;font-size:clamp(40px,9vw,80px);line-height:.98;
    letter-spacing:-.02em;margin:18px 0 0}
  .hero h1 em{font-style:italic;color:var(--teja2)}
  .hero .q{font-family:var(--fd);font-weight:600;font-style:italic;font-size:clamp(20px,3.6vw,28px);
    color:var(--paper);margin:22px 0 0}
  .hero .q b{color:var(--teja2);font-style:normal;font-weight:600}
  .hero p.intro{color:var(--muted);font-size:clamp(15px,2.4vw,18px);max-width:560px;margin:26px 0 0}
  .chip{display:inline-flex;gap:10px;align-items:center;margin-top:34px;background:var(--bg2);
    border:1px solid var(--line);border-radius:999px;padding:9px 16px;font-size:13px;color:var(--muted)}
  .chip b{color:var(--teal);font-family:var(--fm);font-weight:700}
  .cue{display:inline-flex;align-items:center;gap:10px;width:fit-content;margin-top:40px;
    background:rgba(217,116,78,.14);border:1px solid var(--teja);color:var(--teja2);
    padding:13px 24px;border-radius:999px;font-size:14.5px;font-weight:600;letter-spacing:.02em;
    text-decoration:none;cursor:pointer;transition:background .2s,color .2s}
  .cue:hover{background:var(--teja);color:#1a1209}
  .cue .chev{display:inline-block;font-size:17px;animation:bounce 1.5s ease-in-out infinite}
  @keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(5px)}}

  /* CONTRASTE */
  .vs{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:30px}
  .pueblo{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);
    border-radius:16px;padding:22px 20px}
  .pueblo .tag{font:600 11px/1 var(--fb);letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
  .pueblo h3{font-family:var(--fd);font-weight:600;font-size:21px;margin:8px 0 2px;line-height:1.1}
  .pueblo .alt{font-size:12.5px;color:var(--muted)}
  .pueblo .big{font-family:var(--fm);font-weight:700;font-size:clamp(38px,8vw,52px);line-height:1;margin:16px 0 2px}
  .pueblo .lbl{font-size:12.5px;color:var(--muted)}
  .pueblo.cool{border-color:#2f4651} .pueblo.cool .big{color:var(--teal)}
  .pueblo.hot{border-color:#4a2a1d} .pueblo.hot .big{color:var(--rojo)}
  .vs-line{text-align:center;margin-top:18px;color:var(--muted);font-size:14px}
  .vs-line b{color:var(--teja2)}
  .lt-note{display:inline-block;font-family:var(--fb);font-size:12px;font-weight:600;color:var(--muted);
    text-transform:none;letter-spacing:0;margin-left:10px;vertical-align:middle;line-height:1.1}
  .metodo{margin-top:30px;border-left:3px solid var(--teja);background:var(--bg2);
    border-radius:0 12px 12px 0;padding:16px 18px;max-width:780px}
  .metodo h4{font:600 11px/1 var(--fb);letter-spacing:.12em;text-transform:uppercase;color:var(--teja);margin-bottom:8px}
  .metodo p{color:var(--muted);font-size:14.5px;line-height:1.55}
  .metodo b{color:var(--paper)}

  /* MAPA */
  #map{width:100%;height:auto;display:block;margin-top:26px;
    filter:drop-shadow(0 20px 60px rgba(0,0,0,.5))}
  #map circle{transition:opacity .5s}
  .gifs{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:26px}
  @media(max-width:640px){.gifs{grid-template-columns:1fr}}
  .gif{width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:12px}
  .gif-solo{max-width:780px;margin-top:18px}
  .subh{font-family:var(--fd);font-weight:600;font-size:clamp(20px,3.6vw,27px);line-height:1.15;margin-top:44px}
  .subh + .lead{margin-top:10px}
  .legend{display:flex;align-items:center;gap:14px;margin-top:16px;font-size:12.5px;color:var(--muted);
    flex-wrap:wrap}
  .legend .bar{flex:1;min-width:160px;height:9px;border-radius:6px;
    background:linear-gradient(90deg,#86b0c4,#d9a05e,#d9744e,#bf3b22)}
  .foehn{margin-top:34px;background:linear-gradient(180deg,var(--bg2),var(--panel));
    border:1px solid #4a2a1d;border-radius:16px;padding:24px 22px;max-width:780px}
  .foehn .tag{font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;color:var(--teja)}
  .foehn h3{font-family:var(--fd);font-weight:600;font-size:22px;margin:8px 0 10px;line-height:1.15}
  .foehn p{color:var(--muted);font-size:15px}
  .foehn b{color:var(--paper)}

  /* REFUGIOS E INFIERNOS */
  .bars{display:grid;grid-template-columns:1fr 1fr;gap:30px;margin-top:30px}
  .barcol h4{font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;margin-bottom:4px}
  .barcol.ref h4{color:var(--teal)} .barcol.inf h4{color:var(--rojo)}
  .barcol .csub{font-size:12px;color:var(--muted);margin-bottom:18px}
  .barrow{margin-bottom:14px}
  .barrow-top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
  .bn{font-size:13.5px;color:var(--paper);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .bv{font-family:var(--fm);font-size:13px;font-weight:700;color:var(--muted)}
  .bartrack{height:8px;border-radius:5px;background:#2c2114;overflow:hidden;margin:5px 0 2px}
  .bartrack>i{display:block;height:100%;width:0;border-radius:5px;transition:width 1.1s cubic-bezier(.22,1,.36,1)}
  .reveal.in .bartrack>i{width:var(--w)}
  .bp{font-size:11.5px;color:var(--muted)}
  .barnote{margin-top:8px;font-size:12px;color:var(--muted)}
  @media(max-width:560px){.bars{grid-template-columns:1fr;gap:34px}}

  /* CALCULADORA */
  .calc{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);
    border-radius:20px;padding:30px 26px 24px;margin-top:28px;box-shadow:0 30px 80px -30px #000;max-width:620px}
  .calc .sub{color:var(--muted);font-size:14.5px;margin:10px 0 22px}
  .calc label{display:block;font:600 12px/1 var(--fb);letter-spacing:.04em;text-transform:uppercase;
    color:var(--muted);margin:0 2px 7px}
  .calc .rowf{margin-bottom:16px}
  select{width:100%;appearance:none;background:var(--bg)
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%23b3a48c' d='M1 1l5 5 5-5'/%3E%3C/svg%3E")
    no-repeat right 16px center;border:1px solid var(--line);color:var(--paper);
    font-size:16px;padding:14px 40px 14px 15px;border-radius:12px;cursor:pointer;transition:border-color .15s}
  select:hover{border-color:#54402a} select:focus{outline:none;border-color:var(--teja)}
  select:disabled{opacity:.4;cursor:not-allowed}
  .geo{display:inline-flex;align-items:center;gap:7px;background:none;border:none;color:var(--teal);
    font-size:13.5px;cursor:pointer;padding:4px 0;margin-top:-4px}
  .geo:hover{color:#b5cfdb;text-decoration:underline} .geo:disabled{opacity:.5;cursor:default}
  #res{margin-top:22px;border-top:1px solid var(--line);padding-top:22px;display:none}
  #res.show{display:block;animation:fade .4s ease}
  @keyframes fade{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
  .res-loc{font-family:var(--fd);font-weight:600;font-size:22px;line-height:1.15}
  .res-meta{color:var(--muted);font-size:13px;margin-top:2px}
  .big{display:flex;align-items:baseline;gap:12px;margin:18px 0 4px}
  .big .n{font-family:var(--fm);font-weight:700;font-size:64px;line-height:.9;letter-spacing:-.02em}
  .n.cool{color:var(--teal)} .n.warm{color:var(--teja2)} .n.hot{color:var(--rojo)}
  .num-cap{font-size:14px;color:var(--muted);max-width:160px}
  .verd{display:inline-block;font:600 13px/1 var(--fb);padding:7px 12px;border-radius:999px;margin:6px 0 18px}
  .bar2{height:9px;border-radius:6px;background:#2c2114;overflow:hidden;margin:4px 0 6px}
  .bar2>i{display:block;height:100%;border-radius:6px;background:linear-gradient(90deg,var(--teal),var(--teja),var(--rojo))}
  .scale{display:flex;justify-content:space-between;font-size:11px;color:var(--muted)}
  .facts{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:18px 0 6px}
  .fact{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
  .fact b{display:block;font-family:var(--fm);font-size:20px;font-weight:700}
  .fact span{font-size:12px;color:var(--muted)}
  .minimap-h{font-size:13.5px;color:var(--muted);margin-top:18px}
  .minimap-h b{color:var(--paper)}
  .minimap{width:100%;height:auto;display:block;margin-top:8px;background:var(--bg);border:1px solid var(--line);border-radius:12px}
  .minimap-leg{font-size:11.5px;color:var(--muted);margin-top:7px;display:flex;align-items:center;gap:4px;flex-wrap:wrap}
  .minimap-leg .d{display:inline-block;width:11px;height:11px;border-radius:3px;margin:0 2px 0 6px}
  .cmp{font-size:14px;background:var(--bg);border:1px dashed var(--line);border-radius:12px;padding:13px 15px;margin-top:14px}
  .cmp b{color:var(--teja2)}
  .share{display:flex;gap:9px;flex-wrap:wrap;margin-top:18px}
  .share a,.share button{flex:1;min-width:96px;text-align:center;text-decoration:none;border:1px solid var(--line);
    background:var(--bg);color:var(--paper);font-size:13px;font-weight:600;padding:11px 8px;border-radius:11px;cursor:pointer;transition:.15s}
  .share a:hover,.share button:hover{border-color:var(--teja);color:var(--teja2)}
  .capture{margin-top:20px;border:1px solid var(--line);background:var(--bg);border-radius:14px;padding:18px 16px}
  .lead-h{font-family:var(--fd);font-weight:600;font-size:16.5px;margin-bottom:8px;color:var(--paper);line-height:1.25}
  .lead-sub{font-size:13px;color:var(--muted);margin:0 0 14px;line-height:1.5}
  .leadform{display:flex;flex-direction:column;gap:9px}
  .leadform input[type=email],.leadform input[type=text]{width:100%;background:var(--bg2);border:1px solid var(--line);color:var(--paper);font-size:14.5px;padding:11px 12px;border-radius:10px}
  .leadform input:focus{outline:none;border-color:var(--teja)}
  .capture .lrgpd{display:flex;align-items:flex-start;gap:8px;font-size:12px;color:var(--muted);text-transform:none;letter-spacing:0;margin:2px 0;font-weight:400}
  .capture .lrgpd input{margin-top:3px;width:auto}
  .leadform button{background:var(--teja);border:none;color:#1a1209;font-weight:700;font-size:15px;padding:12px;border-radius:10px;cursor:pointer;transition:.15s}
  .leadform button:hover{background:var(--teja2)}
  .bridge{display:inline-block;margin-top:12px;color:var(--teal);font-size:13.5px;text-decoration:none}
  .bridge:hover{color:#b5cfdb;text-decoration:underline}
  .provnav{display:flex;flex-wrap:wrap;gap:9px 16px;margin-top:18px;font-size:14px}
  .provnav a{color:var(--teal);text-decoration:none}
  .provnav a:hover{color:var(--teja2);text-decoration:underline}
  footer{border-top:1px solid var(--line);padding:34px 0 60px;color:#82745d;font-size:12.5px;line-height:1.6}
  footer a{color:#9a8a6f}
  @media(max-width:430px){.vs{grid-template-columns:1fr}}
</style>
</head>
<body>

<header class="hero">
  <div class="wrap">
    <div class="kicker">Reportaje · Datos AEMET</div>
    <h1>El mapa del calor<br>que no te deja <em>dormir</em></h1>
    <p class="q">¿Cuántas <b>noches tropicales</b> tienes que aguantar tú?</p>
    <p class="intro"><span id="h-total" class="num">848</span> estaciones meteorológicas. Diez veranos de datos de AEMET. Una sola pregunta: en tu pueblo, ¿se duerme tapado o se suda hasta el amanecer?</p>
    <div class="chip">Noche tropical: <b>la mínima no baja de 20&nbsp;°C</b></div>
    <a class="cue" href="#s1">Desliza o pulsa para descubrirlo <span class="chev">↓</span></a>
  </div>
</header>

<section id="s1">
  <div class="wrap reveal">
    <div class="secnum">01 — El contraste</div>
    <h2 class="st">Dos pueblos, <em>dos veranos distintos</em></h2>
    <p class="lead">En España, subir a la sierra o quedarte en la costa cambia por completo cómo duermes en agosto. Mira la diferencia entre un refugio de montaña y el litoral mediterráneo.</p>
    <div class="vs">
      <div class="pueblo cool">
        <div class="tag">El refugio</div>
        <h3 id="c-ref-loc">—</h3>
        <div class="alt" id="c-ref-meta">—</div>
        <div class="big num" id="c-ref-nt">—</div>
        <div class="lbl">noches tropicales al año</div>
      </div>
      <div class="pueblo hot">
        <div class="tag">El horno</div>
        <h3 id="c-hor-loc">—</h3>
        <div class="alt" id="c-hor-meta">—</div>
        <div class="big num" id="c-hor-nt">—</div>
        <div class="lbl">noches tropicales al año</div>
      </div>
    </div>
    <p class="vs-line" id="c-line">—</p>
    <div class="metodo">
      <h4>Por qué contamos noches, no medias</h4>
      <p>La media de las mínimas engaña: unas noches frescas y otras tórridas pueden dar un promedio "agradable" que esconde las noches insoportables. Por eso aquí no usamos medias — medimos algo que no miente: <b>cuántas noches al año la temperatura no baja de 20&nbsp;°C</b>.</p>
    </div>
  </div>
</section>

<section style="background:var(--bg2);border-top:1px solid var(--line);border-bottom:1px solid var(--line)">
  <div class="wrap reveal">
    <div class="secnum">02 — El mapa</div>
    <h2 class="st">España, punto a punto, <em>según cómo se duerme</em></h2>
    <p class="lead">Cada punto es una estación de AEMET, pintada según sus noches tropicales de verano. No hemos dibujado España: la dibuja el calor que cae —o no— al anochecer.</p>
    <svg id="map" viewBox="0 0 760 700" role="img" aria-label="Mapa de estaciones de AEMET según noches tropicales"></svg>
    <div class="legend">
      <span>se duerme fresco</span>
      <span class="bar"></span>
      <span>no refresca</span>
    </div>
    <div class="foehn reveal">
      <div class="tag">La sorpresa · el efecto foehn</div>
      <h3>Subes a la montaña buscando el fresco. En Gran Canaria lo encuentras <em>al revés</em>.</h3>
      <p>En el interior de Gran Canaria, el aire baja de la cumbre, se comprime y se recalienta. En <b id="f-loc">—</b> —a <b id="f-alt">—</b> de altitud— se sufren <b id="f-nt">—</b> noches tropicales al año: más que en muchos pueblos de costa. La altura, que en la península salva, aquí condena.</p>
    </div>
  </div>
</section>

<section id="s-ola">
  <div class="wrap reveal">
    <div class="secnum">03 — La ola, día a día</div>
    <h2 class="st">De día todos sufren. <em>De noche, no.</em></h2>
    <p class="lead">Las máximas del día y las mínimas de la noche, día a día este verano. Cuando llega el calor, casi toda España arde de día — pero las sierras del interior se mantienen frescas al anochecer.</p>
    <div class="gifs">
      <img class="gif" src="ola-maximas.gif" alt="Mapa diario de temperaturas máximas de AEMET durante la ola de calor" loading="lazy">
      <img class="gif" src="ola-minimas.gif" alt="Mapa diario de temperaturas mínimas de AEMET durante la ola de calor" loading="lazy">
    </div>
    <p class="barnote">Fuente: AEMET · un fotograma por día. Recarga la página para verlo desde el principio.</p>

    <h3 class="subh">¿Y Canarias? También es España — y de noche, más complicada.</h3>
    <p class="lead">En las islas el efecto foehn recalienta hasta la montaña: el interior de Gran Canaria es de los peores sitios de España para dormir. Estas son sus mínimas nocturnas, noche a noche.</p>
    <img class="gif gif-solo" src="ola-canarias-minimas.gif" alt="Mapa diario de temperaturas mínimas de Canarias (AEMET)" loading="lazy">
  </div>
</section>

<section>
  <div class="wrap reveal" id="rei">
    <div class="secnum">04 — Refugios e infiernos</div>
    <h2 class="st">Dónde dormir tapado, <em>dónde no pegar ojo</em></h2>
    <p class="lead">En un extremo, las sierras del interior: prácticamente cero noches tropicales en diez veranos. En el otro, el litoral y las islas, donde casi todo el verano se suda.</p>
    <div class="bars">
      <div class="barcol ref"><h4>Los refugios</h4><div class="csub">se duerme tapado</div><div id="rl"></div></div>
      <div class="barcol inf"><h4>Los infiernos</h4><div class="csub">el verano entero sudando</div><div id="il"></div></div>
    </div>
    <p class="barnote">Cada barra, sobre 92 noches de verano · una estación por provincia.</p>
  </div>
</section>

<section>
  <div class="wrap reveal">
    <div class="secnum">05 — Búscalo tú</div>
    <h2 class="st">Y en tu pueblo, <em>¿se duerme tapado?</em></h2>
    <div class="calc">
      <p class="sub">Una <b>noche tropical</b> es cuando la temperatura no baja de 20&nbsp;°C. Elige tu provincia y la estación más cercana: te decimos cuántas sufre al año, de unas 92 noches de verano.</p>
      <div class="rowf">
        <label for="prov">Provincia</label>
        <select id="prov"><option value="">Elige provincia…</option></select>
      </div>
      <div class="rowf">
        <label for="est">Estación (localidad · altitud)</label>
        <select id="est" disabled><option value="">Elige primero la provincia</option></select>
        <button class="geo" id="geo" type="button">📍 No sé cuál — usar mi ubicación</button>
      </div>
      <div id="res" aria-live="polite"></div>
    </div>
  </div>
</section>

<section>
  <div class="wrap reveal">
    <div class="secnum">Explora por provincia</div>
    <h2 class="st">Las noches tropicales, <em>provincia a provincia</em></h2>
    <p class="lead">Mira cuántas noches tropicales sufre cada pueblo de tu provincia, de la más fresca a la más calurosa.</p>
    <nav class="provnav">__PROV_NAV__</nav>
  </div>
</section>

<footer>
  <div class="wrap">
    Fuente: <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a> ·
    verano (jun–ago) · <span id="anios">diez veranos</span> · <span id="f-total" class="num">848</span> estaciones.<br>
    Dato medido en la estación, no en el municipio: si tu pueblo no tiene estación, elige la más cercana
    (y ojo al desnivel: en montaña la noche cambia mucho con la altitud).
  </div>
</footer>

<script>
const DATA = __DATA__;
const APPS_SCRIPT_URL = "__APPS_URL__";
const MODO_PRENSA = __MODO_PRENSA__;
const M = DATA.meta, T = M.total;
const $ = s => document.querySelector(s);

// Lista plana (para mapa y geolocalización)
const TODAS = [];
for (const lista of Object.values(DATA.provincias)) for (const e of lista) TODAS.push(e);

// ---------- Utilidades de color ----------
function colorNT(nt){
  const stops=[[0,[134,176,196]],[18,[217,160,94]],[36,[207,75,52]],[60,[150,30,20]]];
  let c=stops[0][1];
  for(let i=0;i<stops.length-1;i++){
    const [a,ca]=stops[i],[b,cb]=stops[i+1];
    if(nt<=b){const t=Math.max(0,(nt-a)/(b-a));c=ca.map((v,k)=>Math.round(v+(cb[k]-v)*t));break;}
    c=cb;
  }
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

// ---------- Rellenar textos del reportaje ----------
$("#h-total").textContent = T; $("#f-total").textContent = T;
const anios = Math.max(...TODAS.map(e=>e.anios));
$("#anios").textContent = anios>=9 ? "diez veranos" : anios.toFixed(0)+" veranos";

function ntTxt(nt){ return nt<1 ? "<1" : (nt<10 ? nt.toFixed(1) : Math.round(nt)); }
function ntBig(nt){ return nt<1 ? '&lt;1<span class="lt-note">menos de 1</span>' : String(ntTxt(nt)); }

const cr=M.contraste.refugio, ch=M.contraste.horno;
$("#c-ref-loc").textContent=cr.loc; $("#c-ref-meta").textContent=`${cr.prov} · ${cr.alt.toLocaleString("es")} m`;
$("#c-ref-nt").innerHTML=ntBig(cr.nt);
$("#c-hor-loc").textContent=ch.loc; $("#c-hor-meta").textContent=`${ch.prov} · ${ch.alt.toLocaleString("es")} m`;
$("#c-hor-nt").innerHTML=ntBig(ch.nt);
$("#c-line").innerHTML = `Mismo país, misma semana de agosto: en <b>${cr.loc}</b> duermes con manta; en <b>${ch.loc}</b> sudas <b>${ntTxt(ch.nt)}</b> de cada 92 noches.`;
const fo=M.foehn;
$("#f-loc").textContent=fo.loc.split(",")[0]; $("#f-alt").textContent=fo.alt.toLocaleString("es")+" m"; $("#f-nt").textContent=ntTxt(fo.nt);

// ---------- Mapa ----------
function project(lat, lon){
  if(lat < 31){ // Canarias -> recuadro inferior izquierdo
    const x = (lon-(-18.3))/((-13.2)-(-18.3));
    const y = (29.6-lat)/(29.6-27.5);
    return [55 + x*200, 590 + y*95];
  }
  const x = (lon-(-9.6))/(4.6-(-9.6));
  const y = (44.2-lat)/(44.2-35.8);
  return [70 + x*640, 35 + y*545];
}
(function drawMap(){
  const svg=$("#map"), NS="http://www.w3.org/2000/svg";
  // recuadro Canarias
  const box=document.createElementNS(NS,"rect");
  box.setAttribute("x",45);box.setAttribute("y",582);box.setAttribute("width",225);box.setAttribute("height",112);
  box.setAttribute("rx",8);box.setAttribute("fill","none");box.setAttribute("stroke","#3a2c1c");
  svg.appendChild(box);
  // puntos: los más calientes encima
  [...TODAS].sort((a,b)=>a.nt-b.nt).forEach(e=>{
    const [x,y]=project(e.lat,e.lon);
    const c=document.createElementNS(NS,"circle");
    c.setAttribute("cx",x.toFixed(1));c.setAttribute("cy",y.toFixed(1));c.setAttribute("r",3.1);
    c.setAttribute("fill",colorNT(e.nt));c.setAttribute("opacity",.9);
    svg.appendChild(c);
  });
})();

// Mini-mapa de ZONA: zoom a los alrededores de la estación elegida, con los
// pueblos vecinos etiquetados y coloreados (para ubicarse y ver los refugios).
function miniMapa(e){
  const W=480, H=360, pad=16;
  const vec = TODAS.map(s=>({s, d:haversine(e.lat,e.lon,s.lat,s.lon)}))
                   .sort((a,b)=>a.d-b.d).slice(0,12).map(o=>o.s);
  let laMin=Math.min(...vec.map(s=>s.lat)), laMax=Math.max(...vec.map(s=>s.lat));
  let loMin=Math.min(...vec.map(s=>s.lon)), loMax=Math.max(...vec.map(s=>s.lon));
  laMin-=0.06; laMax+=0.06; loMin-=0.06; loMax+=0.06;
  const cosLat=Math.cos(e.lat*Math.PI/180);
  const loR=Math.max(0.25,(loMax-loMin)*cosLat), laR=Math.max(0.25,(laMax-laMin));
  const sc=Math.min((W-2*pad)/loR,(H-2*pad)/laR);
  const offX=(W-loR*sc)/2, offY=(H-laR*sc)/2;
  const px=lon=>offX+(lon-loMin)*cosLat*sc, py=lat=>offY+(laMax-lat)*sc;
  const placed=[];
  const choca=(x,y,w)=>{const h=14;for(const r of placed){if(x<r.x+r.w&&x+w>r.x&&y<r.y+r.h&&y+h>r.y)return true;}return false;};
  let dots="", labels="";
  for(const s of [e, ...vec.filter(v=>v.id!==e.id)]){
    const x=px(s.lon), y=py(s.lat), sel=s.id===e.id, c=colorNT(s.nt);
    dots += sel
      ? `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="13" fill="none" stroke="#fff" stroke-width="3"><animate attributeName="r" values="9;19;9" dur="1.7s" repeatCount="indefinite"/><animate attributeName="opacity" values="1;0;1" dur="1.7s" repeatCount="indefinite"/></circle><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="7.5" fill="${c}" stroke="#fff" stroke-width="2"/>`
      : `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5" fill="${c}" stroke="#161009" stroke-width="1"/>`;
    const lw=s.loc.length*5.6+6;
    let lx=x+9; const ly=y+4;
    if(lx+lw>W-2) lx=x-9-lw;
    if(sel || !choca(lx,ly-11,lw)){
      placed.push({x:lx,y:ly-11,w:lw,h:14});
      labels+=`<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" font-size="${sel?12.5:11}" font-weight="${sel?700:400}" fill="${sel?'#fff':'#cdbfa6'}">${s.loc}</text>`;
    }
  }
  return `<div class="minimap-h">📍 <b>${e.loc}</b> y su entorno — descubre los refugios cercanos</div>`
    +`<svg class="minimap" viewBox="0 0 ${W} ${H}" role="img" aria-label="Mapa de la zona de ${e.loc}">${dots}${labels}</svg>`
    +`<div class="minimap-leg">Color = noches tropicales: <span class="d" style="background:${colorNT(0)}"></span> fresco <span class="d" style="background:${colorNT(35)}"></span> templado <span class="d" style="background:${colorNT(75)}"></span> no refresca</div>`;
}

// ---------- Barras: refugios / infiernos ----------
function barras(cont, lista){
  cont.innerHTML = lista.map(e=>{
    const w = Math.max(1.5, Math.min(100, e.nt/92*100));
    const v = e.nt<1 ? "&lt;1" : (e.nt<10 ? e.nt.toFixed(1) : Math.round(e.nt));
    return `<div class="barrow">
      <div class="barrow-top"><span class="bn">${e.loc}</span><span class="bv">${v}</span></div>
      <div class="bartrack"><i style="--w:${w}%;background:${colorNT(e.nt)}"></i></div>
      <div class="bp">${e.prov} · ${e.alt.toLocaleString("es")} m</div></div>`;
  }).join("");
}
barras($("#rl"), M.refugios);
barras($("#il"), M.infiernos);

// ---------- Calculadora ----------
const selP=$("#prov"), selE=$("#est");
for(const prov of Object.keys(DATA.provincias)){
  const o=document.createElement("option");o.value=prov;o.textContent=prov;selP.appendChild(o);
}
selP.addEventListener("change",()=>{poblar(selP.value);$("#res").classList.remove("show");});
selE.addEventListener("change",()=>{if(selE.value)render(selE.value);});

function poblar(prov,sel){
  selE.innerHTML="";
  if(!prov){selE.disabled=true;selE.innerHTML="<option>Elige primero la provincia</option>";return;}
  selE.disabled=false;
  const ph=document.createElement("option");ph.value="";ph.textContent="Elige estación…";selE.appendChild(ph);
  for(const e of DATA.provincias[prov]){
    const o=document.createElement("option");o.value=e.id;
    o.textContent=`${e.loc} — ${e.alt.toLocaleString("es")} m`;selE.appendChild(o);
  }
  if(sel)selE.value=sel;
}
function haversine(a,b,c,d){const R=6371,r=Math.PI/180,dLat=(c-a)*r,dLon=(d-b)*r;
  const x=Math.sin(dLat/2)**2+Math.cos(a*r)*Math.cos(c*r)*Math.sin(dLon/2)**2;return 2*R*Math.asin(Math.sqrt(x));}
$("#geo").addEventListener("click",()=>{
  const btn=$("#geo");
  if(!navigator.geolocation){btn.textContent="Tu navegador no permite ubicación";return;}
  btn.textContent="📍 Buscando la estación más cercana…";btn.disabled=true;
  navigator.geolocation.getCurrentPosition(pos=>{
    const {latitude:la,longitude:lo}=pos.coords;let best=null,bd=1e9;
    for(const e of TODAS){const dd=haversine(la,lo,e.lat,e.lon);if(dd<bd){bd=dd;best=e;}}
    selP.value=best.prov;poblar(best.prov,best.id);render(best.id,bd);
    btn.disabled=false;btn.textContent="📍 Usar mi ubicación";
  },()=>{btn.disabled=false;btn.textContent="No se pudo obtener tu ubicación";},{timeout:8000});
});
function bandas(nt){
  if(nt<1)  return["Refugio climático","var(--verde)","#1e2a17","cool"];
  if(nt<10) return["Se duerme bien","var(--teal)","#16242b","cool"];
  if(nt<30) return["Verano templado","var(--teja2)","#2c2114","warm"];
  if(nt<60) return["Se suda","var(--teja)","#2c1a12","warm"];
  return["Horno: casi todo el verano","var(--rojo)","#2c1411","hot"];
}
function render(id,distKm){
  const e=TODAS.find(x=>x.id===id);if(!e)return;
  const [etq,col,bg,cls]=bandas(e.nt);
  const txt=e.nt<1?"menos de 1":(e.nt<10?e.nt.toFixed(1):Math.round(e.nt));
  const bigT=e.nt<1?'&lt;1<span class="lt-note">menos de 1</span>':txt;
  const pos=Math.min(100,e.nt/90*100);
  const distTxt=distKm?`<div class="res-meta">📍 Estación más cercana a ${distKm.toFixed(0)} km de ti</div>`:"";
  const url="https://prestigyo.github.io/refugio-climatico/";
  const shareTxt=`En ${e.loc} (${e.prov}) se sufren ${txt} noches tropicales al año — puesto ${e.rank} de ${T} de España. ¿Y en tu pueblo?`;
  const modo = MODO_PRENSA ? "prensa" : (e.nt < 10 ? "propietario" : "comprador");
  let leadHead, leadSub, opts, bridgeTxt, zonaPh;
  if(modo==="prensa"){
    leadHead = "¿Quieres el informe de tu zona y aviso si entra en ola de calor?";
    leadSub  = "";
    opts = '<option value="info">Quiero el informe + alertas de calor</option><option value="periodista">Soy periodista o medio</option>';
    bridgeTxt = "";
    zonaPh = "Tu provincia (opcional)";
  } else if(modo==="propietario"){
    leadHead = "Tienes una casa donde se duerme fresco. Hoy eso es un tesoro.";
    leadSub  = "Cada vez más gente huye del calor. Si te planteas venderla, te ponemos en contacto con compradores que buscan exactamente esto.";
    opts = '<option value="tasacion">Quiero una tasación gratuita</option><option value="vender">Me planteo vender</option><option value="info">Solo información de mi zona</option><option value="agente">Soy agente inmobiliario</option>';
    bridgeTxt = "Vendemos sin pasar por Idealista — cómo trabajamos →";
    zonaPh = "¿Dónde está tu casa? (opcional)";
  } else {
    leadHead = e.nt>=30 ? "¿Y si pudieras dormir fresco? Te ayudamos a encontrar tu refugio." : "¿Quieres el informe de tu zona y aviso si entra en ola de calor?";
    leadSub  = "";
    opts = '<option value="info">Quiero el informe + alertas de calor</option><option value="comprar">Me interesa comprar en un refugio</option><option value="alquilar">Me interesa alquilar o veranear</option><option value="agente">Soy agente inmobiliario</option>';
    bridgeTxt = "O conoce La Virgen de la Vega, un refugio a 75 min de Valencia →";
    zonaPh = "¿En qué zona te gustaría? (opcional)";
  }
  const leadSubHTML = leadSub ? `<p class="lead-sub">${leadSub}</p>` : "";
  const mini = miniMapa(e);
  $("#res").innerHTML=`
    <div class="res-loc">${e.loc}</div>
    <div class="res-meta">${e.prov} · ${e.alt.toLocaleString("es")} m de altitud</div>${distTxt}
    <div class="big"><div class="n ${cls}">${bigT}</div>
      <div class="num-cap">noches tropicales al año<br>(de ~92 de verano)</div></div>
    <span class="verd" style="color:${col};background:${bg}">${etq}</span>
    <div class="bar2"><i style="width:${pos}%"></i></div>
    <div class="scale"><span>fresco</span><span>se suda toda la noche</span></div>
    <div class="facts">
      <div class="fact"><b>${e.rank} / ${T}</b><span>puesto en España (1 = mejor refugio)</span></div>
      <div class="fact"><b>${e.ne<1?"<1":Math.round(e.ne)}</b><span>noches ecuatoriales/año (&gt;25&nbsp;°C)</span></div>
    </div>
    ${mini}
    <div class="share">
      <a href="https://wa.me/?text=${encodeURIComponent(shareTxt+" "+url)}" target="_blank" rel="noopener">WhatsApp</a>
      <a href="https://twitter.com/intent/tweet?text=${encodeURIComponent(shareTxt)}&url=${encodeURIComponent(url)}" target="_blank" rel="noopener">X / Twitter</a>
      <button type="button" id="copy">Copiar enlace</button></div>
    <div class="capture">
      <div class="lead-h">${leadHead}</div>
      ${leadSubHTML}
      <form id="leadf" class="leadform">
        <input type="email" id="lemail" placeholder="Tu email" required>
        <select id="lwhat">${opts}</select>
        <input type="text" id="lzona" placeholder="${zonaPh}">
        <input type="text" id="lpet" placeholder="¿Qué dato te gustaría ver? (opcional)">
        <label class="lrgpd"><input type="checkbox" id="lrgpd" required> Acepto que me contactéis sobre esto.</label>
        <button type="submit">Enviar</button>
      </form>
      ${bridgeTxt ? `<a class="bridge" href="https://lavirgendelavega.es" target="_blank" rel="noopener">${bridgeTxt}</a>` : ""}
    </div>`;
  $("#res").classList.add("show");
  $("#copy").addEventListener("click",()=>{navigator.clipboard?.writeText(shareTxt+" "+url);
    $("#copy").textContent="¡Copiado!";setTimeout(()=>{const b=$("#copy");if(b)b.textContent="Copiar enlace";},1800);});
  const lf=$("#leadf");
  if(lf) lf.addEventListener("submit",ev=>{
    ev.preventDefault();
    const lead={timestamp:new Date().toISOString(),email:$("#lemail").value.trim(),
      modo:modo,busca:$("#lwhat").value,zona_interes:$("#lzona").value.trim(),peticion:$("#lpet").value.trim(),
      estacion:e.loc,provincia:e.prov,noches_trop:e.nt,veredicto:etq,
      rgpd:$("#lrgpd").checked?"si":"",source:"refugio-climatico",user_agent:navigator.userAgent};
    const gracias=()=>{const h=document.querySelector("#res .lead-h");if(h)h.textContent="¡Gracias! Te escribimos pronto.";if(lf)lf.remove();};
    if(APPS_SCRIPT_URL){
      fetch(APPS_SCRIPT_URL,{method:"POST",headers:{"Content-Type":"text/plain;charset=utf-8"},body:JSON.stringify(lead)}).then(gracias).catch(gracias);
    } else { console.log("LEAD (sin endpoint configurado):",lead); gracias(); }
  });
}

// ---------- Scroll reveal ----------
const io=new IntersectionObserver((es)=>{es.forEach(x=>{if(x.isIntersecting){x.target.classList.add("in");io.unobserve(x.target);}});},{threshold:.15});
document.querySelectorAll(".reveal").forEach(el=>io.observe(el));
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Capa 3 SEO: una página por provincia, con los datos en HTML (indexable)
# ---------------------------------------------------------------------------
PAGINA_PROVINCIA = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
<link rel="canonical" href="__CANONICAL__">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="article">
<meta property="og:title" content="__OGTITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:url" content="__CANONICAL__">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE_URL__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&family=JetBrains+Mono:wght@700&display=swap" rel="stylesheet">
<style>
 :root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--verde:#8fb07a;--rojo:#cf6b54;--fd:"Fraunces",Georgia,serif;--fb:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--fm:"JetBrains Mono",monospace}
 *{margin:0;padding:0;box-sizing:border-box}
 body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.6;-webkit-font-smoothing:antialiased}
 .wrap{max-width:min(92vw,920px);margin:0 auto;padding:0 22px}
 a{color:var(--teal);text-decoration:none}
 a:hover{text-decoration:underline}
 header.h{padding:46px 0 12px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}
 .crumb{font-size:13px;color:var(--muted)}
 .kick{font:600 12px/1 var(--fb);letter-spacing:.16em;text-transform:uppercase;color:var(--teja);margin:18px 0 8px}
 h1{font-family:var(--fd);font-weight:900;font-size:clamp(30px,6vw,48px);line-height:1.05;letter-spacing:-.01em}
 h1 em{font-style:italic;color:var(--teja2)}
 .intro{color:var(--muted);font-size:clamp(15px,2.4vw,18px);margin:18px 0 0;max-width:720px}
 .intro b{color:var(--paper)}
 section{padding:30px 0}
 table{width:100%;border-collapse:collapse;font-size:15px}
 th,td{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line)}
 th{font:600 11px/1 var(--fb);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
 th.r,td.n{text-align:right}
 td.n{font-family:var(--fm);font-weight:700}
 td.loc{font-weight:600}
 .v{display:inline-block;font:600 11px/1 var(--fb);padding:5px 9px;border-radius:999px}
 .note{font-size:12.5px;color:var(--muted);margin-top:12px}
 .cta{margin:26px 0;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:22px;text-align:center}
 .cta b{font-family:var(--fd);font-weight:600;font-size:19px}
 .cta a.btn{display:inline-block;margin-top:12px;background:var(--teja);color:#1a1209;font-weight:700;padding:12px 20px;border-radius:11px}
 .cta a.btn:hover{background:var(--teja2);text-decoration:none}
 .provnav{display:flex;flex-wrap:wrap;gap:9px 16px;margin-top:14px;font-size:13.5px}
 footer{border-top:1px solid var(--line);padding:30px 0 60px;color:#82745d;font-size:12.5px;margin-top:18px}
 footer a{color:#9a8a6f}
 @media(max-width:520px){th.hide,td.hide{display:none}}
</style>
</head>
<body>
<header class="h"><div class="wrap">
  <div class="crumb"><a href="__HOME__">Refugio Climático</a> · __PROVNAME__</div>
  <div class="kick">Noches tropicales · Datos AEMET</div>
  <h1>__H1__</h1>
  <p class="intro">__INTRO__</p>
</div></header>

<section><div class="wrap">
  <table>
    <thead><tr><th>Localidad</th><th class="hide">Altitud</th><th class="r">Noches tropicales/año</th><th>Cómo se duerme</th></tr></thead>
    <tbody>__TABLE__</tbody>
  </table>
  <p class="note">Una noche tropical es aquella en que la mínima no baja de 20&nbsp;°C. Media anual, veranos 2017–2026. Fuente: AEMET.</p>

  <div class="cta">
    <b>¿Quieres comparar con cualquier pueblo de España?</b><br>
    <a class="btn" href="__HOME__">Abre el mapa y la calculadora →</a>
  </div>
</div></section>

<section><div class="wrap">
  <div class="kick">Todas las provincias</div>
  <nav class="provnav">__PROVNAV__</nav>
</div></section>

<footer><div class="wrap">
  Fuente: <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a> · veranos 2017–2026 · proyecto <a href="__HOME__">Refugio Climático</a> de Ramón J. Lowesting.
</div></footer>
</body>
</html>
"""


def bandas_py(nt: float):
    if nt < 1:
        return ("Refugio", "var(--verde)", "#1e2a17")
    if nt < 10:
        return ("Se duerme bien", "var(--teal)", "#16242b")
    if nt < 30:
        return ("Templado", "var(--teja2)", "#2c2114")
    if nt < 60:
        return ("Se suda", "var(--teja)", "#2c1a12")
    return ("Horno", "var(--rojo)", "#2c1411")


def ntfmt(nt: float) -> str:
    if nt < 1:
        return "&lt;1"
    return f"{nt:.1f}" if nt < 10 else f"{round(nt)}"


def construir_schema_provincia(prov: str, site: str, sl: str, n: int) -> dict:
    return {"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": prov, "item": f"{site}/{sl}/"}]},
        {"@type": "Dataset",
         "name": f"Noches tropicales en {prov} (AEMET, 2017–2026)",
         "description": f"Noches tropicales al año en las {n} estaciones de AEMET de {prov}, veranos 2017–2026.",
         "url": f"{site}/{sl}/", "isBasedOn": "https://opendata.aemet.es",
         "spatialCoverage": {"@type": "Place", "name": prov}, "temporalCoverage": "2017/2026",
         "creator": {"@type": "Person", "name": "Ramón J. Lowesting"}}]}


def construir_pagina_provincia(prov: str, lista: list, site: str, provnav: str) -> str:
    sl = slug(prov)
    ordenadas = sorted(lista, key=lambda x: (x["nt"], -x["alt"]))
    mejor, peor, n = ordenadas[0], max(lista, key=lambda x: x["nt"]), len(lista)
    filas = []
    for e in ordenadas:
        etq, col, bg = bandas_py(e["nt"])
        alt = f"{e['alt']:,}".replace(",", ".")
        filas.append(
            f'<tr><td class="loc">{e["loc"]}</td><td class="hide">{alt} m</td>'
            f'<td class="n">{ntfmt(e["nt"])}</td>'
            f'<td><span class="v" style="color:{col};background:{bg}">{etq}</span></td></tr>')
    mtxt = ("prácticamente no hay noches tropicales" if mejor["nt"] < 1
            else f'son unas {round(mejor["nt"])} al año')
    alt_mejor = f"{mejor['alt']:,}".replace(",", ".")
    intro = (f'En <b>{prov}</b>, en <b>{mejor["loc"]}</b> ({alt_mejor} m) {mtxt}, '
             f'mientras que en <b>{peor["loc"]}</b> se cuentan unas <b>{round(peor["nt"])}</b>. '
             f'Estas son sus {n} estaciones de AEMET, de la más fresca a la más calurosa.')
    title = f"Noches tropicales en {prov}: dónde se duerme fresco | Refugio Climático"
    desc = (f"Cuántas noches tropicales sufre cada pueblo de {prov} al año, según 10 veranos de "
            f"AEMET. {mejor['loc']} es de los más frescos; {peor['loc']}, donde peor se duerme.")
    schema = json.dumps(construir_schema_provincia(prov, site, sl, n), ensure_ascii=False)
    return (PAGINA_PROVINCIA
            .replace("__OGTITLE__", f"Noches tropicales en {prov}")
            .replace("__TITLE__", title)
            .replace("__DESC__", desc)
            .replace("__CANONICAL__", f"{site}/{sl}/")
            .replace("__SITE__", site)
            .replace("__SITE_URL__", site)
            .replace("__HOME__", site + "/")
            .replace("__PROVNAME__", prov)
            .replace("__H1__", f'¿Se duerme bien en verano en <em>{prov}</em>?')
            .replace("__INTRO__", intro)
            .replace("__TABLE__", "".join(filas))
            .replace("__PROVNAV__", provnav)
            .replace("__SCHEMA__", schema))


# Favicon dibujado (no emoji): cuadro oscuro + luna creciente + estrella teja.
FAVICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<rect width="100" height="100" rx="24" fill="#1f1810"/>
<circle cx="45" cy="52" r="30" fill="#efe6d6"/>
<circle cx="60" cy="44" r="29" fill="#1f1810"/>
<circle cx="73" cy="34" r="6.5" fill="#d9744e"/>
</svg>
'''


def main() -> int:
    estaciones, total = cargar_estaciones()
    datos = construir_datos(estaciones, total)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    site = SITE_URL.rstrip("/")
    provnav = "".join(f'<a href="{site}/{slug(p)}/">{p}</a>' for p in datos["provincias"])
    payload = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    schema = json.dumps(construir_schema(datos, site), ensure_ascii=False)
    html = (TEMPLATE.replace("__DATA__", payload)
            .replace("__APPS_URL__", APPS_SCRIPT_URL)
            .replace("__MODO_PRENSA__", "true" if MODO_PRENSA else "false")
            .replace("__SITE_URL__", site)
            .replace("__SCHEMA__", schema)
            .replace("__PROV_NAV__", provnav))
    OUT_HTML.write_text(html, encoding="utf-8")
    # Ficheros SEO: desactivar Jekyll y robots.
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (DOCS_DIR / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {site}/sitemap.xml\n", encoding="utf-8")
    (DOCS_DIR / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")
    # Capa 3: una página indexable por provincia.
    urls = [site + "/"]
    for prov, lista in datos["provincias"].items():
        sl = slug(prov)
        carpeta = DOCS_DIR / sl
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "index.html").write_text(
            construir_pagina_provincia(prov, lista, site, provnav), encoding="utf-8")
        urls.append(f"{site}/{sl}/")
    hoy = date.today().isoformat()
    filas = "\n".join(
        f'  <url><loc>{u}</loc><lastmod>{hoy}</lastmod><changefreq>weekly</changefreq>'
        f'<priority>{"1.0" if u == site + "/" else "0.7"}</priority></url>' for u in urls)
    (DOCS_DIR / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + filas + "\n</urlset>\n", encoding="utf-8")
    print(f"   {len(urls) - 1} páginas de provincia · sitemap con {len(urls)} URLs")
    c = datos["meta"]["contraste"]
    print(f"OK -> {OUT_HTML}")
    print(f"   {total} estaciones en {len(datos['provincias'])} provincias")
    print(f"   contraste: {c['refugio']['loc']} ({c['refugio']['nt']}) "
          f"vs {c['horno']['loc']} ({c['horno']['nt']})")
    print(f"   foehn: {datos['meta']['foehn']['loc']} ({datos['meta']['foehn']['nt']})")
    print(f"   tamaño HTML: {OUT_HTML.stat().st_size/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
