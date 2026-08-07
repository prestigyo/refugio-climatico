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

# URL pública del sitio, sin barra final. Dominio propio desde jul 2026;
# el github.io antiguo redirige (301) aquí. DOMINIO_ANTIGUO se usa para
# migrar los enlaces de las páginas estáticas de docs/ que no genera este script.
SITE_URL = "https://nochetropical.es"
DOMINIO_ANTIGUO = "https://prestigyo.github.io/refugio-climatico"

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
            "tmin": round(float(f["tmin_media_verano"]), 1),
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
                "license": "https://creativecommons.org/licenses/by/4.0/",
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
                "sameAs": ["https://x.com/nochetropicales"],
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
  .lt-note{display:inline-block;font-family:var(--fb);font-size:12.5px;font-weight:600;color:var(--muted);
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
  .barcol .csub{font-size:12.5px;color:var(--muted);margin-bottom:18px}
  .barrow{margin-bottom:14px}
  .barrow-top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
  .bn{font-size:13.5px;color:var(--paper);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .bv{font-family:var(--fm);font-size:13px;font-weight:700;color:var(--muted)}
  .bartrack{height:8px;border-radius:5px;background:#2c2114;overflow:hidden;margin:5px 0 2px}
  .bartrack>i{display:block;height:100%;width:0;border-radius:5px;transition:width 1.1s cubic-bezier(.22,1,.36,1)}
  .reveal.in .bartrack>i{width:var(--w)}
  .bp{font-size:11.5px;color:var(--muted)}
  .barnote{margin-top:8px;font-size:12.5px;color:var(--muted)}
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
  .fact span{font-size:12.5px;color:var(--muted)}
  .minimap-h{font-size:13.5px;color:var(--muted);margin-top:18px}
  .minimap-h b{color:var(--paper)}
  .minimap{width:100%;height:auto;display:block;margin-top:8px;background:var(--bg);border:1px solid var(--line);border-radius:12px}
  .certbadge{display:block;margin-top:18px;text-align:center;background:rgba(143,176,122,.12);border:1px solid var(--verde);color:var(--verde);font-weight:600;font-size:14px;padding:12px;border-radius:11px;text-decoration:none;transition:.15s}
  .certbadge b{font-weight:700}
  .certbadge:hover{background:var(--verde);color:#1a1209}
  .calbtn{margin-top:18px;width:100%;background:var(--bg);border:1px solid var(--line);color:var(--teal);font-weight:600;font-size:14px;padding:12px;border-radius:11px;cursor:pointer;transition:.15s}
  .calbtn:hover{border-color:var(--teja);color:var(--teja2)}
  .calcv{width:100%;height:auto;display:block;margin-top:12px;background:var(--bg);border:1px solid var(--line);border-radius:12px}
  .calleg{display:flex;gap:7px;flex-wrap:wrap;font-size:11px;color:var(--muted);margin-top:7px;align-items:center}
  .calleg .b{height:10px;width:74px;border-radius:3px;display:inline-block}
  .calleg .bmin{background:linear-gradient(90deg,#1e4670,#eaebf0 60%,#c8281e)}
  .calleg .bmax{background:linear-gradient(90deg,#fff7bc,#96140a)}
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
  .capture .lrgpd{display:flex;align-items:flex-start;gap:8px;font-size:12.5px;color:var(--muted);text-transform:none;letter-spacing:0;margin:2px 0;font-weight:400}
  .capture .lrgpd input{margin-top:3px;width:auto}
  .leadform button{background:var(--teja);border:none;color:#1a1209;font-weight:700;font-size:15px;padding:12px;border-radius:10px;cursor:pointer;transition:.15s}
  .leadform button:hover{background:var(--teja2)}
  .bridge{display:inline-block;margin-top:12px;color:var(--teal);font-size:13.5px;text-decoration:none}
  .bridge:hover{color:#b5cfdb;text-decoration:underline}
  .provnav{display:flex;flex-wrap:wrap;gap:9px 16px;margin-top:18px;font-size:14px}
  .provnav a{color:var(--teal);text-decoration:none}
  .provnav a:hover{color:var(--teja2);text-decoration:underline}
  footer{border-top:1px solid var(--line);padding:34px 0 60px;color:#9a8a6f;font-size:12.5px;line-height:1.6}
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
    <div style="text-align:center">
      <a class="cue" href="__SITE_URL__/mapa-estaciones/" style="margin-top:22px">Ver el mapa interactivo · pulsa cada punto →</a>
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
    <p style="margin:16px 0 0"><a href="__SITE_URL__/ola-de-calor/" style="font-weight:700;color:var(--teja2)">Ver el mapa animado a pantalla completa, con las flechas hacia los refugios →</a></p>

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
    <a href="__SITE_URL__/tu-pueblo/" style="color:var(--teja2)">¿Tu pueblo no aparece? →</a><br><br>
    Lee también: <a href="__SITE_URL__/refugio-climatico-natural/" style="color:var(--teja2)">Cómo combatir el calor sin aire acondicionado →</a>
    &nbsp;·&nbsp;<a href="__SITE_URL__/microclimas/" style="color:var(--teja2)">Microclimas: dónde el aire se queda fresco →</a>
    &nbsp;·&nbsp;<a href="__SITE_URL__/refugios-y-espana-vaciada/" style="color:var(--teja2)">Refugios y España vaciada →</a><br>
    <a href="__SITE_URL__/parte/" style="color:var(--teja2)">El parte de la noche (hoy) →</a>
    &nbsp;·&nbsp;<a href="https://x.com/nochetropicales" target="_blank" rel="noopener" style="color:var(--teja2)">Síguenos en X: @nochetropicales</a>
    &nbsp;·&nbsp;<a href="__SITE_URL__/ranking-noches-tropicales/" style="color:var(--teja2)">Ranking: dónde se duerme mejor y peor →</a>
    &nbsp;·&nbsp;<a href="__SITE_URL__/ola-de-calor/" style="color:var(--teja2)">La ola de calor, día y noche →</a>
    &nbsp;·&nbsp;<a href="__SITE_URL__/certificados/" style="color:var(--teja2)">Los refugios certificados →</a>
    &nbsp;·&nbsp;<a href="__SITE_URL__/metodologia/" style="color:var(--teja2)">Metodología y glosario</a>
    &nbsp;·&nbsp;<a href="__SITE_URL__/prensa/" style="color:var(--teja2)">Sala de prensa</a>
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
// ---------- Calendario de calor (canvas, responsive) ----------
function jslug(s){return s.normalize("NFD").replace(/\p{Diacritic}/gu,"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");}
function clerp(a,b,u){u=Math.max(0,Math.min(1,u));return `rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*u)).join(",")})`;}
function cMin(t){if(t==null)return "#241b11";return t<=20?clerp([30,70,112],[234,235,240],(t-6)/14):clerp([234,235,240],[200,40,30],(t-20)/8);}
function cMax(t){if(t==null)return "#241b11";return clerp([255,247,188],[150,20,10],(t-18)/24);}
const CMES=[["may",0],["jun",31],["jul",61],["ago",92],["sep",123]];
function dibujaCal(cv, est, A, N){
  const ctx=cv.getContext("2d"), NY=A.length, dpr=Math.min(2,window.devicePixelRatio||1);
  const W=Math.min(620, cv.parentElement.clientWidth||560), vert=window.innerWidth<700;
  const setup=h=>{cv.style.width=W+"px";cv.width=Math.round(W*dpr);cv.height=Math.round(h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.textBaseline="alphabetic";ctx.clearRect(0,0,W,h);};
  if(!vert){
    const mL=42,mR=50,ch=12,tH=22,mH=18,gap=22,cw=(W-mL-mR)/N,pH=tH+NY*ch+mH;setup(pH*2+gap);
    const panel=(yT,arr,tit,cf,nt)=>{ctx.fillStyle="#efe6d6";ctx.font="600 12px sans-serif";ctx.fillText(tit,mL,yT+14);const gy=yT+tH;
      for(let r=0;r<NY;r++){const y=gy+r*ch;ctx.fillStyle="#b3a48c";ctx.font="9px monospace";ctx.fillText(A[r],3,y+ch-3);
        for(let d=0;d<N;d++){ctx.fillStyle=cf(arr[r][d]);ctx.fillRect(mL+d*cw,y,cw+0.4,ch-1.1);}
        if(nt){ctx.fillStyle=nt[r]>0?"#e89a73":"#6b6150";ctx.font="700 9px monospace";ctx.fillText(nt[r],mL+N*cw+6,y+ch-3);}}
      ctx.fillStyle="#b3a48c";ctx.font="9px sans-serif";for(const[l,o]of CMES)ctx.fillText(l,mL+o*cw,gy+NY*ch+12);};
    panel(0,est.tmax,"MÁX día",cMax,null);panel(pH+gap,est.tmin,"MÍN noche (NT/año →)",cMin,est.nt);
  }else{
    const mL=26,gB=10,tL=48,bN=32,bW=(W-mL-gB)/2,colW=bW/NY,cH=Math.max(3,Math.min(5,520/N)),gH=N*cH;setup(tL+gH+bN);
    const blo=(x0,arr,tit,cf,nt)=>{ctx.fillStyle="#efe6d6";ctx.font="600 11px sans-serif";ctx.textAlign="left";ctx.fillText(tit,x0,12);
      // años: escalonados en dos alturas + línea guía a su columna (en móvil no caben en una fila)
      ctx.textAlign="center";ctx.font="8px monospace";
      for(let c=0;c<NY;c++){const cx=x0+c*colW+colW/2,ly=(c%2?34:23);
        ctx.strokeStyle="#5a4d3a";ctx.lineWidth=0.5;ctx.beginPath();ctx.moveTo(cx,ly+2);ctx.lineTo(cx,tL-1);ctx.stroke();
        ctx.fillStyle="#b3a48c";ctx.fillText("'"+String(A[c]%100).padStart(2,"0"),cx,ly);}
      for(let c=0;c<NY;c++)for(let r=0;r<N;r++){ctx.fillStyle=cf(arr[c][r]);ctx.fillRect(x0+c*colW,tL+r*cH,colW-0.4,cH+0.3);}
      if(nt){ctx.font="700 8px monospace";const by=tL+gH;
        for(let c=0;c<NY;c++){const cx=x0+c*colW+colW/2,ly=by+(c%2?22:11);
          ctx.strokeStyle="#5a4d3a";ctx.lineWidth=0.5;ctx.beginPath();ctx.moveTo(cx,by+1);ctx.lineTo(cx,ly-7);ctx.stroke();
          ctx.fillStyle=nt[c]>0?"#e89a73":"#6b6150";ctx.fillText(nt[c],cx,ly);}}
      ctx.textAlign="left";};
    blo(mL,est.tmax,"MÁX",cMax,null);blo(mL+bW+gB,est.tmin,"MÍN",cMin,est.nt);
    ctx.fillStyle="#b3a48c";ctx.font="8px sans-serif";ctx.textAlign="left";for(const[l,o]of CMES)ctx.fillText(l,0,tL+o*cH+7);
  }
}

function render(id,distKm){
  const e=TODAS.find(x=>x.id===id);if(!e)return;
  const [etq,col,bg,cls]=bandas(e.nt);
  const txt=e.nt<1?"menos de 1":(e.nt<10?e.nt.toFixed(1):Math.round(e.nt));
  const bigT=e.nt<1?'&lt;1<span class="lt-note">menos de 1</span>':txt;
  const pos=Math.min(100,e.nt/90*100);
  const distTxt=distKm?`<div class="res-meta">📍 Estación más cercana a ${distKm.toFixed(0)} km de ti</div>`:"";
  const url="__SITE_URL__/";
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
    ${e.nt<1?`<a class="certbadge" href="__SITE_URL__/certificados/${jslug(e.loc)}/">🏅 Refugio climático certificado — <b>ver su certificado</b></a>`:""}
    <button class="calbtn" id="calbtn" type="button">📅 Ver su calendario de calor (10 veranos)</button>
    <canvas class="calcv" id="calcv" style="display:none"></canvas>
    <div class="calleg" id="calleg" style="display:none"><span>Noche:</span><span class="b bmin"></span>fresco·20°·no refresca<span style="margin-left:8px">Día:</span><span class="b bmax"></span>18°–42°</div>
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
  const cbtn=$("#calbtn");
  if(cbtn) cbtn.addEventListener("click", async ()=>{
    const sl=jslug(e.prov);
    cbtn.textContent="Cargando calendario…"; cbtn.disabled=true;
    try{
      window.__cal=window.__cal||{};
      if(!window.__cal[sl]) window.__cal[sl]=await (await fetch("datos/"+sl+".json")).json();
      const pr=window.__cal[sl], est=pr.est[e.id];
      if(!est){ cbtn.textContent="Sin calendario para esta estación"; return; }
      const _c=$("#calcv"); _c.__d={est,a:pr.anios,n:pr.ndias}; dibujaCal(_c, est, pr.anios, pr.ndias);
      _c.style.display="block"; $("#calleg").style.display="flex"; cbtn.style.display="none";
    }catch(err){ cbtn.textContent="No se pudo cargar el calendario"; cbtn.disabled=false; }
  });
}

// ---------- Scroll reveal ----------
const io=new IntersectionObserver((es)=>{es.forEach(x=>{if(x.isIntersecting){x.target.classList.add("in");io.unobserve(x.target);}});},{threshold:.15});
document.querySelectorAll(".reveal").forEach(el=>io.observe(el));
let __rt; addEventListener("resize",()=>{clearTimeout(__rt);__rt=setTimeout(()=>{const c=document.querySelector("#calcv");if(c&&c.style.display!=="none"&&c.__d)dibujaCal(c,c.__d.est,c.__d.a,c.__d.n);},200);});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Capa 3 SEO: una página por provincia, con los datos en HTML (indexable)
# ---------------------------------------------------------------------------
VECINAS = {
    "A Coruña": ["Lugo", "Pontevedra"],
    "Albacete": ["Murcia", "Alicante", "Valencia", "Cuenca", "Jaén", "Ciudad Real"],
    "Alicante": ["Murcia", "Albacete", "Valencia"],
    "Almería": ["Granada", "Murcia", "Jaén"],
    "Araba/Álava": ["Bizkaia", "Gipuzkoa", "Navarra", "Burgos", "La Rioja"],
    "Asturias": ["Lugo", "León", "Cantabria"],
    "Ávila": ["Salamanca", "Valladolid", "Segovia", "Madrid", "Toledo", "Cáceres"],
    "Badajoz": ["Cáceres", "Ciudad Real", "Córdoba", "Sevilla", "Huelva"],
    "Illes Balears": ["Barcelona", "Valencia", "Alicante"],
    "Barcelona": ["Girona", "Lleida", "Tarragona"],
    "Bizkaia": ["Cantabria", "Burgos", "Araba/Álava", "Gipuzkoa"],
    "Burgos": ["Cantabria", "Palencia", "Valladolid", "Segovia", "Soria", "La Rioja", "Araba/Álava"],
    "Cáceres": ["Salamanca", "Ávila", "Toledo", "Ciudad Real", "Badajoz"],
    "Cádiz": ["Sevilla", "Málaga"],
    "Cantabria": ["Asturias", "León", "Palencia", "Burgos", "Bizkaia"],
    "Castellón": ["Tarragona", "Teruel", "Valencia"],
    "Ceuta": ["Cádiz", "Málaga"],
    "Ciudad Real": ["Toledo", "Cuenca", "Albacete", "Jaén", "Córdoba", "Badajoz", "Cáceres"],
    "Córdoba": ["Badajoz", "Sevilla", "Málaga", "Granada", "Jaén", "Ciudad Real"],
    "Cuenca": ["Guadalajara", "Teruel", "Valencia", "Albacete", "Ciudad Real", "Madrid"],
    "Gipuzkoa": ["Bizkaia", "Araba/Álava", "Navarra"],
    "Girona": ["Barcelona", "Lleida"],
    "Granada": ["Málaga", "Córdoba", "Jaén", "Almería"],
    "Guadalajara": ["Madrid", "Segovia", "Soria", "Zaragoza", "Teruel", "Cuenca"],
    "Huelva": ["Badajoz", "Sevilla"],
    "Huesca": ["Navarra", "Zaragoza", "Lleida"],
    "Jaén": ["Córdoba", "Ciudad Real", "Albacete", "Granada"],
    "La Rioja": ["Burgos", "Araba/Álava", "Navarra", "Soria"],
    "Las Palmas": ["Santa Cruz de Tenerife"],
    "León": ["Asturias", "Lugo", "Ourense", "Zamora", "Valladolid", "Palencia", "Cantabria"],
    "Lleida": ["Huesca", "Zaragoza", "Tarragona", "Barcelona"],
    "Lugo": ["A Coruña", "Pontevedra", "Ourense", "Asturias", "León"],
    "Madrid": ["Segovia", "Ávila", "Toledo", "Cuenca", "Guadalajara"],
    "Málaga": ["Cádiz", "Sevilla", "Córdoba", "Granada"],
    "Melilla": ["Almería", "Málaga"],
    "Murcia": ["Almería", "Albacete", "Alicante"],
    "Navarra": ["Gipuzkoa", "Araba/Álava", "La Rioja", "Zaragoza", "Huesca"],
    "Ourense": ["Lugo", "Pontevedra", "León", "Zamora"],
    "Palencia": ["León", "Cantabria", "Burgos", "Valladolid"],
    "Pontevedra": ["A Coruña", "Lugo", "Ourense"],
    "Salamanca": ["Zamora", "Valladolid", "Ávila", "Cáceres"],
    "Santa Cruz de Tenerife": ["Las Palmas"],
    "Segovia": ["Burgos", "Soria", "Guadalajara", "Madrid", "Ávila", "Valladolid"],
    "Sevilla": ["Huelva", "Badajoz", "Córdoba", "Málaga", "Cádiz"],
    "Soria": ["Burgos", "La Rioja", "Zaragoza", "Guadalajara", "Segovia"],
    "Tarragona": ["Barcelona", "Lleida", "Castellón", "Teruel"],
    "Teruel": ["Castellón", "Tarragona", "Zaragoza", "Guadalajara", "Cuenca", "Valencia"],
    "Toledo": ["Madrid", "Ávila", "Cáceres", "Ciudad Real", "Cuenca"],
    "Valencia": ["Castellón", "Cuenca", "Albacete", "Alicante", "Teruel"],
    "Valladolid": ["Palencia", "Burgos", "Segovia", "Ávila", "Salamanca", "Zamora", "León"],
    "Zamora": ["León", "Salamanca", "Valladolid", "Ourense"],
    "Zaragoza": ["Navarra", "Huesca", "Teruel", "Guadalajara", "Soria", "Lleida", "Tarragona"],
}

MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# Fecha en la que se amplió la landing de provincia con prosa, FAQ y JSON-LD
# Article/FAQPage. Fija (no se regenera cada vez): un "datePublished" de
# artículo no debe cambiar solo porque se vuelve a ejecutar el script.
FECHA_PUBLICACION_LANDINGS = "2026-06-22"


def fecha_es(fecha: date) -> str:
    """date(2026, 6, 22) -> 'junio de 2026'."""
    return f"{MESES_ES[fecha.month - 1]} de {fecha.year}"


def fecha_es_dia(fecha: date) -> str:
    """date(2026, 7, 13) -> '13 de julio de 2026' (con día, para fechar una noche)."""
    return f"{fecha.day} de {MESES_ES[fecha.month - 1]} de {fecha.year}"


# ---------------------------------------------------------------------------
# Menú global ESCUETO: header compartido de solo 4 entradas (Portada · Mapa
# interactivo · Ola de calor · Ranking). Es el patrón con el que unificar el
# chrome de todo el sitio más adelante; de momento solo lo montan las 52
# landings provinciales — el resto de páginas conserva su menú (nav_html/_MENU)
# hasta que se unifique en otra sesión. En móvil no hay hamburguesa: fila
# scrollable horizontal sin JS (lo más ligero, mismo patrón que el chrome
# grande) y el nombre del dominio se oculta dejando solo la luna. Las páginas
# que NO están aquí (/refugio-climatico-natural/, /microclimas/, /prensa/…)
# se enlazan contextualmente en el cuerpo, no desde el menú.
# ---------------------------------------------------------------------------
# "Portada" no va en el menú: la portada ya vive en el logo/marca. Su hueco lo
# ocupa la herramienta estrella de cercanía.
MENU_ESCUETO = [
    ("Observatorio", "/observatorio-del-descanso/"),
    ("Refugios cerca de mí", "/refugios-climaticos-naturales-cerca-de-mi/"),
    ("Hoteles", "/hoteles-refugio-climatico/"),
    ("Ola de calor", "/ola-de-calor/"),
    ("Ranking", "/ranking-noches-tropicales/"),
]

# Estilos del menú escueto, en la paleta de las landings (--bg/--line/--paper/
# --muted/--teja). Sticky y translúcido: es soporte, no protagonista.
CSS_NAV_ESCUETO = (
    '.nav-e{position:sticky;top:0;z-index:30;background:rgba(22,16,9,.88);'
    'backdrop-filter:saturate(1.3) blur(9px);border-bottom:1px solid var(--line)}'
    '.nav-e .in{max-width:min(92vw,920px);margin:0 auto;padding:0 22px;display:flex;'
    'align-items:center;gap:16px;height:54px}'
    '.nav-e .brand{display:flex;align-items:center;gap:9px;font-family:var(--fd);'
    'font-weight:600;font-size:16.5px;color:var(--paper);white-space:nowrap}'
    '.nav-e .brand:hover{text-decoration:none;color:var(--teja2)}'
    '.nav-e .links{margin-left:auto;display:flex;gap:2px;overflow-x:auto;'
    'scrollbar-width:none;-webkit-overflow-scrolling:touch}'
    '.nav-e .links::-webkit-scrollbar{display:none}'
    '.nav-e .links a{font-size:13.5px;color:var(--muted);padding:8px 11px;'
    'border-radius:8px;white-space:nowrap}'
    '.nav-e .links a:hover{color:var(--paper);background:rgba(217,116,78,.14);'
    'text-decoration:none}'
    '.nav-e .links a.lang{margin-left:4px;border:1px solid var(--line);'
    'color:var(--teja2);font-weight:600;letter-spacing:.04em}'
    '.nav-e .links a.lang:hover{border-color:var(--teja);background:rgba(217,116,78,.14)}'
    '@media(max-width:560px){.nav-e .brand span{display:none}'
    '.nav-e .in{gap:8px;padding:0 14px}.nav-e .links a{padding:8px 8px}}'
)

# La luna del favicon, en los colores de la paleta de las landings.
_LOGO_ESCUETO = ('<svg width="24" height="24" viewBox="0 0 100 100" aria-hidden="true">'
                 '<circle cx="45" cy="52" r="30" fill="var(--paper)"/>'
                 '<circle cx="60" cy="44" r="29" fill="var(--bg)"/>'
                 '<circle cx="73" cy="34" r="6.5" fill="var(--teja)"/></svg>'
                 '<span>nochetropical.es</span>')


def nav_escueto_html(site: str) -> str:
    """Header mínimo compartido. En las landings ninguna de las 4 entradas es
    la página actual, así que no se marca aria-current."""
    enlaces = "".join(f'<a href="{site}{href}">{txt}</a>' for txt, href in MENU_ESCUETO)
    # Conmutador de idioma discreto hacia la versión inglesa (simétrico al "ES"
    # del menú inglés; refuerza el hreflang con un enlace navegable).
    enlaces += f'<a href="{site}/en/" hreflang="en" class="lang" aria-label="English version" title="English version">EN</a>'
    return ('<nav class="nav-e" aria-label="principal"><div class="in">'
            f'<a class="brand" href="{site}/" aria-label="nochetropical.es">{_LOGO_ESCUETO}</a>'
            f'<div class="links">{enlaces}</div></div></nav>')


def mininav_footer_html(site: str) -> str:
    """Las mismas 4 entradas del menú global, como mini-nav para el pie."""
    return " · ".join(f'<a href="{site}{href}">{txt}</a>' for txt, href in MENU_ESCUETO)


# Pie COMPLETO del chrome escueto: tres columnas de interlinks con texto ancla
# descriptivo (SEO interno + navegabilidad) y barra de licencia. Lo montan las
# páginas nuevas (confortómetro, dormir con manta); es el patrón para sustituir
# poco a poco los pies mínimos del resto.
CSS_FOOTER_ESCUETO = (
    '.f2{border-top:1px solid var(--line);background:var(--bg2);margin-top:30px;'
    'padding:34px 0 46px}'
    '.f2grid{display:grid;grid-template-columns:repeat(3,1fr);gap:28px}'
    '.f2col h4{font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;'
    'color:var(--teja);margin:0 0 12px}'
    '.f2col a{display:block;color:var(--muted);font-size:13.5px;margin:0 0 8px;'
    'text-decoration:none}'
    '.f2col a:hover{color:var(--paper);text-decoration:underline}'
    '.f2bar{border-top:1px solid var(--line);margin-top:24px;padding-top:16px;'
    'font-size:12.5px;color:#9a8a6f}'
    '.f2bar a{color:#9a8a6f}'
    '.f2brand{margin-bottom:26px;max-width:42ch}'
    '.f2brand .brand{display:inline-flex;align-items:center;gap:9px;font-family:var(--fd);'
    'font-weight:600;font-size:16px;color:var(--paper)}'
    '.f2brand .brand:hover{text-decoration:none;color:var(--teja2)}'
    '.f2brand p{color:var(--muted);font-size:13.5px;margin:10px 0 0;line-height:1.6}'
    '@media(max-width:640px){.f2grid{grid-template-columns:1fr 1fr}}'
    '@media(max-width:420px){.f2grid{grid-template-columns:1fr}}'
)

# Columnas del pie, definidas UNA sola vez para que TODA la web (home y páginas
# de contenido) comparta el mismo pie, bien estructurado y con todos los enlaces
# (incluida la de hoteles). Rutas relativas; cada footer les antepone el site.
_F_TAGLINE = ("Diez veranos de datos de AEMET para responder una pregunta: "
              "¿dónde se duerme fresco en España?")
_F_EXPLORA = [("El Observatorio del Descanso", "/observatorio-del-descanso/"),
              ("Refugios climáticos cerca de mí", "/refugios-climaticos-naturales-cerca-de-mi/"),
              ("El Confortómetro: vota tu zona", "/confortometro/"),
              ("Mapa interactivo de estaciones", "/mapa-estaciones/"),
              ("¿Cuándo acaba la ola de calor?", "/ola-de-calor/"),
              ("Ranking nacional de noches tropicales", "/ranking-noches-tropicales/"),
              ("El parte de la noche", "/parte/"),
              ("Certificados de refugio climático", "/certificados/")]
_F_GUIAS = [("🏨 Hoteles donde dormir con manta", "/hoteles-refugio-climatico/"),
            ("Pueblos para dormir con manta en verano", "/dormir-con-manta-en-verano/"),
            ("La España que nunca se colorea (estudio)", "/la-espana-que-nunca-se-colorea/"),
            ("Microclimas: los refugios de la naturaleza", "/microclimas/"),
            ("Cómo crear un refugio climático natural", "/refugio-climatico-natural/"),
            ("Refugios y España vaciada", "/refugios-y-espana-vaciada/"),
            ("La hipoteca térmica", "/hipoteca-termica/")]
_F_PROYECTO = [("La calculadora de tu pueblo", "/"),
               ("Sobre el proyecto", "/sobre-el-proyecto/"),
               ("Metodología y glosario", "/metodologia/"),
               ("Sala de prensa", "/prensa/"),
               ("Certifica tu hotel", "/tu-hotel/"),
               ("¿Tu pueblo no aparece? Ayúdanos", "/tu-pueblo/"),
               ("Licencia y aviso legal", "/aviso-legal/")]


def footer_escueto_html(site: str, extra: str = "") -> str:
    def col(titulo: str, items: list) -> str:
        enlaces = "".join(f'<a href="{site}{h}">{t}</a>' for t, h in items)
        return f'<div class="f2col"><h4>{titulo}</h4>{enlaces}</div>'

    marca = (f'<div class="f2brand"><a class="brand" href="{site}/" '
             f'aria-label="nochetropical.es">{_LOGO_ESCUETO}</a>'
             f'<p>{_F_TAGLINE}</p></div>')
    return ('<footer class="f2"><div class="wrap">' + marca + '<div class="f2grid">'
            + col("Explora los datos", _F_EXPLORA)
            + col("Guías y artículos", _F_GUIAS)
            + col("Proyecto", _F_PROYECTO)
            + '</div><div class="f2bar">Fuente: '
            '<a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a>'
            ' · datos bajo <a href="https://creativecommons.org/licenses/by/4.0/deed.es" '
            'rel="license">CC&nbsp;BY&nbsp;4.0</a> · © 2026 '
            f'<a href="{site}/">nochetropical.es</a> · Ramón J. Lowesting'
            + (f' · {extra}' if extra else '') + '</div>'
            '</div></footer>')


CONSOLA_INFORMES = r"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Consola de informes · nochetropical.es</title>
<meta name="robots" content="noindex, nofollow">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900&family=Lora:wght@400&display=swap" rel="stylesheet">
<style>
 :root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--fd:"Fraunces",Georgia,serif;--fb:"Lora",Georgia,serif;--fm:ui-monospace,monospace}
 *{margin:0;padding:0;box-sizing:border-box}
 body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.6}
 .wrap{max-width:760px;margin:0 auto;padding:0 24px}
 a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}
 header{padding:40px 0 8px}
 .kick{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--teja);font-weight:600;margin-bottom:12px}
 h1{font-family:var(--fd);font-weight:900;font-size:clamp(26px,5vw,38px)}
 h2{font-family:var(--fd);font-weight:600;font-size:20px;margin:28px 0 10px}
 p{color:var(--muted);font-size:15px;margin:12px 0}
 input{width:100%;background:var(--bg2);border:1px solid var(--line);color:var(--paper);padding:12px 14px;border-radius:10px;font-size:15px;font-family:var(--fb)}
 .cmd{margin-top:14px;background:#0c0906;border:1px solid var(--line);border-radius:10px;padding:14px 16px;font-family:var(--fm);font-size:13.5px;color:var(--verde);word-break:break-all;display:none}
 .cmd b{color:var(--teja2)}
 .copiar{margin-top:10px;background:var(--teja);color:#1a1209;border:0;font-weight:700;padding:10px 16px;border-radius:9px;cursor:pointer;font-family:var(--fb);display:none}
 .verurl{display:none;margin-top:10px;font-size:14px}
 ul{list-style:none;margin:12px 0;padding:0}
 li{padding:12px 0;border-bottom:1px solid var(--line)}
 li a{font-family:var(--fd);font-weight:600;font-size:17px;color:var(--teja2)}
 li span{color:var(--muted);font-size:13px}
 .vacio{color:var(--muted);font-style:italic}
 footer{border-top:1px solid var(--line);margin-top:30px;padding:22px 0 60px;color:#9a8a6f;font-size:12.5px}
</style></head><body>
<header><div class="wrap"><div class="kick">Panel interno · nochetropical.es</div>
<h1>Consola de informes de zona</h1>
<p>Página privada (noindex). Genera y comparte informes por estación de AEMET.</p></div></header>

<section><div class="wrap">
 <h2>1 · Generar un informe</h2>
 <p>Busca una estación (por pueblo, provincia o indicativo) y copia el comando. Ejecútalo en el repo; el informe y su Excel quedan en <span style="font-family:var(--fm)">/informes/&lt;pueblo&gt;/</span>.</p>
 <input id="q" type="text" placeholder="Escribe un pueblo… (p. ej. Gandia, Cuenca, 8058X)" autocomplete="off" list="estlist">
 <datalist id="estlist"></datalist>
 <div class="cmd" id="cmd"></div>
 <button class="copiar" id="copiar" type="button">Copiar comando</button>
 <div class="verurl" id="verurl"></div>
</div></section>

<section><div class="wrap">
 <h2>2 · Informes ya generados</h2>
 <ul id="lista">__LISTA__</ul>
</div></section>

<footer><div class="wrap">Consola interna de <a href="__SITE__/">nochetropical.es</a>. No enlaces esta URL desde páginas públicas.</div></footer>
<script>
var EST=__EST__; // [id, loc, prov, slug]
var dl=document.getElementById("estlist");
EST.forEach(function(e){var o=document.createElement("option");o.value=e[1]+" ("+e[2]+") · "+e[0];dl.appendChild(o);});
var q=document.getElementById("q"),cmd=document.getElementById("cmd"),cop=document.getElementById("copiar"),vu=document.getElementById("verurl");
function buscar(txt){
 txt=txt.toLowerCase().trim();
 var m=txt.match(/·\s*([0-9a-z]{3,7})\s*$/i);
 if(m){for(var i=0;i<EST.length;i++)if(EST[i][0].toLowerCase()===m[1].toLowerCase())return EST[i];}
 for(var j=0;j<EST.length;j++)if(EST[j][0].toLowerCase()===txt)return EST[j];
 for(var k=0;k<EST.length;k++)if((EST[k][1]+" "+EST[k][2]).toLowerCase().indexOf(txt)>=0)return EST[k];
 return null;
}
q.addEventListener("input",function(){
 var e=buscar(q.value);
 if(!e||!q.value){cmd.style.display=cop.style.display=vu.style.display="none";return;}
 cmd.innerHTML="cd aemet-temperaturas<br>python scripts/generar_informe_lead.py --estacion <b>"+e[0]+"</b>";
 cmd.style.display="block";cop.style.display="inline-block";
 vu.style.display="block";
 vu.innerHTML='Una vez generado: <a href="__SITE__/informes/'+e[3]+'/">__SITE__/informes/'+e[3]+'/</a>';
 cop.setAttribute("data-cmd","cd aemet-temperaturas\npython scripts/generar_informe_lead.py --estacion "+e[0]);
});
cop.addEventListener("click",function(){
 var t=cop.getAttribute("data-cmd");
 if(navigator.clipboard)navigator.clipboard.writeText(t).then(function(){cop.textContent="Copiado ✓";setTimeout(function(){cop.textContent="Copiar comando";},1500);});
});
</script>
</body></html>
"""


def construir_consola_informes(estaciones: list, site: str) -> str:
    """Consola interna (noindex) del generador de informes: buscador de las 848
    estaciones que da el comando, y lista de informes ya publicados en
    docs/informes/. Se reconstruye en cada build escaneando la carpeta."""
    est_js = json.dumps(
        [[e["id"], e["loc"], e["prov"], slug(e["loc"])] for e in estaciones],
        ensure_ascii=False, separators=(",", ":"))
    base = DOCS_DIR / "informes"
    entradas = []
    if base.exists():
        for idx in sorted(base.glob("*/index.html")):
            m = re.search(r"<title>Informe de noches tropicales · (.+?) \((.+?)\)</title>",
                          idx.read_text(encoding="utf-8"))
            sl = idx.parent.name
            entradas.append((m.group(1) if m else sl, m.group(2) if m else "", sl))
    entradas.sort(key=lambda x: clave_orden(x[0]))
    if entradas:
        lista = "".join(
            f'<li><a href="{site}/informes/{sl}/">{loc}</a> '
            f'<span>· {prov} · <a href="{site}/informes/{sl}/datos.xlsx">Excel</a></span></li>'
            for loc, prov, sl in entradas)
    else:
        lista = '<li class="vacio">Aún no hay informes generados.</li>'
    return (CONSOLA_INFORMES
            .replace("__EST__", est_js)
            .replace("__LISTA__", lista)
            .replace("__SITE__", site))


def aplicar_menu_escueto(html: str, site: str) -> str:
    """Inyecta el menú escueto en una página cuya plantilla aún no trae ningún
    menú. Idempotente (si ya hay un nav, no toca nada) y solo apto para páginas
    con la paleta de la casa (usa sus variables CSS). Es el camino de migración
    hacia el chrome unificado sin reescribir cada plantilla."""
    nav = nav_escueto_html(site)
    # Si ya se inyectó el menú en un build anterior, se REFRESCA (por si cambió
    # MENU_ESCUETO): así una estática no se queda con un menú viejo ("Portada"
    # en vez de "Refugios cerca de mí", p. ej.).
    if 'class="nav-e"' in html:
        return _NAV_E_RE.sub(lambda _m: nav, html, count=1)
    if 'class="nav"' in html or "--teja:" not in html:
        return html
    html = html.replace("</style>", "\n " + CSS_NAV_ESCUETO + "\n</style>", 1)
    return html.replace("<body>", "<body>\n" + nav, 1)


_NAV_E_RE = re.compile(r'<nav class="nav-e".*?</nav>', re.DOTALL)


# Páginas antiguas cuyo pie es este "Pieza de divulgación…". Se detecta para
# sustituirlo por el pie unificado sin depender de un match byte a byte.
_FOOTER_VIEJO_RE = re.compile(
    r'<footer><div class="wrap">\s*<p>Pieza de divulgaci.*?</footer>', re.DOTALL)

# Interlinks del bloque "Sigue explorando" (texto ancla, href). Se filtra el
# auto-enlace según la carpeta que se procese.
_SIGUE_LINKS = [
    ("la calculadora de tu pueblo", "/"),
    ("los refugios climáticos naturales más cercanos a ti", "/refugios-climaticos-naturales-cerca-de-mi/"),
    ("los pueblos donde se duerme con manta en agosto", "/dormir-con-manta-en-verano/"),
    ("el ranking nacional de noches tropicales", "/ranking-noches-tropicales/"),
    ("por qué existen los microclimas", "/microclimas/"),
    ("cómo crear un refugio climático natural", "/refugio-climatico-natural/"),
    ("el Confortómetro", "/confortometro/"),
]


def enriquecer_estatica(html: str, site: str, carpeta: str) -> str:
    """En páginas antiguas con el pie 'Pieza de divulgación…': lo sustituye por
    el pie unificado (3 columnas con interlinks) precedido de un bloque 'Sigue
    explorando' con textos anclados. Idempotente: si no está ese pie, no toca
    nada (ya migró en un build anterior)."""
    if not _FOOTER_VIEJO_RE.search(html):
        return html
    links = [(t, h) for t, h in _SIGUE_LINKS if h.strip("/") != carpeta]
    lista = (", ".join(f'<a href="{site}{h}">{t}</a>' for t, h in links[:-1])
             + f' o <a href="{site}{links[-1][1]}">{links[-1][0]}</a>')
    sigue = f'<section class="wrap siguemas"><p>Sigue explorando: {lista}.</p></section>'
    html = _FOOTER_VIEJO_RE.sub(lambda _m: sigue + footer_escueto_html(site), html, count=1)
    css = (CSS_FOOTER_ESCUETO
           + '.siguemas{padding:20px 0}.siguemas p{color:var(--muted);font-size:15px;'
             'max-width:72ch;line-height:1.75;margin:0 auto}.siguemas a{color:var(--teal);font-weight:600}')
    return html.replace("</style>", css + "</style>", 1)


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
 .compartir{margin:22px 0;padding:15px 18px;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:14px}
 .compartir .ct{display:block;font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;color:var(--teja);margin-bottom:11px}
 .compartir .cbtns{display:flex;flex-wrap:wrap;gap:9px}
 .compartir .cb{font:600 13.5px/1 var(--fb);padding:9px 15px;border-radius:9px;border:1px solid var(--line);background:transparent;color:var(--paper);cursor:pointer;text-decoration:none;display:inline-block}
 .compartir .cb:hover{border-color:var(--teja);color:var(--teja2);text-decoration:none;background:rgba(217,116,78,.10)}
 .provnav{display:flex;flex-wrap:wrap;gap:9px 16px;margin-top:14px;font-size:13.5px}
 footer{border-top:1px solid var(--line);padding:30px 0 60px;color:#9a8a6f;font-size:12.5px;margin-top:18px}
 footer a{color:#9a8a6f}
 caption{caption-side:top;text-align:left;font-size:13px;color:var(--muted);margin-bottom:10px;font-weight:600}
 .prose{margin:28px 0;max-width:760px}
 .prose h2{font-family:var(--fd);font-weight:700;font-size:clamp(20px,3.6vw,25px);line-height:1.2;margin:30px 0 10px}
 .prose h2:first-child{margin-top:0}
 .prose p{color:var(--muted);font-size:15px;margin:0 0 14px}
 .prose p b{color:var(--paper)}
 .prose p.note{font-size:12.5px}
 .faq{margin-top:6px;max-width:760px}
 .faqitem{padding:16px 0;border-bottom:1px solid var(--line)}
 .faqitem:first-child{padding-top:0}
 .faqitem h3{font-family:var(--fd);font-weight:600;font-size:16.5px;margin-bottom:6px}
 .faqitem p{color:var(--muted);font-size:14.5px}
 .vecinas{font-size:13.5px;margin:8px 0 4px}
 .ctarow{margin:26px 0;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:20px;text-align:center}
 .botones{display:flex;flex-wrap:wrap;gap:10px;justify-content:center}
 .btn{display:inline-block;padding:12px 18px;border-radius:11px;font-weight:700;font-size:14.5px}
 .btn.pri{background:var(--teja);color:#1a1209}.btn.pri:hover{background:var(--teja2);text-decoration:none}
 .btn.sec{background:transparent;border:1px solid var(--teja);color:var(--teja2)}.btn.sec:hover{background:rgba(217,116,78,.12);text-decoration:none}
 .prose p.ctain{margin:-4px 0 18px;font-size:15px}.prose p.ctain a{font-weight:600}
 .tend{display:flex;align-items:flex-end;gap:5px;height:104px;margin:12px 0 4px;max-width:540px}
 .tend .tb{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%}
 .tend .tb>i{width:100%;background:linear-gradient(180deg,var(--teja2),var(--teja));border-radius:3px 3px 0 0;min-height:5px}
 .tend .tb>span{font-size:10px;color:var(--muted);margin-top:5px;font-family:var(--fm)}
 __NAVCSS__
 __FOOTERCSS__
 @media(max-width:520px){th.hide,td.hide{display:none}}
 @media(min-width:1000px){
  .wrap{max-width:min(94vw,1200px)}
  .dcols{display:grid;grid-template-columns:1fr 1.05fr;gap:0 48px;align-items:start}
  .dcols .prose{margin-top:0;max-width:none}
  .dcols .prose h2:first-child{margin-top:0}
  .faq{max-width:none;display:grid;grid-template-columns:1fr 1fr;gap:0 48px}
 }
 .reg-band{padding:20px 0 2px}
 .registro{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:20px 22px}
 .reg-cab{margin-bottom:14px}
 .reg-kick{font:600 12px/1 var(--fb);letter-spacing:.13em;text-transform:uppercase;color:var(--teja)}
 .reg-cols{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
 @media(max-width:640px){.reg-cols{grid-template-columns:1fr}}
 .reg-item{display:flex;flex-direction:column;gap:6px;padding:15px 16px;background:rgba(0,0,0,.18);border:1px solid var(--line);border-radius:12px}
 .reg-big{background:rgba(217,116,78,.09);border-color:rgba(217,116,78,.4)}
 .reg-lab{font:600 11.5px/1.3 var(--fb);letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
 .reg-val{font-family:var(--fd);font-weight:900;font-size:clamp(28px,6vw,38px);line-height:1;color:var(--paper)}
 .reg-sub{font-size:13px;color:var(--muted)}
 .reg-badge{align-self:flex-start;font:700 12.5px/1 var(--fb);padding:6px 11px;border-radius:999px;margin-top:1px}
 .reg-badge.ec{background:rgba(184,52,80,.22);color:#eaa6b2;border:1px solid #B83450}
 .reg-badge.tr{background:rgba(217,116,78,.18);color:var(--teja2);border:1px solid var(--teja)}
 .reg-badge.fr{background:rgba(150,182,196,.16);color:var(--teal);border:1px solid var(--teal)}
 .reg-nota{font-size:13.5px;color:var(--muted);margin:14px 0 0}
 .reg-nota b{color:var(--paper)}
 .reg-nota a{color:var(--teal)}
</style>
</head>
<body>
__NAV__
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">Refugio Climático</a> · __PROVNAME__</nav>
  <div class="kick">Noches tropicales · Datos AEMET</div>
  <h1>__H1__</h1>
  <p class="intro">__INTRO__</p>
</div></header>

__WIDGET__

<section><div class="wrap"><div class="dcols">
  <div><div class="prose">__PROSA__</div></div>

  <div>
  <table>
    <caption>__CAPTION__</caption>
    <thead><tr><th>Localidad</th><th class="hide">Altitud</th><th class="r">Noches tropicales/año</th>__COLHUM__<th>Cómo se duerme</th></tr></thead>
    <tbody>__TABLE__</tbody>
  </table>
  <p class="note">Una noche tropical es aquella en que la mínima no baja de 20&nbsp;°C. Media anual, veranos 2017–2026. Fuente: AEMET. · <a href="datos.csv" download>Descargar estos datos (CSV)</a></p>

  <div class="ctarow">
    <div class="botones">
      <a class="btn pri" href="__SITE__/mapa-estaciones/">📍 Ver __PROVNAME__ en el mapa interactivo →</a>
      <a class="btn sec" href="__SITE__/ola-de-calor/">🌡️ ¿Cómo va la ola de calor hoy? →</a>
    </div>
  </div>

  __COMPARTIR__

  <div class="cta">
    <b>¿Quieres comparar con cualquier pueblo de España?</b><br>
    <a class="btn" href="__HOME__">Abre el mapa y la calculadora →</a>
  </div>
  </div>
</div></div></section>

<section><div class="wrap">
  <div class="kick">Preguntas frecuentes</div>
  <div class="faq">__FAQ__</div>
</div></section>

<section><div class="wrap">
  <div class="cta">
    <b>¿Qué puesto ocupan los pueblos de __PROVNAME__ en el ranking nacional?</b><br>
    <a class="btn" href="__SITE__/ranking-noches-tropicales/">🏆 Ver el ranking nacional →</a>
  </div>
</div></section>

<section><div class="wrap">
  __VECINAS__
  <div class="kick">Todas las provincias</div>
  <nav class="provnav" aria-label="Todas las provincias">__PROVNAV__</nav>
</div></section>

__FOOTER__
<script>
(function(){
 var box=document.querySelector(".compartir"); if(!box) return;
 var url=box.getAttribute("data-url"), text=box.getAttribute("data-text");
 var cp=document.getElementById("cb-copiar");
 if(cp&&navigator.clipboard) cp.addEventListener("click",function(){
   navigator.clipboard.writeText(url).then(function(){
     cp.textContent="Enlace copiado"; setTimeout(function(){cp.textContent="Copiar enlace";},1600);
   });
 });
 var sh=document.getElementById("cb-share");
 if(sh&&navigator.share){ sh.hidden=false;
   sh.addEventListener("click",function(){
     navigator.share({title:document.title,text:text,url:url}).catch(function(){});
   });
 }
})();
</script>
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
    return f"{nt:.1f}".replace(".", ",") if nt < 10 else f"{round(nt)}"


def nt_prosa(nt: float) -> str:
    """Como ntfmt pero para texto plano (meta description): sin entidades HTML."""
    if nt < 1:
        return "menos de 1"
    return f"{nt:.1f}".replace(".", ",") if nt < 10 else f"{round(nt)}"


def construir_schema_provincia(prov: str, site: str, sl: str, n: int, titulo: str,
                                desc: str, faq: list[tuple[str, str]],
                                fecha_mod: str) -> dict:
    url = f"{site}/{sl}/"
    return {"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": prov, "item": url}]},
        {"@type": "Article",
         "headline": titulo,
         "description": desc,
         "image": site + "/og.png",
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "publisher": {"@type": "Organization", "name": "Refugio Climático",
                       "logo": {"@type": "ImageObject", "url": site + "/favicon.svg"}},
         "datePublished": FECHA_PUBLICACION_LANDINGS,
         "dateModified": fecha_mod,
         "mainEntityOfPage": url},
        {"@type": "Dataset",
         "name": f"Noches tropicales en {prov} (AEMET, 2017–2026)",
         "description": (f"Noches tropicales al año en la única estación de AEMET de {prov}"
                          if n == 1 else
                          f"Noches tropicales al año en las {n} estaciones de AEMET de {prov}")
                         + ", veranos 2017–2026.",
         "url": url, "isBasedOn": "https://opendata.aemet.es",
         "spatialCoverage": {"@type": "Place", "name": prov}, "temporalCoverage": "2017/2026",
         "variableMeasured": "Noches tropicales por estación meteorológica",
         "license": "https://creativecommons.org/licenses/by/4.0/",
         "creator": {"@type": "Person", "name": "Ramón J. Lowesting"}},
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq]},
    ]}


def prosa_contraste(prov: str, mejor: dict, peor: dict, n: int) -> str:
    if n <= 1:
        return (f"<h2>Una sola estación con datos suficientes</h2>"
                f"<p>{prov} solo tiene una estación de AEMET con cobertura suficiente para este "
                f"análisis: <b>{mejor['loc']}</b>, a {miles(mejor['alt'])} m de altitud, con "
                f"{ntfmt(mejor['nt'])} noches tropicales al año de media. No hay aquí más puntos "
                f"de comparación dentro de la provincia.</p>")
    ratio = (f" — unas {round(peor['nt'] / mejor['nt'], 1)} veces más"
             if mejor["nt"] >= 1 else "")
    alt_mejor = miles(mejor["alt"])
    alt_peor = miles(peor["alt"])
    return (f"<h2>El contraste en {prov}</h2>"
            f"<p>{prov} tiene {n} estaciones de AEMET con datos suficientes. En <b>{mejor['loc']}</b> "
            f"({alt_mejor} m) se cuentan {ntfmt(mejor['nt'])} noches tropicales al año, mientras que "
            f"en <b>{peor['loc']}</b> ({alt_peor} m) suben hasta {ntfmt(peor['nt'])}{ratio}. Cuanto "
            f"más alta y más alejada de la costa está una estación, más fácil que el aire se enfríe "
            f"de noche; cuanto más próxima al mar o en una cubeta de baja altitud, más cuesta que la "
            f"temperatura baje de los 20&nbsp;°C.</p>")


def prosa_refugios(prov: str, refugios: list) -> str:
    if not refugios:
        return (f"<h2>Los refugios climáticos de {prov}</h2>"
                f"<p>Ninguna estación de {prov} baja de 1 noche tropical al año de media, así que "
                f"no hay aquí un refugio en sentido estricto. La tabla de arriba está ordenada de la "
                f"más fresca a la más calurosa: las primeras filas son las que mejor concilian el "
                f"sueño en la provincia.</p>")
    nombres = ", ".join(f"<b>{e['loc']}</b> ({e['alt']:,} m)".replace(",", ".")
                         for e in refugios[:6])
    plural = "estaciones" if len(refugios) > 1 else "estación"
    return (f"<h2>Los refugios climáticos de {prov}</h2>"
            f"<p>{len(refugios)} {plural} de {prov} no llegan a 1 noche tropical al año de media: "
            f"{nombres}. Son los puntos donde, incluso en pleno verano, la temperatura nocturna baja "
            f"con fiabilidad de los 20&nbsp;°C — normalmente por la altitud, la lejanía del mar o "
            f"ambas cosas a la vez.</p>")


def prosa_peores(prov: str, peores: list, mejor: dict) -> str:
    nombres = ", ".join(f"<b>{e['loc']}</b> ({ntfmt(e['nt'])} noches/año)" for e in peores)
    return (f"<h2>Las localidades donde peor se duerme</h2>"
            f"<p>En el otro extremo, donde peor se duerme en {prov}: {nombres}. Frente a las "
            f"{ntfmt(mejor['nt'])} noches tropicales de {mejor['loc']}, la diferencia suele "
            f"explicarse por la cercanía al mar, la baja altitud o el efecto urbano: el asfalto y el "
            f"cemento retienen el calor del día y lo devuelven por la noche.</p>")


def prosa_metodologia(prov: str, n: int, fecha_txt: str) -> str:
    de_n_estaciones = f"de la única estación" if n == 1 else f"de las {n} estaciones"
    return (f"<h2>Metodología</h2>"
            f"<p>Una <b>noche tropical</b> es aquella en la que la temperatura mínima no baja de "
            f"20&nbsp;°C: el indicador que mejor refleja si se descansa bien en verano, mejor que "
            f"la media (que esconde los picos). Los datos de {prov} proceden {de_n_estaciones} "
            f'de <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a> '
            f"con cobertura suficiente (al menos 3 veranos con datos y, dentro de cada verano, al "
            f"menos 60 días con mínima registrada), promediando los veranos (junio–agosto) de 2017 a "
            f"2026. Limitación: el dato es de la estación, no del municipio entero — en zonas de "
            f"montaña la temperatura puede cambiar mucho en pocos kilómetros según el desnivel.</p>"
            f"<p class=\"note\">Última actualización de los datos: {fecha_txt}.</p>")


def miles(n: int) -> str:
    """1699 -> '1.699' (separador de miles con punto, como el resto de la página)."""
    return f"{n:,}".replace(",", ".")


def construir_faq_provincia(prov: str, mejor: dict, peor: dict, n: int) -> list[tuple[str, str]]:
    faq = [
        (f"¿Dónde se duerme mejor en {prov} en verano?",
         f"En {mejor['loc']} ({miles(mejor['alt'])} m de altitud), con unas {ntfmt(mejor['nt'])} noches "
         "tropicales al año según los datos de AEMET."),
        ("¿Qué es exactamente una noche tropical?",
         "Una noche en la que la temperatura mínima no baja de 20 °C. Es el indicador que mejor "
         "refleja si se descansa bien, porque no se diluye en una media como pasaría con la "
         "temperatura mínima media."),
        (f"¿Cuál es el pueblo más fresco de {prov}?",
         f"{mejor['loc']}, a {miles(mejor['alt'])} m de altitud, con unas {ntfmt(mejor['nt'])} noches "
         "tropicales al año de media."),
    ]
    if n > 1:
        faq.append((f"¿Cuál es el pueblo donde peor se duerme en {prov}?",
                     f"{peor['loc']}, con unas {ntfmt(peor['nt'])} noches tropicales al año — frente "
                     f"a las {ntfmt(mejor['nt'])} de {mejor['loc']}."))
    faq.append(("¿De dónde salen los datos?",
                "De AEMET OpenData, la API pública de la Agencia Estatal de Meteorología. Se usan los "
                "datos diarios de temperatura mínima de los veranos (junio–agosto) de 2017 a 2026."))
    faq.append(("¿Por qué la altitud o la cercanía al mar cambian tanto las noches?",
                "El aire frío es más denso y se acumula en las zonas altas durante la noche, mientras "
                "que el mar libera de noche el calor que ha acumulado de día, lo que mantiene templado "
                "el aire costero. Por eso, en general, cuanto más alta y más alejada de la costa está "
                "una estación, más noches frescas tiene."))
    return faq


def faq_html(faq: list[tuple[str, str]]) -> str:
    return "".join(f'<div class="faqitem"><h3>{q}</h3><p>{a}</p></div>' for q, a in faq)


def vecinas_html(prov: str, site: str) -> str:
    vecinas = VECINAS.get(prov, [])
    bloque = ""
    if vecinas:
        enlaces = " · ".join(f'<a href="{site}/{slug(v)}/">{v}</a>' for v in vecinas)
        bloque = f'<div class="kick">Provincias vecinas</div><p class="vecinas">{enlaces}</p>'
    bloque += (f'<p class="vecinas"><a href="{site}/mapa-estaciones/">'
               f'Ver el mapa interactivo de toda España →</a></p>')
    return bloque


def barra_compartir(url: str, texto: str) -> str:
    """Barra de compartir reutilizable: WhatsApp, X, Copiar enlace y Compartir
    nativo (móvil). WhatsApp y X llevan el texto pre-rellenado. El texto debe
    ir sin emojis y con el dato favorable primero."""
    from urllib.parse import quote
    import html as _html
    wa = "https://wa.me/?text=" + quote(texto + " " + url)
    tw = ("https://twitter.com/intent/tweet?text=" + quote(texto)
          + "&amp;url=" + quote(url))
    ta, ua = _html.escape(texto, quote=True), _html.escape(url, quote=True)
    return (
        f'<div class="compartir" data-url="{ua}" data-text="{ta}">'
        '<span class="ct">Comparte estos datos</span><div class="cbtns">'
        f'<a class="cb" href="{wa}" target="_blank" rel="noopener">WhatsApp</a>'
        f'<a class="cb" href="{tw}" target="_blank" rel="noopener">X</a>'
        '<button class="cb" id="cb-copiar" type="button">Copiar enlace</button>'
        '<button class="cb" id="cb-share" type="button" hidden>Compartir…</button>'
        '</div></div>')


# Slug de la herramienta de cercanía. Lleva "naturales" a propósito: "refugio
# climático" a secas es el término oficial de los locales con aire que abren los
# ayuntamientos en las olas, que es justo lo contrario de lo que contamos.
SLUG_CERCA = "refugios-climaticos-naturales-cerca-de-mi"

# Carpetas que solo contienen una redirección: fuera del sitemap (no son páginas).
REDIRECCIONES: list[str] = []


def escribir_redireccion(site: str, carpeta: str, destino: str, mensaje: str,
                         noindex: bool = False) -> None:
    """Deja en `carpeta` un stub que manda a `destino`.

    GitHub Pages no sabe hacer un 301, así que lo más parecido es un
    meta-refresh instantáneo + canonical. Google lo acaba tratando como
    redirección, aunque más despacio y con menos fuerza que un 301 real.

    `noindex` solo para páginas que NO queremos consolidar (un duplicado que
    sobra). En una MUDANZA de URL hay que dejarlo en False: el canonical es lo
    único que traspasa la señal, y un noindex la borraría.
    """
    REDIRECCIONES.append(carpeta)
    (DOCS_DIR / carpeta).mkdir(parents=True, exist_ok=True)
    robots = '<meta name="robots" content="noindex,nofollow">' if noindex else ""
    (DOCS_DIR / carpeta / "index.html").write_text(
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        + robots
        + f'<link rel="canonical" href="{destino}">'
        f'<meta http-equiv="refresh" content="0; url={destino}">'
        '<title>Redirigiendo a nochetropical.es</title></head><body>'
        f'<p>{mensaje} <a href="{destino}">Continuar</a></p>'
        '</body></html>', encoding="utf-8")


def csv_provincia(lista: list[dict]) -> str:
    """CSV limpio de una provincia (una fila por estación) para descarga en la
    web y para prensa. Formato máquina: decimales con punto. Usa csv.writer por
    si algún nombre lleva coma (p. ej. «Sóller, Puerto»)."""
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["estacion", "altitud_m", "noches_tropicales_anio",
                "noches_ecuatoriales_anio", "latitud", "longitud", "anios_datos"])
    for e in sorted(lista, key=lambda x: (x["nt"], -x["alt"])):
        w.writerow([e["loc"], e["alt"], e["nt"], e["ne"], e["lat"], e["lon"], e["anios"]])
    return buf.getvalue()


def _sensacion_nocturna(tmin, hr: int) -> str:
    """Lectura honesta de la noche combinando la mínima media de agosto y la
    humedad relativa. El bochorno nocturno necesita calor Y humedad; en los
    refugios de altura la mínima baja tanto que no hay bochorno aunque el aire
    sea húmedo. No inventa: solo describe la combinación de dos datos reales."""
    seco = "aire seco" if hr < 50 else ("humedad media" if hr < 68 else "aire húmedo")
    if tmin is None:
        return seco
    if tmin < 16:
        return f"noche fresca, {seco}"
    if tmin < 20:
        return "templada y húmeda" if hr >= 68 else f"templada, {seco}"
    # tmin >= 20: la noche ya es de por sí tropical
    return "noche de bochorno" if hr >= 60 else "noche cálida pero seca"


def cargar_humedad_estaciones(estaciones: list) -> dict:
    """Humedad relativa y viento medios de AGOSTO por estación, leyendo los
    diarios_humedad_*.csv (backfill histórico) y diarios_humedad.csv (rolling
    diario). AEMET da la humedad en % y velmedia/racha en m/s en el producto
    climatológico diario: el viento se pasa a km/h para el público (si el primer
    dato real desmintiera la unidad, basta cambiar el factor de aquí).

    Devuelve {id: {"hr": %, "viento": km/h?, "sensacion": etiqueta}}. Es un
    COMPLEMENTO: degrada a {} mientras no exista el dato (antes del primer
    backfill de humedad), y la web sigue funcionando igual sin él."""
    from collections import defaultdict
    datos_dir = AEMET_DIR / "datos"
    paths = sorted(datos_dir.glob("diarios_humedad_2*.csv"))
    rolling = datos_dir / "diarios_humedad.csv"
    if rolling.exists():
        paths.append(rolling)
    if not paths:
        return {}
    acc_hr: dict = defaultdict(lambda: [0.0, 0])   # id -> [suma, n]
    acc_v: dict = defaultdict(lambda: [0.0, 0])
    for path in paths:
        with path.open(encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            cab = next(rd, None)
            if not cab:
                continue
            try:
                i_f = cab.index("fecha"); i_ind = cab.index("indicativo")
                i_hr = cab.index("hr_media"); i_v = cab.index("vel_media")
            except ValueError:
                continue
            tope = max(i_f, i_ind, i_hr, i_v)
            for row in rd:
                if len(row) <= tope or row[i_f][5:7] != "08":  # solo agosto
                    continue
                ind = row[i_ind]
                try:
                    acc_hr[ind][0] += float(row[i_hr]); acc_hr[ind][1] += 1
                except ValueError:
                    pass
                try:
                    acc_v[ind][0] += float(row[i_v]); acc_v[ind][1] += 1
                except ValueError:
                    pass
    tmin_by = {e["id"]: e.get("tmin") for e in estaciones}
    out: dict = {}
    for ind in set(acc_hr) | set(acc_v):
        hs, hn = acc_hr[ind]
        if hn < 15:  # sin cobertura mínima de agosto no damos el dato (honestidad)
            continue
        hr = round(hs / hn)
        d = {"hr": hr, "sensacion": _sensacion_nocturna(tmin_by.get(ind), hr)}
        vs, vn = acc_v[ind]
        if vn >= 15:
            d["viento"] = round(vs / vn * 3.6)  # m/s -> km/h
        out[ind] = d
    return out


def cargar_tendencia_provincias(estaciones: list) -> dict:
    """Media de noches tropicales por estación y verano (jun–ago), por provincia
    y año, leyendo los CSV diarios (2017–2026). Devuelve {provincia: {año: media}}.
    Contenido ÚNICO por provincia (rompe la similitud de plantilla ante Google) y
    a la vez noticiable. Degrada a {} si no hay CSVs diarios disponibles.

    Nota: lee ~200 MB una sola vez; con csv.reader (no DictReader) tarda ~20 s."""
    ind_prov = {e["id"]: e["prov"] for e in estaciones}
    from collections import defaultdict
    acc: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))
    datos_dir = AEMET_DIR / "datos"
    for path in sorted(datos_dir.glob("diarios_2*.csv")):
        with path.open(encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            cab = next(rd, None)
            if not cab:
                continue
            try:
                i_f, i_ind, i_tmin = cab.index("fecha"), cab.index("indicativo"), cab.index("tmin")
            except ValueError:
                continue
            for row in rd:
                if len(row) <= i_tmin:
                    continue
                prov = ind_prov.get(row[i_ind])
                if not prov:
                    continue
                fecha = row[i_f]
                if fecha[5:7] not in ("06", "07", "08"):
                    continue
                try:
                    tmin = float(row[i_tmin])
                except ValueError:
                    continue
                celda = acc[prov][int(fecha[:4])][row[i_ind]]
                celda[1] += 1
                if tmin >= 20:
                    celda[0] += 1
    resultado: dict = {}
    for prov, anios in acc.items():
        serie = {}
        for anio, inds in anios.items():
            # solo estaciones con verano bien cubierto (>=60 días con mínima)
            vals = [c[0] for c in inds.values() if c[1] >= 60]
            if vals:
                serie[anio] = sum(vals) / len(vals)
        if serie:
            resultado[prov] = serie
    return resultado


def cargar_ultima_noche(estaciones: list) -> dict:
    """Mínima de la ÚLTIMA noche con dato VALIDADO de AEMET, por estación, leyendo
    el rolling datos/diarios_estaciones.csv (y de refuerzo el diario del año en
    curso). Devuelve {indicativo: {"fecha": "YYYY-MM-DD", "tmin": float}} con la
    fecha más reciente que tenga mínima válida en cada estación.

    Es un COMPLEMENTO honesto: el dato climatológico de AEMET llega con 3-5 días de
    retraso, así que NO se etiqueta como 'anoche' sino con su fecha real. Degrada a
    {} si no hay CSV y la web funciona igual sin él."""
    datos_dir = AEMET_DIR / "datos"
    paths = [datos_dir / "diarios_estaciones.csv"]
    diario_anio = datos_dir / f"diarios_{date.today().year}.csv"
    if diario_anio.exists():
        paths.append(diario_anio)
    out: dict = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            cab = next(rd, None)
            if not cab:
                continue
            try:
                i_f, i_ind, i_tmin = cab.index("fecha"), cab.index("indicativo"), cab.index("tmin")
            except ValueError:
                continue
            tope = max(i_f, i_ind, i_tmin)
            for row in rd:
                if len(row) <= tope:
                    continue
                try:
                    tmin = float(row[i_tmin])
                except ValueError:
                    continue
                ind, fecha = row[i_ind], row[i_f]  # ISO -> orden lexicográfico = cronológico
                prev = out.get(ind)
                if prev is None or fecha > prev["fecha"]:
                    out[ind] = {"fecha": fecha, "tmin": tmin}
    return out


def cargar_verano_actual(estaciones: list) -> dict:
    """Recuento de noches tropicales del VERANO EN CURSO (jun–ago del año actual)
    por estación, leyendo datos/diarios_{año}.csv. Devuelve
    {indicativo: {"nt": int, "noches": int, "hasta": "YYYY-MM-DD"}}. Degrada a {} si
    todavía no hay datos de verano (p.ej. antes de junio)."""
    from collections import defaultdict
    datos_dir = AEMET_DIR / "datos"
    anio = str(date.today().year)
    # El fichero del año es la fuente canónica; el rolling se suma para no perder
    # las noches más recientes si aquel va por detrás. Se deduplica por (est, noche).
    paths = [datos_dir / f"diarios_{anio}.csv", datos_dir / "diarios_estaciones.csv"]
    acc: dict = defaultdict(lambda: {"nt": 0, "noches": 0, "hasta": ""})
    vistos: set = set()
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            cab = next(rd, None)
            if not cab:
                continue
            try:
                i_f, i_ind, i_tmin = cab.index("fecha"), cab.index("indicativo"), cab.index("tmin")
            except ValueError:
                continue
            tope = max(i_f, i_ind, i_tmin)
            for row in rd:
                if len(row) <= tope:
                    continue
                f = row[i_f]
                if f[:4] != anio or f[5:7] not in ("06", "07", "08"):
                    continue
                try:
                    tmin = float(row[i_tmin])
                except ValueError:
                    continue
                clave = (row[i_ind], f)
                if clave in vistos:
                    continue
                vistos.add(clave)
                c = acc[row[i_ind]]
                c["noches"] += 1
                if tmin >= 20:
                    c["nt"] += 1
                if f > c["hasta"]:
                    c["hasta"] = f
    return dict(acc)


def estado_noche(tmin: float | None) -> tuple[str, str] | None:
    """(etiqueta, clase CSS) según la mínima nocturna. None si no hay dato.
    Umbrales de AEMET: noche tropical ≥ 20 °C, noche ecuatorial ≥ 25 °C."""
    if tmin is None:
        return None
    if tmin >= 25:
        return ("Noche ecuatorial", "ec")
    if tmin >= 20:
        return ("Noche tropical", "tr")
    return ("Noche fresca", "fr")


def estacion_ciudad(prov: str, lista: list, peor: dict) -> dict:
    """La estación que mejor representa a la capital/ciudad de la provincia. La
    mayoría de capitales españolas comparten nombre con su provincia (Valencia,
    Sevilla, Córdoba, Badajoz…): se prefiere la coincidencia de nombre, excluyendo
    aeropuertos; a igualdad, la de menor altitud (la de dentro de la ciudad). Si no
    hay coincidencia (capital con otro nombre: Oviedo, Bilbao…), cae al 'horno'
    local (la estación más calurosa), que sigue siendo un dato real de la zona."""
    pn = clave_orden(prov)

    def sin_aero(e: dict) -> bool:
        return "aeropuerto" not in clave_orden(e["loc"])

    exactas = [e for e in lista if clave_orden(e["loc"]) == pn]
    if exactas:
        return exactas[0]
    empiezan = [e for e in lista if clave_orden(e["loc"]).startswith(pn) and sin_aero(e)]
    if empiezan:
        return sorted(empiezan, key=lambda e: e["alt"])[0]
    contienen = [e for e in lista if pn in clave_orden(e["loc"]) and sin_aero(e)]
    if contienen:
        return sorted(contienen, key=lambda e: e["alt"])[0]
    return peor


def construir_widget_registro(prov: str, ciudad: dict, ultima: dict | None,
                              verano: dict | None, site: str) -> str:
    """Banda 'El registro nocturno de {ciudad}' sobre la tabla (above the fold):
    última noche con dato de AEMET, recuento del verano en curso y media de 10
    veranos. Todo con dato real; si no hay ni última noche ni verano, devuelve ''
    (la página queda exactamente igual). Traspasa autoridad a /ola-de-calor/."""
    un = (ultima or {}).get(ciudad["id"])
    ve = (verano or {}).get(ciudad["id"])
    if not un and not ve:
        return ""
    items = []
    if un:
        est = estado_noche(un["tmin"])
        badge = f'<span class="reg-badge {est[1]}">{est[0]}</span>' if est else ""
        tmin_txt = f"{un['tmin']:.1f}".replace(".", ",")
        items.append(
            '<div class="reg-item reg-big">'
            '<span class="reg-lab">Última noche registrada</span>'
            f'<span class="reg-val">{tmin_txt}&nbsp;°C</span>{badge}'
            f'<span class="reg-sub">dato de AEMET · {fecha_es_dia(date.fromisoformat(un["fecha"]))}</span></div>')
    if ve and ve["noches"] >= 10:
        items.append(
            '<div class="reg-item">'
            '<span class="reg-lab">Este verano ya</span>'
            f'<span class="reg-val">{int(ve["nt"])}</span>'
            f'<span class="reg-sub">noches tropicales de {int(ve["noches"])} contabilizadas</span></div>')
    items.append(
        '<div class="reg-item">'
        '<span class="reg-lab">Media de 10 veranos</span>'
        f'<span class="reg-val">{ntfmt(ciudad["nt"])}</span>'
        '<span class="reg-sub">noches tropicales al año</span></div>')
    nota = (f'Datos de <b>{ciudad["loc"]}</b>, la estación de AEMET de referencia en {prov}. '
            f'<a href="{site}/ola-de-calor/">Mira cómo va la ola de calor hoy en el mapa de España →</a>')
    return (
        '<section class="reg-band"><div class="wrap"><div class="registro">'
        f'<div class="reg-cab"><span class="reg-kick">🌙 El registro nocturno de {ciudad["loc"]}</span></div>'
        f'<div class="reg-cols">{"".join(items)}</div>'
        f'<p class="reg-nota">{nota}</p>'
        '</div></div></section>')


def prosa_tendencia(prov: str, serie: dict) -> str:
    """Sección '¿Están aumentando las noches tropicales en {prov}?' con la serie
    real por año y un mini-gráfico de barras. Contenido único por provincia. Se
    omite (cadena vacía) si no hay años suficientes para una lectura honesta."""
    if not serie:
        return ""
    anios = sorted(serie)
    if len(anios) < 6:
        return ""
    ini = [serie[a] for a in anios if a <= 2019]
    fin = [serie[a] for a in anios if a >= 2023]
    if len(ini) < 2 or len(fin) < 2:
        return ""
    e, r = sum(ini) / len(ini), sum(fin) / len(fin)

    def n1(x: float) -> str:
        return f"{x:.1f}".replace(".", ",")

    if e >= 3 and r > e * 1.12:
        pct = round((r / e - 1) * 100)
        titular = (f"En {prov}, las noches tropicales <b>van a más</b>: han pasado de una media de "
                   f"<b>{n1(e)} al año</b> por estación (2017–2019) a <b>{n1(r)}</b> (2023–2025), "
                   f"un <b>+{pct}%</b> en menos de una década.")
    elif e >= 3 and r < e * 0.88:
        pct = round((1 - r / e) * 100)
        titular = (f"En {prov}, las noches tropicales han <b>bajado</b> algo en el promedio: de "
                   f"{n1(e)} al año por estación (2017–2019) a {n1(r)} (2023–2025), un −{pct}%. "
                   f"La variabilidad entre veranos es alta, conviene mirarlo con perspectiva.")
    elif r < 1 and e < 1:
        titular = (f"En {prov} las noches tropicales siguen siendo casi <b>inexistentes</b> en sus "
                   f"estaciones de altura: apenas cambian de un año a otro. El calor nocturno no ha "
                   f"hecho mella en sus refugios.")
    else:
        titular = (f"En {prov}, la media de noches tropicales por estación oscila entre "
                   f"<b>{n1(min(serie.values()))} y {n1(max(serie.values()))} al año</b> según el "
                   f"verano, sin una tendencia clara: unos años aprietan y otros dan tregua.")

    mx = max(serie.values()) or 1
    barras = "".join(
        f'<span class="tb"><i style="height:{max(4, round(100 * serie[a] / mx))}%" '
        f'title="{a}: {n1(serie[a])} noches tropicales"></i><span>{str(a)[2:]}</span></span>'
        for a in anios)
    return (f"<h2>¿Están aumentando las noches tropicales en {prov}?</h2>"
            f"<p>{titular}</p>"
            f'<div class="tend">{barras}</div>'
            f'<p class="note">Media de noches tropicales por estación de AEMET y verano en {prov}, '
            f"{anios[0]}–{anios[-1]}. El dato baila mucho de un año a otro —2022 fue extremo, 2021 "
            f"más suave—; la tendencia se lee mejor comparando trienios que años sueltos.</p>")


# Nombres cortos SOLO para el <title> (en la página, la meta y los datos se
# mantiene el nombre oficial). Doble beneficio: caben en el recuadro móvil y
# coinciden con la búsqueda real ("noches tropicales tenerife", no "santa cruz
# de tenerife"). El resto de provincias caben con su nombre completo.
PROV_TITULO_CORTO = {
    "Santa Cruz de Tenerife": "Tenerife",
    "Illes Balears": "Baleares",
    "Araba/Álava": "Álava",
}


def construir_pagina_provincia(prov: str, lista: list, site: str, provnav: str,
                                fecha_mod: str, fecha_mod_txt: str,
                                tendencia: dict | None = None,
                                humedad: dict | None = None,
                                ultima_noche: dict | None = None,
                                verano: dict | None = None) -> str:
    sl = slug(prov)
    ordenadas = sorted(lista, key=lambda x: (x["nt"], -x["alt"]))
    mejor, peor, n = ordenadas[0], max(lista, key=lambda x: x["nt"]), len(lista)
    # Widget "registro nocturno" de la capital/ciudad (above the fold): última
    # noche con dato de AEMET + verano en curso + media de 10 años. Todo con dato
    # real; degrada a "" si no hay datos recientes.
    ciudad = estacion_ciudad(prov, lista, peor)
    # Si la estación de referencia no tiene dato reciente (p.ej. dejó de reportar),
    # cae a la más calurosa de la provincia que SÍ lo tenga: así el widget no
    # desaparece por un hueco puntual de una sola estación.
    if ultima_noche and ciudad["id"] not in ultima_noche:
        con_dato = [e for e in lista if e["id"] in ultima_noche]
        if con_dato:
            ciudad = max(con_dato, key=lambda e: e["nt"])
    widget = construir_widget_registro(prov, ciudad, ultima_noche, verano, site)
    # Columna de humedad de agosto (complemento): solo si al menos una estación
    # de la provincia tiene el dato; si no, la tabla queda exactamente igual.
    hum = humedad or {}
    hay_hum = any(hum.get(e["id"]) for e in ordenadas)
    col_hum_head = '<th class="r hide">Humedad ago.</th>' if hay_hum else ""
    filas = []
    for e in ordenadas:
        etq, col, bg = bandas_py(e["nt"])
        alt = f"{e['alt']:,}".replace(",", ".")
        td_hum = ""
        if hay_hum:
            hd = hum.get(e["id"])
            td_hum = (f'<td class="r hide">{hd["hr"]}%</td>' if hd
                      else '<td class="r hide">—</td>')
        filas.append(
            f'<tr><td class="loc">{e["loc"]}</td><td class="hide">{alt} m</td>'
            f'<td class="n">{ntfmt(e["nt"])}</td>{td_hum}'
            f'<td><span class="v" style="color:{col};background:{bg}">{etq}</span></td></tr>')
    # La unidad se NOMBRA siempre ("noches tropicales al año"): decir "son unas 2
    # al año" dejaba al lector adivinando si eran noches, grados o estaciones, y
    # además desaprovechaba la palabra clave de la página en su primer párrafo.
    def _nt_frase(nt: float, con_al_anio: bool = True) -> str:
        sufijo = " al año" if con_al_anio else ""
        if nt < 1:
            return f"menos de <b>1 noche tropical</b>{sufijo}"
        n_ = round(nt)
        if n_ == 1:
            return f"<b>1 noche tropical</b>{sufijo}"
        return f"<b>{n_} noches tropicales</b>{sufijo}"

    alt_mejor = f"{mejor['alt']:,}".replace(",", ".")
    if n <= 1:
        mtxt = ("prácticamente no se registran <b>noches tropicales</b>"
                if mejor["nt"] < 1 else f'se cuentan {_nt_frase(mejor["nt"])}')
        intro = (f'En <b>{prov}</b>, en su única estación de AEMET con datos suficientes — '
                 f'<b>{mejor["loc"]}</b> ({alt_mejor} m) — {mtxt}.')
    else:
        mtxt = ("prácticamente no se registran <b>noches tropicales</b>"
                if mejor["nt"] < 1 else f'se cuentan {_nt_frase(mejor["nt"])}')
        intro = (f'En <b>{prov}</b>, en <b>{mejor["loc"]}</b> ({alt_mejor} m) {mtxt} '
                 f'—noches en las que la temperatura mínima no baja de 20&nbsp;°C—, '
                 f'mientras que en <b>{peor["loc"]}</b> suben hasta '
                 f'{_nt_frase(peor["nt"], con_al_anio=False)}. '
                 f'Estas son sus {n} estaciones de AEMET, de la más fresca a la más calurosa.')
    # Title orientado a CTR y a MÓVIL (76% del tráfico): Google corta el título
    # a ~50-55 caracteres en móvil, así que el gancho va POR DELANTE (no al
    # final) y la keyword sigue primera para que Google la resalte. Los nombres
    # largos se acortan solo en el título (Tenerife, Baleares, Álava): caben en
    # móvil y además coinciden con lo que la gente busca de verdad.
    prov_titulo = PROV_TITULO_CORTO.get(prov, prov)
    title = f"Noches tropicales en {prov_titulo}: dónde se duerme fresco"
    h1 = (f'¿Se duerme bien en verano en <em>{prov}</em>? '
          f'Te lo contamos con 10 años de datos')
    # Meta description: dato concreto + invitación. Degrada con elegancia según
    # los datos de la provincia (una sola estación, o sin pueblo "fresco").
    if n <= 1:
        cuenta = ("no se cuenta ni 1 noche tropical al año" if mejor["nt"] < 1
                  else f"se cuentan {nt_prosa(mejor['nt'])} noches tropicales al año")
        desc = (f"En {mejor['loc']} ({alt_mejor} m), la única estación de AEMET de "
                f"{prov} con datos suficientes, {cuenta}. Consulta el detalle completo.")
    else:
        if mejor["nt"] < 1:
            primera = f"En {mejor['loc']} ({alt_mejor} m) no hay ni 1 noche tropical al año"
        elif mejor["nt"] < 10:
            primera = (f"En {mejor['loc']} ({alt_mejor} m) apenas "
                       f"{nt_prosa(mejor['nt'])} noches tropicales al año")
        else:
            primera = (f"En {mejor['loc']} ({alt_mejor} m), "
                       f"{nt_prosa(mejor['nt'])} noches tropicales al año")
        desc = (f"{primera}; en {peor['loc']}, {nt_prosa(peor['nt'])}. "
                f"Descubre el mapa completo de {prov} con datos de AEMET.")

    refugios = [e for e in ordenadas if e["nt"] < 1]
    peores = sorted(lista, key=lambda x: -x["nt"])[:3] if n > 1 else []
    # Enlace contextual tras la prosa de refugios (las páginas que no van en el
    # menú escueto se enlazan aquí, integradas en el cuerpo).
    cta_refugio = (f'<p class="ctain"><a href="{site}/refugio-climatico-natural/">'
                   'Descubre el refugio climático natural más cerca de tu casa →</a></p>')
    cta_ola = (f'<p class="ctain"><a href="{site}/ola-de-calor/">'
               f'Sigue la ola de calor de este verano en {prov}, noche a noche, en el mapa de AEMET →</a></p>')
    prosa = (prosa_contraste(prov, mejor, peor, n)
             + prosa_tendencia(prov, tendencia or {})
             + prosa_refugios(prov, refugios)
             + cta_refugio
             + (prosa_peores(prov, peores, mejor) + cta_ola if peores else "")
             + prosa_metodologia(prov, n, fecha_mod_txt))

    faq = construir_faq_provincia(prov, mejor, peor, n)
    schema = json.dumps(
        construir_schema_provincia(prov, site, sl, n, title, desc, faq, fecha_mod),
        ensure_ascii=False)

    url_comp = f"{site}/{sl}/"
    if mejor["nt"] < 1:
        texto_comp = (f"En {prov} se duerme fresco: {mejor['loc']} apenas tiene noches "
                      f"tropicales, según diez veranos de datos de AEMET. ¿Y tu pueblo?")
    else:
        texto_comp = (f"¿Cuántas noches tropicales sufre cada pueblo de {prov}? El mapa del "
                      f"calor nocturno, con diez veranos de datos de AEMET. ¿Y tu pueblo?")

    return (PAGINA_PROVINCIA
            .replace("__NAVCSS__", CSS_NAV_ESCUETO)
            .replace("__FOOTERCSS__", CSS_FOOTER_ESCUETO)
            .replace("__NAV__", nav_escueto_html(site))
            .replace("__FOOTER__", footer_escueto_html(
                site, f"Última actualización de los datos: {fecha_mod_txt}"))
            .replace("__OGTITLE__", title)
            .replace("__TITLE__", title)
            .replace("__DESC__", desc)
            .replace("__CANONICAL__", f"{site}/{sl}/")
            .replace("__SITE__", site)
            .replace("__SITE_URL__", site)
            .replace("__HOME__", site + "/")
            .replace("__PROVNAME__", prov)
            .replace("__H1__", h1)
            .replace("__INTRO__", intro)
            .replace("__WIDGET__", widget)
            .replace("__COLHUM__", col_hum_head)
            .replace("__TABLE__", "".join(filas))
            .replace("__COMPARTIR__", barra_compartir(url_comp, texto_comp))
            .replace("__CAPTION__", f"Estaciones de AEMET en {prov}, de la más fresca a la más calurosa")
            .replace("__PROSA__", prosa)
            .replace("__FAQ__", faq_html(faq))
            .replace("__VECINAS__", vecinas_html(prov, site))
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


# ===========================================================================
# Páginas complementarias data-driven: Sala de prensa y Ranking nacional.
# Se generan desde los mismos datos del reportaje; sin scripts ni deps nuevas.
# ===========================================================================

# Material descargable que vive en docs/ (lo crea generar_gif.py).
ASSETS_PRENSA = [
    ("ola-dia-noche.gif", "GIF · La ola, día y noche", "Panel doble, ideal para X/Twitter"),
    ("ola-maximas.gif", "GIF · Máximas, día a día", "La península, verano en curso"),
    ("ola-minimas.gif", "GIF · Mínimas, día a día", "Lo que de verdad importa de noche"),
    ("ola-canarias-minimas.gif", "GIF · Mínimas en Canarias", "El archipiélago aparte"),
    ("og.png", "Imagen de portada", "1200×630, para abrir piezas"),
    ("og-cuadrada.png", "Imagen cuadrada", "1080×1080, para redes"),
]

# Muestra de color en línea: siempre que un texto nombra un color, se enseña.
# Los valores han de ser los EXACTOS de la paleta de AEMET (verificados píxel a
# píxel sobre la barra del propio GIF) para que se puedan cotejar con el mapa.
_CSS_MU = ('.mu{display:inline-block;width:.78em;height:.78em;border-radius:3px;'
           'margin:0 .16em 0 .1em;position:relative;top:.04em;'
           'box-shadow:0 0 0 1px rgba(255,255,255,.3)}')

# En móvil el nombre del dominio se comía 190 de los 375 px de la barra (el 51 %)
# y no cabía entero ni UNO de los nueve elementos del menú. Se queda solo la luna;
# el nombre sigue en el <title>, en el pie y en el aria-label del enlace.
_CSS_NAV_MOVIL = ('@media(max-width:560px){.nav .brand span{display:none}'
                  '.nav .in{gap:14px}.menu a{padding:8px 10px}}')

# Reglas que quiere cualquier página con el chrome nuevo.
_CSS_COMUN = _CSS_MU + _CSS_NAV_MOVIL

# Colores de la escala de AEMET, para no volver a teclearlos de memoria.
AEMET = {"verde": "#66FF66", "lima": "#CCFF00", "amarillo": "#FFFF00",
         "naranja": "#FF7F00", "rojo": "#FF0000", "granate": "#B83450",
         "turquesa": "#15C5C0", "cian": "#00EDED", "azul": "#1E8EFF"}

_CSS_CHROME = (
    ':root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;'
    '--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;'
    '--fd:"Fraunces",Georgia,serif;--fb:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;'
    '--fm:"JetBrains Mono",monospace}'
    '*{margin:0;padding:0;box-sizing:border-box}'
    'body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.7;-webkit-font-smoothing:antialiased}'
    'a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}'
    'header.h{padding:48px 0 14px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}'
    '.crumb{font-size:13px;color:var(--muted)}.crumb a{color:var(--muted)}'
    '.kick{font:600 12px/1 var(--fb);letter-spacing:.15em;text-transform:uppercase;color:var(--teja);margin:10px 0 10px}'
    'h1{font-family:var(--fd);font-weight:900;font-size:clamp(30px,6vw,46px);line-height:1.06;letter-spacing:-.01em}'
    'h1 em{font-style:italic;color:var(--teja2)}'
    '.intro{color:#e7dcc8;font-size:clamp(16px,2.5vw,18px);margin:18px 0 0}.intro b{color:var(--paper)}'
    '.cta{margin:10px 0;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:24px;text-align:center}'
    '.cta b{font-family:var(--fd);font-size:19px}'
    '.botones{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin-top:14px}'
    '.btn{display:inline-block;padding:12px 18px;border-radius:11px;font-weight:700;font-size:14.5px}'
    '.btn.pri{background:var(--teja);color:#1a1209}.btn.pri:hover{background:var(--teja2);text-decoration:none}'
    '.btn.sec{background:transparent;border:1px solid var(--teja);color:var(--teja2)}.btn.sec:hover{background:rgba(217,116,78,.12);text-decoration:none}'
    'footer{border-top:1px solid var(--line);padding:28px 0 60px;color:#9a8a6f;font-size:12.5px;margin-top:24px}'
    'footer a{color:#9a8a6f}'
    '.compartir{margin:22px 0;padding:15px 18px;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:14px}'
    '.compartir .ct{display:block;font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;color:var(--teja);margin-bottom:11px}'
    '.compartir .cbtns{display:flex;flex-wrap:wrap;gap:9px}'
    '.compartir .cb{font:600 13.5px/1 var(--fb);padding:9px 15px;border-radius:9px;border:1px solid var(--line);background:transparent;color:var(--paper);cursor:pointer;text-decoration:none;display:inline-block}'
    '.compartir .cb:hover{border-color:var(--teja);color:var(--teja2);text-decoration:none;background:rgba(217,116,78,.10)}'
    + _CSS_MU
)

# ---------------------------------------------------------------------------
# Chrome nuevo (paleta negra): menú y pie COMPARTIDOS por todas las páginas que
# ya lo llevan. Fuente única: al añadir una página nueva al site se toca aquí y
# aparece en el menú de todas. Antes estaba duplicado literal en cada plantilla.
# ---------------------------------------------------------------------------

# (clave, href, texto). La clave es la que se pasa a nav_html() para marcar
# la página actual. REDUCIDO a las 4 entradas del menú escueto (jul 2026):
# el menú de 9 no cabía en móvil y diluía lo importante. Todo lo que salió
# del menú (refugios cerca, el parte, certificados, metodología, artículos)
# sigue enlazado desde el pie (FOOTER_HTML) y desde enlaces contextuales.
_MENU = [
    ("obs", "__SITE__/observatorio-del-descanso/", "Observatorio"),
    ("cerca", "__SITE__/refugios-climaticos-naturales-cerca-de-mi/", "Refugios cerca de mí"),
    ("hoteles", "__SITE__/hoteles-refugio-climatico/", "Hoteles"),
    ("ola", "__SITE__/ola-de-calor/", "Ola de calor"),
    ("mapa", "__SITE__/mapa-estaciones/", "Mapa"),
    ("ranking", "__SITE__/ranking-noches-tropicales/", "Ranking"),
]

_LOGO = ('<svg width="{px}" height="{px}" viewBox="0 0 100 100" aria-hidden="true">'
         '<circle cx="45" cy="52" r="30" fill="var(--brand)"/>'
         '<circle cx="60" cy="44" r="29" fill="var({hueco})"/></svg>'
         '<span>nochetropical.es</span>')


def nav_html(actual: str = "") -> str:
    """Menú superior. `actual` es una clave de _MENU; marca el enlace activo."""
    def destino(k: str, href: str) -> str:
        # "Artículos" es una sección DE la portada: desde ella basta el ancla;
        # desde cualquier otra página hay que viajar a la portada.
        if k == "articulos" and actual == "inicio":
            return "#articulos"
        return href

    enlaces = "".join(
        '<a href="%s"%s>%s</a>' % (destino(k, href),
                                   ' aria-current="page"' if k == actual else "", txt)
        for k, href, txt in _MENU)
    # Conmutador de idioma discreto: enlace real a la versión inglesa (refuerza
    # el hreflang y da salida al público angloparlante).
    enlaces += '<a href="__SITE__/en/" hreflang="en" class="lang" aria-label="English version" title="English version">EN</a>'
    logo = _LOGO.format(px=26, hueco="--bg")
    return ('<nav class="nav"><div class="in">\n'
            '    <a class="brand" href="__HOME__" aria-label="nochetropical.es">' + logo + '</a>\n'
            '    <div class="menu">\n'
            '      ' + enlaces + '\n'
            '    </div>\n'
            '  </div></nav>')


def _fcol_home(titulo: str, items: list) -> str:
    enlaces = "".join(f'<a href="__SITE__{h}">{t}</a>' for t, h in items)
    return f'      <div class="fcol"><h4>{titulo}</h4>{enlaces}</div>\n'


# Pie de la HOME: mismas 3 columnas compartidas (_F_*) que el pie escueto, más
# la columna de marca — así el pie es idéntico en toda la web.
FOOTER_HTML = (
    '<footer>\n'
    '    <div class="in fgrid">\n'
    '      <div class="fcol">\n'
    '        <a class="brand" href="__HOME__" style="margin-bottom:12px">'
    + _LOGO.format(px=24, hueco="--surface") + '</a>\n'
    f'        <p class="fabout">{_F_TAGLINE}</p>\n'
    '      </div>\n'
    + _fcol_home("Explora los datos", _F_EXPLORA)
    + _fcol_home("Guías y artículos", _F_GUIAS)
    + _fcol_home("Proyecto", _F_PROYECTO)
    + '    </div>\n'
    '    <div class="in fbar">© 2026 nochetropical.es · Datos de AEMET bajo CC BY 4.0 · '
    'Ramón J. Lowesting</div>\n'
    '  </footer>'
)

# Paleta negra + contenedores + menú + pie. Lo que necesita una página para
# llevar el chrome nuevo; las reglas propias de cada página van aparte.
CSS_CHROME2 = (
    ':root{--bg:#080705;--surface:#16120c;--panel:#211a12;--ink:#f2eae0;--muted:#c3b6a2;'
    '--muted2:#9a8d79;--line:#3a3122;--brand:#ee9769;--brand-ink:#160f08;'
    '--shadow:0 1px 2px rgba(0,0,0,.5),0 12px 34px rgba(0,0,0,.45);--c-ref:#3f9aa8;'
    '--font-d:Georgia,"Times New Roman",serif;'
    '--font-b:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;'
    '--font-m:ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace}'
    '*{box-sizing:border-box}'
    'body{margin:0}'
    '.pg{background:var(--bg);color:var(--ink);font-family:var(--font-b);line-height:1.55}'
    '.in{max-width:1100px;margin:0 auto;padding:0 24px}'
    '.nav{position:sticky;top:0;z-index:20;background:rgba(8,7,5,.85);'
    'backdrop-filter:saturate(1.3) blur(9px);border-bottom:1px solid var(--line)}'
    '.nav .in{display:flex;align-items:center;gap:20px;height:60px}'
    '.brand{display:flex;align-items:center;gap:10px;font-family:var(--font-d);font-weight:700;'
    'font-size:18px;color:var(--ink);text-decoration:none;white-space:nowrap}'
    '.menu{margin-left:auto;display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}'
    '.menu::-webkit-scrollbar{display:none}'
    '.menu a{font-size:14.5px;color:var(--muted);text-decoration:none;padding:8px 12px;'
    'border-radius:8px;white-space:nowrap}'
    '.menu a:hover{color:var(--ink);background:rgba(238,151,105,.14)}'
    '.menu a[aria-current]{color:var(--brand);font-weight:600}'
    '.hero{padding:50px 0 6px}'
    '.kick{font:600 12px/1 var(--font-b);letter-spacing:.16em;text-transform:uppercase;'
    'color:var(--brand);margin:0 0 14px}'
    'h1{font-family:var(--font-d);font-weight:700;font-size:clamp(30px,5vw,46px);line-height:1.06;'
    'margin:0;letter-spacing:-.01em;text-wrap:balance}'
    '.lede{font-size:clamp(16.5px,2.2vw,19px);color:var(--muted);max-width:58ch;margin:18px 0 0}'
    'footer{margin-top:54px;border-top:1px solid var(--line);background:var(--surface)}'
    '.fgrid{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;gap:28px;padding:44px 0 28px}'
    '.fcol h4{font:600 11px/1 var(--font-b);letter-spacing:.14em;text-transform:uppercase;'
    'color:var(--muted);margin:0 0 14px}'
    '.fcol a{display:block;color:var(--ink);text-decoration:none;font-size:15px;margin:0 0 9px;opacity:.9}'
    '.fcol a:hover{opacity:1;color:var(--brand)}'
    '.fabout{font-size:14.5px;color:var(--muted);max-width:34ch}'
    '.fbar{border-top:1px solid var(--line);padding:18px 0;font-size:13px;color:var(--muted)}'
    '@media(max-width:660px){.fgrid{grid-template-columns:1fr 1fr}}'
    '@media(max-width:430px){.fgrid{grid-template-columns:1fr}}'
    + _CSS_COMUN
)

PAGINA_PRENSA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sala de prensa · Refugio Climático (datos de noches tropicales, AEMET)</title>
<meta name="description" content="Material para prensa del proyecto Refugio Climático: 5 datos para titular, titulares sugeridos, gráficos descargables, metodología y contacto. Datos de AEMET, 2017–2026.">
<link rel="canonical" href="__SITE__/prensa/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="website">
<meta property="og:title" content="Sala de prensa · Refugio Climático">
<meta property="og:description" content="5 datos para titular, gráficos descargables, metodología y contacto. Datos de AEMET.">
<meta property="og:url" content="__SITE__/prensa/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&family=JetBrains+Mono:wght@700&display=swap" rel="stylesheet">
<style>
 __CSS__
 .wrap{max-width:760px;margin:0 auto;padding:0 22px}
 section{padding:24px 0;border-top:1px solid var(--line)}
 section:first-of-type{border-top:none}
 p{font-size:clamp(15.5px,2.3vw,17px);color:#e3d8c4;margin:0 0 14px}p b{color:var(--paper)}
 .big{font-family:var(--fd);font-size:clamp(19px,3vw,24px);line-height:1.35;color:#efe6d6}
 .note{font-size:12.5px;color:var(--muted)}
 ol.datos{margin:6px 0 0;padding:0;list-style:none;counter-reset:d}
 ol.datos li{counter-increment:d;position:relative;padding:13px 0 13px 42px;border-bottom:1px solid var(--line);font-size:clamp(15px,2.3vw,16.5px);color:#e3d8c4;line-height:1.55}
 ol.datos li::before{content:counter(d);position:absolute;left:0;top:13px;width:26px;height:26px;display:grid;place-items:center;background:var(--teja);color:#1a1209;font-family:var(--fm);font-weight:700;border-radius:50%;font-size:13px}
 ol.datos li b{color:var(--paper)} ol.datos li em{font-style:italic;color:var(--teal)}
 ul.tit{list-style:none;padding:0;margin:0}
 ul.tit li{padding:11px 0 11px 20px;position:relative;color:#e7dcc8;font-family:var(--fd);font-size:clamp(16px,2.4vw,18px);line-height:1.3;border-bottom:1px solid var(--line)}
 ul.tit li::before{content:"\00ab";position:absolute;left:0;color:var(--teja)}
 .descargas{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:4px 0}
 .card{display:block;padding:14px 16px;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:12px;color:var(--teja2);font-weight:700;font-size:14px}
 .card:hover{border-color:var(--teja);text-decoration:none}
 .card span{display:block;color:var(--muted);font-weight:400;font-size:12.5px;margin-top:3px}
 .cita{font-family:var(--fm);font-size:13px;background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:14px;color:#e3d8c4;line-height:1.5}
 ul.medios{list-style:none;margin:6px 0 0;padding:0}
 ul.medios li{padding:14px 0;border-bottom:1px solid var(--line)}
 ul.medios li:last-child{border-bottom:none}
 ul.medios a{display:block;color:var(--teja2);font-family:var(--fd);font-weight:600;font-size:clamp(16px,2.4vw,18.5px);line-height:1.3;text-decoration:none}
 ul.medios a:hover{text-decoration:underline}
 ul.medios .meta{display:block;font-family:var(--fm);font-size:12.5px;color:var(--muted);margin-top:6px}
 @media(max-width:520px){.descargas{grid-template-columns:1fr}}
</style>
</head>
<body>
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">Refugio Climático</a> · Sala de prensa</nav>
  <div class="kick">Para periodistas · Datos abiertos AEMET</div>
  <h1>Sala de prensa</h1>
  <p class="intro"><b>Refugio Climático</b> analiza 10 veranos de datos de AEMET (2017–2026) para mostrar dónde se duerme fresco en España y dónde no refresca de noche. Proyecto de datos de interés público; todo el material es libre citando la fuente.</p>
</div></header>

<section><div class="wrap">
  <div class="kick">En una frase</div>
  <p class="big">No todos los veranos españoles se sufren igual de noche: mientras en las sierras del interior se sigue durmiendo tapado, en buena parte del litoral y de las islas la temperatura no baja de 20&nbsp;°C casi ninguna noche.</p>
</div></section>

<section><div class="wrap">
  <div class="kick">Nos han citado</div>
  <ul class="medios">__MEDIOS__</ul>
</div></section>

<section><div class="wrap">
  <div class="kick">Cinco datos para titular</div>
  <ol class="datos">__DATOS__</ol>
  <p class="note">Fuente: AEMET OpenData · veranos 2017–2026 · __TOTAL__ estaciones.</p>
</div></section>

<section><div class="wrap">
  <div class="kick">Titulares que puedes usar</div>
  <ul class="tit">
    <li>El mapa del calor que no te deja dormir: dónde se duerme fresco en España y dónde se suda hasta el amanecer.</li>
    <li>La costa mediterránea y las islas, entre los peores sitios de España para dormir en verano.</li>
    <li>Hay pueblos en España con cero noches tropicales y otros con más de 80: el mapa que lo demuestra.</li>
    <li>El punto más caliente de noche no está en el sur peninsular, sino en la montaña de Gran Canaria.</li>
  </ul>
</div></section>

<section><div class="wrap">
  <div class="kick">Material descargable</div>
  <div class="descargas">__DESCARGAS__</div>
  <p class="note">Puede publicarse citando «Fuente: AEMET · Refugio Climático».</p>
</div></section>

<section><div class="wrap">
  <div class="kick">Metodología</div>
  <p>Una <b>noche tropical</b> es aquella en que la temperatura mínima no baja de 20&nbsp;°C. Se cuentan sobre los datos diarios de temperatura mínima de <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a>, en los veranos (junio–agosto) de 2017 a 2026, para __TOTAL__ estaciones con cobertura suficiente. El proceso es reproducible y los datos proceden íntegramente de fuentes públicas de AEMET. Importante: el dato es de la <b>estación</b>, no del municipio; en montaña la noche cambia mucho con la altitud.</p>
</div></section>

<section><div class="wrap">
  <div class="kick">Cómo citar</div>
  <p class="cita">Refugio Climático (2026). <i>El mapa del calor que no te deja dormir.</i> Análisis de noches tropicales con datos de AEMET (2017–2026). __HOME__</p>
</div></section>

<section><div class="wrap">
  <div class="cta">
    <b>¿Quieres datos en bruto, gráficos en alta o una entrevista?</b><br>
    Ramón J. Lowesting · <a href="mailto:lowesting@gmail.com">lowesting@gmail.com</a>
    <div class="botones">
      <a class="btn pri" href="__SITE__/mapa-estaciones/">Mapa interactivo</a>
      <a class="btn sec" href="__SITE__/ranking-noches-tropicales/">El ranking</a>
      <a class="btn sec" href="__HOME__">La calculadora</a>
    </div>
  </div>
</div></section>

<footer><div class="wrap">
  Fuente: <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a> · proyecto Refugio Climático de Ramón J. Lowesting · datos bajo <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">CC&nbsp;BY&nbsp;4.0</a>. Actualizado en __FECHA__.
</div></footer>
<script>
/* Atajo interno (no visible): teclea la palabra secreta en cualquier punto de
   esta página y saltas a la consola de informes. Seguridad por oscuridad: la
   consola es noindex y no está enlazada en ningún sitio público, pero su URL
   es adivinable, así que no guardes ahí nada sensible. Cambia la palabra en
   PALABRA_CONSOLA (generar_calculadora.py). */
(function(){var s="",k=atob("__CLAVE_CONSOLA__");document.addEventListener("keydown",function(e){if(e.key&&e.key.length===1){s=(s+e.key.toLowerCase()).slice(-k.length);if(s===k)location.href="__SITE__/informes/";}});})();
</script>
</body>
</html>
"""

PAGINA_RANKING = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dónde se duerme mejor y peor en verano en España (ranking de noches tropicales) | Refugio Climático</title>
<meta name="description" content="Ranking de noches tropicales en España con 10 veranos de datos de AEMET: los lugares donde peor se duerme (más noches con la mínima sobre 20 °C) y los refugios donde mejor.">
<link rel="canonical" href="__SITE__/ranking-noches-tropicales/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="article">
<meta property="og:title" content="Dónde se duerme mejor y peor en verano en España">
<meta property="og:description" content="El ranking de noches tropicales con 10 veranos de datos de AEMET.">
<meta property="og:url" content="__SITE__/ranking-noches-tropicales/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&family=JetBrains+Mono:wght@700&display=swap" rel="stylesheet">
<style>
 __CSS__
 .wrap{max-width:880px;margin:0 auto;padding:0 22px}
 section{padding:24px 0}
 h2{font-family:var(--fd);font-weight:700;font-size:clamp(21px,4vw,28px);margin:6px 0 6px;letter-spacing:-.01em}
 .note{font-size:12.5px;color:var(--muted);margin-bottom:12px}
 table{width:100%;border-collapse:collapse;font-size:14.5px}
 th,td{text-align:left;padding:10px 10px;border-bottom:1px solid var(--line)}
 th{font:600 11px/1 var(--fb);letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
 th.r,td.n{text-align:right}
 td.n{font-family:var(--fm);font-weight:700}
 td.pos{font-family:var(--fm);color:var(--teja2);width:34px}
 td.loc{font-weight:600}
 tbody tr:hover{background:rgba(217,116,78,.05)}
 .kick{font:600 12px/1 var(--fb);letter-spacing:.15em;text-transform:uppercase;color:var(--teja);margin:0 0 10px}
 .provnav{display:flex;flex-wrap:wrap;gap:9px 16px;margin-top:6px;font-size:14px}
 .provnav a{color:var(--teal);text-decoration:none}
 .provnav a:hover{color:var(--teja2);text-decoration:underline}
 @media(max-width:520px){th.hide,td.hide{display:none}}
</style>
</head>
<body>
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">Refugio Climático</a> · Ranking</nav>
  <div class="kick">Ranking · Datos AEMET 2017–2026</div>
  <h1>Dónde se duerme <em>mejor</em> y <em>peor</em> en verano en España</h1>
  <p class="intro">El ranking de <b>noches tropicales</b> —noches en que la mínima no baja de 20&nbsp;°C— de __TOTAL__ estaciones de AEMET, con diez veranos de datos. Cuantas más noches tropicales, peor se duerme.</p>
</div></header>

<section><div class="wrap">
  <h2>Los 30 lugares donde peor se duerme</h2>
  <p class="note">Más noches tropicales al año = más noches sin que baje de 20&nbsp;°C. Dato de la estación de AEMET.</p>
  <table>
    <thead><tr><th>#</th><th>Lugar</th><th>Provincia</th><th class="r hide">Altitud</th><th class="r">Noches trop./año</th></tr></thead>
    <tbody>__PEOR__</tbody>
  </table>
</div></section>

<section><div class="wrap">
  <h2>Los refugios: donde mejor se duerme</h2>
  <p class="note"><b>__CERO__ estaciones</b> no registran ni una noche tropical al año de media. Estas son 30 de ellas, las de mayor altitud entre las de cero.</p>
  <table>
    <thead><tr><th>Lugar</th><th>Provincia</th><th class="r hide">Altitud</th><th class="r">Noches trop./año</th></tr></thead>
    <tbody>__MEJOR__</tbody>
  </table>
</div></section>

<section><div class="wrap">__COMPARTIR__</div></section>

<section><div class="wrap">
  <div class="cta">
    <b>¿Y tu pueblo en qué puesto está?</b><br>
    <div class="botones">
      <a class="btn pri" href="__HOME__">Búscalo en la calculadora →</a>
      <a class="btn sec" href="__SITE__/mapa-estaciones/">Ver el mapa interactivo</a>
    </div>
  </div>
</div></section>

<section><div class="wrap">
  <div class="kick">Todas las provincias</div>
  <p class="note">¿No ves tu pueblo en las tablas de arriba? Entra en tu provincia y mira el detalle de todas sus estaciones, de la más fresca a la más calurosa.</p>
  <nav class="provnav" aria-label="Todas las provincias">__PROVNAV__</nav>
</div></section>

<footer><div class="wrap">
  Fuente: <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a> · veranos 2017–2026 · proyecto <a href="__HOME__">Refugio Climático</a> de Ramón J. Lowesting · datos bajo <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">CC&nbsp;BY&nbsp;4.0</a>. Actualizado en __FECHA__.
</div></footer>
<script>
(function(){
 var box=document.querySelector(".compartir"); if(!box) return;
 var url=box.getAttribute("data-url"), text=box.getAttribute("data-text");
 var cp=document.getElementById("cb-copiar");
 if(cp&&navigator.clipboard) cp.addEventListener("click",function(){
   navigator.clipboard.writeText(url).then(function(){
     cp.textContent="Enlace copiado"; setTimeout(function(){cp.textContent="Copiar enlace";},1600);
   });
 });
 var sh=document.getElementById("cb-share");
 if(sh&&navigator.share){ sh.hidden=false;
   sh.addEventListener("click",function(){
     navigator.share({title:document.title,text:text,url:url}).catch(function(){});
   });
 }
})();
</script>
</body>
</html>
"""


# Medios que han citado el proyecto (crece con cada aparición; el más reciente
# arriba). SOLO entradas con enlace real y verificado — nunca inventar.
MEDIOS = [
    {"medio": "iLeon", "grupo": "eldiario.es", "fecha": "10 jul 2026",
     "titular": "León, uno de los sitios donde mejor se duerme de España pese al "
                "calor, aunque cada vez más extremo durante la noche",
     "url": "https://ileon.eldiario.es/provincia/leon-sitios-mejor-duerme-espana-"
            "pese-calor-vez-extremo-durante-noche_1_13368230.html"},
]


def construir_pagina_prensa(datos: dict, estaciones: list, site: str,
                            fecha_iso: str, fecha_txt: str) -> str:
    m = datos["meta"]
    total = m["total"]
    cero = sum(1 for e in estaciones if e["nt"] < 1)
    top = sorted(estaciones, key=lambda x: -x["nt"])[:4]
    top_txt = ", ".join(f"{e['loc']} (~{round(e['nt'])})" for e in top)
    cr, ch, fo = m["contraste"]["refugio"], m["contraste"]["horno"], m["foehn"]
    items = [
        f"<b>España duerme partida en dos:</b> {cero} estaciones no llegan ni a una noche "
        "tropical al año, frente a costa e islas donde la mínima no baja de 20&nbsp;°C casi todo el verano.",
        f"<b>Donde peor se duerme:</b> {top_txt} noches tropicales al año.",
        f"<b>El peor no está en el sur peninsular:</b> está en Canarias. Y por el <em>efecto "
        f"foehn</em>, hasta la montaña de Gran Canaria no refresca: {fo['loc'].split(',')[0]} "
        f"(a {miles(fo['alt'])}&nbsp;m) suma unas {round(fo['nt'])} noches tropicales al año.",
        "<b>Los refugios son montaña interior:</b> sierras de Teruel, Pirineos, Gredos o "
        "Sierra Nevada apenas registran noches tropicales en una década.",
        f"<b>El contraste de manual:</b> {cr['loc']} ({ntfmt(cr['nt'])} noches/año) frente a "
        f"{ch['loc']} (~{round(ch['nt'])}). Mismo país, dos veranos distintos.",
    ]
    datos_html = "".join(f"<li>{x}</li>" for x in items)
    desc_html = "".join(
        f'<a class="card" href="{site}/{f}" download>{lbl}<span>{sub}</span></a>'
        for f, lbl, sub in ASSETS_PRENSA)
    url = site + "/prensa/"
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Sala de prensa", "item": url}]},
        {"@type": "WebPage", "name": "Sala de prensa · Refugio Climático", "url": url,
         "description": "Material para prensa: datos, titulares, gráficos descargables, metodología y contacto.",
         "isPartOf": {"@type": "WebSite", "name": "Refugio Climático", "url": site + "/"}}]},
        ensure_ascii=False)
    medios_html = "".join(
        f'<li><a href="{md["url"]}" target="_blank" rel="noopener">{md["titular"]}</a>'
        f'<span class="meta">{md["medio"]} · {md["grupo"]} · {md["fecha"]}</span></li>'
        for md in MEDIOS)
    import base64
    clave = base64.b64encode(PALABRA_CONSOLA.encode()).decode()
    return (PAGINA_PRENSA
            .replace("__SCHEMA__", schema)
            .replace("__MEDIOS__", medios_html)
            .replace("__CSS__", _CSS_CHROME)
            .replace("__DATOS__", datos_html)
            .replace("__DESCARGAS__", desc_html)
            .replace("__TOTAL__", str(total))
            .replace("__FECHA__", fecha_txt)
            .replace("__CLAVE_CONSOLA__", clave)
            .replace("__HOME__", site + "/")
            .replace("__SITE__", site))


def construir_pagina_ranking(estaciones: list, site: str,
                             fecha_iso: str, fecha_txt: str, provnav: str = "") -> str:
    peor = sorted(estaciones, key=lambda x: -x["nt"])[:30]
    refus = [e for e in estaciones if e["nt"] < 1]
    cero = len(refus)
    mejor = sorted(refus, key=lambda x: (x["nt"], -x["alt"]))[:30]
    filas_peor = "".join(
        f'<tr><td class="pos">{i}</td><td class="loc">{e["loc"]}</td>'
        f'<td><a href="{site}/{slug(e["prov"])}/">{e["prov"]}</a></td>'
        f'<td class="n hide">{miles(e["alt"])}&nbsp;m</td>'
        f'<td class="n">{ntfmt(e["nt"])}</td></tr>'
        for i, e in enumerate(peor, 1))
    filas_mejor = "".join(
        f'<tr><td class="loc">{e["loc"]}</td>'
        f'<td><a href="{site}/{slug(e["prov"])}/">{e["prov"]}</a></td>'
        f'<td class="n hide">{miles(e["alt"])}&nbsp;m</td>'
        f'<td class="n">{ntfmt(e["nt"])}</td></tr>'
        for e in mejor)
    url = site + "/ranking-noches-tropicales/"
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Ranking de noches tropicales", "item": url}]},
        {"@type": "Article",
         "headline": "Dónde se duerme mejor y peor en verano en España",
         "description": "Ranking de noches tropicales en España con 10 veranos de datos de AEMET.",
         "image": site + "/og.png",
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "publisher": {"@type": "Organization", "name": "Refugio Climático",
                       "logo": {"@type": "ImageObject", "url": site + "/favicon.svg"}},
         "datePublished": FECHA_PUBLICACION_LANDINGS, "dateModified": fecha_iso,
         "mainEntityOfPage": url}]}, ensure_ascii=False)
    texto_comp = ("Buena parte de España sigue durmiendo fresco en verano, aunque el litoral "
                  "y las islas se pasan la noche sudando. El ranking nacional de noches "
                  "tropicales, con diez veranos de datos de AEMET:")
    return (PAGINA_RANKING
            .replace("__SCHEMA__", schema)
            .replace("__COMPARTIR__", barra_compartir(url, texto_comp))
            .replace("__CSS__", _CSS_CHROME)
            .replace("__PEOR__", filas_peor)
            .replace("__MEJOR__", filas_mejor)
            .replace("__CERO__", str(cero))
            .replace("__TOTAL__", str(len(estaciones)))
            .replace("__FECHA__", fecha_txt)
            .replace("__PROVNAV__", provnav)
            .replace("__HOME__", site + "/")
            .replace("__SITE__", site))


# ===========================================================================
# Página /metodologia/: cómo se mide todo + GLOSARIO de términos (fase 1).
# ===========================================================================

PAGINA_METODOLOGIA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Metodología y glosario: cómo medimos dónde se duerme fresco | Noche Tropical</title>
<meta name="description" content="Qué es una noche tropical, de dónde salen los datos (AEMET OpenData, 2017–2026, 848 estaciones), cómo se otorga el certificado de Refugio Climático y qué diferencia un refugio climático medido, uno natural y uno publicitario.">
<link rel="canonical" href="__SITE__/metodologia/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="article">
<meta property="og:title" content="Metodología y glosario · Noche Tropical">
<meta property="og:description" content="Cómo medimos dónde se duerme fresco en España: fuente, criterio del certificado y glosario.">
<meta property="og:url" content="__SITE__/metodologia/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&family=JetBrains+Mono:wght@700&display=swap" rel="stylesheet">
<style>
 __CSS__
 .wrap{max-width:720px;margin:0 auto;padding:0 22px}
 section{padding:8px 0}
 h2{font-family:var(--fd);font-weight:700;font-size:clamp(20px,3.6vw,26px);margin:34px 0 10px}
 p{font-size:clamp(15.5px,2.3vw,17px);color:#e3d8c4;margin:0 0 14px;line-height:1.7}
 p b{color:var(--paper)}
 .glosario{margin:14px 0}
 .termino{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:0 0 12px}
 .termino h3{font-family:var(--fd);font-weight:600;font-size:18px;color:var(--teja2);margin:0 0 6px}
 .termino p{font-size:14.5px;color:var(--muted);margin:0}
 .termino p b{color:#e7dcc8}
 .cita{font-family:var(--fm);font-size:13px;background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:14px;color:#e3d8c4;line-height:1.5;margin:8px 0 18px}
</style>
</head>
<body>
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">Refugio Climático</a> · Metodología y glosario</nav>
  <div class="kick">Metodología · Datos abiertos</div>
  <h1>Cómo medimos dónde se duerme fresco</h1>
  <p class="intro">Todo lo que publica este proyecto sale de datos públicos y de un método que cabe en una página. Esta es esa página.</p>
</div></header>

<section><div class="wrap">
  <h2>El dato: la noche tropical</h2>
  <p>Una <b>noche tropical</b> es aquella en que la temperatura mínima <b>no baja de 20&nbsp;°C</b>; una <b>noche ecuatorial</b>, cuando no baja de 25&nbsp;°C. Es el indicador que mejor refleja si se descansa: por encima de esos umbrales, el cuerpo no disipa bien el calor y el sueño se fragmenta. Usamos <b>recuentos</b> de noches, nunca medias de temperatura: una media esconde noches horno compensadas por noches frescas.</p>

  <h2>La fuente y el periodo</h2>
  <p>Valores climatológicos diarios de <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a> (temperatura mínima por estación y día), veranos <b>2017–2026</b> (junio–agosto), en <b>__TOTAL__ estaciones</b> con cobertura suficiente. <a href="__SITE__/parte/">El parte de la noche</a> usa además la red de observación en tiempo real de AEMET (datos provisionales de las últimas horas, ventana nocturna 18:00–08:00 UTC), y se consolida después con los valores validados.</p>

  <h2>Los límites (léelos antes de citar)</h2>
  <p>El dato es de la <b>estación</b>, no del municipio: si tu pueblo no tiene estación, la más cercana es una referencia, no una medición local — y en montaña la noche cambia mucho con la altitud. Hay <b>muchos pueblos frescos sin estación</b> que no podemos certificar por falta de datos: que un pueblo no aparezca no significa que no sea un refugio, significa que aún no podemos medirlo. Si conoces una estación que no controlamos, <a href="__SITE__/tu-pueblo/">cuéntanoslo aquí</a>.</p>

  <h2>El certificado de Refugio Climático</h2>
  <p>Se certifica a las estaciones con <b>menos de una noche tropical al año</b> de media en los diez veranos analizados. Lo consiguen <b>__NREF__ de las __TOTAL__</b>; el <b>Top 25</b> reúne, de entre ellas, las de mayor altitud. Cada certificado es <a href="__SITE__/certificados/">público, verificable e imprimible</a>.</p>

  <h2>Glosario: tres «refugios» que no son lo mismo</h2>
  <div class="glosario">
    <div class="termino"><h3>Refugio climático (medido)</h3>
    <p>Lugar donde la noche refresca de verdad, <b>acreditado con datos</b>: menos de una noche tropical al año de media (AEMET, 2017–2026). Es lo que certifica este proyecto.</p></div>
    <div class="termino"><h3>Refugio climático natural</h3>
    <p>El que <b>construye la naturaleza</b>: altitud, aire seco, bosques que transpiran, valles con inversión térmica, cielo limpio que deja escapar el calor. Lo contamos en <a href="__SITE__/microclimas/">Microclimas</a> y en <a href="__SITE__/refugio-climatico-natural/">Refugio climático natural</a>. Todo refugio medido lo es gracias a estos mecanismos.</p></div>
    <div class="termino"><h3>Refugio climático «de cartel»</h3>
    <p>El que solo existe en la placa: una lona que se recalienta, un nebulizador que sube el bochorno, una sala con aire acondicionado que enfría dentro y <b>calienta la calle</b>. Si no mueve la física (sombra viva, evaporación, inercia, ventilación), es decoración.</p></div>
  </div>

  <h2>Reproducibilidad y licencia</h2>
  <p>Los datos proceden íntegramente de fuentes públicas de AEMET y el proceso es reproducible. Todo el material del proyecto puede usarse citando la fuente (<a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">CC&nbsp;BY&nbsp;4.0</a>).</p>
  <div class="cita">Noche Tropical (2026). <i>El mapa del calor que no te deja dormir.</i> Análisis de noches tropicales con datos de AEMET (2017–2026). __HOME__</div>

  <div class="cta">
    <b>¿Dudas con un dato? ¿Eres periodista?</b><br>
    <div class="botones">
      <a class="btn pri" href="__SITE__/prensa/">Sala de prensa</a>
      <a class="btn sec" href="__HOME__">La calculadora</a>
    </div>
  </div>
</div></section>

<footer><div class="wrap">
  Proyecto <a href="__HOME__">Refugio Climático · nochetropical.es</a> · Datos: AEMET OpenData · <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">CC&nbsp;BY&nbsp;4.0</a>. Actualizado en __FECHA__.
</div></footer>
</body>
</html>
"""


def construir_pagina_metodologia(estaciones: list, total: int, site: str,
                                 fecha_iso: str, fecha_txt: str) -> str:
    nref = sum(1 for e in estaciones if e["nt"] < 1)
    url = site + "/metodologia/"
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Metodología y glosario", "item": url}]},
        {"@type": "Article",
         "headline": "Metodología y glosario: cómo medimos dónde se duerme fresco",
         "description": "Fuente, periodo, criterio del certificado y glosario de términos del proyecto.",
         "image": site + "/og.png",
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "publisher": {"@type": "Organization", "name": "Refugio Climático",
                       "logo": {"@type": "ImageObject", "url": site + "/favicon.svg"}},
         "datePublished": FECHA_PUBLICACION_LANDINGS, "dateModified": fecha_iso,
         "mainEntityOfPage": url}]}, ensure_ascii=False)
    return (PAGINA_METODOLOGIA
            .replace("__SCHEMA__", schema)
            .replace("__CSS__", _CSS_CHROME)
            .replace("__TOTAL__", str(total))
            .replace("__NREF__", str(nref))
            .replace("__FECHA__", fecha_txt)
            .replace("__HOME__", site + "/")
            .replace("__SITE__", site))


# ===========================================================================
# Página /tu-pueblo/: honestidad convertida en captación (fase 1). Aviso de
# los pueblos sin estación + formulario doble (nueva estación / estudio).
# ===========================================================================

PAGINA_TUPUEBLO = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>¿Tu pueblo no aparece? Ayúdanos a medirlo | Noche Tropical</title>
<meta name="description" content="Solo podemos certificar refugios climáticos donde hay estación meteorológica con datos suficientes. Si tu pueblo no aparece, cuéntanos: ¿conoces una estación que no controlamos? ¿Quieres que estudiemos tu zona?">
<link rel="canonical" href="__SITE__/tu-pueblo/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="website">
<meta property="og:title" content="¿Tu pueblo no aparece? Ayúdanos a medirlo">
<meta property="og:description" content="Que un pueblo no aparezca no significa que no sea un refugio: significa que aún no podemos medirlo.">
<meta property="og:url" content="__SITE__/tu-pueblo/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&family=JetBrains+Mono:wght@700&display=swap" rel="stylesheet">
<style>
 __CSS__
 .wrap{max-width:680px;margin:0 auto;padding:0 22px}
 section{padding:8px 0}
 p{font-size:clamp(15.5px,2.3vw,17px);color:#e3d8c4;margin:0 0 14px;line-height:1.7}
 p b{color:var(--paper)}
 .capture{margin:26px 0;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid #54402a;border-radius:18px;padding:26px 24px}
 .capture h2{font-family:var(--fd);font-weight:700;font-size:clamp(19px,3.4vw,24px);margin:0 0 14px;text-align:center}
 .capture form{display:grid;gap:12px;max-width:440px;margin:0 auto}
 .capture input,.capture select,.capture textarea{width:100%;background:var(--bg);border:1px solid var(--line);border-radius:10px;color:var(--paper);font-family:var(--fb);font-size:15px;padding:12px 14px}
 .capture textarea{min-height:88px;resize:vertical}
 .capture input:focus,.capture select:focus,.capture textarea:focus{outline:none;border-color:var(--teja)}
 .capture .rgpd{display:flex;gap:8px;align-items:flex-start;font-size:12.5px;color:var(--muted);line-height:1.5}
 .capture .rgpd input{width:auto;margin-top:3px}
 .capture button{background:var(--teja);color:#1a1209;font-weight:700;font-size:15.5px;border:none;border-radius:11px;padding:14px;cursor:pointer}
 .capture button:hover{background:var(--teja2)}
 .capture .ok{font-family:var(--fd);font-size:19px;text-align:center;color:var(--verde,#8fb07a);padding:18px 0}
 .nota{font-size:13px;color:var(--muted)}
</style>
</head>
<body>
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">Refugio Climático</a> · ¿Tu pueblo no aparece?</nav>
  <div class="kick">Pueblos sin estación · Ayúdanos a medir</div>
  <h1>¿Tu pueblo no aparece?</h1>
  <p class="intro">Solo podemos acreditar refugios climáticos donde hay una <b>estación meteorológica con datos suficientes</b>. España tiene muchos más pueblos frescos que estaciones: <b>que el tuyo no aparezca no significa que no sea un refugio — significa que aún no podemos medirlo</b>.</p>
</div></header>

<section><div class="wrap">
  <p>Sabemos que hay refugios sin certificar en sierras enteras. Nos faltan datos, y ahí puedes ayudar tú: redes municipales, estaciones agrarias, aficionados con estación propia que publican sus registros… Si el dato existe y es serio, queremos conocerlo. Las estaciones que no son de AEMET no pueden certificar con el mismo rigor, pero sí entrar como <b>«en estudio»</b>.</p>

  <div class="capture">
    <h2>Cuéntanoslo</h2>
    <form id="leadf">
      <select id="ltipo">
        <option value="estacion">Conozco una estación meteorológica que no controláis</option>
        <option value="estudio">Quiero que estudiéis mi pueblo o mi zona</option>
        <option value="otro">Otra cosa (te leemos)</option>
      </select>
      <input type="text" id="lzona" placeholder="Pueblo o zona (y provincia)" required>
      <textarea id="lpet" placeholder="Cuéntanos: ¿dónde publica sus datos esa estación? ¿Qué sabes del clima de tu pueblo?"></textarea>
      <input type="email" id="lemail" placeholder="tu@email.com" required>
      <label class="rgpd"><input type="checkbox" id="lrgpd" required> Acepto que me contactéis sobre esto. Sin spam.</label>
      <button type="submit">Enviar</button>
    </form>
  </div>

  <p class="nota">Mientras tanto, tu referencia más honesta es la estación más cercana (en la <a href="__HOME__">calculadora</a>) — con cuidado: en montaña la noche cambia mucho con la altitud. El método completo, en <a href="__SITE__/metodologia/">metodología</a>.</p>
</div></section>

<footer><div class="wrap">
  Proyecto <a href="__HOME__">Refugio Climático · nochetropical.es</a> · Datos: AEMET OpenData · <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">CC&nbsp;BY&nbsp;4.0</a>
</div></footer>

<script>
const APPS_SCRIPT_URL="__APPS_URL__";
const lf=document.getElementById("leadf");
lf.addEventListener("submit",ev=>{
  ev.preventDefault();
  const lead={timestamp:new Date().toISOString(),
    email:document.getElementById("lemail").value.trim(),
    modo:"tu-pueblo",
    busca:document.getElementById("ltipo").value,
    zona_interes:document.getElementById("lzona").value.trim(),
    peticion:document.getElementById("lpet").value.trim(),
    estacion:"",provincia:"",noches_trop:"",veredicto:"",
    rgpd:document.getElementById("lrgpd").checked?"si":"",
    source:"tu-pueblo",user_agent:navigator.userAgent};
  const gracias=()=>{lf.outerHTML='<p class="ok">¡Gracias! Lo revisamos y te escribimos.</p>';};
  fetch(APPS_SCRIPT_URL,{method:"POST",headers:{"Content-Type":"text/plain;charset=utf-8"},body:JSON.stringify(lead)}).then(gracias).catch(gracias);
});
</script>
</body>
</html>
"""


def construir_pagina_tupueblo(site: str) -> str:
    url = site + "/tu-pueblo/"
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "¿Tu pueblo no aparece?", "item": url}]},
        {"@type": "WebPage", "name": "¿Tu pueblo no aparece? Ayúdanos a medirlo", "url": url,
         "isPartOf": {"@type": "WebSite", "name": "Refugio Climático", "url": site + "/"}}]},
        ensure_ascii=False)
    return (PAGINA_TUPUEBLO
            .replace("__SCHEMA__", schema)
            .replace("__CSS__", _CSS_CHROME)
            .replace("__APPS_URL__", APPS_SCRIPT_URL)
            .replace("__HOME__", site + "/")
            .replace("__SITE__", site))


# ===========================================================================
# Página /refugios-y-espana-vaciada/: artículo con datos. Cruza los refugios
# (nt<1) con la geografía de la despoblación. Tesis: el frío que despobló
# estos pueblos es hoy su mayor activo frente al calor.
# ===========================================================================

# Núcleo de la Serranía Celtibérica (la "Laponia del sur"): las 4 provincias
# más emblemáticas de la España vaciada por su bajísima densidad.
_CELTIBERICA = ("Teruel", "Soria", "Cuenca", "Guadalajara")

PAGINA_VACIADA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Refugios climáticos y España vaciada: el frío que los despobló es hoy su activo | Noche Tropical</title>
<meta name="description" content="Muchos de los pueblos de España donde mejor se duerme en verano están en la España vaciada. El mismo frío de montaña que un día los despobló es hoy, con el cambio climático, su mayor activo. Análisis con datos de AEMET.">
<link rel="canonical" href="__SITE__/refugios-y-espana-vaciada/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="article">
<meta property="og:title" content="Refugios climáticos y España vaciada">
<meta property="og:description" content="El frío que despobló la España vaciada es hoy, frente al calor, su mayor activo. Con datos de AEMET.">
<meta property="og:url" content="__SITE__/refugios-y-espana-vaciada/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&family=JetBrains+Mono:wght@700&display=swap" rel="stylesheet">
<style>
 __CSS__
 .wrap{max-width:720px;margin:0 auto;padding:0 22px}
 .lead{margin:22px 0 0}.lead p{font-size:clamp(17px,2.7vw,19px);color:#e7dcc8;margin:0 0 16px}.lead p b{color:var(--paper)}
 article{padding:8px 0 10px}
 article h2{font-family:var(--fd);font-weight:700;font-size:clamp(22px,4.2vw,30px);line-height:1.15;letter-spacing:-.01em;margin:44px 0 14px}
 article p{font-size:clamp(16px,2.4vw,18px);color:#e3d8c4;margin:0 0 18px}
 article p b{color:var(--paper)} article em{font-style:italic;color:var(--teal)}
 .datos{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:26px 0}
 .datos .c{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:16px 12px;text-align:center}
 .datos .v{font-family:var(--fm);font-weight:700;font-size:clamp(24px,5vw,34px);color:var(--verde);line-height:1.1}
 .datos .l{font-size:12px;color:var(--muted);margin-top:5px}
 .reflexion{margin:32px 0;padding:22px 26px;border-left:3px solid var(--teja);background:linear-gradient(180deg,rgba(217,116,78,.09),transparent);border-radius:0 14px 14px 0}
 .reflexion p{font-family:var(--fd);font-size:clamp(17px,2.7vw,20px);font-style:italic;line-height:1.6;color:#efe6d6;margin:0}
 .reflexion p b{font-style:normal;color:var(--teja2)}
 .provs{font-size:14.5px;color:var(--muted);line-height:2;margin:6px 0 18px}
 .provs b{color:#e7dcc8}
 @media(max-width:560px){.datos{grid-template-columns:1fr 1fr}}
</style>
</head>
<body>
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">Refugio Climático</a> · Refugios y España vaciada</nav>
  <div class="kick">Análisis · Despoblación y clima</div>
  <h1>Los refugios del calor están, muchas veces, en la España vaciada</h1>
  <div class="lead">
    <p>Hemos analizado diez veranos de datos de AEMET para encontrar dónde no se suda de noche. Y al poner los <b>__NREF__ pueblos donde apenas hay noches tropicales</b> sobre el mapa, aparece una coincidencia que da que pensar: muchos son los mismos que llevan décadas perdiendo habitantes. <b>El frío que un día los vació es hoy, frente al calor, su mayor activo.</b></p>
  </div>
</div></header>

<article><div class="wrap">

  <div class="datos">
    <div class="c"><div class="v">__NREF__</div><div class="l">pueblos donde <b>casi no hay</b> noches tropicales</div></div>
    <div class="c"><div class="v">__ALTMEDIA__ m</div><div class="l">altitud media de esos refugios</div></div>
    <div class="c"><div class="v">__CELTIB__</div><div class="l">solo en la Serranía Celtibérica</div></div>
  </div>

  <h2>Hay dos Españas donde se duerme fresco</h2>
  <p>No todos los refugios son iguales. Una familia es la <b>España verde atlántica</b> —Asturias, Galicia, Cantabria—, donde el mar templa las noches de verano; son frescas, pero no están vacías. La otra es la <b>España de interior y altura</b>: las sierras de León, el Pirineo de Huesca y Lleida, los páramos de Soria y Burgos, las muelas de Teruel. Aquí la noche fresca no la trae el mar, sino la <em>altitud</em> y la <em>continentalidad</em> — y aquí es donde el mapa del frescor se superpone, casi calcado, con el mapa de la despoblación.</p>

  <h2>La paradoja de la Serranía Celtibérica</h2>
  <p>El caso extremo es la <b>Serranía Celtibérica</b> (Teruel, Soria, Cuenca, Guadalajara y su entorno): con una densidad en torno a <b>7-8 habitantes por km²</b>, de las más bajas de toda la Unión Europea, se la conoce como <em>«la Laponia del sur»</em>. Es de los territorios más despoblados del continente. Y a la vez concentra <b>__CELTIB__ de nuestros refugios</b>: pueblos donde, en plena ola de calor, sigue haciendo falta una manta por la noche.</p>

  <div class="reflexion">
    <p>Lo que durante siglos fue una condena —inviernos durísimos, aislamiento, tierras difíciles— es exactamente lo que hoy convierte a estos pueblos en <b>refugios frente al calor</b>. El clima le ha dado la vuelta al signo.</p>
  </div>

  <h2>El clima cambia el signo</h2>
  <p>Mientras la costa mediterránea encadena noches sin bajar de 20&nbsp;°C y el aire acondicionado se vuelve imprescindible, estos pueblos ofrecen gratis lo que allí se paga a precio de oro: <b>dormir tapado en agosto</b>. En un país que se calienta, eso deja de ser una anécdota rural para convertirse en un activo real —para el turismo climático, para el teletrabajo, para quien se plantea dónde envejecer—. La España vaciada tiene, sin saberlo del todo, una carta que jugar: <b>el confort térmico</b>.</p>
  <p>No es la solución a la despoblación —hacen falta servicios, trabajo, conexión—, pero sí un argumento nuevo y medible a favor de estos territorios, justo cuando más lo necesitan.</p>

  <h2>Los datos, provincia a provincia</h2>
  <p>De los __NREF__ refugios (estaciones de AEMET con menos de una noche tropical al año de media, 2017–2026), así se reparten por provincia (número de estaciones-refugio):</p>
  <p class="provs">__PROVS__</p>
  <p class="note" style="font-size:12.5px;color:var(--muted)">Nota: el dato es por estación meteorológica, no por municipio; y «España vaciada» se usa aquí en sentido amplio (provincias de baja densidad del interior). Muchos pueblos frescos sin estación no aparecen — <a href="__SITE__/tu-pueblo/">ayúdanos a medirlos</a>.</p>

  <div class="cierre">
    <h2 style="margin:0 0 12px">¿Y tu pueblo?</h2>
    <p>Busca si es uno de los refugios, mira su certificado, o cuéntanos el tuyo si aún no lo medimos.</p>
    <div class="botones">
      <a class="btn pri" href="__HOME__">Buscar en la calculadora →</a>
      <a class="btn sec" href="__SITE__/certificados/">Los refugios certificados</a>
    </div>
  </div>

</div></article>

<footer><div class="wrap">
  <p>Pieza de divulgación del proyecto <a href="__HOME__">Refugio Climático</a>. Datos: <b>AEMET</b> OpenData (2017–2026). Densidades: fuentes públicas (INE, Red SSPA). Bajo <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">CC&nbsp;BY&nbsp;4.0</a>. Actualizado en __FECHA__.</p>
</div></footer>
</body>
</html>
"""


def construir_pagina_vaciada(estaciones: list, site: str,
                             fecha_iso: str, fecha_txt: str) -> str:
    ref = [e for e in estaciones if e["nt"] < 1]
    nref = len(ref)
    altmedia = round(sum(e["alt"] for e in ref) / nref) if ref else 0
    cuenta: dict[str, int] = {}
    for e in ref:
        cuenta[e["prov"]] = cuenta.get(e["prov"], 0) + 1
    celtib = sum(cuenta.get(p, 0) for p in _CELTIBERICA)
    # TODAS las provincias con refugios (antes se cortaba a 14 y quedaban fuera
    # provincias emblemáticas de la España vaciada con pocas estaciones —Teruel,
    # Cuenca, Guadalajara—, justo las que el artículo ensalza).
    top = sorted(cuenta.items(), key=lambda kv: (-kv[1], clave_orden(kv[0])))
    provs = " · ".join(f'<a href="{site}/{slug(p)}/"><b>{p}</b></a> ({n})' for p, n in top)
    url = site + "/refugios-y-espana-vaciada/"
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Refugios y España vaciada", "item": url}]},
        {"@type": "Article",
         "headline": "Refugios climáticos y España vaciada: el frío que los despobló es hoy su activo",
         "description": "Muchos de los pueblos donde mejor se duerme en verano están en la España vaciada; el frío que los despobló es hoy su mayor activo frente al calor.",
         "image": site + "/og.png",
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "publisher": {"@type": "Organization", "name": "Refugio Climático",
                       "logo": {"@type": "ImageObject", "url": site + "/favicon.svg"}},
         "datePublished": "2026-07-06", "dateModified": fecha_iso,
         "mainEntityOfPage": url}]}, ensure_ascii=False)
    return (PAGINA_VACIADA
            .replace("__SCHEMA__", schema)
            .replace("__CSS__", _CSS_CHROME)
            .replace("__NREF__", str(nref))
            .replace("__ALTMEDIA__", str(altmedia))
            .replace("__CELTIB__", str(celtib))
            .replace("__PROVS__", provs)
            .replace("__FECHA__", fecha_txt)
            .replace("__HOME__", site + "/")
            .replace("__SITE__", site))


# ===========================================================================
# Página /ola-de-calor/: los GIFs de AEMET (máx de día / mín de noche) con una
# CAPA de flechas hacia 8 refugios climáticos, activable con un botón.
#
# CALIBRACIÓN lat/lon -> píxel del GIF (630x546). Transformación afín
# (equirectangular) ajustada visualmente sobre el mapa de AEMET. Si en el futuro
# AEMET cambia el encuadre de sus mapas, reajusta SOLO estas 4 parejas:
_OLA_W, _OLA_H = 630, 546          # dimensiones del GIF
_CAL_LON_W, _CAL_X_W = -10.2, 24   # borde oeste  (lon -> x)
_CAL_LON_E, _CAL_X_E = 4.9, 596    # borde este
_CAL_LAT_N, _CAL_Y_N = 44.3, 42    # borde norte  (lat -> y, y crece hacia abajo)
_CAL_LAT_S, _CAL_Y_S = 34.8, 540   # borde sur
# ===========================================================================

# 8 refugios a señalar: (nombre, lat, lon, slug de provincia). La punta de la
# flecha cae en (lat, lon). Ninguno está en Canarias (que va en recuadro aparte).
REFUGIOS_OLA = [
    ("Puerto del Pico", 40.3211, -5.0125, "avila"),
    ("Sanabria", 42.1069, -6.6350, "zamora"),
    ("Rascafría", 40.9053, -3.8811, "madrid"),
    ("Villablino", 42.9394, -6.3186, "leon"),
    ("Benasque", 42.6042, 0.5231, "huesca"),
    ("Vall de Boí", 42.5183, 0.8464, "lleida"),
    ("Beariz", 42.4661, -8.2708, "ourense"),
    ("Cedrillas", 40.431, -0.849, "teruel"),
    ("Sierra Nevada", 37.0555, -3.3656, "granada"),
]


def _px_ola(lat: float, lon: float) -> tuple[float, float]:
    x = _CAL_X_W + (lon - _CAL_LON_W) / (_CAL_LON_E - _CAL_LON_W) * (_CAL_X_E - _CAL_X_W)
    y = _CAL_Y_N + (_CAL_LAT_N - lat) / (_CAL_LAT_N - _CAL_LAT_S) * (_CAL_Y_S - _CAL_Y_N)
    return round(x, 1), round(y, 1)


def construir_marcadores_ola(site: str) -> str:
    """SVG de los 8 marcadores (flecha + tooltip + enlace a provincia)."""
    out = []
    for nombre, lat, lon, sl in REFUGIOS_OLA:
        x, y = _px_ola(lat, lon)
        w = int(len(nombre) * 6.6 + 16)
        out.append(
            f'<a class="marca" href="{site}/{sl}/" data-slug="{sl}" '
            f'role="link" aria-label="{nombre} (abrir {sl})">'
            f'<path class="flecha" d="M{x},{y} L{x - 7},{y - 18} L{x + 7},{y - 18} Z"/>'
            f'<g class="tt" transform="translate({x},{y - 18})">'
            f'<rect x="{-w // 2}" y="-16" width="{w}" height="14" rx="3"/>'
            f'<text x="0" y="-5" text-anchor="middle">{nombre}</text></g></a>')
    return "\n".join(out)


PAGINA_OLA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapa de la ola de calor en España hoy: máximas y mínimas de AEMET</title>
<meta name="description" content="Mapa de la ola de calor en España, animado día a día con datos de AEMET: las temperaturas máximas de hoy y las mínimas de esta noche. Ve si la ola afloja o aprieta y, si no da tregua, dónde refugiarte.">
<link rel="canonical" href="__SITE__/ola-de-calor/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="article">
<meta property="og:title" content="¿Cuándo acaba la ola de calor? Mapa AEMET de hoy: máximas y mínimas">
<meta property="og:description" content="El mapa animado de temperaturas de AEMET —máximas de día, mínimas de noche— para seguir la ola jornada a jornada, con la capa de refugios climáticos naturales.">
<meta property="og:url" content="__SITE__/ola-de-calor/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<style>
__CSS__
 .pg{line-height:1.7}
 a{color:var(--brand)}
 .wrap{max-width:720px;margin:0 auto;padding:0 22px}
 p{font-size:clamp(15.5px,2.3vw,17px);color:var(--muted);margin:0 0 14px}p b{color:var(--ink)}
 .crumb{font-size:13px;color:var(--muted2)}.crumb a{color:var(--muted2)}
 .hero{padding:26px 0 4px}
 .hero .wrap{padding:0 22px}
 .lede{max-width:none}
 .btn{display:inline-block;padding:12px 18px;border-radius:11px;font-weight:700;font-size:14.5px;text-decoration:none}
 .btn.pri{background:var(--brand);color:var(--brand-ink)}
 .btn.pri:hover{filter:brightness(1.08)}
 .btn.sec{background:transparent;border:1px solid var(--line);color:var(--ink)}
 .btn.sec:hover{border-color:var(--brand);color:var(--brand)}
 .botones{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin-top:14px}
 .toggle-refugios{display:inline-flex;align-items:center;gap:8px;background:rgba(238,151,105,.14);border:1px solid var(--brand);color:var(--brand);padding:11px 20px;border-radius:999px;font-family:var(--font-b);font-weight:600;font-size:14.5px;cursor:pointer;transition:.2s;margin:8px 0 20px}
 .toggle-refugios:hover,.toggle-refugios.on{background:var(--brand);color:var(--brand-ink)}
 .mapa{margin:0 0 26px}
 .mapa h2{font-family:var(--font-d);font-weight:700;font-size:clamp(16px,2.6vw,19px);color:var(--brand);margin:0 0 8px;text-align:center}
 .gifwrap{position:relative;max-width:630px;margin:0 auto;border-radius:8px;overflow:hidden}
 .gifwrap img{width:100%;height:auto;display:block}
 .capa{position:absolute;inset:0;width:100%;height:100%;transition:opacity .25s ease;pointer-events:none}
 .capa.oculta{opacity:0}
 .marca{pointer-events:auto;cursor:pointer}
 .capa.oculta .marca{pointer-events:none}
 .flecha{fill:#111;stroke:#fff;stroke-width:1.2;stroke-linejoin:round}
 .marca:hover .flecha,.marca.activa .flecha{fill:var(--brand)}
 .tt{opacity:0;transition:opacity .12s ease}
 .marca:hover .tt,.marca.activa .tt{opacity:1}
 .tt rect{fill:rgba(20,14,8,.94);stroke:#5a4d3a;stroke-width:.7}
 .tt text{fill:#f2eae0;font-family:var(--font-m);font-size:11px;font-weight:700}
 .note{font-size:13px;color:var(--muted);text-align:center;margin:0 0 18px}
 .aviso{font-size:13.5px;color:var(--muted);line-height:1.65;background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--brand);border-radius:12px;padding:15px 18px;margin:0 auto;max-width:600px}
 .aviso b{color:var(--ink)}
 /* El texto de las flechas se revela justo bajo el botón al activarlas
    (divulgación progresiva): aparece cuando de verdad hace falta y no satura
    antes. El truco grid 0fr->1fr anima una altura desconocida con suavidad. */
 .aviso-wrap{display:grid;grid-template-rows:0fr;opacity:0;margin:0;transition:grid-template-rows .38s ease,opacity .3s ease,margin .38s ease}
 .aviso-wrap>div{overflow:hidden;min-height:0}
 .aviso-wrap.abierto{grid-template-rows:1fr;opacity:1;margin:0 0 22px}
 .guia{margin:34px auto 28px;max-width:660px}
 .guia h2{font-family:var(--font-d);font-weight:600;font-size:clamp(18px,3vw,22px);color:var(--ink);margin:0 0 6px;text-align:center}
 .guia .sub{font-size:14.5px;color:var(--muted);text-align:center;margin:0 0 18px}
 .claves{display:grid;grid-template-columns:1fr 1fr;gap:14px}
 @media(max-width:620px){.claves{grid-template-columns:1fr}}
 .clave{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px}
 .clave h3{font-family:var(--font-b);font-weight:600;font-size:15px;color:var(--brand);margin:0 0 10px;display:flex;align-items:center;gap:8px;line-height:1.35}
 .chip{width:14px;height:14px;border-radius:4px;flex:none;box-shadow:0 0 0 1px rgba(255,255,255,.2)}
 .clave p{font-size:14px;line-height:1.6;color:var(--muted);margin:0 0 9px}
 .clave p:last-child{margin:0}
 .guia .pie{font-size:14px;color:var(--muted);text-align:center;margin:16px 0 0}
 .cierre{margin:40px 0 10px;background:linear-gradient(180deg,var(--surface),var(--panel));border:1px solid var(--line);border-radius:18px;padding:28px 24px;text-align:center}
 .cierre b{font-family:var(--font-d);font-size:19px;color:var(--ink)}
 .notas{font-size:13px;color:var(--muted2);border-top:1px dashed var(--line);padding-top:16px;margin:34px 0 0;line-height:1.65}
 .notas b{color:var(--muted)}
 .notas a{color:var(--muted)}
</style>
</head>
<body>
<div class="pg">
__NAV__

<header class="hero"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">Refugio Climático</a> · Mapa de la ola de calor</nav>
  <p class="kick">Mapa animado · Datos AEMET</p>
  <h1>Mapa de la ola de calor en España, hoy: <em>día y noche</em></h1>
  <p class="lede">El <b>mapa de la ola de calor en España</b>, animado día a día con los datos de AEMET: las <b>máximas de hoy</b> y las <b>mínimas de esta noche</b>. La forma más rápida de ver si la ola <b>afloja o aprieta</b> — y dónde, pese a todo, <b>se sigue durmiendo fresco</b>.</p>
</div></header>

<section><div class="wrap">
  <button class="toggle-refugios" id="toggle" aria-pressed="false" aria-controls="aviso-flechas">📍 Mostrar refugios climáticos</button>

  <div class="aviso-wrap" id="aviso-flechas" aria-hidden="true"><div>
  <p class="aviso"><b>Las flechas son orientativas.</b> A esta escala tan grande no marcan un punto exacto, sino la zona. Cada punto es la <b>estación meteorológica</b> y la población donde está; eso <b>no significa que los pueblos de alrededor no pertenezcan a ese mismo refugio climático</b> —el fresco no entiende de límites municipales—. <b>Cedrillas</b>, por ejemplo, abarca también Gúdar, Cabra de Mora, Alcalá de la Selva, Valdelinares, Allepuz o El Castellar. Señalan zonas donde, durante la ola, los colores se mantienen <b>lejos del lima<span class="mu" style="background:#CCFF00" aria-hidden="true"></span> y del amarillo<span class="mu" style="background:#FFFF00" aria-hidden="true"></span></b>: la prueba visual de que en España hay <b>refugios climáticos naturales</b> con margen de sobra para aguantar el calor sin artificios ni aire acondicionado. Pasa el ratón —o tócalas en el móvil— para ver el nombre; púlsalas para abrir su provincia. Los datos, pueblo a pueblo, están en la <a href="__HOME__">calculadora</a>.</p>
  </div></div>

  <div class="mapa">
    <h2>De noche · temperaturas mínimas</h2>
    <div class="gifwrap">
      <img src="__SITE__/ola-minimas.gif" width="630" height="546" alt="Mapa de las temperaturas mínimas de noche en España durante la ola de calor (AEMET): dónde no se baja de 20 °C y dónde se duerme fresco" loading="eager" fetchpriority="high">
      <svg class="capa oculta" viewBox="0 0 630 546" aria-label="Refugios climáticos señalados sobre el mapa">__MARCADORES__</svg>
    </div>
  </div>

  <div class="mapa">
    <h2>De día · temperaturas máximas</h2>
    <div class="gifwrap">
      <img src="__SITE__/ola-maximas.gif" width="630" height="546" alt="Mapa de calor de España: mapa animado de las temperaturas máximas de día durante la ola de calor, día a día (AEMET)" loading="lazy">
      <svg class="capa oculta" viewBox="0 0 630 546" aria-label="Refugios climáticos señalados sobre el mapa">__MARCADORES__</svg>
    </div>
  </div>

  <div class="mapa">
    <h2>Canarias · mínimas de noche</h2>
    <div class="gifwrap">
      <img src="__SITE__/ola-canarias-minimas.gif" alt="Mapa de las temperaturas mínimas nocturnas de Canarias durante la ola de calor (AEMET): el efecto foehn recalienta hasta la montaña" loading="lazy" style="width:100%;height:auto;display:block">
    </div>
    <p style="font-size:14px;color:var(--muted);margin-top:12px">En las islas el <b>efecto foehn</b> recalienta hasta la montaña: el interior de Gran Canaria es de los peores sitios de España para dormir de noche. Por eso va en su propio mapa.</p>
  </div>

  <div class="guia">
    <h2>Cómo leer el mapa para encontrar un refugio climático</h2>
    <p class="sub">Solo hay que mirar un mapa, y solo hay que buscar un color. Aquí está el truco.</p>
    <div class="claves">
      <div class="clave">
        <h3><span class="chip" style="background:#15c5c0"></span> Mapa de mínimas · la noche</h3>
        <p><b>Busca las zonas que nunca llegan a ponerse lima<span class="mu" style="background:#CCFF00" aria-hidden="true"></span> ni amarillas<span class="mu" style="background:#FFFF00" aria-hidden="true"></span>.</b> Eso es un refugio. Y no es una interpretación nuestra: en la escala de AEMET <b>el verde<span class="mu" style="background:#66FF66" aria-hidden="true"></span> acaba exactamente en 20 °C y el lima<span class="mu" style="background:#CCFF00" aria-hidden="true"></span> empieza exactamente en 20</b>. Ese salto de color <i>es</i> la raya de la noche tropical.</p>
        <p>Por debajo de 20 se duerme, aunque sean 19,5 a las tres de la madrugada. A partir de 20 no baja en toda la noche y no hay descanso. Que una zona toque el verde<span class="mu" style="background:#66FF66" aria-hidden="true"></span> en su peor noche no la descalifica — <b>lo que la descalifica es cruzar al lima<span class="mu" style="background:#CCFF00" aria-hidden="true"></span></b>. Superponiendo todas las noches, <b>una quinta parte de España no la cruza nunca</b>.</p>
      </div>
      <div class="clave">
        <h3><span class="chip" style="background:#FF0000"></span> Mapa de máximas · el día</h3>
        <p>Este <b>no sirve para buscar refugios</b>, y conviene decirlo. Hemos superpuesto los rojos<span class="mu" style="background:#FF0000" aria-hidden="true"></span> de todos los fotogramas: <b>el 98 % de España se pone roja</b> y casi la mitad pasa de 40 °C<span class="mu" style="background:#B83450" aria-hidden="true"></span>. No distingue nada, porque de día aquí hace calor en todas partes.</p>
        <p>Es más: los mejores refugios <b>se ponen rojos</b><span class="mu" style="background:#FF0000" aria-hidden="true"></span>. Teruel supera los 32 °C cincuenta y tres días al año y casi no tiene noches tropicales. El refugio español no es donde no aprieta el sol — <b>es donde la noche se lleva el calor</b>. Este mapa está aquí para que veas de qué se escapan.</p>
      </div>
    </div>
    <p class="pie">¿Has localizado una zona? Compruébala con el dato exacto en <a href="__SITE__/mapa-estaciones/">el mapa de refugios climáticos</a>, estación a estación, o mira <a href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/">qué refugios tienes cerca de ti</a>.</p>
  </div>

  <div class="cierre">
    <b>¿Y tu pueblo, aguanta fresco de noche?</b><br>
    <div class="botones">
      <a class="btn pri" href="__HOME__">Búscalo en la calculadora →</a>
      <a class="btn sec" href="__SITE__/mapa-estaciones/">Ver el mapa interactivo</a>
      <a class="btn sec" href="__SHARE_X__" target="_blank" rel="noopener">Compartir en X</a>
    </div>
  </div>

  <p class="notas">Mapas: <b>AEMET</b> (© Agencia Estatal de Meteorología), animados por el proyecto <a href="__HOME__">Refugio Climático</a>. Un fotograma por día. Datos bajo <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">CC&nbsp;BY&nbsp;4.0</a>. Actualizado en __FECHA__.</p>
</div></section>

__FOOTER__
</div>

<script>
const SITE="__SITE__";
const capas=[...document.querySelectorAll(".capa")];
const boton=document.getElementById("toggle");
boton.addEventListener("click",()=>{
  const mostrar=capas[0].classList.contains("oculta");
  capas.forEach(c=>c.classList.toggle("oculta",!mostrar));
  boton.classList.toggle("on",mostrar);
  boton.setAttribute("aria-pressed",mostrar?"true":"false");
  boton.textContent=mostrar?"✕ Ocultar refugios":"📍 Mostrar refugios climáticos";
  const aviso=document.getElementById("aviso-flechas");
  aviso.classList.toggle("abierto",mostrar);
  aviso.setAttribute("aria-hidden",mostrar?"false":"true");
});
const tactil=window.matchMedia("(hover:none)").matches;
document.querySelectorAll(".marca").forEach(g=>{
  g.addEventListener("click",e=>{
    if(tactil && !g.classList.contains("activa")){
      e.preventDefault();
      document.querySelectorAll(".marca.activa").forEach(m=>m.classList.remove("activa"));
      g.classList.add("activa");
    }
    // en escritorio (o segundo toque en móvil) el enlace <a> navega solo
  });
});
</script>
</body>
</html>
"""


def construir_pagina_ola(site: str, fecha_iso: str, fecha_txt: str) -> str:
    from urllib.parse import quote
    url = site + "/ola-de-calor/"
    tuit_ola = ("En plena ola de calor, España conserva refugios climáticos naturales "
                "donde de noche se duerme fresco, sin aire acondicionado. "
                "El mapa animado de AEMET, de día y de noche:")
    share_x = ("https://twitter.com/intent/tweet?text=" + quote(tuit_ola)
               + "&url=" + quote(url))
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Mapa de la ola de calor", "item": url}]},
        {"@type": "Article",
         "headline": "¿Cuándo acaba la ola de calor? Mapa AEMET de hoy: máximas y mínimas",
         "description": "El mapa animado de temperaturas de AEMET (máximas de día y mínimas de noche) con la capa de refugios climáticos naturales y las claves para leerlo.",
         "image": site + "/og.png",
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "publisher": {"@type": "Organization", "name": "Refugio Climático",
                       "logo": {"@type": "ImageObject", "url": site + "/favicon.svg"}},
         "datePublished": FECHA_PUBLICACION_LANDINGS, "dateModified": fecha_iso,
         "mainEntityOfPage": url}]}, ensure_ascii=False)
    return (PAGINA_OLA
            .replace("__SCHEMA__", schema)
            .replace("__SHARE_X__", share_x)
            # chrome nuevo: paleta negra + menú + pie, compartidos con la portada
            .replace("__CSS__", CSS_CHROME2)
            .replace("__NAV__", nav_html("ola"))
            .replace("__FOOTER__", FOOTER_HTML)
            .replace("__MARCADORES__", construir_marcadores_ola(site))
            .replace("__FECHA__", fecha_txt)
            .replace("__HOME__", site + "/")
            .replace("__SITE__", site))


PAGINA_BETA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>El termómetro de las noches tropicales: ¿dónde se duerme fresco en España? | nochetropical.es</title>
<meta name="description" content="¿Dónde se duerme fresco en España? Diez veranos de datos de AEMET (2017–2026) sobre las noches tropicales, pueblo a pueblo. Busca tu pueblo en el termómetro, mira el mapa animado de la ola de calor y aprende a localizar los refugios climáticos naturales.">
<meta name="robots" content="noindex,nofollow">
<link rel="canonical" href="__SITE__/">
<meta property="og:type" content="website">
<meta property="og:title" content="El termómetro de las noches tropicales">
<meta property="og:description" content="¿Dónde se duerme fresco en España? Diez veranos de datos de AEMET, pueblo a pueblo.">
<meta property="og:url" content="__SITE__/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<style>
 :root{
   --bg:#080705; --surface:#16120c; --panel:#211a12; --ink:#f2eae0;
   --muted:#c3b6a2; --muted2:#9a8d79; --line:#3a3122;
   --brand:#ee9769; --brand-ink:#160f08;
   --shadow:0 1px 2px rgba(0,0,0,.5),0 12px 34px rgba(0,0,0,.45);
   --c-ref:#3f9aa8; --c-bien:#63b6a0; --c-temp:#e6b64e; --c-suda:#e6873f; --c-horno:#d8462e;
   --font-d:Georgia,"Times New Roman",serif;
   --font-b:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
   --font-m:ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace;
 }
 *{box-sizing:border-box}
 body{margin:0}
 .betabar{background:#2a1c0f;color:#e6c9a8;font-size:12.5px;text-align:center;padding:7px 16px;border-bottom:1px solid #4a3420}
 .betabar a{color:var(--brand)}
 .pg{background:var(--bg);color:var(--ink);font-family:var(--font-b);line-height:1.55}
 .in{max-width:1100px;margin:0 auto;padding:0 24px}
 .nav{position:sticky;top:0;z-index:20;background:rgba(8,7,5,.85);backdrop-filter:saturate(1.3) blur(9px);border-bottom:1px solid var(--line)}
 .nav .in{display:flex;align-items:center;gap:20px;height:60px}
 .brand{display:flex;align-items:center;gap:10px;font-family:var(--font-d);font-weight:700;font-size:18px;color:var(--ink);text-decoration:none;white-space:nowrap}
 .menu{margin-left:auto;display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}
 .menu::-webkit-scrollbar{display:none}
 .menu a{font-size:14.5px;color:var(--muted);text-decoration:none;padding:8px 12px;border-radius:8px;white-space:nowrap}
 .menu a:hover{color:var(--ink);background:rgba(238,151,105,.14)}
 .menu a[aria-current]{color:var(--brand);font-weight:600}
 .menu a.lang{margin-left:4px;border:1px solid var(--line);color:var(--brand);font-weight:600;letter-spacing:.04em}
 .menu a.lang:hover{border-color:var(--brand);background:rgba(238,151,105,.14)}
 .hero{padding:50px 0 6px}
 .kick{font:600 12px/1 var(--font-b);letter-spacing:.16em;text-transform:uppercase;color:var(--brand);margin:0 0 14px}
 h1{font-family:var(--font-d);font-weight:700;font-size:clamp(30px,5vw,50px);line-height:1.06;margin:0;letter-spacing:-.01em;text-wrap:balance}
 .lede{font-size:clamp(16.5px,2.2vw,19px);color:var(--muted);max-width:56ch;margin:18px 0 0}
 .scale-card{background:var(--surface);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);padding:28px 26px 22px;margin:38px 0}
 .scale-h2{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;margin-bottom:56px}
 .scale-h2 .t{font-family:var(--font-d);font-weight:700;font-size:20px}
 .scale-h2 .s{font-size:13.5px;color:var(--muted)}
 .howto{font-size:14px;color:var(--muted);border-top:1px dashed var(--line);padding-top:14px;margin-top:6px}
 .howto b{color:var(--ink)}
 .lab{font-size:12.5px;font-weight:600;white-space:nowrap;background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:3px 10px;display:inline-block;box-shadow:var(--shadow);color:var(--ink)}
 .lab .val{font-family:var(--font-m);color:var(--muted);font-size:11.5px;font-weight:400;margin-left:3px}
 .scale{position:relative;height:210px}
 .track{position:absolute;left:0;right:0;top:96px;height:26px;border-radius:13px;background:linear-gradient(90deg,var(--c-ref),var(--c-bien) 18%,var(--c-temp) 46%,var(--c-suda) 72%,var(--c-horno));box-shadow:inset 0 0 0 1px rgba(255,255,255,.06)}
 .band{position:absolute;top:130px;transform:translateX(-50%);font-size:12px;color:var(--muted);text-align:center;width:96px;line-height:1.25}
 .divi{position:absolute;top:90px;height:38px;width:1px;background:rgba(242,234,224,.25)}
 .pin{position:absolute;top:60px;transform:translateX(-50%);text-align:center}
 .pin .stem{width:2px;height:34px;background:var(--ink);margin:5px auto 0;opacity:.5}
 .pin .dot{width:13px;height:13px;border-radius:50%;background:var(--panel);border:3px solid var(--ink);margin:-6px auto 0;position:relative;top:2px}
 .pin.tu .dot{background:var(--brand);border-color:var(--brand);width:16px;height:16px}
 .pin.tu .lab{background:var(--brand);color:var(--brand-ink);border-color:var(--brand)}
 .pin.tu .lab .val{color:var(--brand-ink)}
 .axis{position:absolute;left:0;right:0;top:170px;display:flex;justify-content:space-between;font-family:var(--font-m);font-size:11.5px;color:var(--muted)}
 .scale-v-wrap{display:none}
 .scale-v{position:relative;height:440px;margin:2px 0 16px}
 .vtrack{position:absolute;left:56px;top:0;bottom:0;width:26px;border-radius:13px;background:linear-gradient(to top,var(--c-ref),var(--c-bien) 18%,var(--c-temp) 46%,var(--c-suda) 72%,var(--c-horno));box-shadow:inset 0 0 0 1px rgba(255,255,255,.07)}
 .vaxis-top{position:absolute;left:6px;top:-4px;font-family:var(--font-m);font-size:11.5px;color:var(--muted)}
 .vaxis-bot{position:absolute;left:6px;bottom:-4px;font-family:var(--font-m);font-size:11.5px;color:var(--muted);white-space:nowrap}
 .vpin{position:absolute;left:0;transform:translateY(50%)}
 .vpin .vdot{position:absolute;left:69px;transform:translateX(-50%);bottom:-7px;width:14px;height:14px;border-radius:50%;background:var(--panel);border:3px solid var(--ink);box-shadow:0 0 0 3px var(--bg)}
 .vpin .vstem{position:absolute;left:82px;bottom:-1px;width:18px;height:2px;background:var(--ink);opacity:.5}
 .vpin .lab{position:absolute;left:106px;bottom:-12px}
 .vpin.tu .vdot{background:var(--brand);border-color:var(--brand);width:16px;height:16px}
 .vpin.tu .lab{background:var(--brand);color:var(--brand-ink);border-color:var(--brand)}
 .vpin.tu .lab .val{color:var(--brand-ink)}
 .legend{display:flex;flex-wrap:wrap;gap:9px 15px;font-size:13px;color:var(--muted);border-top:1px dashed var(--line);padding-top:14px}
 .legend span{display:inline-flex;align-items:center}
 .legend i{width:12px;height:12px;border-radius:3px;margin-right:6px}
 .find{display:flex;gap:10px;flex-wrap:wrap;align-items:stretch;margin:30px 0 8px}
 .field{position:relative;flex:1;min-width:190px}
 .field select,.find input{width:100%;background:#2c2216;border:1.5px solid #5f5138;border-radius:11px;color:var(--ink);font-size:15px;padding:13px 14px;font-family:var(--font-b);box-shadow:inset 0 1px 0 rgba(255,255,255,.05)}
 .field select:hover,.find input:hover{border-color:#7d6a49}
 .field.sel select{appearance:none;-webkit-appearance:none;padding-right:40px;cursor:pointer}
 .field.sel::after{content:"";position:absolute;right:16px;top:50%;width:9px;height:9px;border-right:2.5px solid var(--brand);border-bottom:2.5px solid var(--brand);transform:translateY(-70%) rotate(45deg);pointer-events:none}
 .find select:focus,.find input:focus{outline:2px solid var(--brand);outline-offset:1px}
 .find button{background:var(--brand);color:var(--brand-ink);border:0;border-radius:11px;font-weight:700;font-size:15px;padding:13px 20px;cursor:pointer;white-space:nowrap}
 .find button:hover{filter:brightness(1.08)}
 .result{font-size:15.5px;color:var(--ink);margin:14px 0 0;padding:14px 16px;background:var(--panel);border:1px solid var(--line);border-radius:12px}
 .result b{font-weight:700}
 .result .chip{display:inline-block;font-weight:700;font-size:12.5px;padding:4px 11px;border-radius:999px;color:#160f08;margin-right:10px}
 .certbadge{display:block;margin-top:12px;background:rgba(99,182,154,.12);border:1px solid var(--c-bien);color:#8fd7bd;font-size:14px;font-weight:600;padding:10px 14px;border-radius:10px;text-decoration:none;line-height:1.4}
 .certbadge:hover{background:rgba(99,182,154,.2)}
 .capture{margin-top:16px;padding-top:16px;border-top:1px solid var(--line)}
 .capture .lead-h{font-family:var(--font-d);font-weight:700;font-size:16.5px;color:var(--ink);margin-bottom:6px;line-height:1.3}
 .capture .lead-sub{font-size:13.5px;color:var(--muted);margin:0 0 12px;line-height:1.5}
 .leadform{display:grid;gap:9px}
 .leadform input,.leadform select{width:100%;background:#2c2216;border:1.5px solid #5f5138;border-radius:10px;color:var(--ink);font-size:14.5px;padding:11px 13px;font-family:var(--font-b)}
 .leadform input::placeholder{color:var(--muted2)}
 .leadform input:focus,.leadform select:focus{outline:2px solid var(--brand);outline-offset:1px}
 .leadform .lrgpd{display:flex;gap:8px;align-items:flex-start;font-size:12.5px;color:var(--muted);line-height:1.45}
 .leadform .lrgpd input{width:auto;margin-top:2px;accent-color:var(--brand)}
 .leadform button[type=submit]{background:var(--brand);color:var(--brand-ink);border:0;border-radius:10px;font-weight:700;font-size:15px;padding:12px;cursor:pointer;margin-top:2px}
 .leadform button[type=submit]:hover{filter:brightness(1.08)}
 .capture .bridge{display:inline-block;margin-top:13px;color:var(--brand);font-size:13.5px;font-weight:600;text-decoration:none}
 .capture .bridge:hover{text-decoration:underline}
 .foot-note{font-size:12.5px;color:var(--muted2);margin-top:10px}
 footer{margin-top:54px;border-top:1px solid var(--line);background:var(--surface)}
 .fgrid{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;gap:28px;padding:44px 0 28px}
 .fcol h4{font:600 11px/1 var(--font-b);letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 14px}
 .fcol a{display:block;color:var(--ink);text-decoration:none;font-size:15px;margin:0 0 9px;opacity:.9}
 .fcol a:hover{opacity:1;color:var(--brand)}
 .fabout{font-size:14.5px;color:var(--muted);max-width:34ch}
 .fbar{border-top:1px solid var(--line);padding:18px 0;font-size:13px;color:var(--muted)}
 .sec-h{font-family:var(--font-d);font-weight:700;font-size:clamp(20px,3.5vw,26px);margin:46px 0 4px}
 .sec-s{color:var(--muted);font-size:15px;margin:0 0 14px;max-width:60ch}
 .gifmod{background:var(--surface);border:1px solid var(--line);border-radius:16px;overflow:hidden;margin:14px 0}
 .gifmod img{width:100%;height:auto;display:block;border-bottom:1px solid var(--line)}
 .gifmod .gm-b{padding:15px 18px}
 .gifmod .gm-b a{color:var(--brand);font-weight:600;text-decoration:none}
 .gifmod .gm-b a:hover{text-decoration:underline}
 .mods{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;margin:14px 0}
 .card2{display:block;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px;text-decoration:none;color:var(--ink)}
 .card2:hover{border-color:var(--brand)}
 .card2.destacada{border-color:var(--brand);background:linear-gradient(180deg,rgba(217,116,78,.12),var(--surface))}
 .card2.destacada h3{color:var(--brand)}
 .card2 h3{font-family:var(--font-d);font-weight:700;font-size:18px;margin:0 0 6px}
 .card2 p{font-size:13.5px;color:var(--muted);margin:0;line-height:1.5}
 .leer{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--brand);border-radius:0 14px 14px 0;padding:18px 20px;margin:16px 0 0}
 .leer h3{font-family:var(--font-d);font-weight:700;font-size:19px;margin:0 0 8px}
 .leer p{font-size:15px;color:var(--muted);margin:0 0 10px;line-height:1.6}
 .leer p:last-child{margin-bottom:0}
 .leer b{color:var(--ink)}
 @media(max-width:660px){.scale-h-wrap{display:none}.scale-v-wrap{display:block}.fgrid{grid-template-columns:1fr 1fr}}
 @media(max-width:430px){.fgrid{grid-template-columns:1fr}}
__CSS_COMUN__
</style>
</head>
<body>
<div class="betabar">Versión <b>beta</b> del nuevo diseño · en pruebas · <a href="__HOME__">volver a la web actual</a></div>
<div class="pg">
  __NAV__
  <header class="hero"><div class="in">
    <p class="kick">¿Dónde se duerme fresco en España?</p>
    <h1>El termómetro de las noches tropicales</h1>
    <p class="lede">Cuántas noches al año no baja de 20&nbsp;°C, según diez veranos de datos de AEMET (2017–2026). Cuantas más noches tropicales, peor se duerme. Elige tu pueblo y mira en qué zona cae:</p>
  </div></header>
  <section><div class="in">
    <div class="scale-card">
      <div class="scale-h2"><span class="t">Noches tropicales al año</span><span class="s">De ~92 noches de verano · media 2017–2026</span></div>
      <div class="scale-h-wrap"><div class="scale" role="img" aria-label="Escala de noches tropicales de 0 a 90.">
        <div class="track"></div>
        <div class="divi" style="left:1.1%"></div><div class="divi" style="left:11%"></div><div class="divi" style="left:33%"></div><div class="divi" style="left:67%"></div>
        <div class="band" style="left:6%">Refugio</div><div class="band" style="left:22%">Se duerme bien</div><div class="band" style="left:50%">Templado</div><div class="band" style="left:67%">Se suda</div><div class="band" style="left:84%">Horno</div>
        <div class="pin" style="left:0%"><span class="lab">Cedrillas<span class="val">0</span></span><div class="stem"></div><div class="dot"></div></div>
        <div class="pin" style="left:71%;top:0"><span class="lab">Valencia<span class="val">64</span></span><div class="stem" style="height:70px"></div><div class="dot"></div></div>
        <div class="pin tu" id="tu-h" style="left:0%;display:none"><span class="lab">Tu pueblo<span class="val" id="tuh-val"></span></span><div class="stem"></div><div class="dot"></div></div>
        <div class="axis"><span>0 noches</span><span>90</span></div>
      </div></div>
      <div class="scale-v-wrap">
        <div class="scale-v" role="img" aria-label="Termómetro vertical de noches tropicales.">
          <span class="vaxis-top">90</span><span class="vaxis-bot">0 noches</span>
          <div class="vtrack"></div>
          <div class="vpin" style="bottom:0%"><span class="vdot"></span><span class="vstem"></span><span class="lab">Cedrillas<span class="val">0</span></span></div>
          <div class="vpin" style="bottom:71%"><span class="vdot"></span><span class="vstem"></span><span class="lab">Valencia<span class="val">64</span></span></div>
          <div class="vpin tu" id="tu-v" style="bottom:0%;display:none"><span class="vdot"></span><span class="vstem"></span><span class="lab">Tu pueblo<span class="val" id="tuv-val"></span></span></div>
        </div>
        <div class="legend">
          <span><i style="background:var(--c-ref)"></i>Refugio</span><span><i style="background:var(--c-bien)"></i>Se duerme bien</span><span><i style="background:var(--c-temp)"></i>Templado</span><span><i style="background:var(--c-suda)"></i>Se suda</span><span><i style="background:var(--c-horno)"></i>Horno</span>
        </div>
      </div>
      <p class="howto">Cómo leerlo: cuanto más <b>abajo/izquierda</b>, más fresco (un <b>refugio</b> es &lt;1 noche tropical al año); cuanto más <b>arriba/derecha</b>, más se suda. Cada pueblo cae en una de las cinco <b>zonas</b>.</p>
    </div>
    <div class="find">
      <div class="field sel"><select id="prov" aria-label="Provincia"><option value="">Elige provincia…</option></select></div>
      <div class="field sel"><select id="est" aria-label="Estación"><option value="">…y tu estación</option></select></div>
    </div>
    <p class="result" id="result" hidden></p>
    <p class="foot-note">Con las 848 estaciones de AEMET · media de los veranos 2017–2026.</p>
  </div></section>
  <section><div class="in">
    <h2 class="sec-h">La ola de calor, noche a noche</h2>
    <p class="sec-s">De día casi toda España arde; de noche, no. El mapa que dio origen al proyecto, con datos de AEMET día a día.</p>
    <div class="gifmod">
      <a href="__SITE__/ola-de-calor/" aria-label="Ver el mapa animado completo de la ola de calor en España"><img src="__SITE__/ola-minimas.gif" alt="Mapa de temperaturas de España de noche durante la ola de calor (AEMET): las mínimas nocturnas, dónde se queda por encima de 20 °C y dónde se duerme fresco" loading="lazy"></a>
      <div class="gm-b"><a href="__SITE__/ola-de-calor/">Ver el mapa de la ola de calor, animado y completo, con Canarias y las flechas a los refugios →</a></div>
    </div>
    <div class="leer">
      <h3>Cómo leer el mapa para encontrar un refugio</h3>
      <p>La clave está en el <b>color</b>, y se resume en una frase: busca las zonas que <b>nunca llegan a ponerse lima<span class="mu" style="background:#CCFF00" aria-hidden="true"></span> ni amarillas<span class="mu" style="background:#FFFF00" aria-hidden="true"></span></b>. No es una interpretación nuestra: en la escala de AEMET el verde<span class="mu" style="background:#66FF66" aria-hidden="true"></span> acaba <b>exactamente</b> en 20&nbsp;°C y el lima<span class="mu" style="background:#CCFF00" aria-hidden="true"></span> empieza <b>exactamente</b> en 20. Ese salto de color <i>es</i> la raya de la noche tropical.</p>
      <p>Un <b>refugio climático natural</b> es justo eso: una zona que <b>no cruza los 20&nbsp;°C</b> ninguna noche, ni en plena ola de calor. Por debajo de 20 se duerme, aunque sean 19,5 a las tres de la madrugada; a partir de 20 ya no baja en toda la noche. Que toque el verde<span class="mu" style="background:#66FF66" aria-hidden="true"></span> en su peor noche no la descalifica — lo que la descalifica es <b>pasar al lima</b><span class="mu" style="background:#CCFF00" aria-hidden="true"></span>. Superponiendo todas las noches del verano, <b>una quinta parte de España no lo hace nunca</b>.</p>
    </div>
    <h2 class="sec-h">Explora los datos</h2>
    <div class="mods">
      <a class="card2 destacada" href="__SITE__/observatorio-del-descanso/"><h3>🌙 El Observatorio del Descanso</h3><p>¿Cómo has dormido esta noche? El mapa ciudadano del descanso: cuéntalo en 10 segundos y descubre dónde se duerme mejor.</p></a>
      <a class="card2 destacada" href="__SITE__/ola-de-calor/"><h3>🔥 Mapa de la ola de calor</h3><p>El mapa de calor de España, día a día: las máximas de hoy y las mínimas de esta noche, con datos de AEMET.</p></a>
      <a class="card2" href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/"><h3>Refugios cerca de ti</h3><p>Los refugios climáticos más cercanos, con la distancia y la ruta.</p></a>
      <a class="card2" href="__SITE__/confortometro/"><h3>El Confortómetro</h3><p>El estudio participativo: vota cómo se siente el clima en tu zona.</p></a>
      <a class="card2" href="__SITE__/mapa-estaciones/"><h3>Mapa interactivo</h3><p>Las 848 estaciones de AEMET sobre el mapa de España.</p></a>
      <a class="card2" href="__SITE__/ranking-noches-tropicales/"><h3>Ranking nacional</h3><p>Dónde se duerme mejor y peor de toda España.</p></a>
      <a class="card2" href="__SITE__/parte/"><h3>El parte de la noche</h3><p>Quién durmió fresco anoche. Cada mañana.</p></a>
      <a class="card2" href="__SITE__/certificados/"><h3>Certificados</h3><p>Los pueblos acreditados como refugio climático.</p></a>
    </div>
    <h2 class="sec-h" id="articulos">Artículos y estudios</h2>
    <div class="mods">
      <a class="card2 destacada" href="__SITE__/la-espana-que-nunca-se-colorea/"><h3>🗺️ La España que nunca se colorea</h3><p>Superponemos los mapas de AEMET del verano: el mapa honesto de los refugios climáticos, de noche y de día.</p></a>
      <a class="card2 destacada" href="__SITE__/hoteles-refugio-climatico/"><h3>🏨 Hoteles donde dormir con manta</h3><p>25 hoteles en refugios climáticos naturales: la geografía del descanso, con el dato de AEMET de cada zona.</p></a>
      <a class="card2" href="__SITE__/dormir-con-manta-en-verano/"><h3>Dormir con manta en verano</h3><p>Un destino fresco medido por provincia: el mapa del turismo climático.</p></a>
      <a class="card2" href="__SITE__/microclimas/"><h3>Microclimas</h3><p>Por qué un valle puede ser más fresco que la cima de al lado.</p></a>
      <a class="card2" href="__SITE__/refugio-climatico-natural/"><h3>Refugio climático natural</h3><p>Combatir el calor sin aire acondicionado, como se hacía antes.</p></a>
      <a class="card2" href="__SITE__/refugios-y-espana-vaciada/"><h3>Refugios y España vaciada</h3><p>El frío que despobló estos pueblos es hoy su mayor activo.</p></a>
      <a class="card2" href="__SITE__/hipoteca-termica/"><h3>La hipoteca térmica</h3><p>Lo que cuesta cada verano, en euros y en sueño, vivir donde la noche no refresca.</p></a>
      <a class="card2" href="__SITE__/margen-refugios-climaticos/"><h3>El margen de los refugios</h3><p>¿Cuántas décadas de fresco le quedan a un refugio? El caso de Cedrillas.</p></a>
    </div>
  </div></section>
  __FOOTER__
</div>
<script>
const DATA=__DATA__;
const SITE="__SITE__";
const APPS_SCRIPT_URL="__APPS_URL__";
// true = modo consumidor/prensa (sin compra/venta/agente ni puente inmobiliario);
// false = modo inmobiliario (propietario/comprador). Prudentes hasta tener repercusión.
const MODO_PRENSA=true;
function banda(nt){if(nt<1)return["Refugio","var(--c-ref)"];if(nt<10)return["Se duerme bien","var(--c-bien)"];if(nt<30)return["Templado","var(--c-temp)"];if(nt<60)return["Se suda","var(--c-suda)"];return["Horno","var(--c-horno)"];}
function num(nt){return nt===0?"0":(nt<10?nt.toFixed(1).replace(".",","):Math.round(nt)+"");}
var prov=document.getElementById("prov"),est=document.getElementById("est");
Object.keys(DATA).forEach(function(p){var o=document.createElement("option");o.value=p;o.textContent=p;prov.appendChild(o);});
prov.addEventListener("change",function(){
  est.innerHTML='<option value="">…y tu estación</option>';
  (DATA[prov.value]||[]).forEach(function(e,i){var o=document.createElement("option");o.value=i;o.textContent=e.l+" ("+e.a+" m)";est.appendChild(o);});
  document.getElementById("result").hidden=true;
  document.getElementById("tu-h").style.display="none";
  document.getElementById("tu-v").style.display="none";
});
function mostrar(){
  var lst=DATA[prov.value]; if(!lst||est.value==="")return;
  var e=lst[+est.value], pos=Math.min(e.nt,90)/90*100, b=banda(e.nt);
  var th=document.getElementById("tu-h"),tv=document.getElementById("tu-v");
  th.style.left=pos+"%"; th.style.display="block"; document.getElementById("tuh-val").textContent=num(e.nt);
  tv.style.bottom=pos+"%"; tv.style.display="block"; document.getElementById("tuv-val").textContent=num(e.nt);
  var r=document.getElementById("result");
  r.hidden=false;
  var cert=e.c?"<a class='certbadge' href='"+SITE+"/certificados/"+e.c+"/'>Este pueblo es un refugio climático certificado. Ver su certificado →</a>":"";
  var etq=b[0];
  var modo=MODO_PRENSA?"prensa":(e.nt<10?"propietario":"comprador");
  var lh,ls,opts,bridge,zph;
  if(modo==="prensa"){
    lh="¿Quieres el informe de tu zona y aviso si entra en ola de calor?";ls="";
    opts="<option value='info'>Quiero el informe y alertas de calor</option><option value='periodista'>Soy periodista o medio</option>";
    bridge="";zph="Tu provincia (opcional)";
  }else if(modo==="propietario"){
    lh="Tienes una casa donde se duerme fresco. Hoy eso es un tesoro.";
    ls="Cada vez más gente huye del calor. Si te planteas venderla, te ponemos en contacto con compradores que buscan exactamente esto.";
    opts="<option value='tasacion'>Quiero una tasación gratuita</option><option value='vender'>Me planteo vender</option><option value='info'>Solo información de mi zona</option><option value='agente'>Soy agente inmobiliario</option>";
    bridge="Vendemos sin pasar por Idealista — cómo trabajamos →";zph="¿Dónde está tu casa? (opcional)";
  }else{
    lh=e.nt>=30?"¿Y si pudieras dormir fresco? Te ayudamos a encontrar tu refugio.":"¿Quieres el informe de tu zona y aviso si entra en ola de calor?";ls="";
    opts="<option value='info'>Quiero el informe y alertas de calor</option><option value='comprar'>Me interesa comprar en un refugio</option><option value='alquilar'>Me interesa alquilar o veranear</option><option value='agente'>Soy agente inmobiliario</option>";
    bridge="O conoce La Virgen de la Vega, un refugio a 75 min de Valencia →";zph="¿En qué zona te gustaría? (opcional)";
  }
  var cap="<div class='capture'><div class='lead-h'>"+lh+"</div>"+(ls?"<p class='lead-sub'>"+ls+"</p>":"")
    +"<form id='leadf' class='leadform'>"
    +"<input type='email' id='lemail' placeholder='Tu email' required>"
    +"<select id='lwhat'>"+opts+"</select>"
    +"<input type='text' id='lzona' placeholder='"+zph+"'>"
    +"<input type='text' id='lpet' placeholder='¿Qué dato te gustaría ver? (opcional)'>"
    +"<label class='lrgpd'><input type='checkbox' id='lrgpd' required> Acepto que me contactéis sobre esto.</label>"
    +"<button type='submit'>Enviar</button></form>"
    +(bridge?"<a class='bridge' href='https://lavirgendelavega.es' target='_blank' rel='noopener'>"+bridge+"</a>":"")
    +"</div>";
  r.innerHTML="<span class='chip' style='background:"+b[1]+"'>"+b[0]+"</span><b>"+e.l+"</b> ("+prov.value+"), "+e.a+" m — <b>"+num(e.nt)+"</b> noches tropicales al año."+cert+cap;
  var lf=document.getElementById("leadf");
  if(lf) lf.addEventListener("submit",function(ev){
    ev.preventDefault();
    var lead={timestamp:new Date().toISOString(),email:document.getElementById("lemail").value.trim(),
      modo:modo,busca:document.getElementById("lwhat").value,zona_interes:document.getElementById("lzona").value.trim(),
      peticion:document.getElementById("lpet").value.trim(),estacion:e.l,provincia:prov.value,noches_trop:e.nt,
      veredicto:etq,rgpd:document.getElementById("lrgpd").checked?"si":"",source:"portada",user_agent:navigator.userAgent};
    var gracias=function(){var h=document.querySelector("#result .lead-h");if(h)h.textContent="¡Gracias! Te escribimos pronto.";if(lf)lf.remove();};
    if(APPS_SCRIPT_URL){fetch(APPS_SCRIPT_URL,{method:"POST",headers:{"Content-Type":"text/plain;charset=utf-8"},body:JSON.stringify(lead)}).then(gracias).catch(gracias);}
    else{gracias();}
  });
  // En móvil la escala queda arriba, fuera de pantalla: la traemos a la vista
  // para que se aprecie el pin de tu pueblo al seleccionar.
  if(window.matchMedia("(max-width:660px)").matches){
    var rm=window.matchMedia("(prefers-reduced-motion:reduce)").matches;
    tv.scrollIntoView({behavior:rm?"auto":"smooth",block:"center"});
  }
}
est.addEventListener("change",mostrar);
</script>
</body>
</html>
"""


def construir_pagina_beta(datos: dict, site: str, es_portada: bool = False) -> str:
    beta = {prov: [dict(l=e["loc"], nt=e["nt"], a=e["alt"],
                        **({"c": slug(e["loc"])} if e["nt"] < 1 else {}))
                   for e in sorted(lista, key=lambda x: (x["nt"], -x["alt"]))]
            for prov, lista in datos["provincias"].items()}
    data_json = json.dumps(beta, ensure_ascii=False, separators=(",", ":"))
    schema = json.dumps(construir_schema(datos, site), ensure_ascii=False)
    plantilla = PAGINA_BETA
    if es_portada:
        # Como portada real: indexable y sin la barra superior de "beta".
        plantilla = (plantilla
                     .replace('<meta name="robots" content="noindex,nofollow">',
                              '<meta name="robots" content="index,follow,max-image-preview:large">')
                     .replace('<div class="betabar">Versión <b>beta</b> del nuevo diseño · en pruebas · <a href="__HOME__">volver a la web actual</a></div>\n', ''))
    return (plantilla
            .replace('<link rel="canonical" href="__SITE__/">',
                     '<link rel="canonical" href="__SITE__/">\n'
                     + hreflang_block("/", "/en/"))
            .replace("__NAV__", nav_html("inicio"))
            .replace("__FOOTER__", FOOTER_HTML)
            .replace("__CSS_COMUN__", " " + _CSS_COMUN)
            .replace("__DATA__", data_json)
            .replace("__SCHEMA__", schema)
            .replace("__APPS_URL__", APPS_SCRIPT_URL)
            .replace("__HOME__", site + "/")
            .replace("__SITE__", site))


# ===========================================================================
# Página /refugios-climaticos-naturales-cerca-de-mi/: geolocaliza (o eliges estación) y te da los 5
# refugios climáticos naturales más cercanos, con distancia y ruta.
# FASE A: sin dataset de municipios. FASE B (pendiente): buscar por municipio
# (INE) y listar los pueblos bajo la influencia de cada refugio (±150 m alt).
# ===========================================================================
PAGINA_CERCA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Refugios climáticos cerca de ti: dónde se duerme fresco más cerca | nochetropical.es</title>
<meta name="description" content="¿Cuál es el refugio climático natural más cercano a ti? Los pueblos de España sin noches tropicales, con la distancia y la ruta para llegar. Diez veranos de datos de AEMET.">
<link rel="canonical" href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="website">
<meta property="og:title" content="Refugios climáticos cerca de ti">
<meta property="og:description" content="Los pueblos donde se duerme fresco más cerca de ti, con distancia y ruta. Datos de AEMET.">
<meta property="og:url" content="__SITE__/refugios-climaticos-naturales-cerca-de-mi/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<style>
 :root{--bg:#080705;--surface:#16120c;--panel:#211a12;--ink:#f2eae0;--muted:#c3b6a2;--muted2:#9a8d79;--line:#3a3122;--brand:#ee9769;--brand-ink:#160f08;--shadow:0 1px 2px rgba(0,0,0,.5),0 12px 34px rgba(0,0,0,.45);--c-ref:#3f9aa8;--font-d:Georgia,"Times New Roman",serif;--font-b:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--font-m:ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace}
 *{box-sizing:border-box}
 body{margin:0}
 .pg{background:var(--bg);color:var(--ink);font-family:var(--font-b);line-height:1.55}
 .in{max-width:1100px;margin:0 auto;padding:0 24px}
 .nav{position:sticky;top:0;z-index:20;background:rgba(8,7,5,.85);backdrop-filter:saturate(1.3) blur(9px);border-bottom:1px solid var(--line)}
 .nav .in{display:flex;align-items:center;gap:20px;height:60px}
 .brand{display:flex;align-items:center;gap:10px;font-family:var(--font-d);font-weight:700;font-size:18px;color:var(--ink);text-decoration:none;white-space:nowrap}
 .menu{margin-left:auto;display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}
 .menu::-webkit-scrollbar{display:none}
 .menu a{font-size:14.5px;color:var(--muted);text-decoration:none;padding:8px 12px;border-radius:8px;white-space:nowrap}
 .menu a:hover{color:var(--ink);background:rgba(238,151,105,.14)}
 .menu a[aria-current]{color:var(--brand);font-weight:600}
 .menu a.lang{margin-left:4px;border:1px solid var(--line);color:var(--brand);font-weight:600;letter-spacing:.04em}
 .menu a.lang:hover{border-color:var(--brand);background:rgba(238,151,105,.14)}
 .hero{padding:50px 0 6px}
 .kick{font:600 12px/1 var(--font-b);letter-spacing:.16em;text-transform:uppercase;color:var(--brand);margin:0 0 14px}
 h1{font-family:var(--font-d);font-weight:700;font-size:clamp(30px,5vw,46px);line-height:1.06;margin:0;letter-spacing:-.01em;text-wrap:balance}
 .lede{font-size:clamp(16.5px,2.2vw,19px);color:var(--muted);max-width:58ch;margin:18px 0 0}
 .tool{background:var(--surface);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);padding:24px;margin:32px 0}
 .geobtn{width:100%;background:var(--brand);color:var(--brand-ink);border:0;border-radius:12px;font-weight:700;font-size:16px;padding:15px;cursor:pointer}
 .geobtn:hover{filter:brightness(1.08)}
 .geobtn:disabled{opacity:.6;cursor:default}
 .hint{font-size:12.5px;color:var(--muted2);margin:12px 0 0}
 .orsep{display:flex;align-items:center;gap:12px;margin:18px 0;color:var(--muted2);font-size:13px;white-space:nowrap}
 .orsep::before,.orsep::after{content:"";flex:1;height:1px;background:var(--line)}
 .picks{display:flex;gap:10px;flex-wrap:wrap}
 .field{position:relative;flex:1;min-width:190px}
 .field select{width:100%;background:#2c2216;border:1.5px solid #5f5138;border-radius:11px;color:var(--ink);font-size:15px;padding:13px 40px 13px 14px;font-family:var(--font-b);appearance:none;-webkit-appearance:none;cursor:pointer}
 .field select:hover{border-color:#7d6a49}
 .field select:focus{outline:2px solid var(--brand);outline-offset:1px}
 .field::after{content:"";position:absolute;right:16px;top:50%;width:9px;height:9px;border-right:2.5px solid var(--brand);border-bottom:2.5px solid var(--brand);transform:translateY(-70%) rotate(45deg);pointer-events:none}
 .msg{font-size:15px;color:var(--ink);margin:26px 0 0;font-weight:600}
 .refs{list-style:none;padding:0;margin:14px 0 0;display:grid;gap:12px}
 .ref{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
 .ref.first{border-color:var(--c-ref)}
 .rtop{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
 .rn{font-family:var(--font-d);font-weight:700;font-size:18px}
 .rkm{font-family:var(--font-m);font-weight:700;font-size:16px;color:var(--brand);white-space:nowrap}
 .rp{font-size:13.5px;color:var(--muted);margin:4px 0 0}
 .rp .nt{color:var(--c-ref);font-weight:600}
 .rp.rh{font-size:12.5px;opacity:.82;margin:2px 0 0}
 .racc{display:flex;gap:9px;flex-wrap:wrap;margin-top:12px}
 .racc a{font:600 13.5px/1 var(--font-b);padding:9px 14px;border-radius:9px;border:1px solid var(--line);color:var(--ink);text-decoration:none}
 .racc a:hover{border-color:var(--brand);color:var(--brand)}
 .racc a.pri{background:var(--brand);color:var(--brand-ink);border-color:var(--brand)}
 .racc a.pri:hover{color:var(--brand-ink);filter:brightness(1.08)}
 .notas{font-size:13px;color:var(--muted2);border-top:1px dashed var(--line);padding-top:16px;margin-top:34px;line-height:1.65}
 .notas b{color:var(--muted)}
 .compartir{margin:38px 0 0;padding:24px;background:var(--surface);border:1px solid var(--line);border-radius:16px}
 .compartir h2{font-family:var(--font-d);font-weight:700;font-size:clamp(18px,2.6vw,22px);color:var(--ink);margin:0 0 8px;line-height:1.25;text-wrap:balance}
 .compartir p{font-size:14.5px;color:var(--muted);margin:0 0 16px;max-width:58ch}
 .compartir p b{color:var(--ink)}
 .cbtns{display:flex;gap:9px;flex-wrap:wrap}
 .cb{font:600 14px/1 var(--font-b);padding:11px 16px;border-radius:10px;border:1px solid var(--line);background:transparent;color:var(--ink);cursor:pointer;text-decoration:none;display:inline-block}
 .cb:hover{border-color:var(--brand);color:var(--brand)}
 .cb.pri{background:var(--brand);color:var(--brand-ink);border-color:var(--brand)}
 .cb.pri:hover{color:var(--brand-ink);filter:brightness(1.08)}
 footer{margin-top:54px;border-top:1px solid var(--line);background:var(--surface)}
 .fgrid{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;gap:28px;padding:44px 0 28px}
 .fcol h4{font:600 11px/1 var(--font-b);letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 14px}
 .fcol a{display:block;color:var(--ink);text-decoration:none;font-size:15px;margin:0 0 9px;opacity:.9}
 .fcol a:hover{opacity:1;color:var(--brand)}
 .fabout{font-size:14.5px;color:var(--muted);max-width:34ch}
 .fbar{border-top:1px solid var(--line);padding:18px 0;font-size:13px;color:var(--muted)}
 @media(max-width:660px){.fgrid{grid-template-columns:1fr 1fr}}
 @media(max-width:430px){.fgrid{grid-template-columns:1fr}}
__CSS_COMUN__
</style>
</head>
<body>
<div class="pg">
  __NAV__

  <header class="hero"><div class="in">
    <p class="kick">Herramienta · Datos de AEMET</p>
    <h1>¿Dónde está tu refugio climático más cercano?</h1>
    <p class="lede">En España hay <b>218 estaciones de AEMET</b> que no registran ni una noche tropical al año: sitios donde se sigue durmiendo tapado en agosto. Te decimos cuáles tienes más cerca, a qué distancia y cómo llegar.</p>
  </div></header>

  <section><div class="in">
    <div class="tool">
      <button class="geobtn" id="geo" type="button">Usar mi ubicación</button>
      <p class="hint" id="geohint">El cálculo se hace en tu navegador: no guardamos ni enviamos tu ubicación.</p>
      <div class="orsep">o elige tu pueblo (o el más cercano)</div>
      <div class="picks">
        <div class="field"><select id="prov" aria-label="Provincia"><option value="">Elige provincia…</option></select></div>
        <div class="field"><select id="est" aria-label="Estación"><option value="">…y tu estación</option></select></div>
      </div>
    </div>
    <p class="msg" id="msg"></p>
    <ol class="refs" id="refs"></ol>

    <div class="compartir" data-url="__SITE__/refugios-climaticos-naturales-cerca-de-mi/" data-text="__SHARE_TXT__">
      <h2>Ayuda a un amigo a encontrar el refugio climático natural más cercano a su casa</h2>
      <p>Compártela con quien peor lo pase en verano — o úsala tú para elegir tu <b>próximo punto de vacaciones</b>: los sitios de España donde todavía se duerme sin aire acondicionado.</p>
      <div class="cbtns">
        <a class="cb pri" href="__SHARE_WA__" target="_blank" rel="noopener">Enviar por WhatsApp</a>
        <a class="cb" href="__SHARE_X__" target="_blank" rel="noopener">Compartir en X</a>
        <button class="cb" id="cb-copiar" type="button">Copiar enlace</button>
        <button class="cb" id="cb-share" type="button" hidden>Compartir…</button>
      </div>
    </div>

    <p class="notas">
      <b>Cómo se calcula:</b> un <b>refugio climático natural</b> es una estación de AEMET con <b>menos de una noche tropical al año</b> de media (veranos 2017–2026); una noche tropical es aquella en que la mínima no baja de 20&nbsp;°C. La <b>distancia es en línea recta</b>; el botón «Ver ruta» abre el mapa con la ruta real por carretera, con kilómetros y tiempo.<br>
      <b>El límite honesto:</b> el dato es de la <b>estación meteorológica</b>, no del municipio exacto — y en montaña la noche cambia mucho con la altitud. Los pueblos del entorno de un refugio suelen compartir su clima; eso lo mediremos pronto.
    </p>
  </div></section>

  __FOOTER__
</div>
<script>
const REF=__REF__;
const EST=__EST__;
const SITE="__SITE__";
function hav(la1,lo1,la2,lo2){var R=6371,r=Math.PI/180,dLa=(la2-la1)*r,dLo=(lo2-lo1)*r;
 var x=Math.sin(dLa/2)*Math.sin(dLa/2)+Math.cos(la1*r)*Math.cos(la2*r)*Math.sin(dLo/2)*Math.sin(dLo/2);
 return 2*R*Math.asin(Math.sqrt(x));}
function km(d){return d<10?d.toFixed(1).replace(".",","):Math.round(d)+"";}
function ntTxt(nt){return nt===0?"cero noches tropicales al año":(nt<1?"menos de 1 noche tropical al año":nt.toFixed(1).replace(".",",")+" al año");}
function pinta(la,lo,origen){
 var lista=REF.map(function(x){return {x:x,d:hav(la,lo,x.la,x.lo)};}).sort(function(a,b){return a.d-b.d;}).slice(0,5);
 var ol=document.getElementById("refs"); ol.innerHTML="";
 lista.forEach(function(o,i){
   var x=o.x;
   var ruta="https://www.google.com/maps/dir/?api=1&origin="+la+","+lo+"&destination="+x.la+","+x.lo;
   var li=document.createElement("li");
   li.className="ref"+(i===0?" first":"");
   li.innerHTML="<div class='rtop'><span class='rn'>"+x.n+"</span><span class='rkm'>"+km(o.d)+" km</span></div>"
     +"<div class='rp'>"+x.p+" · "+x.a+" m · <span class='nt'>"+ntTxt(x.nt)+"</span></div>"
     +(x.h?"<div class='rp rh'>"+x.h+"% humedad media en agosto"+(x.v?" · "+x.v+" km/h de viento":"")+"</div>":"")
     +"<div class='racc'><a class='pri' href='"+ruta+"' target='_blank' rel='noopener'>Ver ruta</a>"
     +"<a href='"+SITE+"/certificados/"+x.c+"/'>Ver su certificado</a>"
     +"<a href='"+SITE+"/"+x.s+"/'>Ver "+x.p+"</a></div>";
   ol.appendChild(li);
 });
 document.getElementById("msg").textContent="Tus 5 refugios climáticos naturales más cercanos"+(origen?" a "+origen:"")+":";
 document.getElementById("msg").scrollIntoView({behavior:"smooth",block:"start"});
}
var gb=document.getElementById("geo"), gh=document.getElementById("geohint");
gb.addEventListener("click",function(){
 if(!navigator.geolocation){gh.textContent="Tu navegador no permite la geolocalización. Elige tu provincia y estación aquí abajo.";return;}
 gb.disabled=true; gb.textContent="Buscando tu ubicación…";
 navigator.geolocation.getCurrentPosition(function(p){
   gb.disabled=false; gb.textContent="Usar mi ubicación";
   pinta(p.coords.latitude,p.coords.longitude,"tu ubicación");
 },function(){
   gb.disabled=false; gb.textContent="Usar mi ubicación";
   gh.textContent="No se pudo obtener tu ubicación (¿permiso denegado?). Elige tu provincia y estación aquí abajo.";
 },{timeout:9000});
});
var prov=document.getElementById("prov"), est=document.getElementById("est");
Object.keys(EST).forEach(function(p){var o=document.createElement("option");o.value=p;o.textContent=p;prov.appendChild(o);});
prov.addEventListener("change",function(){
 est.innerHTML='<option value="">…y tu estación</option>';
 (EST[prov.value]||[]).forEach(function(e,i){var o=document.createElement("option");o.value=i;o.textContent=e.n+" ("+e.a+" m)";est.appendChild(o);});
});
est.addEventListener("change",function(){
 var l=EST[prov.value]; if(!l||est.value==="")return;
 var e=l[+est.value]; pinta(e.la,e.lo,e.n);
});

// Compartir: copiar al portapapeles y hoja nativa del móvil (si la hay).
(function(){
 var box=document.querySelector(".compartir"); if(!box) return;
 var url=box.getAttribute("data-url"), text=box.getAttribute("data-text");
 var cp=document.getElementById("cb-copiar");
 if(cp&&navigator.clipboard) cp.addEventListener("click",function(){
   navigator.clipboard.writeText(url).then(function(){
     cp.textContent="Enlace copiado"; setTimeout(function(){cp.textContent="Copiar enlace";},1600);
   });
 });
 var sh=document.getElementById("cb-share");
 if(sh&&navigator.share){ sh.hidden=false;
   sh.addEventListener("click",function(){
     navigator.share({title:document.title,text:text,url:url}).catch(function(){});
   });
 }
})();
</script>
</body>
</html>
"""


def construir_pagina_cerca(estaciones: list, datos: dict, site: str,
                           humedad: dict | None = None) -> str:
    """Los 218 refugios (nt<1) con coordenadas + todas las estaciones para poder
    elegir origen sin geolocalización. El cálculo (Haversine) va en el navegador.
    Cada refugio lleva, si existe, el complemento de humedad/viento de agosto."""
    hum = humedad or {}

    def _ref(e):
        r = {"n": e["loc"], "p": e["prov"], "a": e["alt"], "nt": e["nt"],
             "la": e["lat"], "lo": e["lon"], "c": slug(e["loc"]), "s": slug(e["prov"])}
        hd = hum.get(e["id"])
        if hd:
            r["h"] = hd["hr"]
            if hd.get("viento") is not None:
                r["v"] = hd["viento"]
        return r
    refs = [_ref(e) for e in sorted(estaciones, key=lambda x: (x["nt"], -x["alt"]))
            if e["nt"] < 1]
    est = {prov: [{"n": e["loc"], "a": e["alt"], "la": e["lat"], "lo": e["lon"]}
                  for e in sorted(lista, key=lambda x: clave_orden(x["loc"]))]
           for prov, lista in datos["provincias"].items()}
    url = site + "/refugios-climaticos-naturales-cerca-de-mi/"
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Refugios cerca de ti", "item": url}]},
        {"@type": "WebApplication", "name": "Refugios climáticos cerca de ti",
         "url": url, "applicationCategory": "ReferenceApplication",
         "operatingSystem": "Web",
         "description": "Encuentra los refugios climáticos naturales más cercanos a tu ubicación, con la distancia y la ruta. Con diez veranos de datos de AEMET.",
         "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"},
         "isPartOf": {"@type": "WebSite", "name": "Refugio Climático", "url": site + "/"}}]},
        ensure_ascii=False)
    # Texto para compartir: dato favorable primero y sin emojis.
    from urllib.parse import quote
    import html as _html
    url_cerca = site + "/refugios-climaticos-naturales-cerca-de-mi/"
    share_txt = ("En España quedan 218 pueblos donde no se registra ni una noche tropical al año: "
                 "se duerme tapado en agosto y sin aire acondicionado. "
                 "Mira cuál te pilla más cerca, con los datos de AEMET de diez veranos:")
    return (PAGINA_CERCA
            .replace("__NAV__", nav_html("cerca"))
            .replace("__FOOTER__", FOOTER_HTML)
            .replace("__CSS_COMUN__", " " + _CSS_COMUN)
            .replace("__SHARE_WA__", "https://wa.me/?text=" + quote(share_txt + " " + url_cerca))
            .replace("__SHARE_X__", "https://twitter.com/intent/tweet?text=" + quote(share_txt)
                     + "&amp;url=" + quote(url_cerca))
            .replace("__SHARE_TXT__", _html.escape(share_txt, quote=True))
            .replace("__SCHEMA__", schema)
            .replace("__REF__", json.dumps(refs, ensure_ascii=False, separators=(",", ":")))
            .replace("__EST__", json.dumps(est, ensure_ascii=False, separators=(",", ":")))
            .replace("__HOME__", site + "/")
            .replace("__SITE__", site))


# ===========================================================================
# EL CONFORTÓMETRO: termómetro colectivo de sensación nocturna.
# La gente vota cómo siente la noche (de fresquito a insoportable) y el voto
# se contrasta con el dato de AEMET de su zona. Privacidad: la geolocalización
# se resuelve EN el navegador a la estación AEMET más cercana; las coordenadas
# exactas nunca se envían ni se guardan.
# Backend sin servidor: Google Apps Script + Sheet (mismo patrón que los
# leads). Ver scripts/apps_script_confortometro.gs; al desplegarlo, pegar la
# URL /exec en APPS_SCRIPT_CONFORT_URL. Con la URL vacía la página funciona
# en modo demostración (no guarda votos y lo dice).
# ===========================================================================
APPS_SCRIPT_CONFORT_URL = ("https://script.google.com/macros/s/AKfycbwjIxpPVGrwcUJb"
                           "29i6L75tTQyN5h6IB243GblSXwIHAonMiQB9cEtJk2zaRI3P4W4PWg/exec")

# Buzón del OBSERVATORIO DEL DESCANSO (las noches: cómo se ha dormido). Es un
# despliegue DISTINTO del confortómetro —otra hoja, otras columnas—: ver
# scripts/apps_script_observatorio.gs. Con la URL vacía el Observatorio funciona
# en modo demostración: deja votar, enseña el resultado y AVISA de que la noche
# no se ha guardado. En cuanto se pegue aquí la URL /exec, empieza a guardarlas.
APPS_SCRIPT_OBS_URL = ("https://script.google.com/macros/s/AKfycbz4bvNwAVEBDA0NId5_"
                       "uv42a_Q9oXlA2h4q25CZ8ZuDRmWilVIDbg2qAmGGHDChmVhmyg/exec")

# Palabra secreta del atajo de teclado de la sala de prensa: tecléala en
# /prensa/ y saltas a la consola interna de informes (/informes/). Va ofuscada
# en base64 en el HTML (no en claro), pero es seguridad por oscuridad: cámbiala
# cuando quieras y no guardes nada sensible en la consola.
PALABRA_CONSOLA = "refugio"

# Niveles de sensación: escala SIMÉTRICA de 9 puntos (ampliación de la ASHRAE
# de 7), en lenguaje de calle. Cubre también el frío: el confortómetro es un
# estudio de TODO el año (verano e invierno, día y noche), no solo de noches
# de calor — es la base del concepto "turismo climático". El valor 1-9 es lo
# que viaja y lo que usa el detector de coherencia.
NIVELES_CONFORT = [
    (1, "🧊", "Helador: se pasa frío de verdad"),
    (2, "🥶", "Frío: imprescindible abrigo"),
    (3, "🧣", "Fresco: de manta o chaqueta"),
    (4, "😌", "Muy a gusto"),
    (5, "🙂", "Cómodo: ni frío ni calor"),
    (6, "😐", "Templado: el calor se nota"),
    (7, "🥵", "Caluroso: incomoda"),
    (8, "😫", "Mucho calor: se suda hasta quieto"),
    (9, "🔥", "Insoportable"),
]

CSV_ROLLING = AEMET_DIR / "datos" / "diarios_estaciones.csv"


def cargar_termometro_reciente() -> dict[str, tuple[str, float, float | None]]:
    """Última mínima y máxima disponibles por estación del CSV rolling (AEMET
    publica con 3-5 días de retraso). {indicativo: (fecha, tmin, tmax)}.
    La mínima referencia los votos nocturnos; la máxima, los diurnos."""
    if not CSV_ROLLING.exists():
        return {}
    ultimas: dict[str, tuple[str, float, float | None]] = {}
    with CSV_ROLLING.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                tmin = float(row["tmin"])
            except (ValueError, KeyError, TypeError):
                continue
            try:
                tmax = float(row["tmax"])
            except (ValueError, KeyError, TypeError):
                tmax = None
            ind, fecha = row["indicativo"], row["fecha"]
            if ind not in ultimas or fecha > ultimas[ind][0]:
                ultimas[ind] = (fecha, tmin, tmax)
    return ultimas


def cargar_climatologia_mes(mes: int) -> dict[str, tuple[float, float | None]]:
    """Media histórica (2017-2026) de tmin y tmax del mes dado, por estación.
    Es la referencia de RESPALDO para el confortómetro: unas ~76 estaciones del
    catálogo (Valencia Viveros, Girona, Ronda…) dejaron de publicar en el feed
    diario de AEMET y no tienen dato reciente; para esas, la media del mes en
    curso de nuestros 10 años de datos hace de referencia de coherencia.
    {indicativo: (tmin_media, tmax_media|None)}."""
    mm = f"{mes:02d}"
    s_min: dict[str, float] = {}
    n_min: dict[str, int] = {}
    s_max: dict[str, float] = {}
    n_max: dict[str, int] = {}
    for ruta in sorted((AEMET_DIR / "datos").glob("diarios_2*.csv")):
        with ruta.open(newline="", encoding="utf-8") as f:
            lector = csv.reader(f)
            cab = next(lector, None)
            if not cab:
                continue
            ix = {c: i for i, c in enumerate(cab)}
            ii, ifch, itn = ix.get("indicativo"), ix.get("fecha"), ix.get("tmin")
            itx = ix.get("tmax")
            if ii is None or ifch is None or itn is None:
                continue
            for row in lector:
                if len(row) <= itn or row[ifch][5:7] != mm:  # solo el mes pedido
                    continue
                ind = row[ii]
                try:
                    s_min[ind] = s_min.get(ind, 0.0) + float(row[itn])
                    n_min[ind] = n_min.get(ind, 0) + 1
                except ValueError:
                    pass
                if itx is not None and len(row) > itx:
                    try:
                        s_max[ind] = s_max.get(ind, 0.0) + float(row[itx])
                        n_max[ind] = n_max.get(ind, 0) + 1
                    except ValueError:
                        pass
    clima: dict[str, tuple[float, float | None]] = {}
    for ind, suma in s_min.items():
        tmax = round(s_max[ind] / n_max[ind], 1) if n_max.get(ind) else None
        clima[ind] = (round(suma / n_min[ind], 1), tmax)
    return clima


PAGINA_CONFORTOMETRO = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>El Confortómetro: el estudio que mide cómo se siente el clima en España</title>
<meta name="description" content="Estudio de investigación participativa: miles de votos anónimos, de helador a insoportable, contrastados con AEMET. Vota cómo se siente tu zona ahora — de día, de noche, en verano y en invierno.">
<link rel="canonical" href="__SITE__/confortometro/">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="website">
<meta property="og:title" content="El Confortómetro: el estudio que mide cómo se siente el clima en España">
<meta property="og:description" content="De helador a insoportable: el clima que se siente, votado por la gente y contrastado con AEMET. Participa: son 10 segundos.">
<meta property="og:url" content="__SITE__/confortometro/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&family=JetBrains+Mono:wght@700&display=swap" rel="stylesheet">
<style>
 :root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--verde:#8fb07a;--rojo:#cf6b54;--fd:"Fraunces",Georgia,serif;--fb:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--fm:"JetBrains Mono",monospace}
 *{margin:0;padding:0;box-sizing:border-box}
 body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.6;-webkit-font-smoothing:antialiased}
 .wrap{max-width:min(92vw,760px);margin:0 auto;padding:0 22px}
 a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}
 header.h{padding:46px 0 12px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}
 .crumb{font-size:13px;color:var(--muted)}
 .kick{font:600 12px/1 var(--fb);letter-spacing:.16em;text-transform:uppercase;color:var(--teja);margin:18px 0 8px}
 h1{font-family:var(--fd);font-weight:900;font-size:clamp(30px,6vw,46px);line-height:1.05;letter-spacing:-.01em}
 h1 em{font-style:italic;color:var(--teja2)}
 .intro{color:var(--muted);font-size:clamp(15px,2.4vw,17.5px);margin:18px 0 0;max-width:640px}
 .intro b{color:var(--paper)}
 section{padding:26px 0}
 .como{margin:0 0 4px;border-left:3px solid var(--teja);background:var(--bg2);border-radius:0 12px 12px 0;padding:14px 16px;font-size:14px;color:var(--muted);line-height:1.55}
 .como b{color:var(--paper)}
 .dirbox{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:20px}
 .dirn{font-size:14px;color:var(--muted)}.dirn b{color:var(--teja2);font-family:var(--fm)}
 .brow{display:flex;align-items:center;gap:10px;margin:6px 0}
 .blab{flex:0 0 168px;font-size:13px;color:var(--muted);text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .btrack{flex:1;height:10px;background:var(--bg);border-radius:99px;overflow:hidden}
 .bfill{display:block;height:100%;background:var(--teja);border-radius:99px}
 .bnum{flex:0 0 30px;font-family:var(--fm);font-size:12.5px;color:var(--paper)}
 .dzl{list-style:none;margin:6px 0 0;padding:0;font-size:14px;color:var(--muted)}
 .dzl li{padding:6px 0;border-bottom:1px solid var(--line)}.dzl li:last-child{border-bottom:none}
 .dzl b{color:var(--paper)}
 @media(max-width:520px){.blab{flex-basis:120px}}
 .paso{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:20px;margin:14px 0}
 .paso .pt{font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;color:var(--teja);margin-bottom:12px}
 .geo{display:inline-block;background:var(--teja);color:#1a1209;font-weight:700;padding:12px 20px;border-radius:11px;border:0;font-size:15px;cursor:pointer}
 .geo:hover{background:var(--teja2)}
 .geo[disabled]{opacity:.6;cursor:wait}
 .hint{font-size:12.5px;color:var(--muted);margin-top:10px}
 .priv{font-size:12.5px;color:var(--verde);margin-top:8px}
 .zona{display:none;margin-top:12px;font-size:15px}
 .zona b{color:var(--teja2)}
 .selects{display:flex;flex-wrap:wrap;gap:9px;margin-top:12px}
 select{background:var(--bg);border:1px solid var(--line);color:var(--paper);padding:10px 12px;border-radius:9px;font-size:14px;max-width:100%}
 .niveles{display:grid;grid-template-columns:1fr 1fr;gap:7px}
 .nvl{display:flex;align-items:center;gap:9px;background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:8px 11px;cursor:pointer;color:var(--paper);text-align:left;width:100%}
 .nvl:hover{border-color:var(--teja)}
 .nvl.sel{border-color:var(--teja);background:rgba(217,116,78,.16)}
 .nvl .em{font-size:19px;flex:0 0 auto}
 .nvl .nl{display:flex;flex-direction:column;min-width:0;line-height:1.15}
 .nvl .nl b{font-size:13.5px;font-weight:700}
 .nvl .nl .d{font-size:11px;color:var(--muted);margin-top:1px}
 .nvl.sel .nl .d{color:var(--teja2)}
 .chips{display:flex;flex-wrap:wrap;gap:8px}
 .chip{background:var(--bg);border:1px solid var(--line);border-radius:999px;padding:8px 14px;font-size:13.5px;color:var(--muted);cursor:pointer}
 .chip:hover{border-color:var(--teja)}
 .chip.sel{border-color:var(--teja);color:var(--teja2);background:rgba(217,116,78,.12);font-weight:600}
 .subq{font-size:13px;color:var(--muted);margin:12px 0 8px}
 #clima{display:none}
 .enviar{width:100%;margin-top:6px;background:var(--teja);color:#1a1209;font-weight:700;padding:14px;border-radius:12px;border:0;font-size:16px;cursor:pointer}
 .enviar:hover{background:var(--teja2)}
 .enviar[disabled]{opacity:.4;cursor:not-allowed}
 .gracias{display:none;text-align:center;padding:26px 18px}
 .gracias .big{font-family:var(--fd);font-weight:600;font-size:22px;margin-bottom:8px}
 .racha{font-size:14px;color:var(--teja2);font-weight:600;margin-top:2px}
 .manana{font-size:13px;color:var(--muted);margin:14px auto 0;max-width:480px}
 .manana b{color:var(--paper)}
 .resultado{margin-top:14px;font-size:14.5px;color:var(--muted)}
 .resultado b{color:var(--paper)}
 .resultado .num{font-family:var(--fm);color:var(--teja2)}
 .zinfo{margin:16px auto 0;max-width:480px;text-align:left;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:14px 16px;font-size:14px;color:var(--muted)}
 .zinfo b{color:var(--paper)} .zinfo .num{font-family:var(--fm);color:var(--teja2)}
 .zinfo a{display:inline-block;margin-top:8px;font-weight:600}
 .compartir{margin:18px auto 0;max-width:480px;padding:14px 16px;background:var(--bg);border:1px solid var(--line);border-radius:12px;text-align:left}
 .compartir .ct{display:block;font:600 11px/1 var(--fb);letter-spacing:.12em;text-transform:uppercase;color:var(--teja);margin-bottom:10px}
 .compartir .cbtns{display:flex;flex-wrap:wrap;gap:8px}
 .compartir .cb{font:600 13px/1 var(--fb);padding:9px 14px;border-radius:9px;border:1px solid var(--line);background:transparent;color:var(--paper);cursor:pointer;text-decoration:none;display:inline-block}
 .compartir .cb:hover{border-color:var(--teja);color:var(--teja2);text-decoration:none}
 .demo{display:none;font-size:12.5px;color:var(--teja2);margin-top:10px}
 .hp{position:absolute;left:-9999px;opacity:0;height:0;overflow:hidden}
 .prose{margin:10px 0;max-width:680px}
 .prose h2{font-family:var(--fd);font-weight:700;font-size:clamp(19px,3.4vw,23px);margin:26px 0 8px}
 .prose p{color:var(--muted);font-size:14.5px;margin:0 0 12px}
 .prose p b{color:var(--paper)}
 .faq{margin-top:6px;max-width:680px}
 .faqitem{padding:14px 0;border-bottom:1px solid var(--line)}
 .faqitem h3{font-family:var(--fd);font-weight:600;font-size:16px;margin-bottom:5px}
 .faqitem p{color:var(--muted);font-size:14px}
 /* --- Asistente paso a paso: una pregunta por pantalla --- */
 .wstage{position:relative;display:flex;flex-direction:column;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:20px;padding:18px 18px 14px;max-width:640px;margin:0 auto;min-height:min(62vh,520px)}
 .wbar{height:5px;background:var(--bg);border-radius:99px;overflow:hidden;margin-bottom:16px;flex:0 0 auto}
 /* El paso del nivel tiene 9 opciones: cabecera compacta para que quepan todas. */
 #s-nivel .wq{font-size:clamp(20px,4.6vw,28px);margin-bottom:4px}
 #s-nivel .wsub{font-size:12.5px;margin-bottom:10px}
 .wbar span{display:block;height:100%;width:0;background:var(--teja);border-radius:99px;transition:width .35s ease}
 .wstep{display:none}
 .wstep.on{display:flex;flex-direction:column;flex:1 1 auto;animation:wfade .28s ease}
 @keyframes wfade{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
 .wq{font-family:var(--fd);font-weight:700;font-size:clamp(22px,4.8vw,31px);line-height:1.12;letter-spacing:-.01em;margin:0 0 8px}
 .wsub{color:var(--muted);font-size:14.5px;line-height:1.55;margin:0 0 18px;max-width:46ch}
 .wstep .como{margin:0 0 18px}
 .wstep .chips.big{gap:10px;margin-top:2px}
 .wstep .chips.big .chip{font-size:15px;padding:12px 18px}
 .wcont{align-self:flex-start;margin-top:22px;background:var(--teja);color:#1a1209;font-weight:700;padding:13px 24px;border-radius:11px;border:0;font-size:15px;cursor:pointer}
 .wcont[disabled]{opacity:.4;cursor:not-allowed}
 .wcont:hover:not([disabled]){background:var(--teja2)}
 .wnav{display:flex;align-items:center;gap:12px;margin-top:18px;padding-top:15px;border-top:1px solid var(--line);flex:0 0 auto}
 .wback{background:none;border:0;color:var(--muted);font-size:14px;cursor:pointer;padding:6px 2px}
 .wback:hover{color:var(--paper)}
 .wskip{margin-left:auto;background:none;border:0;color:var(--muted);font-size:14px;cursor:pointer;text-decoration:underline;text-underline-offset:3px}
 .wskip:hover{color:var(--paper)}
 .wya{background:none;border:1px solid var(--line);color:var(--teja2);font:600 13px/1 var(--fb);cursor:pointer;padding:9px 13px;border-radius:9px}
 .wya:hover{border-color:var(--teja)}
 .gnav{margin:20px auto 0;max-width:520px;text-align:left}
 .gnav .ct{display:block;font:600 11px/1 var(--fb);letter-spacing:.12em;text-transform:uppercase;color:var(--teja);margin-bottom:11px;text-align:center}
 .gnav-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
 .gnav-grid a{display:block;background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:11px 13px;font-size:13.5px;color:var(--paper);font-weight:600}
 .gnav-grid a:hover{border-color:var(--teja);color:var(--teja2);text-decoration:none}
 @media(max-width:520px){.gnav-grid{grid-template-columns:1fr}}
 __NAVCSS__
 __FOOTERCSS__
 @media(min-width:560px){.niveles{grid-template-columns:1fr 1fr}}
 @media(min-width:980px){
  .wrap{max-width:min(94vw,1150px)}
  .prose{max-width:none;column-count:2;column-gap:52px}
  .prose h2{break-after:avoid;margin-top:0}
  .prose h2:not(:first-child){margin-top:26px}
  .prose p{break-inside:avoid}
  .faq{max-width:none;display:grid;grid-template-columns:1fr 1fr;gap:0 52px}
 }
</style>
</head>
<body>
__NAV__
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">Refugio Climático</a> · El Confortómetro</nav>
  <div class="kick">Estudio de investigación participativa · Turismo climático</div>
  <h1>El Confortómetro: el estudio que mide cómo <em>se siente</em> España</h1>
  <p class="intro">El termómetro dice una cosa; tu cuerpo, otra. Este estudio nacional recopila, voto a voto y durante todo el año, <b>el clima que se siente</b> — de día y de noche, en verano y en invierno — y lo contrasta con el que miden las estaciones de AEMET. Tu voto es anónimo y cuesta 10 segundos.</p>
</div></header>

<section><div class="wrap" id="widget">
  <div class="wstage" id="wstage">
    <div class="wbar" aria-hidden="true"><span id="wfill"></span></div>

    <div class="wstep" data-step="zona" id="s-zona">
      <p class="como"><b>Funciona como los avisos de Google Maps.</b> Tú informas de cómo se siente el clima en tu zona ahora mismo; los votos de los demás lo confirman o lo matizan, y el dato oficial de AEMET hace de árbitro. Cuanta más gente vota, más vivo es el mapa.</p>
      <h2 class="wq">¿Desde qué zona votas?</h2>
      <div id="geoform">
        <button class="geo" id="geo" type="button">📍 Usar mi zona</button>
        <p class="priv">Tu ubicación exacta nunca sale del móvil: aquí mismo se redondea a una celda de ~1 km y se busca la estación de AEMET de referencia. Solo viajan esas dos cosas; el punto exacto, jamás.</p>
        <p class="hint" id="geohint">¿Sin GPS o no quieres darlo? Elige a mano:</p>
        <div class="selects">
          <select id="prov"><option value="">Tu provincia…</option></select>
          <select id="est"><option value="">…y tu zona</option></select>
        </div>
      </div>
      <p class="zona" id="zona"></p>
      <button class="wcont" id="wcont" type="button" disabled>Continuar →</button>
    </div>

    <div class="wstep" data-step="nivel" id="s-nivel">
      <h2 class="wq">¿Cómo se siente ahí ahora mismo?</h2>
      <p class="wsub">Elige lo que siente tu cuerpo, no lo que marca el termómetro.</p>
      <div class="niveles" id="niveles">__NIVELES__</div>
    </div>

    <div class="wstep opt" data-step="agusto" id="s-agusto">
      <h2 class="wq">¿Qué tal se está aquí ahora?</h2>
      <p class="wsub">La ciencia del confort no mide los grados: mide <b>cuánta gente está a gusto</b> (lo que llaman «satisfacción térmica»). Esta es tu parte.</p>
      <div class="chips big" id="agusto">
        <button class="chip" type="button" data-v="5">😍 ¡Qué bien se está!</button>
        <button class="chip" type="button" data-v="4">🙂 Se está bien</button>
        <button class="chip" type="button" data-v="3">😐 Ni fu ni fa</button>
        <button class="chip" type="button" data-v="2">😖 Se está incómodo</button>
        <button class="chip" type="button" data-v="1">😫 Se está fatal</button>
      </div>
    </div>

    <div class="wstep opt" data-step="boch" id="s-boch">
      <h2 class="wq">¿El aire se siente húmedo, pegajoso?</h2>
      <p class="wsub">La humedad no es más calor: es sudor que no evapora. Cuenta distinto.</p>
      <div class="chips big" id="boch">
        <button class="chip" type="button" data-v="1">💦 Sí, bochorno</button>
        <button class="chip" type="button" data-v="0">🌵 No, aire seco</button>
      </div>
    </div>

    <div class="wstep opt" data-step="viento" id="s-viento">
      <h2 class="wq">¿Y el viento? Lo cambia todo.</h2>
      <div class="chips big" id="viento">
        <button class="chip" type="button" data-v="calma">🍃 Calma total</button>
        <button class="chip" type="button" data-v="ligera">🌬️ Ligera brisa</button>
        <button class="chip" type="button" data-v="brisa">😌 Brisa agradable</button>
        <button class="chip" type="button" data-v="viento">💨 Viento</button>
        <button class="chip" type="button" data-v="molesto">😣 Viento molesto</button>
        <button class="chip" type="button" data-v="fuerte">🌪️ Viento fuerte</button>
      </div>
    </div>

    <div class="wstep opt" data-step="cielo" id="s-cielo">
      <h2 class="wq">¿Qué tiempo hace ahí fuera?</h2>
      <div class="chips big" id="cielochips">
        <button class="chip" type="button" data-v="sol">☀️ Sol radiante</button>
        <button class="chip" type="button" data-v="nubes">⛅ Nubes y claros</button>
        <button class="chip" type="button" data-v="nublado">☁️ Cielo cubierto</button>
        <button class="chip" type="button" data-v="bruma">🌫️ Bruma o calima</button>
        <button class="chip" type="button" data-v="niebla">🌁 Niebla</button>
        <button class="chip" type="button" data-v="xirimiri">🌦️ Sirimiri</button>
        <button class="chip" type="button" data-v="lluvia">🌧️ Llueve</button>
      </div>
    </div>

    <div class="wstep opt" data-step="lugar" id="s-lugar">
      <h2 class="wq">¿Dónde estás ahora?</h2>
      <div class="chips big" id="lugar">
        <button class="chip" type="button" data-v="casa">🏠 Dentro de casa</button>
        <button class="chip" type="button" data-v="oficina">🏢 Oficina o despacho</button>
        <button class="chip" type="button" data-v="fabrica">🏭 Fábrica o nave</button>
        <button class="chip" type="button" data-v="colegio">🏫 Colegio o aula</button>
        <button class="chip" type="button" data-v="terraza">🌆 Terraza o balcón</button>
        <button class="chip" type="button" data-v="calle">🚶 En la calle</button>
      </div>
    </div>

    <div class="wstep opt" data-step="clima" id="s-clima">
      <h2 class="wq">Y ahí dentro, ¿con qué te apañas?</h2>
      <div class="chips big" id="climachips">
        <button class="chip" type="button" data-v="nada">Nada</button>
        <button class="chip" type="button" data-v="ventana">Ventana abierta</button>
        <button class="chip" type="button" data-v="ventilador">Ventilador</button>
        <button class="chip" type="button" data-v="aire">Aire acondicionado</button>
        <button class="chip" type="button" data-v="calefaccion">Calefacción</button>
      </div>
    </div>

    <div class="wstep opt" data-step="entorno" id="s-entorno">
      <h2 class="wq">¿Cómo es tu zona?</h2>
      <div class="chips big" id="entorno">
        <button class="chip" type="button" data-v="playa">🏖️ Playa / costa</button>
        <button class="chip" type="button" data-v="ciudad">🏙️ Ciudad</button>
        <button class="chip" type="button" data-v="pueblo">🏡 Pueblo / campo</button>
        <button class="chip" type="button" data-v="montana">⛰️ Montaña</button>
      </div>
    </div>

    <div class="wstep opt" data-step="origen" id="s-origen">
      <h2 class="wq">¿Eres de aquí o estás de visita?</h2>
      <p class="wsub">Un vecino y un forastero sienten distinto el mismo sitio — y comparar las dos cosas es justo lo interesante.</p>
      <div class="chips big" id="origen">
        <button class="chip" type="button" data-v="local">🏡 Del pueblo · vivo aquí</button>
        <button class="chip" type="button" data-v="visita">🧳 De visita · de paso</button>
      </div>
    </div>

    <div class="wstep" data-step="enviar" id="s-enviar">
      <h2 class="wq">Ya está. ¿Enviamos tu voto?</h2>
      <p class="wsub" id="resumen"></p>
      <input class="hp" type="text" name="web" id="hp" tabindex="-1" autocomplete="off" aria-hidden="true">
      <button class="enviar" id="enviar" type="button" disabled>Enviar mi voto</button>
      <p class="hint" id="estado"></p>
    </div>

    <div class="wnav" id="wnav">
      <button class="wback" id="wback" type="button">‹ Atrás</button>
      <button class="wskip" id="wskip" type="button">Omitir ›</button>
      <button class="wya" id="wya" type="button">Enviar ya ›</button>
    </div>
  </div>

  <div class="paso gracias" id="gracias">
    <div class="big">🌙 Gracias: tu voto ya forma parte del estudio.</div>
    <p class="racha" id="racha"></p>
    <div class="resultado" id="resultado"></div>
    <div class="zinfo" id="zinfo"></div>
    <p class="manana">📅 <b>Vuelve mañana.</b> Cada mañana publicamos <a href="__SITE__/parte/">el parte de la noche</a> — quién durmió fresco y quién no pegó ojo — y tu zona quedará recordada aquí para votar con un solo toque. Cuantos más días votes, más fino será el mapa del confort.</p>
    <p class="demo" id="demo">Modo demostración: el buzón de votos aún no está desplegado, así que este voto no se ha guardado.</p>
    <div class="gnav">
      <span class="ct">No te vayas todavía · sigue explorando</span>
      <div class="gnav-grid">
        <a href="__SITE__/ranking-noches-tropicales/">🏆 El ranking: dónde se duerme mejor y peor</a>
        <a href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/">📍 Refugios climáticos cerca de mí</a>
        <a href="__SITE__/dormir-con-manta-en-verano/">🛌 Pueblos para dormir con manta en agosto</a>
        <a href="__SITE__/ola-de-calor/">🔥 ¿Cuándo acaba la ola de calor?</a>
        <a href="__SITE__/parte/">🌙 El parte de la noche de hoy</a>
        <a href="__SITE__/">🏡 La calculadora de tu pueblo</a>
      </div>
    </div>
    <div class="compartir">
      <span class="ct">Un estudio así se construye compartiéndolo</span>
      <div class="cbtns">
        <a class="cb" id="cb-wa" target="_blank" rel="noopener">WhatsApp</a>
        <a class="cb" id="cb-x" target="_blank" rel="noopener">X</a>
        <button class="cb" id="cb-copiar" type="button">Copiar enlace</button>
        <button class="cb" id="cb-share" type="button" hidden>Compartir…</button>
      </div>
    </div>
  </div>
</div></section>

<section><div class="wrap" id="directo">
  <div class="kick">El resultado, en directo</div>
  <div class="dirbox" id="dirbox"><p class="hint">Cargando los votos de las últimas 24 horas…</p></div>
</div></section>

<section><div class="wrap"><div class="prose">
  <h2>¿Por qué un confortómetro?</h2>
  <p>Cuando quieres saber cómo se está en otro sitio, hoy solo tienes dos fuentes: <b>lo que te cuente alguien que está allí</b> o <b>el termómetro más cercano</b> que le encuentre el móvil a esa localidad. Y muchas veces no cuadran: tu amigo jura que no ha pegado ojo y el aparato marca una cifra de lo más razonable. ¿Coincide lo que sienten las personas con lo que dice el termómetro de su pueblo? Nosotros tenemos serias dudas.</p>
  <p>Porque la temperatura es un valor <b>relativo</b>: orienta, pero no establece las condiciones exactas. Un termómetro no suda, no nota la humedad que impide que el sudor evapore, ni el asfalto que devuelve por la noche el calor del día, ni la brisa que lo cambia todo. El Confortómetro nace para medir lo que ese número no cuenta: <b>el estado de confort de las personas, en su momento y en su lugar</b>. Una herramienta participativa para levantar, voto a voto, el mapa del grado de confort real en las poblaciones españolas — y compararlo con el de los termómetros.</p>

  <h2>Un estudio para todo el año: hacia el turismo climático</h2>
  <p>Este estudio no es solo de noches de verano. Se vota <b>de día y de noche, en agosto y en enero</b>: la escala va del frío helador al calor insoportable. Con el tiempo, esos votos dibujan algo que hoy no existe: el calendario del confort de cada zona de España — dónde se está bien en cada época del año. Esa es la base del <b>turismo climático</b>: elegir destino no por lo que hay que ver, sino por cómo se va a sentir el cuerpo al estar allí. <a href="__SITE__/dormir-con-manta-en-verano/">Los pueblos donde se duerme con manta en agosto</a> ya lo saben; este estudio quiere ponerle números y mapa. Y si lo que quieres es escapar del calor este fin de semana, <a href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/">busca el refugio climático natural más cerca de ti →</a></p>

  <h2>Cómo funciona (y cómo detectamos trolas)</h2>
  <p>Cada voto se contrasta con lo que marcó la <a href="__SITE__/mapa-estaciones/">estación de AEMET de su zona</a>: si alguien vota «insoportable» una noche de mínima 14&nbsp;°C en la calle, su voto <b>no se borra, pero pesa menos</b>. Votar «fresco» con el aire acondicionado puesto, en cambio, es perfectamente coherente — por eso preguntamos el contexto: dónde estás, qué viento hace, si te da el sol. Una zona no muestra resultado hasta reunir al menos <b>5 votos en 24 horas</b>, el agregado es una mediana ponderada (un voto disparatado no mueve el resultado) y cada dispositivo puede votar una vez por hora.</p>
  <p>¿Por qué medir la sensación si ya hay termómetros? Porque el termómetro no suda: 22&nbsp;°C secos en el interior se duermen bien y 22&nbsp;°C con el 85&nbsp;% de humedad en la costa son <a href="__SITE__/ranking-noches-tropicales/">una noche en vela</a>. Y porque el mismo termómetro con brisa o en calma total cuenta dos noches distintas. La diferencia entre <b>lo que se mide y lo que se siente</b> es exactamente lo que este proyecto quiere contar.</p>

  <h2>Sigue explorando</h2>
  <p>Si el estudio te ha picado la curiosidad: mira <a href="__SITE__/ranking-noches-tropicales/">dónde se duerme mejor y peor de toda España</a>, sigue <a href="__SITE__/ola-de-calor/">la ola de calor de hoy en el mapa de AEMET</a>, apunta <a href="__SITE__/dormir-con-manta-en-verano/">los pueblos donde se duerme con manta en pleno agosto</a>, localiza <a href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/">tu refugio climático natural más cercano</a> o entiende <a href="__SITE__/microclimas/">por qué un valle puede ser más fresco que la cima de al lado</a>. Y cada mañana, <a href="__SITE__/parte/">el parte de la noche</a> cuenta quién durmió fresco.</p>
</div></div></section>

<section><div class="wrap">
  <div class="kick">Preguntas frecuentes</div>
  <div class="faq">
    <div class="faqitem"><h3>¿Guardáis mi ubicación?</h3><p>No. Antes de enviar nada, tu navegador redondea las coordenadas a una celda de ~1&nbsp;km (suficiente para dibujar el mapa fino del calor urbano, insuficiente para saber dónde vives) y calcula la estación de AEMET de referencia. Solo viajan la celda y la zona. Sin cuentas, sin cookies de rastreo, sin IP.</p></div>
    <div class="faqitem"><h3>¿Qué es cada nivel de la escala?</h3><p>Una escala simétrica de 9 puntos, del frío helador al calor insoportable, basada en la escala clásica de confort térmico y escrita en el lenguaje en que se cuenta de verdad. El bochorno se pregunta aparte porque la humedad es otra cosa: no es más calor, es sudor que no evapora.</p></div>
    <div class="faqitem"><h3>¿Qué es el turismo climático?</h3><p>Elegir destino por cómo se va a sentir el cuerpo: pueblos donde se duerme con manta en agosto, costas templadas en enero. Este estudio quiere construir el primer calendario del confort real de las poblaciones españolas, votado por quienes están allí y contrastado con AEMET.</p></div>
    <div class="faqitem"><h3>¿Y si la gente miente?</h3><p>Es el mismo principio que los avisos de tráfico de Google Maps: informes de personas que se verifican entre sí. Cada voto se contrasta además con el dato oficial de AEMET de la zona y con su contexto (interior, exterior, viento, aire acondicionado…). Los incoherentes pesan menos, los dispositivos sistemáticamente incoherentes pierden peso, y ninguna zona publica resultado con menos de 5 votos.</p></div>
    <div class="faqitem"><h3>¿Para qué servirán los datos?</h3><p>Para el mapa del desacuerdo: dónde la gente sufre más de lo que marca el termómetro (costa húmeda, islas de calor urbanas). Se publicarán agregados y anónimos, como todo en este proyecto.</p></div>
  </div>
</div></section>

__FOOTER__

<script>
var EST=__EST__;
var URL_API="__CONFORT_URL__";
var sel={zona:null,celda:null,nivel:null,agusto:null,boch:null,viento:null,lugar:null,clima:null,cielo:null,entorno:null,origen:null};
var t0=Date.now();

function uid(){
 try{
  var u=localStorage.getItem("cf_uid");
  if(!u){u=Math.random().toString(36).slice(2)+Date.now().toString(36);localStorage.setItem("cf_uid",u);}
  return u;
 }catch(e){return "anon";}
}
function puedeVotar(){
 try{var t=+localStorage.getItem("cf_last")||0;return Date.now()-t>3600e3;}catch(e){return true;}
}
function marcaVoto(){try{localStorage.setItem("cf_last",""+Date.now());}catch(e){}}

function fijaZona(e,celda){
 sel.zona=e;
 sel.celda=celda||null; // celda ~1 km del punto del check; sin GPS no hay celda
 try{localStorage.setItem("cf_zona",e[0]);}catch(er){} // recordada para la próxima visita
 // Zona fijada: el formulario de posición desaparece (molesta una vez
 // localizado) y queda la zona con un enlace para cambiarla.
 document.getElementById("geoform").style.display="none";
 var z=document.getElementById("zona");
 z.style.display="block";
 z.innerHTML="📍 Tu zona: <b>"+e[3]+"</b> ("+e[4]+")"
  +(e[5]!==null?" · anoche la mínima oficial fue <b>"+String(e[5]).replace(".",",")+" °C</b>":"")
  +' · <a href="#" id="zcambiar">cambiar</a>';
 document.getElementById("zcambiar").addEventListener("click",function(ev){
  ev.preventDefault();
  document.getElementById("geoform").style.display="block";
  z.style.display="none";
 });
 valida();
}
function cerca(la,lo){
 var mejor=null,md=1e9;
 for(var i=0;i<EST.length;i++){
  var e=EST[i],dla=(e[1]-la),dlo=(e[2]-lo)*Math.cos(la*Math.PI/180),d=dla*dla+dlo*dlo;
  if(d<md){md=d;mejor=e;}
 }
 return mejor;
}
document.getElementById("geo").addEventListener("click",function(){
 var b=this,h=document.getElementById("geohint");
 if(!navigator.geolocation){h.textContent="Tu navegador no da la ubicación. Elige tu zona a mano:";return;}
 b.disabled=true;b.textContent="Buscando…";
 navigator.geolocation.getCurrentPosition(function(p){
  b.disabled=false;b.textContent="📍 Usar mi zona";
  var la=p.coords.latitude,lo=p.coords.longitude;
  // Redondeo EN el navegador a 2 decimales (~1 km): el punto exacto no viaja.
  fijaZona(cerca(la,lo),la.toFixed(2)+","+lo.toFixed(2));
 },function(){
  b.disabled=false;b.textContent="📍 Usar mi zona";
  h.textContent="No se pudo (¿permiso denegado?). Elige tu zona a mano:";
 },{timeout:9000});
});
var prov=document.getElementById("prov"),est=document.getElementById("est"),PR={};
EST.forEach(function(e){(PR[e[4]]=PR[e[4]]||[]).push(e);});
Object.keys(PR).sort(function(a,b){return a.localeCompare(b,"es");}).forEach(function(p){
 var o=document.createElement("option");o.value=p;o.textContent=p;prov.appendChild(o);
});
prov.addEventListener("change",function(){
 est.innerHTML='<option value="">…y tu zona</option>';
 (PR[prov.value]||[]).forEach(function(e,i){
  var o=document.createElement("option");o.value=i;o.textContent=e[3];est.appendChild(o);
 });
});
est.addEventListener("change",function(){
 if(est.value!=="")fijaZona(PR[prov.value][+est.value]);
});
// Visita recurrente: si ya nos dio su zona otro día, el paso 1 viene hecho
// (queda el enlace "cambiar" por si se ha movido).
try{
 var zg=localStorage.getItem("cf_zona");
 if(zg){for(var zi=0;zi<EST.length;zi++)if(EST[zi][0]===zg){fijaZona(EST[zi]);break;}}
}catch(e){}

// Racha de días seguidos participando (solo con votos guardados de verdad).
function racha(){
 try{
  var d0=new Date().toISOString().slice(0,10);
  var prev=localStorage.getItem("cf_dia")||"";
  var n=+localStorage.getItem("cf_racha")||0;
  if(prev!==d0){
   var ayer=new Date(Date.now()-864e5).toISOString().slice(0,10);
   n=(prev===ayer)?n+1:1;
   localStorage.setItem("cf_dia",d0);localStorage.setItem("cf_racha",""+n);
  }
  return n||1;
 }catch(e){return 0;}
}

document.getElementById("niveles").addEventListener("click",function(ev){
 var b=ev.target.closest(".nvl");if(!b)return;
 document.querySelectorAll(".nvl").forEach(function(x){x.classList.remove("sel");});
 b.classList.add("sel");sel.nivel=+b.getAttribute("data-v");valida();avanzar();
});
function chips(id,campo,cb){
 document.getElementById(id).addEventListener("click",function(ev){
  var b=ev.target.closest(".chip");if(!b)return;
  this.querySelectorAll(".chip").forEach(function(x){x.classList.remove("sel");});
  b.classList.add("sel");sel[campo]=b.getAttribute("data-v");if(cb)cb();
 });
}
chips("agusto","agusto",avanzar);
chips("origen","origen",avanzar);
chips("boch","boch",avanzar);
chips("viento","viento",avanzar);
chips("entorno","entorno",avanzar);
chips("cielochips","cielo",avanzar);
var INTERIOR={casa:1,oficina:1,fabrica:1,colegio:1};
chips("lugar","lugar",function(){
 if(!INTERIOR[sel.lugar])sel.clima=null; // fuera no se pregunta la climatización
 avanzar();                              // el paso "clima" se salta solo si no es interior
});
chips("climachips","clima",avanzar);

function valida(){
 document.getElementById("wcont").disabled=!sel.zona;
 document.getElementById("enviar").disabled=!(sel.zona&&sel.nivel);
}

// --- Máquina del asistente: una pregunta por pantalla ---------------------
var ORDEN=["zona","nivel","agusto","boch","viento","cielo","lugar","clima","entorno","origen","enviar"];
var pasoAct="zona";
function visiblePaso(s){return s==="clima"?!!INTERIOR[sel.lugar]:true;}
function pasosVis(){return ORDEN.filter(visiblePaso);}
function resumen(){
 var ETQ=["","Helador","Frío","Fresco","Muy a gusto","Cómodo","Templado","Caluroso","Mucho calor","Insoportable"];
 var AG=["","fatal","incómodo","ni fu ni fa","bien","de maravilla"];
 var t="Votas «<b>"+(ETQ[sel.nivel]||"—")+"</b>»"+(sel.zona?" desde <b>"+sel.zona[3]+"</b>":"")+".";
 if(sel.agusto)t+=" Aquí se está <b>"+AG[+sel.agusto]+"</b>.";
 var extra=[sel.boch!==null,sel.viento,sel.cielo,sel.lugar,sel.clima,sel.entorno,sel.origen].filter(Boolean).length;
 t+=extra?" Con "+extra+" dato"+(extra>1?"s":"")+" de contexto para afinar el mapa.":" Sin más contexto: rápido y anónimo.";
 document.getElementById("resumen").innerHTML=t;
}
function irPaso(s){
 pasoAct=s;
 ORDEN.forEach(function(x){var el=document.getElementById("s-"+x);if(el)el.classList.toggle("on",x===s);});
 var vis=pasosVis(),i=vis.indexOf(s);
 document.getElementById("wfill").style.width=Math.round(100*i/(vis.length-1))+"%";
 var nav=document.getElementById("wnav"),opt=document.getElementById("s-"+s).classList.contains("opt");
 nav.style.display=(s==="zona")?"none":"flex"; // en "enviar" queda solo el Atrás
 document.getElementById("wback").style.visibility=(s==="nivel"||i<=0)?"hidden":"visible";
 document.getElementById("wskip").style.display=opt?"inline-block":"none";
 document.getElementById("wya").style.display=opt?"inline-block":"none";
 if(s==="enviar")resumen();
 try{document.getElementById("wstage").scrollIntoView({block:"nearest"});}catch(e){}
}
function avanzar(){setTimeout(function(){var vis=pasosVis(),i=vis.indexOf(pasoAct);irPaso(vis[Math.min(i+1,vis.length-1)]);},180);}
document.getElementById("wback").addEventListener("click",function(){var vis=pasosVis(),i=vis.indexOf(pasoAct);irPaso(vis[Math.max(i-1,0)]);});
document.getElementById("wskip").addEventListener("click",function(){var vis=pasosVis(),i=vis.indexOf(pasoAct);irPaso(vis[Math.min(i+1,vis.length-1)]);});
document.getElementById("wya").addEventListener("click",function(){irPaso("enviar");});
document.getElementById("wcont").addEventListener("click",function(){if(sel.zona)irPaso("nivel");});
// Arranque: si ya conocemos la zona de otra visita, empezamos por la pregunta.
irPaso(sel.zona?"nivel":"zona");
document.getElementById("enviar").addEventListener("click",function(){
 var st=document.getElementById("estado");
 if(document.getElementById("hp").value){return;}
 if(Date.now()-t0<3000){st.textContent="Un segundo… (comprobación anti-robots)";return;}
 if(!puedeVotar()){st.textContent="Ya has votado hace poco: se admite un voto por hora, para que cada noche cuente una vez.";return;}
 var p={z:sel.zona[0],g:sel.celda,s:sel.nivel,a:sel.agusto,dq:sel.origen,b:sel.boch,w:sel.viento,l:sel.lugar,c:sel.clima,o:sel.cielo,e:sel.entorno,u:uid(),v:1};
 var fin=function(guardado){
  marcaVoto();
  document.getElementById("wstage").style.display="none";
  var g=document.getElementById("gracias");g.style.display="block";
  try{g.scrollIntoView({behavior:"smooth",block:"start"});}catch(e){}
  if(!guardado)document.getElementById("demo").style.display="block";
  if(guardado){var nr=racha();if(nr>=2)document.getElementById("racha").textContent="🔥 Llevas "+nr+" días seguidos aportando al estudio.";}
  var z=sel.zona,r=document.getElementById("resultado"),partes=[];
  if(z[5]!==null&&z[5]!==undefined)partes.push("mínima <span class=\"num\">"+String(z[5]).replace(".",",")+" °C</span>");
  if(z[6]!==null&&z[6]!==undefined)partes.push("máxima <span class=\"num\">"+String(z[6]).replace(".",",")+" °C</span>");
  if(partes.length)
   r.innerHTML="Último dato oficial de tu zona: "+partes.join(" · ")+". Tu voto cuenta cómo se viven esos números.";
  var zi=document.getElementById("zinfo");
  zi.innerHTML="📍 <b>"+z[3]+"</b> ("+z[4]+"), a <span class=\"num\">"+String(z[7]).replace(/\B(?=(\d{3})+(?!\d))/g,".")+" m</span> de altitud · media de <span class=\"num\">"+String(z[8]).replace(".",",")+"</span> noches tropicales al año (2017–2026)."
   +"<br><a href=\"__SITE__/"+z[9]+"/\">Ver el mapa del calor nocturno de "+z[4]+" →</a>";
  var urlC="__SITE__/confortometro/";
  var txtC="Estoy participando en el Confortómetro, el estudio que mide cómo se siente el clima en España, zona a zona. Vota tú también: son 10 segundos y es anónimo.";
  document.getElementById("cb-wa").href="https://wa.me/?text="+encodeURIComponent(txtC+" "+urlC);
  document.getElementById("cb-x").href="https://twitter.com/intent/tweet?text="+encodeURIComponent(txtC)+"&url="+encodeURIComponent(urlC);
  var cp=document.getElementById("cb-copiar");
  if(cp&&navigator.clipboard)cp.addEventListener("click",function(){
   navigator.clipboard.writeText(urlC).then(function(){cp.textContent="Enlace copiado";setTimeout(function(){cp.textContent="Copiar enlace";},1600);});
  });
  var sh=document.getElementById("cb-share");
  if(sh&&navigator.share){sh.hidden=false;
   sh.addEventListener("click",function(){navigator.share({title:document.title,text:txtC,url:urlC}).catch(function(){});});}
  if(guardado&&URL_API){
   fetch(URL_API+"?zona="+encodeURIComponent(z[0])).then(function(x){return x.json();}).then(function(d){
    if(d&&d.n>=5){
     r.innerHTML+="<br>Ahora mismo en tu zona: <b>"+d.mediana_txt+"</b> (mediana de <span class=\"num\">"+d.n+"</span> votos en 24 h"+(d.pct_bochorno!==null?", "+d.pct_bochorno+" % con bochorno":"")+").";
     if(d.pct_agusto!==null&&d.pct_agusto!==undefined){
      var ag="<br>Y el <b>"+d.pct_agusto+" %</b> dice que aquí <b>se está a gusto</b>";
      if(d.pct_agusto_local!==null&&d.pct_agusto_local!==undefined&&d.pct_agusto_visita!==null&&d.pct_agusto_visita!==undefined)
       ag+=" — los de visita el "+d.pct_agusto_visita+" %, los de aquí el "+d.pct_agusto_local+" %";
      r.innerHTML+=ag+".";
     }
    }
    else if(d)
     r.innerHTML+="<br>Tu zona aún no llega a 5 votos en 24 h: en cuanto llegue, su resultado se publica abajo, en «El resultado, en directo».";
   }).catch(function(){});
   fetch(URL_API+"?global=1").then(function(x){return x.json();}).then(function(d){
    if(d&&d.ok)r.innerHTML+="<br>Tu voto es uno de los <span class=\"num\">"+d.n+"</span> de las últimas 24 horas en toda España.";
    pintaDirecto(d);
   }).catch(function(){});
  }
 };
 var this_btn=this;
 if(!URL_API){fin.call(this,false);return;}
 this_btn.disabled=true;st.textContent="Enviando…";
 fetch(URL_API,{method:"POST",body:JSON.stringify(p)})
  .then(function(x){return x.json();})
  .then(function(){fin.call(this_btn,true);})
  .catch(function(){this_btn.disabled=false;st.textContent="No se pudo enviar (¿sin conexión?). Prueba otra vez.";});
});

// "El resultado, en directo": el agregado nacional de las últimas 24 h — la
// recompensa visible desde el primer voto, sin esperar a que una zona junte 5.
var ETQ=["","Helador","Frío","Fresco","Muy a gusto","Cómodo","Templado","Caluroso","Mucho calor","Insoportable"];
var EMO=["","🧊","🥶","🧣","😌","🙂","😐","🥵","😫","🔥"];
function pintaDirecto(d){
 var b=document.getElementById("dirbox");
 if(!d||!d.ok||!d.n){
  b.innerHTML='<p class="hint">El estudio acaba de arrancar: aquí se verá, en directo, cómo se siente España según los votos de las últimas 24 horas. Los primeros votos — como el tuyo — son los que lo encienden.</p>';
  return;
 }
 var NOMB={};EST.forEach(function(e){NOMB[e[0]]=[e[3],e[4]];});
 var max=Math.max.apply(null,d.niveles)||1;
 var html='<p class="dirn">🔴 <b>'+d.n+'</b> votos en las últimas 24 horas en España</p><div class="bars">';
 for(var i=0;i<9;i++){
  html+='<div class="brow"><span class="blab">'+EMO[i+1]+' '+ETQ[i+1]+'</span>'
   +'<span class="btrack"><span class="bfill" style="width:'+Math.round(100*d.niveles[i]/max)+'%"></span></span>'
   +'<span class="bnum">'+d.niveles[i]+'</span></div>';
 }
 html+='</div>';
 if(d.zonas&&d.zonas.length){
  html+='<p class="dirn" style="margin-top:14px">Zonas con resultado (5 votos o más), de más calurosa a más fresca sentida:</p><ul class="dzl">';
  d.zonas.forEach(function(x){
   var nm=NOMB[x.z]||[x.z,""];
   html+='<li>'+EMO[Math.round(x.m)]+' <b>'+nm[0]+'</b>'+(nm[1]?' ('+nm[1]+')':'')+': '+ETQ[Math.round(x.m)]+' · '+x.n+' votos</li>';
  });
  html+='</ul>';
 }
 b.innerHTML=html;
}
(function(){
 var b=document.getElementById("dirbox");
 if(!URL_API){b.innerHTML='<p class="hint">Los resultados en directo aparecerán aquí en cuanto el buzón de votos esté desplegado.</p>';return;}
 fetch(URL_API+"?global=1").then(function(x){return x.json();}).then(pintaDirecto)
  .catch(function(){b.innerHTML='<p class="hint">No se pudieron cargar los resultados en directo. Prueba a recargar en un rato.</p>';});
})();
</script>
</body>
</html>
"""


def construir_pagina_confortometro(estaciones: list, site: str,
                                   tmin_rec: dict) -> str:
    # [id, lat, lon, nombre, provincia, tmin, tmax, altitud, nt/año, slug prov]
    def _fila(e):
        ult = tmin_rec.get(e["id"])
        return [e["id"], e["lat"], e["lon"], e["loc"], e["prov"],
                ult[1] if ult else None, ult[2] if ult else None,
                e["alt"], e["nt"], slug(e["prov"])]
    est_js = json.dumps([_fila(e) for e in estaciones],
                        ensure_ascii=False, separators=(",", ":"))
    def _niv_label(txt):
        # "Nombre: descripción" -> nombre destacado + descripción pequeña, para
        # una rejilla compacta de 2 columnas que quepa entera en el móvil.
        if ": " in txt:
            w, d = txt.split(": ", 1)
            return f'<b>{w}</b><span class="d">{d}</span>'
        return f'<b>{txt}</b>'
    niveles = "".join(
        f'<button class="nvl" type="button" data-v="{v}">'
        f'<span class="em">{em}</span><span class="nl">{_niv_label(txt)}</span></button>'
        for v, em, txt in NIVELES_CONFORT)
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "El confortómetro",
             "item": site + "/confortometro/"}]},
        {"@type": "WebApplication",
         "name": "El Confortómetro: estudio participativo del clima que se siente en España",
         "url": site + "/confortometro/",
         "applicationCategory": "ReferenceApplication",
         "operatingSystem": "Web",
         "browserRequirements": "Requires JavaScript",
         "description": ("Estudio de investigación participativa sobre confort climático y "
                          "turismo climático: votos anónimos de sensación térmica (día y "
                          "noche, verano e invierno) contrastados con los datos oficiales "
                          "de AEMET de cada zona."),
         "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"}},
    ]}, ensure_ascii=False)
    return (PAGINA_CONFORTOMETRO
            .replace("__NAVCSS__", CSS_NAV_ESCUETO)
            .replace("__FOOTERCSS__", CSS_FOOTER_ESCUETO)
            .replace("__NAV__", nav_escueto_html(site))
            .replace("__FOOTER__", footer_escueto_html(site))
            .replace("__SCHEMA__", schema)
            .replace("__NIVELES__", niveles)
            .replace("__EST__", est_js)
            .replace("__CONFORT_URL__", APPS_SCRIPT_CONFORT_URL)
            .replace("__SITE__", site)
            .replace("__HOME__", site + "/"))


# ===========================================================================
# Estudio "La España que nunca se colorea": superposición de los mapas de AEMET
# (scripts/estudio_colores.py). Landing data-driven: lee las cifras del JSON
# que genera ese script. Si no existe, la página no se construye.
# ===========================================================================
PAGINA_ESTUDIO = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
<link rel="canonical" href="__SITE__/la-espana-que-nunca-se-colorea/">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="article">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:url" content="__SITE__/la-espana-que-nunca-se-colorea/">
<meta property="og:image" content="__SITE__/estudios/refugios-nocturnos.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/estudios/refugios-nocturnos.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&display=swap" rel="stylesheet">
<style>
 :root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--fd:"Fraunces",Georgia,serif;--fb:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
 *{margin:0;padding:0;box-sizing:border-box}
 body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.7;-webkit-font-smoothing:antialiased}
 .wrap{max-width:min(92vw,760px);margin:0 auto;padding:0 22px}
 a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}
 header.h{padding:46px 0 10px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}
 .crumb{font-size:13px;color:var(--muted)}
 .kick{font:600 12px/1 var(--fb);letter-spacing:.16em;text-transform:uppercase;color:var(--teja);margin:18px 0 8px}
 h1{font-family:var(--fd);font-weight:900;font-size:clamp(30px,6vw,48px);line-height:1.04;letter-spacing:-.01em}
 h1 em{font-style:italic;color:var(--teja2)}
 .intro{color:var(--muted);font-size:clamp(15px,2.4vw,17.5px);margin:18px 0 0}
 .intro b{color:var(--paper)}
 section{padding:22px 0}
 h2{font-family:var(--fd);font-weight:700;font-size:clamp(21px,3.6vw,27px);margin:0 0 12px;line-height:1.15}
 p{font-size:clamp(15px,2.2vw,16.5px);color:var(--muted);margin:0 0 14px}p b{color:var(--paper)}
 figure{margin:8px 0 6px;background:var(--bg2);border:1px solid var(--line);border-radius:16px;padding:12px;overflow:hidden}
 figure img{width:100%;height:auto;display:block;border-radius:9px}
 figcaption{font-size:13.5px;color:var(--muted);margin-top:10px;padding:0 4px}
 .leg{display:flex;flex-wrap:wrap;gap:7px 18px;margin:12px 4px 2px;font-size:13px;color:var(--muted)}
 .leg .it{display:inline-flex;align-items:center;gap:7px}
 .leg .sw{width:14px;height:14px;border-radius:3px;flex:none;border:1px solid rgba(255,255,255,.14)}
 .esc-t{font-size:12.5px;color:var(--muted);margin:12px 4px 6px}
 .esc{display:flex;flex-wrap:wrap;gap:3px;margin:0 4px 2px}
 .esc .st{width:54px;text-align:center;font-size:11.5px;color:var(--muted)}
 .esc .st .b{display:block;height:16px;border-radius:3px;margin-bottom:3px}
 .dato{display:flex;gap:14px;flex-wrap:wrap;margin:6px 0 18px}
 .dcard{flex:1;min-width:150px;background:var(--bg2);border:1px solid var(--line);border-radius:13px;padding:14px 16px}
 .dcard .n{font-family:var(--fd);font-weight:900;font-size:30px;color:var(--teja2);line-height:1}
 .dcard .l{font-size:13px;color:var(--muted);margin-top:6px}
 .metodo{background:var(--bg2);border-left:3px solid var(--teja);border-radius:0 12px 12px 0;padding:16px 18px;font-size:14px;color:var(--muted)}
 .metodo b{color:var(--paper)}
 .sigue{border-top:1px solid var(--line);margin-top:28px;padding-top:22px}
 .navcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:12px;margin-top:4px}
 .navcard{display:block;background:var(--bg2);border:1px solid var(--line);border-radius:13px;padding:15px 16px;text-decoration:none}
 .navcard:hover{border-color:var(--teja);background:var(--panel);text-decoration:none}
 .navcard .ic{font-size:22px;display:block;margin-bottom:7px}
 .navcard b{display:block;color:var(--paper);font-family:var(--fd);font-weight:600;font-size:15.5px;margin-bottom:3px}
 .navcard span{display:block;color:var(--muted);font-size:13px;line-height:1.45}
 __NAVCSS__
 __FOOTERCSS__
</style>
</head>
<body>
__NAV__
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">Refugio Climático</a> · La España que nunca se colorea</nav>
  <div class="kick">Estudio · Refugios climáticos · Datos AEMET</div>
  <h1>La España que <em>nunca se colorea</em></h1>
  <p class="intro">Hemos superpuesto <b>__N__ mapas diarios de AEMET</b> de este verano, píxel a píxel, para responder a una pregunta simple: <b>¿qué parte de España nunca cruza la línea del calor?</b> El resultado dibuja, en negativo, los <b>refugios climáticos reales</b> de la península — y desmonta un espejismo.</p>
</div></header>

<section><div class="wrap">
  <h2>De noche: el mapa del sueño</h2>
  <p>Una <b>noche tropical</b> es aquella en que la mínima no baja de 20&nbsp;°C. Pero el termómetro engaña: una mínima <i>puntual</i> de 19,5&nbsp;°C al amanecer, tras una noche infernal, es un <b>falso alivio</b>. Por eso distinguimos tres Españas: la que <b>baja de 18&nbsp;°C cada noche</b> (frescor real, sueño garantizado), la que nunca es tropical pero <b>roza los 18-20</b> (el espejismo), y la que <b>alguna noche cruza los 20</b>.</p>
  <div class="dato">
    <div class="dcard"><div class="n">__PROFUNDO__ %</div><div class="l">baja de 18° cada noche · refugio profundo</div></div>
    <div class="dcard"><div class="n">__MARGEN__ %</div><div class="l">nunca tropical, pero roza los 20° · falso alivio</div></div>
    <div class="dcard"><div class="n">__TROPICAL__ %</div><div class="l">alguna noche tropical</div></div>
  </div>
  <figure>
    <a href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/" aria-label="Encuentra el refugio climático natural más cercano a ti"><img src="__SITE__/estudios/refugios-nocturnos.png" alt="Mapa de España con los refugios climáticos nocturnos: las zonas donde la temperatura mínima nunca cruza los 20 grados, superponiendo los mapas de mínimas de AEMET de todo el verano" loading="lazy"></a>
    <figcaption>En teal, los refugios profundos (montaña interior). En ámbar, el falso alivio que rodea las cumbres. En rojo, la España tropical. Fuente: mapas de mínimas de AEMET, __INI__ – __FIN__.</figcaption>
    <div class="leg" aria-label="Leyenda del mapa">
      <span class="it"><span class="sw" style="background:#a9c6d4"></span>Baja de 18° cada noche · refugio profundo (__PROFUNDO__ %)</span>
      <span class="it"><span class="sw" style="background:#c9a24a"></span>Nunca tropical, pero roza los 20° · falso alivio (__MARGEN__ %)</span>
      <span class="it"><span class="sw" style="background:#c94a2e"></span>Alguna noche tropical, ≥20° (__TROPICAL__ %)</span>
    </div>
  </figure>
  <p>Los refugios profundos son <b>montaña interior seca</b>: la Cordillera Cantábrica, el Sistema Central, el Ibérico, el Pirineo. Y fíjate en el <b>halo ámbar</b> que los rodea: al bajar de la sierra hacia el valle, primero se cruza esa franja dudosa. Por eso, para valorar un pueblo, <a href="__SITE__/">no vale la media — hay que mirar su peor noche</a>.</p>
</div></section>

<section><div class="wrap">
  <h2>De día: la España que no se colorea de rojo</h2>
  <p>¿Y de día? Aquí no hay refugio para casi nadie: en verano <b>España arde de sol a sol</b>. Si pintamos cada zona con <b>su día más caliente</b> de todo el periodo, el <b>__ENROJECE__&nbsp;%</b> del territorio llega al rojo (32&nbsp;°C) alguna jornada. Solo un __NUNCA_ROJO__&nbsp;% —las cumbres— <b>no se colorea de rojo jamás</b>.</p>
  <figure>
    <a href="__SITE__/ola-de-calor/" aria-label="Ver el mapa de la ola de calor en directo"><img src="__SITE__/estudios/techo-del-calor.png" alt="Mapa de España pintado con la temperatura máxima más alta de cada zona en el verano: casi todo el país enrojece por encima de 32 grados y solo las cumbres se quedan en amarillo, según las máximas de AEMET" loading="lazy"></a>
    <figcaption>Cada punto, con la máxima más alta que alcanzó en todo el periodo. Casi toda España enrojece; solo las cumbres (en amarillo/naranja) resisten. Fuente: mapas de máximas de AEMET, __INI__ – __FIN__.</figcaption>
    <div class="esc-t">Escala de la máxima alcanzada (°C) · el amarillo son las cumbres, el magenta el horno:</div>
    <div class="esc" aria-label="Escala de temperatura máxima">
      <span class="st"><span class="b" style="background:#ffff00"></span>22°</span>
      <span class="st"><span class="b" style="background:#ffbf00"></span>26°</span>
      <span class="st"><span class="b" style="background:#ff7f00"></span>30°</span>
      <span class="st"><span class="b" style="background:#ff0000"></span>32°</span>
      <span class="st"><span class="b" style="background:#ff33b2"></span>36°</span>
      <span class="st"><span class="b" style="background:#d03471"></span>40°</span>
    </div>
  </figure>
  <p>Solo un puñado de <b>cumbres</b> aguanta fresco también a mediodía. Este otro mapa cuenta, punto por punto, cuántos días la máxima se quedó por debajo de __UMBRAL__&nbsp;°C:</p>
  <figure>
    <a href="__SITE__/ola-de-calor/" aria-label="Ver el mapa de la ola de calor en directo"><img src="__SITE__/estudios/frescor-dia.png" alt="Mapa de España del frescor de día: las cumbres donde la temperatura máxima se mantiene baja incluso a mediodía en verano, según las máximas de AEMET" loading="lazy"></a>
    <figcaption>Cuanto más claro, más a menudo hace fresco a mediodía. Brillan Sierra Nevada, el Pirineo, la Cantábrica y, muy cerca, la sierra de Gúdar. Casi todo lo demás está oscuro. Fuente: mapas de máximas de AEMET, __INI__ – __FIN__.</figcaption>
    <div class="leg" aria-label="Leyenda del mapa">
      <span class="it"><span class="sw" style="background:#78c8d6"></span>Cumbres que resisten: Sierra Nevada, Pirineo, Cantábrica, Gúdar</span>
      <span class="it"><span class="sw" style="background:#463e30"></span>De día también aprieta</span>
    </div>
  </figure>
  <p>Sierra Nevada resplandece: tan alta que refresca de día hasta en Andalucía. Y hay sierras que se quedan <b>a un pelo</b> — la <b>sierra de Gúdar</b>, en Teruel, no alcanza ese nivel de brillo pero anda cerquísima. Es exactamente por eso que <a href="__SITE__/">Alcalá de la Selva</a> y La Virgen de la Vega son refugios climáticos naturales de manual: si el día ya perdona algo y <b>la noche siempre refresca</b>, tienes el combo completo.</p>
</div></section>

<section><div class="wrap">
  <h2>El refugio total está donde coinciden los dos mapas</h2>
  <p>De noche hay refugio para bastantes; de día, casi solo para las cumbres. <b>Donde se solapan</b> — Pirineo, Cantábrica, las sierras altas de Teruel y Gúdar, el techo del Sistema Central — está el <b>refugio total</b>: fresco al mediodía y fresco de madrugada. Son los pueblos donde en agosto se cena con chaqueta y se duerme con manta.</p>
  <p class="metodo"><b>Cómo está hecho.</b> Superponemos los mapas diarios de AEMET (__N__ jornadas de este verano) y, con su propia escala de color, clasificamos cada píxel por su banda de temperatura. Es una <b>ventana</b>: el titular «nunca» se refiere al periodo observado (__INI__ – __FIN__); a medida que avanza el verano la mancha crece y el refugio se ajusta. Iremos publicando los estudios de veranos anteriores y posteriores. Todo es regenerable con <code>scripts/estudio_colores.py</code> sobre datos de AEMET.</p>
  <div class="sigue">
    <h2>Sigue explorando</h2>
    <div class="navcards">
      <a class="navcard" href="__SITE__/"><span class="ic">🏡</span><b>Tu pueblo</b><span>¿Cuántas noches tropicales tiene? Búscalo en la calculadora.</span></a>
      <a class="navcard" href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/"><span class="ic">📍</span><b>Refugios cerca de ti</b><span>El refugio climático natural más cercano, con la ruta.</span></a>
      <a class="navcard" href="__SITE__/ranking-noches-tropicales/"><span class="ic">🏆</span><b>Ranking nacional</b><span>Dónde se duerme mejor y peor de toda España.</span></a>
      <a class="navcard" href="__SITE__/ola-de-calor/"><span class="ic">🔥</span><b>Mapa de la ola de calor</b><span>Máximas y mínimas de AEMET, día a día.</span></a>
      <a class="navcard" href="__SITE__/dormir-con-manta-en-verano/"><span class="ic">🛌</span><b>Dormir con manta en agosto</b><span>Los destinos frescos, provincia a provincia.</span></a>
      <a class="navcard" href="__SITE__/hoteles-refugio-climatico/"><span class="ic">🏨</span><b>Hoteles refugio</b><span>25 hoteles donde dormir en estas zonas frescas.</span></a>
      <a class="navcard" href="__SITE__/microclimas/"><span class="ic">🌿</span><b>Microclimas</b><span>Por qué un valle es más fresco que la cima de al lado.</span></a>
    </div>
  </div>
</div></section>

__FOOTER__
</body>
</html>
"""


def construir_pagina_estudio(site: str, datos: dict) -> str:
    per = datos["periodo"]; noc = datos["nocturno"]; dia = datos["dia"]
    ini = fecha_es(date.fromisoformat(per["ini"]))
    fin = fecha_es(date.fromisoformat(per["fin"]))
    n = per["noches"]
    title = "La España que nunca se colorea: el mapa de los refugios climáticos"
    desc = (f"Superponemos {n} mapas de AEMET: solo el {noc['profundo']:.0f} % de España baja "
            f"de 18° cada noche y apenas un puñado de cumbres resiste el calor de día. El mapa "
            f"honesto de los refugios climáticos reales, de noche y de día.")
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "La España que nunca se colorea",
             "item": site + "/la-espana-que-nunca-se-colorea/"}]},
        {"@type": "Article", "headline": title, "description": desc,
         "image": site + "/estudios/refugios-nocturnos.png",
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "publisher": {"@type": "Organization", "name": "nochetropical.es"},
         "isBasedOn": "https://opendata.aemet.es"}],
    }, ensure_ascii=False)
    return (PAGINA_ESTUDIO
            .replace("__NAVCSS__", CSS_NAV_ESCUETO)
            .replace("__FOOTERCSS__", CSS_FOOTER_ESCUETO)
            .replace("__NAV__", nav_escueto_html(site))
            .replace("__FOOTER__", footer_escueto_html(site))
            .replace("__SCHEMA__", schema)
            .replace("__TITLE__", title)
            .replace("__DESC__", desc)
            .replace("__PROFUNDO__", f"{noc['profundo']:.0f}")
            .replace("__MARGEN__", f"{noc['margen']:.0f}")
            .replace("__TROPICAL__", f"{noc['tropical']:.0f}")
            .replace("__ENROJECE__", f"{dia.get('enrojece', 98):.0f}")
            .replace("__NUNCA_ROJO__", f"{dia.get('nunca_rojo', 2):.0f}")
            .replace("__UMBRAL__", f"{dia['umbral']:.0f}")
            .replace("__N__", str(n))
            .replace("__INI__", ini)
            .replace("__FIN__", fin)
            .replace("__SITE__", site)
            .replace("__HOME__", site + "/"))


# ===========================================================================
# Página SEO "dormir con manta en verano": la búsqueda clásica del calor
# ("pueblos de España donde dormir con manta", "destinos frescos para agosto",
# "hoteles rurales frescos") respondida con datos: los refugios medidos por
# AEMET, uno por provincia para que sirva de mapa de destinos. Es además la
# página pilar del concepto "turismo climático".
# ===========================================================================
PAGINA_MANTA = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pueblos de España donde dormir con manta en verano: destinos frescos</title>
<meta name="description" content="__DESC__">
<link rel="canonical" href="__SITE__/dormir-con-manta-en-verano/">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="article">
<meta property="og:title" content="Pueblos de España donde dormir con manta en verano: destinos frescos">
<meta property="og:description" content="__DESC__">
<meta property="og:url" content="__SITE__/dormir-con-manta-en-verano/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&family=JetBrains+Mono:wght@700&display=swap" rel="stylesheet">
<style>
 :root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--verde:#8fb07a;--fd:"Fraunces",Georgia,serif;--fb:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--fm:"JetBrains Mono",monospace}
 *{margin:0;padding:0;box-sizing:border-box}
 body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.6;-webkit-font-smoothing:antialiased}
 .wrap{max-width:min(92vw,860px);margin:0 auto;padding:0 22px}
 a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}
 header.h{padding:46px 0 12px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}
 .crumb{font-size:13px;color:var(--muted)}
 .kick{font:600 12px/1 var(--fb);letter-spacing:.16em;text-transform:uppercase;color:var(--teja);margin:18px 0 8px}
 h1{font-family:var(--fd);font-weight:900;font-size:clamp(30px,6vw,46px);line-height:1.05;letter-spacing:-.01em}
 h1 em{font-style:italic;color:var(--teja2)}
 .intro{color:var(--muted);font-size:clamp(15px,2.4vw,17.5px);margin:18px 0 0;max-width:680px}
 .intro b{color:var(--paper)}
 section{padding:28px 0}
 table{width:100%;border-collapse:collapse;font-size:15px}
 th,td{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line)}
 th{font:600 11px/1 var(--fb);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
 th.r,td.n{text-align:right}
 td.n{font-family:var(--fm);font-weight:700;color:var(--verde)}
 td.loc{font-weight:600}
 caption{caption-side:top;text-align:left;font-size:13px;color:var(--muted);margin-bottom:10px;font-weight:600}
 .note{font-size:12.5px;color:var(--muted);margin-top:12px}
 .prose{margin:10px 0;max-width:720px}
 .prose h2{font-family:var(--fd);font-weight:700;font-size:clamp(20px,3.6vw,25px);margin:28px 0 10px}
 .prose p{color:var(--muted);font-size:15px;margin:0 0 14px}
 .prose p b{color:var(--paper)}
 .faq{margin-top:6px;max-width:720px}
 .faqitem{padding:15px 0;border-bottom:1px solid var(--line)}
 .faqitem h3{font-family:var(--fd);font-weight:600;font-size:16.5px;margin-bottom:6px}
 .faqitem p{color:var(--muted);font-size:14.5px}
 .cta{margin:26px 0;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:22px;text-align:center}
 .cta b{font-family:var(--fd);font-weight:600;font-size:19px}
 .botones{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin-top:14px}
 .btn{display:inline-block;padding:12px 18px;border-radius:11px;font-weight:700;font-size:14.5px}
 .btn.pri{background:var(--teja);color:#1a1209}.btn.pri:hover{background:var(--teja2);text-decoration:none}
 .btn.sec{background:transparent;border:1px solid var(--teja);color:var(--teja2)}.btn.sec:hover{background:rgba(217,116,78,.12);text-decoration:none}
 .twrap{overflow-x:auto}
 __NAVCSS__
 __FOOTERCSS__
 @media(max-width:520px){th.hide,td.hide{display:none}table{font-size:13.5px}th,td{padding:9px 8px}}
 @media(min-width:980px){
  .wrap{max-width:min(94vw,1150px)}
  .dcols{display:grid;grid-template-columns:1.05fr .95fr;gap:0 52px;align-items:start}
  .prose{max-width:none}
  .prose h2:first-child{margin-top:0}
  .faq{max-width:none;display:grid;grid-template-columns:1fr 1fr;gap:0 52px}
 }
</style>
</head>
<body>
__NAV__
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">Refugio Climático</a> · Dormir con manta en verano</nav>
  <div class="kick">Turismo climático · Datos AEMET 2017–2026</div>
  <h1>Dormir con manta en agosto: los pueblos más <em>frescos</em> de España</h1>
  <p class="intro">Buscar «pueblos donde dormir con manta en verano» es un clásico por una razón: <b>el mejor aire acondicionado es un clima que no lo necesita</b>. Esta lista no es de oídas — son estaciones de AEMET donde la noche baja de 20&nbsp;°C prácticamente <b>todo el verano</b>, medida a medida, una por provincia. Tu próximo destino fresco para agosto está aquí.</p>
</div></header>

<section><div class="wrap"><div class="dcols">
  <div>
  <div class="twrap"><table>
    <caption>Un destino fresco por provincia, ordenados por altitud. Todos con menos de 1 noche tropical al año de media.</caption>
    <thead><tr><th>Pueblo / zona</th><th>Provincia</th><th class="hide r">Altitud</th><th class="r">Noches trop./año</th></tr></thead>
    <tbody>__TABLA__</tbody>
  </table></div>
  <p class="note">Una noche tropical es aquella en que la mínima no baja de 20&nbsp;°C. Media de los veranos 2017–2026. Fuente: AEMET OpenData. El dato es de la estación; el pueblo enlaza a su provincia con todas las estaciones.</p>
  </div>

  <div>
  <div class="prose">
    <h2>Por qué en estos pueblos se duerme con manta</h2>
    <p>Casi todos comparten receta: <b>altitud</b> (600–1.700 m), <b>interior</b> (lejos del mar, que de noche devuelve el calor acumulado) y <b>aire seco</b> de clima continental, que deja escapar el calor del día en cuanto se pone el sol. Es el mecanismo que explican <a href="__SITE__/microclimas/">los microclimas</a>: mientras la costa mediterránea encadena hasta 86 noches tropicales seguidas — compruébalo en <a href="__SITE__/ranking-noches-tropicales/">el ranking nacional</a> —, en estas sierras la manta es obligatoria hasta en pleno agosto.</p>
    <h2>Turismo climático: elegir destino por cómo se siente</h2>
    <p>Cada verano más gente organiza las vacaciones huyendo del calor: es el <b>turismo climático</b>. No va de monumentos, va de <b>cómo se va a sentir el cuerpo</b>: dormir sin ventilador, cenar con chaqueta fina, pasear a mediodía sin sufrir mientras <a href="__SITE__/ola-de-calor/">la ola de calor</a> asa el resto del mapa. Estos datos son su mapa — y <a href="__SITE__/confortometro/">el Confortómetro</a>, nuestro estudio participativo, le está poniendo la capa que faltaba: cómo se siente cada zona, votado por quienes están allí.</p>
    <p>¿Y si buscas <b>hoteles rurales frescos</b> — ese «hotel sin aire acondicionado pero fresco» que promete la búsqueda? Hemos seleccionado <b>25 hoteles</b> situados en estos refugios climáticos, con el dato de AEMET de cada zona (medimos el clima del entorno, no el interior del hotel: donde la noche refresca de verdad, se duerme fresco).</p>
    <p style="margin:6px 0 4px"><a class="btn pri" href="__SITE__/hoteles-refugio-climatico/">🏨 Los 25 hoteles donde se duerme con manta →</a></p>
    <p><a href="__SITE__/refugios-y-espana-vaciada/">Muchos de estos pueblos están en la España vaciada: el frío que los despobló es hoy su activo →</a></p>
  </div>

  <div class="cta">
    <b>¿Cuál te pilla más cerca?</b>
    <div class="botones">
      <a class="btn pri" href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/">📍 Refugios climáticos cerca de mí →</a>
      <a class="btn sec" href="__SITE__/confortometro/">🌡️ Vota en el Confortómetro →</a>
    </div>
  </div>
  </div>
</div></div></section>

<section><div class="wrap">
  <div class="kick">Preguntas frecuentes</div>
  <div class="faq">__FAQ__</div>
</div></section>

__FOOTER__
</body>
</html>
"""


def construir_pagina_manta(estaciones: list, site: str) -> str:
    # Un refugio (nt < 1) por provincia, el de mayor altitud; ordenados por
    # altitud descendente. Si una provincia no tiene refugio, no aparece.
    por_prov: dict[str, dict] = {}
    for e in estaciones:
        if e["nt"] >= 1:
            continue
        actual = por_prov.get(e["prov"])
        if actual is None or e["alt"] > actual["alt"]:
            por_prov[e["prov"]] = e
    destinos = sorted(por_prov.values(), key=lambda x: -x["alt"])
    filas = []
    for e in destinos:
        filas.append(
            f'<tr><td class="loc"><a href="{site}/{slug(e["prov"])}/">{e["loc"]}</a></td>'
            f'<td>{e["prov"]}</td><td class="hide n">{miles(e["alt"])} m</td>'
            f'<td class="n">&lt;1</td></tr>')
    top = destinos[0]
    desc = (f"{len(destinos)} pueblos medidos por AEMET donde se duerme con manta en pleno "
            f"agosto, de {top['loc']} ({miles(top['alt'])} m) para abajo: menos de 1 noche "
            f"tropical al año. El mapa de los destinos frescos de España.")
    faq = [
        ("¿Dónde se puede dormir con manta en verano en España?",
         f"En las sierras del interior, entre 600 y 1.700 m: {len(destinos)} zonas medidas "
         f"por AEMET no llegan a 1 noche tropical al año. Las más altas: "
         + ", ".join(f"{e['loc']} ({e['prov']})" for e in destinos[:3]) + "."),
        ("¿Cuáles son los destinos más frescos de España para agosto?",
         "Los pueblos de montaña del interior peninsular: sierras de Teruel y Cuenca, "
         "Pirineo de Huesca y Lleida, montaña cantábrica y leonesa, Sanabria, Gredos o "
         "el Moncayo. En la tabla hay un destino medido por provincia."),
        ("¿Cómo encuentro un hotel rural fresco, sin aire acondicionado?",
         "Busca el alojamiento por término municipal: si el pueblo no tiene noches "
         "tropicales, el hotel tampoco. Esta lista sale de las estaciones de AEMET, no "
         "de opiniones."),
        ("¿Qué es el turismo climático?",
         "Elegir destino por el confort térmico: dormir fresco en agosto, huir del "
         "bochorno. Con el cambio climático es una razón de viaje creciente, y estos "
         "datos —junto al Confortómetro, nuestro estudio participativo— son su mapa."),
    ]
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Dormir con manta en verano",
             "item": site + "/dormir-con-manta-en-verano/"}]},
        {"@type": "Article",
         "headline": "Pueblos de España donde dormir con manta en verano: destinos frescos",
         "description": desc,
         "image": site + "/og.png",
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "publisher": {"@type": "Organization", "name": "Refugio Climático",
                       "logo": {"@type": "ImageObject", "url": site + "/favicon.svg"}},
         "datePublished": "2026-07-18",
         "dateModified": date.today().isoformat(),
         "mainEntityOfPage": site + "/dormir-con-manta-en-verano/"},
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq]},
    ]}, ensure_ascii=False)
    return (PAGINA_MANTA
            .replace('<link rel="canonical" href="__SITE__/dormir-con-manta-en-verano/">',
                     '<link rel="canonical" href="__SITE__/dormir-con-manta-en-verano/">\n'
                     + hreflang_block("/dormir-con-manta-en-verano/", "/en/coolest-towns-spain/"))
            .replace("__NAVCSS__", CSS_NAV_ESCUETO)
            .replace("__FOOTERCSS__", CSS_FOOTER_ESCUETO)
            .replace("__NAV__", nav_escueto_html(site))
            .replace("__FOOTER__", footer_escueto_html(site))
            .replace("__SCHEMA__", schema)
            .replace("__DESC__", desc)
            .replace("__TABLA__", "".join(filas))
            .replace("__FAQ__", faq_html(faq))
            .replace("__SITE__", site)
            .replace("__HOME__", site + "/"))


PAGINA_AVISO_LEGAL = r"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Licencia, derechos de autor y aviso legal | nochetropical.es</title>
<meta name="description" content="Qué puedes reutilizar de nochetropical.es y cómo citarlo: los datos de noches tropicales están bajo licencia CC BY 4.0; la marca, el diseño y los textos están reservados. Fuente de los datos: AEMET.">
<link rel="canonical" href="__SITE__/aviso-legal/">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="website">
<meta property="og:title" content="Licencia, derechos de autor y aviso legal · nochetropical.es">
<meta property="og:description" content="Los datos, bajo CC BY 4.0 (reutilizables citando la fuente); la marca, el diseño y los textos, reservados.">
<meta property="og:url" content="__SITE__/aviso-legal/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900&family=Lora:ital,wght@0,400;0,600&display=swap" rel="stylesheet">
<style>
 :root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--verde:#8fb07a;--fd:"Fraunces",Georgia,serif;--fb:"Lora",Georgia,serif;--fm:ui-monospace,monospace}
 *{margin:0;padding:0;box-sizing:border-box}
 body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.65;-webkit-font-smoothing:antialiased}
 .wrap{max-width:760px;margin:0 auto;padding:0 24px}
 a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}
 header.h{padding:44px 0 12px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}
 .crumb{font-size:13px;color:var(--muted)}
 .kick{font:600 12px/1 var(--fb);letter-spacing:.16em;text-transform:uppercase;color:var(--teja);margin:16px 0 8px}
 h1{font-family:var(--fd);font-weight:900;font-size:clamp(28px,5.5vw,42px);line-height:1.05}
 .intro{color:var(--muted);font-size:clamp(15px,2.4vw,17px);margin:16px 0 0}
 section{padding:22px 0}
 h2{font-family:var(--fd);font-weight:600;font-size:clamp(19px,3.4vw,24px);margin:18px 0 10px}
 p{color:var(--muted);font-size:15.5px;margin:0 0 14px}p b{color:var(--paper)}
 ul{margin:0 0 14px 20px;color:var(--muted);font-size:15.5px}li{margin:6px 0}
 .lic{display:flex;flex-wrap:wrap;gap:12px;align-items:center;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:6px 0 14px}
 .lic .b{font-family:var(--fm);font-weight:700;color:var(--verde);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:13px;white-space:nowrap}
 .cita{font-family:var(--fm);font-size:13px;background:#0c0906;border:1px solid var(--line);border-radius:10px;padding:14px 16px;color:#e3d8c4;line-height:1.5;margin:6px 0 14px}
 .ok{color:var(--verde)}.no{color:var(--teja2)}
 __NAVCSS__
 __FOOTERCSS__
</style></head><body>
__NAV__
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">nochetropical.es</a> · Aviso legal y licencia</nav>
  <div class="kick">Licencia · Derechos de autor</div>
  <h1>Licencia, derechos de autor y aviso legal</h1>
  <p class="intro">Este proyecto nace para compartirse. Aquí explicamos, sin letra pequeña, <b>qué puedes reutilizar y cómo citarlo</b>, y qué está reservado. En resumen: los <b>datos</b> son libres citando la fuente; el <b>nombre, el diseño y los textos</b>, no.</p>
</div></header>

<section><div class="wrap">
  <h2>Titularidad</h2>
  <p><b>nochetropical.es</b> (también accesible desde el github.io original) es un proyecto de datos de <b>Ramón&nbsp;J.&nbsp;Lowesting</b>. Los datos meteorológicos de base proceden de <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a>, la Agencia Estatal de Meteorología, y se tratan aquí de forma reproducible a partir de fuentes públicas.</p>

  <h2>Los datos: libres con atribución (CC BY 4.0)</h2>
  <div class="lic">
    <span class="b">CC BY 4.0</span>
    <span style="color:var(--muted);font-size:14.5px">Los datos de noches tropicales por estación —conteos, medias, rankings y los CSV/Excel descargables— se publican bajo <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license" target="_blank">Creative Commons Reconocimiento 4.0</a>.</span>
  </div>
  <p>Eso significa que <span class="ok">puedes copiarlos, redistribuirlos, adaptarlos y usarlos —incluso con fines comerciales—</span> siempre que <b>cites la fuente</b> y enlaces a la licencia. Nos encanta que se reutilicen: es justo para lo que están.</p>
  <p><b>Cómo citar:</b></p>
  <div class="cita">Fuente: AEMET · nochetropical.es (Refugio Climático), datos bajo CC BY 4.0.<br>https://nochetropical.es</div>

  <h2>Lo que está reservado</h2>
  <p>La licencia CC BY 4.0 cubre <b>los datos</b>, no todo lo demás. Se reservan todos los derechos sobre:</p>
  <ul>
    <li>El <b>nombre y la marca</b> «nochetropical.es» / «Refugio Climático» y el logotipo.</li>
    <li>El <b>diseño</b>, la interfaz, la identidad visual y el <b>código</b> del sitio.</li>
    <li>Los <b>textos editoriales</b> (reportajes, artículos, análisis redactados) y las imágenes originales.</li>
  </ul>
  <p>En corto: <span class="ok">reutiliza los números citándonos</span>; <span class="no">no clones el sitio, no copies los textos ni te hagas pasar por nochetropical.es</span>.</p>

  <h2>Usos que no autorizamos</h2>
  <ul>
    <li>Reproducir el sitio o sus textos <b>de forma sustancial y sin atribución</b>, o presentándolos como propios.</li>
    <li>Usar el <b>nombre o la marca</b> de forma que sugiera afiliación, respaldo u origen que no existe.</li>
    <li>Republicar los datos <b>ocultando o falseando</b> que proceden de AEMET y de este proyecto.</li>
  </ul>

  <h2>¿Reutilizas nuestro trabajo? ¿O ves un uso indebido?</h2>
  <p>Si quieres reutilizar algo más allá de lo que permite CC BY (por ejemplo, textos o diseño), o si detectas una copia que incumple lo anterior, escríbenos: <a href="mailto:lowesting@gmail.com">lowesting@gmail.com</a>. Para citas normales de los datos no hace falta pedir permiso —basta con atribuir.</p>

  <h2>Datos personales</h2>
  <p><b>No usamos cookies</b> —ni de rastreo ni de ningún tipo—, así que no verás ningún aviso de consentimiento: no hay nada que consentir. Tampoco hay perfiles publicitarios. El <a href="__SITE__/confortometro/">Confortómetro</a> guarda tu voto de forma <b>anónima</b> por zona y usa el almacenamiento local de tu navegador (no una cookie) solo para recordar tu zona y no dejarte votar dos veces seguidas; la ubicación exacta nunca sale de tu dispositivo. Si nos dejas tu correo para recibir un informe o alertas, lo usamos solo para eso; puedes pedir su baja en la dirección de arriba.</p>

  <h2>Descargo</h2>
  <p>La información se ofrece «tal cual», con fines divulgativos. El dato es de la <b>estación</b> de AEMET, no del municipio entero, y no sustituye a la información oficial de AEMET ni a un aviso meteorológico. Hacemos lo posible por que sea correcta, pero no garantizamos que esté libre de errores.</p>
</div></section>
__FOOTER__
</body></html>
"""


PAGINA_SOBRE = r"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sobre el proyecto: quién hay detrás de nochetropical.es y por qué</title>
<meta name="description" content="Quién está detrás de nochetropical.es: no una empresa ni una redacción, sino una persona, sus ratos libres y una pregunta —¿por qué no se conocen los pueblos donde de verdad se duerme fresco?—. Datos abiertos de AEMET, método reproducible, sin publicidad.">
<link rel="canonical" href="__SITE__/sobre-el-proyecto/">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="website">
<meta property="og:title" content="Sobre el proyecto: quién hay detrás de nochetropical.es y por qué">
<meta property="og:description" content="Una persona, sus ratos libres y una pregunta que lleva años rondando. Datos abiertos de AEMET, método reproducible, sin publicidad ni rastreo.">
<meta property="og:url" content="__SITE__/sobre-el-proyecto/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900&family=Lora:ital,wght@0,400;0,600&display=swap" rel="stylesheet">
<style>
 :root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--verde:#8fb07a;--fd:"Fraunces",Georgia,serif;--fb:"Lora",Georgia,serif;--fm:ui-monospace,monospace}
 *{margin:0;padding:0;box-sizing:border-box}
 body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.7;-webkit-font-smoothing:antialiased}
 .wrap{max-width:720px;margin:0 auto;padding:0 24px}
 a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}
 header.h{padding:46px 0 12px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}
 .crumb{font-size:13px;color:var(--muted)}
 .kick{font:600 12px/1 var(--fb);letter-spacing:.16em;text-transform:uppercase;color:var(--teja);margin:16px 0 8px}
 h1{font-family:var(--fd);font-weight:900;font-size:clamp(29px,5.6vw,44px);line-height:1.05;letter-spacing:-.01em}
 h1 em{font-style:italic;color:var(--teja2)}
 .intro{color:var(--muted);font-size:clamp(15.5px,2.5vw,18px);margin:16px 0 0;max-width:60ch}
 .intro b{color:var(--paper)}
 section{padding:20px 0}
 h2{font-family:var(--fd);font-weight:600;font-size:clamp(20px,3.6vw,25px);margin:20px 0 10px}
 p{color:#d9ccb6;font-size:16px;margin:0 0 15px;max-width:66ch}p b{color:var(--paper)}
 .firma{border-left:3px solid var(--teja);background:var(--bg2);border-radius:0 12px 12px 0;padding:16px 18px;margin:8px 0 6px;font-size:15px;color:var(--muted)}
 .firma b{color:var(--paper)}
 .valores{list-style:none;margin:8px 0 6px;padding:0;display:grid;gap:10px}
 .valores li{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:12px;padding:14px 16px;font-size:15px;color:var(--muted)}
 .valores b{color:var(--paper)}
 .cta{margin:22px 0 6px;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:22px;text-align:center}
 .cta b{font-family:var(--fd);font-weight:600;font-size:19px;color:var(--paper)}
 .botones{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin-top:14px}
 .btn{display:inline-block;padding:12px 18px;border-radius:11px;font-weight:700;font-size:14.5px}
 .btn.pri{background:var(--teja);color:#1a1209}.btn.pri:hover{background:var(--teja2);text-decoration:none}
 .btn.sec{background:transparent;border:1px solid var(--teja);color:var(--teja2)}.btn.sec:hover{background:rgba(217,116,78,.12);text-decoration:none}
 __NAVCSS__
 __FOOTERCSS__
</style></head><body>
__NAV__
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">nochetropical.es</a> · Sobre el proyecto</nav>
  <div class="kick">Quiénes somos · Por qué se hace</div>
  <h1>Quién hay detrás de <em>nochetropical.es</em></h1>
  <p class="intro">Aquí no hay una empresa ni una redacción: hay <b>una persona, sus ratos libres y una pregunta</b> que le lleva años rondando. Esta es la historia, sin adornos.</p>
</div></header>

<section><div class="wrap">
  <h2>La chispa: una casa donde de verdad se duerme</h2>
  <p>Tengo la suerte de tener una casita en uno de esos pueblos donde en pleno agosto hay que dormir con manta. Desde el primer verano pensé lo mismo: «el día que esto se sepa, aquí no cabrá un alfiler». Han pasado los años… y no ha pasado. La gente sigue amontonándose en costas donde no se pega ojo, pagando aire acondicionado para combatir noches que <b>a una hora de distancia, tierra adentro, sencillamente no existen</b>.</p>
  <p>Quise entender por qué. Por qué medimos el calor del día hasta la obsesión y casi nadie mira <b>el que de verdad nos quita el sueño</b>. Esa pregunta es el origen de nochetropical.es. Antes lo gestionaba a mano, con paciencia; hoy lo hace un puñado de scripts, pero la pregunta es la misma.</p>

  <h2>Quién lo hace</h2>
  <div class="firma">
    Me llamo Ramón y firmo como <b>Ramón&nbsp;J.&nbsp;Lowesting</b> — un guiño a <i>El príncipe de las mareas</i>, una película que me relaja y cuyo personaje me prestó el apellido.
  </div>
  <p>Me considero un <b>emprendedor incansable</b> y un curioso profesional. Me fijo en las incongruencias que asumimos por comodidad —desde farolas plantadas más altas que los árboles, que acaban iluminando las copas mientras la acera se queda a oscuras bajo la sombra, hasta rotondas que sustituyen a un cruce con semáforo y, lejos de agilizarlo, rompen la fluidez del tráfico— y me pregunto si no se podrían hacer mejor. Las <b>noches tropicales</b> son una de esas incongruencias: hay un mapa del calor diurno en cada telediario, y el calor nocturno —el que decide si descansas o no— apenas se cuenta. Este proyecto es mi granito de arena para cambiarlo.</p>

  <h2>Cómo se hace: con datos, a la vista de todos</h2>
  <p>Aquí no se opina, se mide. Todo lo que ves sale de los <b>datos abiertos de AEMET</b> (veranos de 2017 a 2026), se calcula con scripts que cualquiera puede revisar y <b>se puede reproducir paso a paso</b>. Sin estimaciones ni retoques: si un dato aparece, es porque una estación lo registró. Por eso lo publicamos bajo <a href="__SITE__/aviso-legal/">licencia libre (CC&nbsp;BY)</a> — cógelo, contrástalo, úsalo. Un dato que no se puede comprobar no vale nada; estos se pueden comprobar todos. El detalle del método está en la <a href="__SITE__/metodologia/">metodología</a>.</p>

  <h2>Cómo se sostiene</h2>
  <ul class="valores">
    <li><b>Con ratos libres.</b> Esto se mantiene a base de tardes y fines de semana. Si llego a saber el trabajo que iba a dar, quizá no me habría atrevido a empezarlo — y me alegro de no haberlo sabido.</li>
    <li><b>Sin publicidad, sin cookies, sin rastreo.</b> No hay banners, no se comercia con tus datos y —algo cada vez más raro— <b>no usamos ni una sola cookie</b>: no tendrás que aceptar ningún aviso molesto para entrar, porque no hay nada que aceptar. La web es lo que ves.</li>
    <li><b>El dinero, como consecuencia.</b> Algún día me gustaría que se sostuviera solo, no lo escondo. Pero tengo una creencia firme: el dinero debe ser el resultado, la consecuencia de hacer las cosas bien, no el objetivo. Primero el valor; lo demás, ya vendrá.</li>
  </ul>

  <h2>Si eres periodista</h2>
  <p>La <a href="__SITE__/prensa/">sala de prensa</a> tiene datos para titular, gráficos descargables, metodología y contacto. Y si algo de lo que cuento aquí te parece mejorable o discutible, escríbeme: <a href="mailto:lowesting@gmail.com">lowesting@gmail.com</a>. Se agradece de verdad — este proyecto se ha hecho siempre mejor cuando alguien me ha llevado la contraria con datos.</p>

  <div class="cta">
    <b>¿Y tu pueblo? ¿Se duerme bien?</b>
    <div class="botones">
      <a class="btn pri" href="__HOME__">Búscalo en la calculadora →</a>
      <a class="btn sec" href="__SITE__/confortometro/">Vota en el Confortómetro →</a>
    </div>
  </div>
</div></section>
__FOOTER__
</body></html>
"""


def construir_pagina_sobre(site: str) -> str:
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "nochetropical.es", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Sobre el proyecto",
             "item": site + "/sobre-el-proyecto/"}]},
        {"@type": "AboutPage", "name": "Sobre el proyecto · nochetropical.es",
         "url": site + "/sobre-el-proyecto/",
         "description": ("Quién está detrás de nochetropical.es y por qué: un proyecto personal "
                         "de datos abiertos sobre noches tropicales, con método reproducible y "
                         "sin publicidad."),
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "isPartOf": {"@type": "WebSite", "name": "Refugio Climático", "url": site + "/"}}]},
        ensure_ascii=False)
    return (PAGINA_SOBRE
            .replace("__NAVCSS__", CSS_NAV_ESCUETO)
            .replace("__FOOTERCSS__", CSS_FOOTER_ESCUETO)
            .replace("__NAV__", nav_escueto_html(site))
            .replace("__FOOTER__", footer_escueto_html(site))
            .replace("__SCHEMA__", schema)
            .replace("__HOME__", site + "/")
            .replace("__SITE__", site))


def construir_pagina_aviso_legal(site: str) -> str:
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "nochetropical.es", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Aviso legal y licencia",
             "item": site + "/aviso-legal/"}]},
        {"@type": "WebPage", "name": "Licencia, derechos de autor y aviso legal",
         "url": site + "/aviso-legal/",
         "description": ("Condiciones de reutilización de nochetropical.es: datos bajo "
                         "CC BY 4.0 con atribución; marca, diseño y textos reservados."),
         "license": "https://creativecommons.org/licenses/by/4.0/",
         "isPartOf": {"@type": "WebSite", "name": "Refugio Climático", "url": site + "/"}}]},
        ensure_ascii=False)
    return (PAGINA_AVISO_LEGAL
            .replace("__NAVCSS__", CSS_NAV_ESCUETO)
            .replace("__FOOTERCSS__", CSS_FOOTER_ESCUETO)
            .replace("__NAV__", nav_escueto_html(site))
            .replace("__FOOTER__", footer_escueto_html(site))
            .replace("__SCHEMA__", schema)
            .replace("__HOME__", site + "/")
            .replace("__SITE__", site))


# ===========================================================================
# VERSIÓN EN INGLÉS (/en/) — FASE 1
# ---------------------------------------------------------------------------
# Solo se traducen las páginas con más intención de búsqueda para el público
# angloparlante que vive en o viaja a España ("coolcation", "where to escape
# the heat in Spain"): la home /en/ y la guía /en/coolest-towns-spain/.
# Inglés británico. SEO completo: slugs propios, title/description/H1/H2 en
# inglés, schema, hreflang bidireccional (es-ES / en-GB / x-default→ES) y
# navegación entre landings SIEMPRE con tarjetas y botones, nunca enlaces
# sueltos "en letra pequeña". Reutiliza la paleta oscura y el chrome escueto.
# El estudio con mapas en inglés y el mapa de la ola en vivo son fases 2 y 3.
# ===========================================================================

def hreflang_block(es_path: str, en_path: str) -> str:
    """Bloque hreflang bidireccional. x-default apunta al español, que es el
    idioma original y de mayor cobertura. Usa __SITE__ (se resuelve luego)."""
    return (f'<link rel="alternate" hreflang="es-ES" href="__SITE__{es_path}">\n'
            f'<link rel="alternate" hreflang="en-GB" href="__SITE__{en_path}">\n'
            f'<link rel="alternate" hreflang="x-default" href="__SITE__{es_path}">')


# Menú escueto en inglés: reaprovecha las clases de CSS_NAV_ESCUETO. La última
# entrada es el conmutador de idioma hacia la web en español.
MENU_EN = [
    ("Coolest towns", "/en/coolest-towns-spain/"),
    ("Live heatwave map", "/ola-de-calor/"),
    ("Interactive map", "/mapa-estaciones/"),
]


def nav_en_html(site: str) -> str:
    enlaces = "".join(f'<a href="{site}{href}">{txt}</a>' for txt, href in MENU_EN)
    enlaces += f'<a href="{site}/" hreflang="es" class="lang">ES · Español</a>'
    return ('<nav class="nav-e" aria-label="main"><div class="in">'
            f'<a class="brand" href="{site}/en/" aria-label="nochetropical.es">{_LOGO_ESCUETO}</a>'
            f'<div class="links">{enlaces}</div></div></nav>')


def footer_en_html(site: str) -> str:
    c1 = [("Coolest towns to sleep in summer", "/en/coolest-towns-spain/"),
          ("Live heatwave map (animated)", "/ola-de-calor/"),
          ("Interactive station map", "/mapa-estaciones/"),
          ("National tropical-nights ranking", "/ranking-noches-tropicales/")]
    c2 = [("Search any Spanish town (calculator)", "/"),
          ("Methodology & data sources", "/metodologia/"),
          ("About the project", "/sobre-el-proyecto/"),
          ("Licence & legal notice", "/aviso-legal/")]
    c3 = [("Versión en español (Spanish site)", "/"),
          ("Where to sleep under a blanket (ES)", "/dormir-con-manta-en-verano/"),
          ("The Spain that never turns red (ES)", "/la-espana-que-nunca-se-colorea/")]

    def col(titulo: str, items: list) -> str:
        enlaces = "".join(f'<a href="{site}{h}">{t}</a>' for t, h in items)
        return f'<div class="f2col"><h4>{titulo}</h4>{enlaces}</div>'

    return ('<footer class="f2"><div class="wrap"><div class="f2grid">'
            + col("Explore the data", c1)
            + col("The project", c2)
            + col("Other languages & guides", c3)
            + '</div><div class="f2bar">Source: '
            '<a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a>'
            ' · data under <a href="https://creativecommons.org/licenses/by/4.0/" '
            'rel="license">CC&nbsp;BY&nbsp;4.0</a> · © 2026 '
            f'<a href="{site}/">nochetropical.es</a> · Ramón J. Lowesting</div>'
            '</div></footer>')


# CSS común de las páginas en inglés: misma paleta oscura, tipografías y estilo
# de tarjetas/botones que el resto del sitio, para una identidad uniforme.
_CSS_EN = (
    ':root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;'
    '--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--verde:#8fb07a;'
    '--fd:"Fraunces",Georgia,serif;--fb:"Lora",Georgia,serif;--fm:ui-monospace,monospace}'
    '*{margin:0;padding:0;box-sizing:border-box}'
    'body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.7;'
    '-webkit-font-smoothing:antialiased}'
    '.wrap{max-width:min(92vw,880px);margin:0 auto;padding:0 24px}'
    'a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}'
    'header.h{padding:46px 0 12px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}'
    '.crumb{font-size:13px;color:var(--muted)}'
    '.kick{font:600 12px/1 var(--fb);letter-spacing:.16em;text-transform:uppercase;color:var(--teja);margin:16px 0 8px}'
    'h1{font-family:var(--fd);font-weight:900;font-size:clamp(29px,5.6vw,46px);line-height:1.04;letter-spacing:-.01em}'
    'h1 em{font-style:italic;color:var(--teja2)}'
    '.intro{color:var(--muted);font-size:clamp(15.5px,2.5vw,18px);margin:16px 0 0;max-width:64ch}'
    '.intro b{color:var(--paper)}'
    'section{padding:20px 0}'
    'h2{font-family:var(--fd);font-weight:600;font-size:clamp(20px,3.6vw,26px);margin:22px 0 10px}'
    'h3{font-family:var(--fd);font-weight:600;font-size:19px;margin:2px 0 2px;color:var(--paper)}'
    'p{color:#d9ccb6;font-size:16px;margin:0 0 15px;max-width:68ch}p b{color:var(--paper)}'
    '.hero-img{width:100%;height:auto;border:1px solid var(--line);border-radius:14px;margin:22px 0 4px;display:block}'
    '.cap{font-size:13px;color:var(--muted);margin:0 0 10px}'
    '.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:20px 0 6px}'
    '.card2{display:block;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);'
    'border-radius:14px;padding:18px 18px 16px;color:var(--paper)}'
    '.card2:hover{border-color:var(--teja);text-decoration:none;transform:translateY(-2px);transition:.15s}'
    '.card2 .ic{font-size:22px}'
    '.card2 .t{font-family:var(--fd);font-weight:600;font-size:17.5px;margin:6px 0 4px}'
    '.card2 .d{color:var(--muted);font-size:13.5px;line-height:1.5}'
    '.card2.pri{background:linear-gradient(180deg,#3a2416,#2a1a10);border-color:var(--teja)}'
    '.region{margin:26px 0 0}'
    '.region>.rh{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px;border-bottom:1px solid var(--line);padding-bottom:8px}'
    '.region .rh .sub{color:var(--teja2);font-size:13px;letter-spacing:.06em;text-transform:uppercase;font-weight:600}'
    '.region .rd{color:var(--muted);font-size:14.5px;margin:10px 0 4px;max-width:70ch}'
    '.refuges{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:12px 0 4px}'
    '.refuge-card{display:block;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);'
    'border-radius:13px;padding:15px 16px;color:var(--paper)}'
    '.refuge-card:hover{border-color:var(--teal);text-decoration:none}'
    '.refuge-card .rn{font-family:var(--fd);font-weight:600;font-size:17px;color:var(--paper)}'
    '.refuge-card .rp{color:var(--muted);font-size:12.5px;margin:1px 0 10px}'
    '.refuge-card .stats{display:flex;gap:14px}'
    '.refuge-card .st{flex:1}'
    '.refuge-card .st .v{font-family:var(--fm);font-weight:700;font-size:18px;color:var(--teal)}'
    '.refuge-card .st .v.tj{color:var(--teja2)}'
    '.refuge-card .st .k{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}'
    '.contrast{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:16px 0}'
    '.contrast .cc{background:var(--bg2);border:1px solid var(--line);border-radius:13px;padding:16px}'
    '.contrast .cc .v{font-family:var(--fm);font-weight:700;font-size:30px}'
    '.contrast .cool .v{color:var(--teal)}.contrast .hot .v{color:var(--teja2)}'
    '.contrast .cc .k{color:var(--muted);font-size:13px;margin-top:4px}'
    '.cta{margin:26px 0 6px;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);'
    'border-radius:16px;padding:24px;text-align:center}'
    '.cta b{font-family:var(--fd);font-weight:600;font-size:20px;color:var(--paper)}'
    '.cta p{margin:8px auto 0;max-width:52ch}'
    '.botones{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin-top:16px}'
    '.btn{display:inline-block;padding:13px 20px;border-radius:11px;font-weight:700;font-size:14.5px}'
    '.btn.pri{background:var(--teja);color:#1a1209}.btn.pri:hover{background:var(--teja2);text-decoration:none}'
    '.btn.sec{background:transparent;border:1px solid var(--teja);color:var(--teja2)}'
    '.btn.sec:hover{background:rgba(217,116,78,.12);text-decoration:none}'
    '.faq{margin:12px 0}.faq details{border-bottom:1px solid var(--line);padding:14px 0}'
    '.faq summary{font-family:var(--fd);font-weight:600;font-size:16.5px;color:var(--paper);cursor:pointer;list-style:none}'
    '.faq summary::-webkit-details-marker{display:none}'
    '.faq summary::before{content:"+ ";color:var(--teja)}'
    '.faq details[open] summary::before{content:"– "}'
    '.faq p{margin:10px 0 2px;font-size:15px}'
    '.lang-note{font-size:13px;color:var(--muted);background:var(--bg2);border:1px solid var(--line);'
    'border-radius:10px;padding:11px 14px;margin:14px 0}'
    # Etiqueta "in Spanish": marca los enlaces que cruzan a una página española,
    # para que el usuario inglés sepa que su navegador se la traducirá.
    '.estag{display:inline-block;font-size:10.5px;color:var(--teja2);border:1px solid var(--line);'
    'border-radius:5px;padding:1px 5px;margin-left:6px;letter-spacing:.03em;vertical-align:middle}'
    # Leyenda de color en HTML (el texto que antes iba incrustado en el mapa).
    '.leg{display:flex;flex-wrap:wrap;gap:7px 18px;margin:12px 2px 2px;font-size:13px;color:var(--muted)}'
    '.leg .it{display:inline-flex;align-items:center;gap:7px}'
    '.leg .sw{width:14px;height:14px;border-radius:3px;flex:none;border:1px solid rgba(255,255,255,.14)}'
    # Envoltorio de figura (mapa + pie + leyenda) reutilizable.
    '.fig{background:var(--bg2);border:1px solid var(--line);border-radius:16px;padding:12px;margin:0}'
    '.fig img{width:100%;height:auto;display:block;border-radius:9px}'
    '.fig figcaption{font-size:13px;color:var(--muted);margin-top:10px;padding:0 2px}'
    # Maquetación de ESCRITORIO: aprovecha el ancho en vez de dejar una columna
    # estrecha con los lados vacíos. Móvil: una sola columna (por defecto).
    '@media(min-width:980px){'
    '.wrap{max-width:min(94vw,1180px)}'
    '.hero-grid{display:grid;grid-template-columns:1.02fr .98fr;gap:12px 48px;align-items:center}'
    '.hero-grid .intro{max-width:none}'
    '.twocol{columns:2;column-gap:52px}'
    '.twocol>*{break-inside:avoid}'
    '.twocol h2{margin-top:0}'
    '.faq.grid2{columns:2;column-gap:52px}.faq.grid2 details{break-inside:avoid}'
    '}'
)

_FUENTES_LINK = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
                 '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                 '<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;'
                 '0,9..144,900&family=Lora:ital,wght@0,400;0,600&display=swap" rel="stylesheet">')


def _faq_en_html(faq: list) -> str:
    return ('<div class="faq">'
            + "".join(f'<details><summary>{q}</summary><p>{a}</p></details>' for q, a in faq)
            + '</div>')


def _cabeza_en(site: str, titulo: str, desc: str, path: str, es_path: str,
               og_img: str, schema: str, extra_css: str = "") -> str:
    """<head> completo y uniforme para las páginas en inglés."""
    return (
        '<!doctype html>\n<html lang="en-GB"><head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{titulo}</title>\n'
        f'<meta name="description" content="{desc}">\n'
        f'<link rel="canonical" href="{site}{path}">\n'
        + hreflang_block(es_path, path).replace("__SITE__", site) + '\n'
        '<meta name="robots" content="index, follow, max-image-preview:large">\n'
        '<meta name="author" content="Ramón J. Lowesting">\n'
        '<meta property="og:type" content="website">\n'
        f'<meta property="og:title" content="{titulo}">\n'
        f'<meta property="og:description" content="{desc}">\n'
        f'<meta property="og:url" content="{site}{path}">\n'
        f'<meta property="og:image" content="{site}{og_img}">\n'
        '<meta property="og:locale" content="en_GB">\n'
        '<meta property="og:locale:alternate" content="es_ES">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        f'<meta name="twitter:image" content="{site}{og_img}">\n'
        f'<link rel="icon" type="image/svg+xml" href="{site}/favicon.svg">\n'
        f'<script type="application/ld+json">{schema}</script>\n'
        + _FUENTES_LINK + '\n<style>'
        + _CSS_EN + CSS_NAV_ESCUETO + CSS_FOOTER_ESCUETO + extra_css
        + '</style></head><body>\n')


def construir_pagina_en_home(site: str, datos_estudio: dict | None = None) -> str:
    titulo = ("Spain Climate Refuges & Summer Heatwave Map: Where to Sleep Cool "
              "| NocheTropical.es")
    desc = ("Planning a coolcation in Spain? Ten summers of official AEMET data reveal "
            "the mountain towns where the night still cools down — and where you will "
            "never get a wink of sleep. Find your natural climate refuge.")
    # Cifras del estudio (si están): porcentaje del país que refresca de verdad.
    if datos_estudio:
        prof = datos_estudio["nocturno"]["profundo"]
        rojo = datos_estudio["dia"]["enrojece"]
        stat_line = (f"Across a whole Spanish summer, only about <b>{prof:.0f}% of the "
                     f"country</b> drops below 18&nbsp;°C every single night — the only "
                     f"cool that truly lets you sleep — while <b>{rojo:.0f}%</b> turns "
                     f"red-hot (over 32&nbsp;°C) by day at some point.")
    else:
        stat_line = ("Only a sliver of Spain — the mountain interior — stays cool enough "
                     "to sleep every night of the summer.")
    tarjetas = [
        ("pri", "🌙", "The coolest towns to sleep in", False,
         "Region by region, the Spanish mountain towns with almost zero tropical nights — "
         "backed by AEMET data.", "/en/coolest-towns-spain/"),
        ("", "🔥", "Live heatwave map (animated)", True,
         "Watch the heat spread across Spain day by day — highs by day, lows by night, "
         "straight from AEMET maps.", "/ola-de-calor/"),
        ("", "🗺️", "Interactive station map", True,
         "Zoom into 848 weather stations and see the tropical-night count anywhere in Spain.",
         "/mapa-estaciones/"),
        ("", "🏨", "Where to stay: cool-sleep hotels", True,
         "Hand-picked hotels in Spain's climate refuges, where the night cools down and "
         "you sleep without air conditioning — the geography of rest.", "/hoteles-refugio-climatico/"),
        ("", "🔎", "Search any town (calculator)", True,
         "Type any Spanish town into the calculator and see how many tropical nights it "
         "endures each summer.", "/"),
    ]
    cards_html = ""
    for cls, ic, t, es, d, href in tarjetas:
        hl = ' hreflang="es"' if es else ''
        tag = ' <span class="estag">in Spanish</span>' if es else ''
        cards_html += (f'<a class="card2 {cls}" href="{site}{href}"{hl}>'
                       f'<div class="ic">{ic}</div>'
                       f'<div class="t">{t}{tag}</div>'
                       f'<div class="d">{d}</div></a>')
    # Leyenda del mapa nocturno, en inglés (el texto ya no va incrustado).
    if datos_estudio:
        nz = datos_estudio["nocturno"]
        leg_pct = (f' ({nz["profundo"]:.0f}%)', f' ({nz["margen"]:.0f}%)',
                   f' ({nz["tropical"]:.0f}%)')
    else:
        leg_pct = ("", "", "")
    leyenda_noche = (
        '<div class="leg" aria-label="Map legend">'
        f'<span class="it"><span class="sw" style="background:#a9c6d4"></span>'
        f'Below 18&nbsp;°C every night — deep refuge{leg_pct[0]}</span>'
        f'<span class="it"><span class="sw" style="background:#c9a24a"></span>'
        f'Never tropical, but hovers near 20&nbsp;°C — false relief{leg_pct[1]}</span>'
        f'<span class="it"><span class="sw" style="background:#c94a2e"></span>'
        f'Some tropical nights, ≥20&nbsp;°C{leg_pct[2]}</span>'
        '</div>')
    faq = [
        ("What is a coolcation?",
         "A coolcation is a holiday chosen for its cool climate rather than sun and beach — "
         "escaping the summer heat instead of chasing it. In Spain that means the mountain "
         "interior, where nights stay fresh even in August."),
        ("Where in Spain can you sleep without air conditioning in summer?",
         "In the highland interior, roughly 600–1,700&nbsp;m above sea level: the Pyrenees, "
         "the Sierra de Gúdar in Teruel, the Gredos and Guadarrama ranges, the Cantabrian "
         "Mountains, Sanabria and the Soria highlands. These towns barely record a single "
         "tropical night per year."),
        ("What is a tropical night?",
         "A tropical night is one where the temperature never drops below 20&nbsp;°C. The "
         "more tropical nights a place has, the harder it is to sleep. The Mediterranean "
         "coast can string together 80+ in a row; the mountain interior often has none."),
        ("Is the data reliable?",
         "Yes. Everything comes from AEMET, Spain's national meteorological agency, using "
         "the summers of 2017–2026. It is open, free of cookies and fully reproducible — "
         "the code that builds this site is public."),
    ]
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "name": "NocheTropical.es",
         "url": site + "/", "inLanguage": "es-ES",
         "description": "Where to sleep cool in Spain, with ten summers of AEMET data."},
        {"@type": "WebPage", "name": titulo, "url": site + "/en/",
         "inLanguage": "en-GB", "description": desc,
         "isPartOf": {"@type": "WebSite", "name": "NocheTropical.es", "url": site + "/"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "NocheTropical.es", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Climate refuges in Spain (English)",
             "item": site + "/en/"}]},
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq]},
    ]}, ensure_ascii=False)
    cuerpo = (
        nav_en_html(site)
        + '<header class="h"><div class="wrap"><div class="hero-grid">'
        '<div>'
        '<nav class="crumb" aria-label="breadcrumb">'
        f'<a href="{site}/en/">NocheTropical.es</a> · Climate refuges in Spain</nav>'
        '<div class="kick">Coolcation Spain · 10 summers of AEMET data</div>'
        '<h1>Find Your Natural <em>Climate Refuge</em> in Spain</h1>'
        f'<p class="intro">Not every Spanish summer is a sleepless one. {stat_line} '
        'This is the map of where the night still cools down — town by town, '
        'built from ten years of official AEMET records.</p>'
        '</div>'
        f'<figure class="fig"><img src="{site}/estudios/refugios-nocturnos.png" '
        'alt="Map of Spain showing overnight climate refuges: the mountain interior stays '
        'below 20°C at night while the coasts glow with tropical nights, from AEMET data" '
        'width="902" height="734" loading="eager">'
        '<figcaption>Overnight lows superimposed across a full Spanish summer (AEMET). '
        'The teal zones are the real climate refuges — where the night reliably cools down.'
        '</figcaption>' + leyenda_noche + '</figure>'
        '</div></div></header>'
        '<section><div class="wrap">'
        '<div class="cards">' + cards_html + '</div>'
        '</div></section>'
        '<section><div class="wrap">'
        '<div class="twocol">'
        '<div><h2>Why a coolcation in Spain?</h2>'
        '<p>Spain is famous for sun and beaches — and infamous, in August, for nights you '
        'cannot sleep through. But the country is not one climate: an hour inland and a '
        'few hundred metres up, the air changes completely. In the high sierras the '
        'temperature plunges after dark, and you sleep <b>under a blanket</b> while the '
        'coast swelters. That is a coolcation: choosing your destination for the cool, '
        'not the heat.</p></div>'
        '<div><h2>How we measure it</h2>'
        '<p>We count <b>tropical nights</b> — nights that never drop below 20&nbsp;°C — at '
        '848 AEMET weather stations across the summers of 2017–2026. We do not use averages, '
        'which hide the heat spikes; we use honest thresholds and worst-case streaks. A town '
        'with almost zero tropical nights is a place where you can genuinely sleep in summer, '
        'no air conditioning required.</p></div>'
        '</div>'
        '<div class="cta">'
        '<b>Ready to find where to sleep cool?</b>'
        '<p>Explore the mountain regions where Spain stays fresh all summer long.</p>'
        '<div class="botones">'
        f'<a class="btn pri" href="{site}/en/coolest-towns-spain/">See the coolest towns →</a>'
        f'<a class="btn sec" href="{site}/ola-de-calor/" hreflang="es">Live heatwave map →</a>'
        '</div></div>'
        '<h2>Frequently asked questions</h2>'
        + _faq_en_html(faq).replace('class="faq"', 'class="faq grid2"')
        + '</div></section>'
        + footer_en_html(site))
    return _cabeza_en(site, titulo, desc, "/en/", "/",
                      "/og.png", schema) + cuerpo + "</body></html>\n"


# Regiones de montaña para la guía en inglés. Cada una define fragmentos de
# nombre que se buscan en el catálogo real de estaciones (case-insensitive):
# así las cifras (noches tropicales, Tmin, altitud) salen SIEMPRE del dato vivo,
# nunca inventadas. Si un pueblo no está en los datos, se omite en silencio.
REGIONES_EN = [
    ("The Pyrenees", "Aragón & Val d'Aran",
     "Spain's highest mountains. In these alpine valleys the night barely registers a "
     "tropical night all summer — you will want a blanket even in August.",
     ["benasque", "canfranc", "torla - ordesa", "naut aran", "isaba"]),
    ("Sierra de Gúdar", "Teruel",
     "Teruel's high plateau is the poster child of the Spanish coolcation, with the "
     "sharpest day-to-night contrast in the country: scorching noons, genuinely cold nights.",
     ["cedrillas", "albarrac"]),
    ("Gredos & Guadarrama", "The Central System",
     "The granite sierras within easy reach of Madrid, where the mountain air drops like "
     "a stone the moment the sun goes down.",
     ["puerto del pico", "rascafr"]),
    ("The Cantabrian Mountains", "Cantabria & Palencia",
     "Green, Atlantic-facing highlands where summer nights stay reliably, dependably cool.",
     ["alto campoo", "reinosa", "cervera de pisuerga"]),
    ("Sanabria", "Zamora",
     "A glacial-lake highland in the north-west — and, by the numbers, one of the very "
     "coolest places to sleep in all of Spain.",
     ["sanabria"]),
    ("The Soria Highlands", "Iberian System",
     "The pine-forested sierras of Urbión and the upper Duero: continental, dry and high.",
     ["vinuesa"]),
]


def _mejor_estacion(estaciones: list, frag: str) -> dict | None:
    cand = [e for e in estaciones if frag in e["loc"].lower()]
    if not cand:
        return None
    return sorted(cand, key=lambda e: (e["nt"], e["tmin"]))[0]


def construir_pagina_en_pueblos(estaciones: list, site: str) -> str:
    titulo = ("Where to Escape the Heat in Spain: The Coolest Towns to Sleep in Summer "
              "| NocheTropical.es")
    desc = ("The best cool-climate towns in Spain for a summer coolcation, region by "
            "region. Mountain villages with almost no tropical nights, ranked with ten "
            "summers of AEMET data — where you sleep under a blanket in August.")
    # Contraste real (dato vivo): el pueblo más fresco encontrado vs el más tórrido.
    peor = max(estaciones, key=lambda e: e["nt"])
    # Construye las regiones con datos vivos.
    regiones_html = []
    n_pueblos = 0
    item_list = []
    coolest = None
    for nombre, sub, descr, frags in REGIONES_EN:
        cards = []
        for frag in frags:
            e = _mejor_estacion(estaciones, frag)
            if not e:
                continue
            n_pueblos += 1
            if coolest is None or e["tmin"] < coolest["tmin"]:
                coolest = e
            nt_txt = "0" if e["nt"] < 0.05 else f'{e["nt"]:.1f}'
            item_list.append({"@type": "ListItem", "position": len(item_list) + 1,
                              "item": {"@type": "Place", "name": e["loc"],
                                       "address": {"@type": "PostalAddress",
                                                   "addressRegion": e["prov"],
                                                   "addressCountry": "ES"}}})
            cards.append(
                f'<a class="refuge-card" href="{site}/{slug(e["prov"])}/" hreflang="es" '
                f'aria-label="{e["loc"]} climate data (page in Spanish)">'
                f'<div class="rn">{e["loc"]}</div>'
                f'<div class="rp">{e["prov"]} · {miles(e["alt"])}&nbsp;m above sea level</div>'
                '<div class="stats">'
                f'<div class="st"><div class="v">{nt_txt}</div>'
                '<div class="k">tropical nights / yr</div></div>'
                f'<div class="st"><div class="v tj">{e["tmin"]:.1f}&nbsp;°</div>'
                '<div class="k">avg summer low</div></div>'
                '</div></a>')
        if not cards:
            continue
        regiones_html.append(
            '<div class="region"><div class="rh">'
            f'<h3>{nombre}</h3><span class="sub">{sub}</span></div>'
            f'<p class="rd">{descr}</p>'
            '<div class="refuges">' + "".join(cards) + '</div></div>')
    faq = [
        ("Where can you sleep with a blanket in Spain in summer?",
         "In the highland interior between roughly 600 and 1,700&nbsp;m: the Pyrenees, the "
         "Sierra de Gúdar in Teruel, Gredos and Guadarrama, the Cantabrian Mountains, "
         "Sanabria and the Soria highlands. These towns record almost no tropical nights."),
        ("What is the coolest town in Spain to sleep in summer?",
         (f"By average summer overnight low, {coolest['loc']} ({coolest['prov']}, "
          f"{miles(coolest['alt'])}&nbsp;m) is among the coolest, at about "
          f"{coolest['tmin']:.1f}&nbsp;°C — and effectively zero tropical nights a year.")
         if coolest else
         "The highland villages of the interior, where the average summer low sits below "
         "10&nbsp;°C and tropical nights are practically unknown."),
        ("Are these good places for a coolcation?",
         "Yes — they are the natural cool-climate destinations of Spain. Many sit inside "
         "national parks (Ordesa, Aigüestortes, Picos de Europa) or ski areas that reinvent "
         "themselves in summer as an escape from the heat. Cool days, cold nights, no crowds."),
        ("Is a town's climate the same as a hotel's temperature?",
         "No — and we are careful about that. The data describe the outdoor climate of the "
         "town from AEMET stations: if the night cools down outside, sleeping is easier. It "
         "does not measure any individual building's interior."),
    ]
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "NocheTropical.es", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Climate refuges in Spain",
             "item": site + "/en/"},
            {"@type": "ListItem", "position": 3, "name": "Coolest towns to sleep in summer",
             "item": site + "/en/coolest-towns-spain/"}]},
        {"@type": "Article",
         "headline": "The coolest towns to sleep in during a Spanish summer",
         "description": desc, "image": site + "/estudios/frescor-dia.png",
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "publisher": {"@type": "Organization", "name": "NocheTropical.es",
                       "logo": {"@type": "ImageObject", "url": site + "/favicon.svg"}},
         "inLanguage": "en-GB", "datePublished": "2026-07-25",
         "dateModified": date.today().isoformat(),
         "mainEntityOfPage": site + "/en/coolest-towns-spain/"},
        {"@type": "ItemList", "name": "Coolest towns to sleep in summer in Spain",
         "numberOfItems": len(item_list), "itemListElement": item_list},
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq]},
    ]}, ensure_ascii=False)
    leyenda_dia = (
        '<div class="leg" aria-label="Map legend">'
        '<span class="it"><span class="sw" style="background:#78c8d6"></span>'
        'Peaks that stay cool by day: Sierra Nevada, the Pyrenees, the Cantabrian range, Gúdar</span>'
        '<span class="it"><span class="sw" style="background:#463e30"></span>'
        'Hot by day too</span>'
        '</div>')
    cuerpo = (
        nav_en_html(site)
        + '<header class="h"><div class="wrap"><div class="hero-grid">'
        '<div>'
        '<nav class="crumb" aria-label="breadcrumb">'
        f'<a href="{site}/en/">NocheTropical.es</a> · Coolest towns</nav>'
        '<div class="kick">Coolcation Spain · region by region</div>'
        '<h1>The Coolest Towns to <em>Sleep</em> in Spain in Summer</h1>'
        f'<p class="intro">Where do you actually sleep well in a Spanish August? These are '
        f'the {n_pueblos} mountain towns, grouped by region, where AEMET records almost no '
        '<b>tropical nights</b> — the nights that never drop below 20&nbsp;°C. Real data, '
        'ten summers, no marketing.</p>'
        f'<div class="contrast"><div class="cc cool"><div class="v">~0</div>'
        f'<div class="k">tropical nights a year in the coolest villages '
        f'(e.g. {coolest["loc"] if coolest else "Sanabria"})</div></div>'
        f'<div class="cc hot"><div class="v">{peor["nt"]:.0f}</div>'
        f'<div class="k">a year in the worst spot for sleep, {peor["loc"]} '
        f'({peor["prov"]})</div></div></div>'
        '</div>'
        f'<figure class="fig"><img src="{site}/estudios/frescor-dia.png" '
        'alt="Map of Spain\'s daytime coolness: only the high mountain interior stays under '
        '24°C on a typical summer day, from AEMET data" '
        'width="902" height="734" loading="eager">'
        '<figcaption>The teal islands are the highland interiors that stay coolest by day — '
        'and coolest by night. Each town below sits inside one of them.</figcaption>'
        + leyenda_dia + '</figure>'
        '</div></div></header>'
        '<section><div class="wrap">'
        '<div class="lang-note">The town cards open their Spanish data page — the numbers '
        'read the same in any language, and your browser can translate the rest. A fully '
        'English destination guide is on its way.</div>'
        + "".join(regiones_html)
        + '<div class="cta">'
        '<b>Not sure which region suits you?</b>'
        '<p>Search any town in the calculator, or watch the heatwave move across Spain in '
        'real time.</p>'
        '<div class="botones">'
        f'<a class="btn pri" href="{site}/" hreflang="es">Search any town →</a>'
        f'<a class="btn sec" href="{site}/ola-de-calor/" hreflang="es">Live heatwave map →</a>'
        '</div></div>'
        '<h2>Frequently asked questions</h2>'
        + _faq_en_html(faq).replace('class="faq"', 'class="faq grid2"')
        + '</div></section>'
        + footer_en_html(site))
    return _cabeza_en(site, titulo, desc, "/en/coolest-towns-spain/",
                      "/dormir-con-manta-en-verano/", "/estudios/frescor-dia.png",
                      schema) + cuerpo + "</body></html>\n"


# ===========================================================================
# HOTELES EN REFUGIOS CLIMÁTICOS (monetización con afiliación de Booking) + el
# sello "Refugio Climático Natural". Data-driven desde datos/hoteles.csv: cada
# hotel se cruza con su estación AEMET de referencia (dato real, fuente única =
# el ranking). Los enlaces a Booking son de afiliado vía CJ (rel="sponsored"),
# con SID por hotel para saber cuál convierte. La página lleva disclosure de
# afiliados y NO usa schema de hotel falso: solo el listado (ItemList) honesto.
# El sello se emite en SVG en cada build (docs/badges/<slug>.svg); los PNG no
# editables para descarga/impresión se pre-renderizan aparte.
# ===========================================================================
CJ_PID = "101842593"  # Publisher ID de CJ Affiliate para Booking.com


def cj_deeplink(booking_slug: str, sid: str) -> str:
    """Deep-link de afiliado de CJ que envuelve la ficha real de Booking. El
    formato /links/PID/type/dlg/URL está verificado (deja el cjevent y el aid).
    El sid identifica el hotel en el informe de clics de CJ."""
    dest = f"https://www.booking.com/hotel/es/{booking_slug}.html?sid={sid}"
    return f"https://www.anrdoezrs.net/links/{CJ_PID}/type/dlg/{dest}"


# --- Sello "Refugio Climático Natural" (SVG parametrizado) -----------------
_SELLO = dict(bg="#161009", bg2="#241b11", line="#3a2c1c", paper="#efe6d6",
              muted="#b3a48c", teja="#d9744e", teja2="#e89a73", teal="#96b6c4",
              verde="#8fb07a")
_SELLO_FD = "'Fraunces','Playfair Display','Georgia',serif"
_SELLO_FB = "'Lora','Georgia',serif"


def _n_es(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def sello_svg(zona: str, prov: str, tmin: float, nt: float, nivel: str = "A",
              ref_desc: str = "", tema: str = "oscuro") -> str:
    """Sello circular. tema 'oscuro' (embeber en web) o 'claro' (impresión: sin
    masas de tinta). Texto honesto: 'basado en datos de AEMET', certifica el
    clima de la ZONA (estación), no el interior del hotel."""
    if tema == "claro":
        C = dict(fondo=None, borde_int="#cdbb9c", ink="#2a1d10", sub="#8a7757",
                 metric="#2f7c8a", verde="#5c7d43", tejaA="#b8542e", tealB="#2f7c8a",
                 dominio="#b8542e")
    else:
        C = dict(fondo="url(#bg)", borde_int=_SELLO["line"], ink=_SELLO["paper"],
                 sub=_SELLO["muted"], metric=_SELLO["teal"], verde=_SELLO["verde"],
                 tejaA=_SELLO["teja"], tealB=_SELLO["teal"], dominio=_SELLO["teja2"])
    acento = C["tejaA"] if nivel == "A" else C["tealB"]
    etiqueta = "REFUGIO CERTIFICADO" if nivel == "A" else "ZONA VERIFICADA"
    nt_txt = "0" if nt < 0.05 else _n_es(nt)
    fuente_linea = (f"Estación AEMET de {zona}" if nivel == "A"
                    else (ref_desc or "Estación AEMET más cercana"))
    zona_up = (zona if len(zona) <= 18 else zona[:17] + "…").upper()
    alt = (f"Sello Refugio Climático Natural — {zona} ({prov}). Mínima media de "
           f"agosto {_n_es(tmin)}°C, {nt_txt} noches tropicales al año. Basado en "
           f"datos de AEMET.")
    fondo = (f'fill="{C["fondo"]}"' if C["fondo"] else 'fill="none"')
    opac = ".9" if tema == "claro" else "1"
    url = SITE_URL + "/hoteles-refugio-climatico/"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        f'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" viewBox="0 0 300 300" '
        f'width="300" height="300" role="img" aria-label="{alt}">'
        f'<title>{alt}</title>'
        f'<desc>{alt} Emitido por nochetropical.es a partir de 10 veranos de datos oficiales '
        f'de AEMET (CC BY 4.0). Certifica el clima nocturno de la zona, no el interior del establecimiento.</desc>'
        f'<metadata><rdf:RDF><rdf:Description rdf:about="{url}">'
        f'<dc:title>Refugio Climático Natural — {zona} ({prov})</dc:title>'
        f'<dc:creator>Ramón J. Lowesting · nochetropical.es</dc:creator>'
        f'<dc:rights>© nochetropical.es · datos de AEMET bajo CC BY 4.0</dc:rights>'
        f'<dc:source>{url}</dc:source>'
        f'<dc:subject>refugio climático natural, noches tropicales, dormir fresco, AEMET, {zona}, {prov}</dc:subject>'
        f'</rdf:Description></rdf:RDF></metadata>'
        f'<defs><radialGradient id="bg" cx="50%" cy="34%" r="74%">'
        f'<stop offset="0" stop-color="{_SELLO["bg2"]}"/><stop offset="1" stop-color="{_SELLO["bg"]}"/>'
        f'</radialGradient>'
        f'<path id="arcTop" d="M 31 150 A 119 119 0 0 1 269 150" fill="none"/>'
        f'<path id="arcBot" d="M 31 150 A 119 119 0 0 0 269 150" fill="none"/></defs>'
        f'<circle cx="150" cy="150" r="147" {fondo} stroke="{acento}" stroke-width="2.5"/>'
        f'<circle cx="150" cy="150" r="137" fill="none" stroke="{C["borde_int"]}" stroke-width="1"/>'
        f'<text font-family="{_SELLO_FB}" font-size="12.5" letter-spacing="2.4" font-weight="600" fill="{C["ink"]}">'
        f'<textPath href="#arcTop" startOffset="50%" text-anchor="middle">REFUGIO CLIMÁTICO NATURAL</textPath></text>'
        f'<g transform="translate(150,60)">'
        f'<path d="M 4.5 -10 A 12 12 0 1 0 4.5 10 A 9.5 9.5 0 1 1 4.5 -10 Z" fill="{acento}" opacity="{opac}"/>'
        f'<circle cx="8" cy="-8" r="2.4" fill="{acento}"/></g>'
        f'<g transform="translate(150,90)">'
        f'<rect x="-74" y="-9.5" width="148" height="19" rx="9.5" fill="none" stroke="{acento}" stroke-width="1"/>'
        f'<text x="0" y="3.5" font-family="{_SELLO_FB}" font-size="8.5" letter-spacing="1.1" font-weight="700" fill="{acento}" text-anchor="middle">{etiqueta}</text></g>'
        f'<text x="150" y="142" font-family="{_SELLO_FD}" font-size="44" font-weight="600" fill="{C["metric"]}" text-anchor="middle">{_n_es(tmin)}°</text>'
        f'<text x="150" y="158" font-family="{_SELLO_FB}" font-size="10" letter-spacing=".4" fill="{C["sub"]}" text-anchor="middle">mín. media en agosto</text>'
        f'<line x1="112" y1="167" x2="188" y2="167" stroke="{C["borde_int"]}" stroke-width="1"/>'
        f'<text x="150" y="183" font-family="{_SELLO_FB}" font-size="11.5" font-weight="600" fill="{C["verde"]}" text-anchor="middle">{nt_txt} noches tropicales/año</text>'
        f'<text x="150" y="205" font-family="{_SELLO_FD}" font-size="14.5" font-weight="600" fill="{C["ink"]}" text-anchor="middle">{zona_up}</text>'
        f'<text x="150" y="218" font-family="{_SELLO_FB}" font-size="9" letter-spacing="1" fill="{C["sub"]}" text-anchor="middle">{prov.upper()}</text>'
        f'<text x="150" y="233" font-family="{_SELLO_FB}" font-size="8" fill="{C["sub"]}" text-anchor="middle" opacity=".9">{fuente_linea}</text>'
        f'<text x="150" y="247" font-family="{_SELLO_FB}" font-size="9.5" letter-spacing=".5" font-weight="600" fill="{C["dominio"]}" text-anchor="middle">nochetropical.es</text>'
        f'<text font-family="{_SELLO_FB}" font-size="8.5" letter-spacing="1.5" font-weight="600" fill="{C["sub"]}">'
        f'<textPath href="#arcBot" startOffset="50%" text-anchor="middle">BASADO EN DATOS DE AEMET · 2017–2026</textPath></text>'
        f'</svg>')


def cargar_hoteles(estaciones: list) -> list:
    """Lee datos/hoteles.csv y enriquece cada hotel con el dato REAL de su
    estación de referencia (fuente única: el ranking). Descarta silenciosamente
    los que no encuentren estación."""
    ruta = AEMET_DIR / "datos" / "hoteles.csv"
    if not ruta.exists():
        return []
    porid = {e["id"]: e for e in estaciones}
    out = []
    for fila in csv.DictReader(ruta.open(encoding="utf-8")):
        e = porid.get(fila["est_ref_indicativo"])
        if not e:
            continue
        out.append({
            "hotel": fila["hotel"], "municipio": fila["municipio"],
            "provincia": fila["provincia"], "nivel": fila["nivel"].strip().upper(),
            "ref_desc": fila.get("ref_desc", ""), "slug_booking": fila["booking_slug"],
            "web": fila.get("web", ""), "telefono": fila.get("telefono", ""),
            "slug": slug(fila["hotel"]), "est_id": fila["est_ref_indicativo"],
            "tmin": e["tmin"], "nt": e["nt"], "alt": e["alt"], "est": e["loc"],
            "lat": e["lat"], "lon": e["lon"],  # coords de la estación de ref. (para el buscador cercano)
        })
    return out


PAGINA_HOTELES = r"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hoteles donde el verano te deja dormir · La geografía del descanso | nochetropical.es</title>
<meta name="description" content="__DESC__">
<link rel="canonical" href="__SITE__/hoteles-refugio-climatico/">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="article">
<meta property="og:title" content="Hoteles de España donde se duerme con manta en verano">
<meta property="og:description" content="__DESC__">
<meta property="og:url" content="__SITE__/hoteles-refugio-climatico/">
<meta property="og:image" content="__OGIMG__">
<meta property="og:image:alt" content="Sello Refugio Climático Natural: certificado con datos de AEMET">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__OGIMG__">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900&family=Lora:ital,wght@0,400;0,600&display=swap" rel="stylesheet">
<style>
 :root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--verde:#8fb07a;--fd:"Fraunces",Georgia,serif;--fb:"Lora",Georgia,serif;--fm:ui-monospace,monospace}
 *{margin:0;padding:0;box-sizing:border-box}
 body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.65;-webkit-font-smoothing:antialiased}
 .wrap{max-width:min(94vw,1120px);margin:0 auto;padding:0 24px}
 a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}
 header.h{padding:46px 0 10px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}
 .crumb{font-size:13px;color:var(--muted)}
 .kick{font:600 12px/1 var(--fb);letter-spacing:.16em;text-transform:uppercase;color:var(--teja);margin:16px 0 8px}
 h1{font-family:var(--fd);font-weight:900;font-size:clamp(28px,5.4vw,44px);line-height:1.05;max-width:20ch}
 h1 em{font-style:italic;color:var(--teja2)}
 .intro{color:var(--muted);font-size:clamp(15px,2.4vw,17.5px);margin:16px 0 0;max-width:66ch}
 .intro b{color:var(--paper)}
 .disc{margin:18px 0 0;font-size:12.5px;color:#9a8a6f;background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:11px 14px;max-width:none}
 .disc b{color:var(--muted)}
 /* Sello de ejemplo: imagen REDONDA y prominente en la cabecera. Es la pieza
    que Google puede tomar como miniatura del resultado (contrasta con las fotos
    cuadradas), y a la vez enseña al visitante qué certificado otorgamos. */
 .sello-ej{float:right;width:min(40vw,210px);margin:2px 0 14px 26px;text-align:center}
 .sello-ej img{width:100%;height:auto;display:block;filter:drop-shadow(0 8px 26px rgba(0,0,0,.45))}
 .sello-ej figcaption{font-size:12.5px;color:var(--muted);margin-top:9px;line-height:1.45}
 .sello-ej figcaption a{color:var(--teja2)}
 @media(max-width:560px){.sello-ej{float:none;width:200px;margin:16px auto 6px}}
 .edwrap{padding:26px 0 6px;background:radial-gradient(120% 70% at 50% 0,#1d150d,var(--bg) 70%)}
 .ed{max-width:720px}
 .ed .lead{font-family:var(--fd);font-weight:600;font-size:clamp(22px,4vw,32px);line-height:1.22;color:var(--paper);margin:6px 0 22px}
 .ed .lead b{color:var(--teja2);font-weight:600}
 .ed h2{font-family:var(--fd);font-weight:600;font-size:clamp(20px,3.4vw,26px);color:var(--teja2);margin:30px 0 12px;line-height:1.18}
 .ed p{font-size:clamp(15.5px,2.3vw,17px);color:#d9ccb6;margin:0 0 16px;line-height:1.75}
 .ed p b{color:var(--paper)}
 .ed .firma{font-family:var(--fd);font-size:clamp(17px,2.6vw,19px);color:var(--paper);border-left:3px solid var(--teja);padding:4px 0 4px 16px;margin-top:24px}
 section{padding:20px 0}
 h2.reg{font-family:var(--fd);font-weight:600;font-size:clamp(19px,3.2vw,24px);color:var(--teja2);margin:26px 0 12px;padding-bottom:7px;border-bottom:1px solid var(--line)}
 .hgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
 .hcard{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:15px;padding:16px 17px;display:flex;flex-direction:column}
 .hcard.nA{border-left:3px solid var(--teja)}
 .hcard.nB{border-left:3px solid var(--teal)}
 .htop{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px}
 .niv{font-size:11.5px;font-weight:700;letter-spacing:.02em;color:var(--muted)}
 .sello{font-size:11.5px;color:var(--teal)}
 .hcard h3{font-family:var(--fd);font-weight:600;font-size:18px;color:var(--paper);line-height:1.2}
 .hcard h3 a{color:var(--paper)}.hcard h3 a:hover{color:var(--teja2);text-decoration:none}
 .loc{font-size:13px;color:var(--muted);margin:3px 0 12px}
 .stats{display:flex;gap:14px;margin-bottom:12px}
 .st{flex:1;background:#0c0906;border:1px solid var(--line);border-radius:10px;padding:9px 11px}
 .st .v{display:block;font-family:var(--fm);font-weight:700;font-size:19px;color:var(--teal)}
 .st .v.tj{color:var(--teja2)}
 .st .k{display:block;font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-top:2px}
 .ref{font-size:12.5px;color:#9a8a6f;margin:-4px 0 12px;font-style:italic}
 .btn{margin-top:auto;display:block;text-align:center;background:var(--teja);color:#1a1209;font-weight:700;font-size:14px;padding:11px 14px;border-radius:10px}
 .btn:hover{background:var(--teja2);text-decoration:none}
 .btn.web{background:transparent;border:1px solid var(--teja);color:var(--teja2)}
 .btn.web:hover{background:rgba(217,116,78,.12)}
 .noweb{margin-top:auto;font-size:12.5px;color:#9a8a6f;background:#0c0906;border:1px dashed var(--line);border-radius:10px;padding:10px 12px;line-height:1.5}
 .noweb a{color:var(--teal)}
 .cta{margin:30px 0 6px;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:24px;text-align:center}
 .cta b{font-family:var(--fd);font-weight:600;font-size:20px;color:var(--paper)}
 .cta p{color:var(--muted);font-size:14.5px;margin:8px auto 0;max-width:56ch}
 .botones{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin-top:16px}
 .b2{display:inline-block;padding:12px 18px;border-radius:11px;font-weight:700;font-size:14.5px}
 .b2.pri{background:var(--teja);color:#1a1209}.b2.pri:hover{background:var(--teja2);text-decoration:none}
 .b2.sec{background:transparent;border:1px solid var(--teja);color:var(--teja2)}.b2.sec:hover{background:rgba(217,116,78,.12);text-decoration:none}
 .faq{margin:10px 0}.faq details{border-bottom:1px solid var(--line);padding:14px 0}
 .faq summary{font-family:var(--fd);font-weight:600;font-size:16.5px;color:var(--paper);cursor:pointer;list-style:none}
 .faq summary::-webkit-details-marker{display:none}
 .faq summary::before{content:"+ ";color:var(--teja)}
 .faq details[open] summary::before{content:"– "}
 .faq p{margin:10px 0 2px;font-size:15px;color:var(--muted)}
 @media(min-width:900px){.faq{columns:2;column-gap:48px}.faq details{break-inside:avoid}}
 /* Banner de cabecera (ilustración SVG nocturna, autocontenida) */
 .heroimg{width:100%;max-height:300px;overflow:hidden;line-height:0;border-bottom:1px solid var(--line)}
 .heroimg svg{width:100%;height:auto;display:block}
 @media(max-width:560px){.heroimg{max-height:190px}}
 /* Buscador "cerca de mí" */
 .buscar{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:22px 22px 24px;margin:6px 0 28px}
 .buscar h2{font-family:var(--fd);font-weight:600;font-size:clamp(19px,3.4vw,26px);color:var(--paper);margin:0 0 5px;border:0;padding:0}
 .buscar .sub{font-size:14.5px;color:var(--muted);margin:0 0 16px;max-width:64ch}
 .geobtn{width:100%;background:var(--teja);color:#1a1209;border:0;border-radius:12px;font-weight:700;font-size:16px;padding:14px;cursor:pointer;font-family:var(--fb)}
 .geobtn:hover{background:var(--teja2)}
 .geobtn:disabled{opacity:.6;cursor:default}
 .ghint{font-size:12.5px;color:#9a8a6f;margin:10px 0 0}
 .prov-pick{margin-top:14px;position:relative}
 .prov-pick select{width:100%;background:#2c2216;border:1.5px solid #5f5138;border-radius:11px;color:var(--paper);font-size:15px;padding:12px 14px;font-family:var(--fb);cursor:pointer;appearance:none;-webkit-appearance:none}
 .prov-pick select:focus{outline:2px solid var(--teja);outline-offset:1px}
 .prov-pick::after{content:"";position:absolute;right:16px;top:50%;width:9px;height:9px;border-right:2.5px solid var(--teja);border-bottom:2.5px solid var(--teja);transform:translateY(-70%) rotate(45deg);pointer-events:none}
 .buscar .msg{font-family:var(--fd);font-weight:600;font-size:16px;color:var(--paper);margin:20px 0 0}
 .hres{list-style:none;padding:0;margin:12px 0 0;display:grid;gap:11px}
 .hres li{background:#0c0906;border:1px solid var(--line);border-radius:13px;padding:14px 16px}
 .hres li.first{border-color:var(--teja)}
 .hr-top{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
 .hr-n{font-family:var(--fd);font-weight:600;font-size:17px;color:var(--paper)}
 .hr-km{font-family:var(--fm);font-weight:700;font-size:15px;color:var(--teja2);white-space:nowrap}
 .hr-loc{font-size:13px;color:var(--muted);margin:3px 0 0;line-height:1.5}
 .hr-loc .b{color:var(--teal)}
 .hr-acc{display:flex;gap:8px;flex-wrap:wrap;margin-top:11px}
 .hr-acc a{font:600 13px/1 var(--fb);padding:8px 13px;border-radius:9px;border:1px solid var(--line);color:var(--paper);text-decoration:none}
 .hr-acc a.pri{background:var(--teja);color:#1a1209;border-color:var(--teja)}
 .hr-acc a:hover{border-color:var(--teja);color:var(--teja2);text-decoration:none}
 .hr-acc a.pri:hover{color:#1a1209;background:var(--teja2)}
 .dirnote{font-size:13.5px;color:var(--muted);margin:0 0 18px;line-height:1.55}
 .dirnote b{color:var(--paper)}
 __NAVCSS__
 __FOOTERCSS__
</style></head><body>
__NAV__
<div class="heroimg">
  <svg viewBox="0 0 1200 300" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Ilustración de un pueblo de montaña de noche bajo la luna: una casa con la ventana iluminada y las cumbres frescas donde se duerme sin aire acondicionado">
    <defs>
      <linearGradient id="hsky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#160f08"/><stop offset=".5" stop-color="#33220f"/><stop offset="1" stop-color="#7a4326"/>
      </linearGradient>
      <radialGradient id="hmoon" cx="42%" cy="40%" r="60%">
        <stop offset="0" stop-color="#fdf6e9"/><stop offset="1" stop-color="#e6c295"/>
      </radialGradient>
      <mask id="hcut"><rect width="1200" height="300" fill="#fff"/><circle cx="1012" cy="60" r="30" fill="#000"/></mask>
    </defs>
    <rect width="1200" height="300" fill="url(#hsky)"/>
    <g fill="#efe6d6" opacity=".9">
      <circle cx="120" cy="48" r="1.6"/><circle cx="230" cy="92" r="1.1"/><circle cx="300" cy="38" r="1.9"/>
      <circle cx="440" cy="66" r="1.3"/><circle cx="560" cy="34" r="1.6"/><circle cx="655" cy="96" r="1"/>
      <circle cx="770" cy="52" r="1.5"/><circle cx="900" cy="40" r="1.2"/><circle cx="185" cy="128" r="1"/>
      <circle cx="392" cy="120" r="1.2"/><circle cx="520" cy="140" r=".9"/><circle cx="705" cy="128" r="1.3"/>
    </g>
    <g mask="url(#hcut)"><circle cx="994" cy="66" r="38" fill="url(#hmoon)"/></g>
    <path d="M0 205 L150 152 L320 200 L470 142 L640 196 L820 138 L1000 192 L1200 150 L1200 300 L0 300 Z" fill="#2a1c10" opacity=".9"/>
    <path d="M0 250 L180 198 L360 246 L520 190 L720 250 L900 200 L1080 250 L1200 214 L1200 300 L0 300 Z" fill="#160f08"/>
    <g transform="translate(150 196)">
      <rect x="0" y="0" width="58" height="46" fill="#0c0805"/>
      <path d="M-8 0 L29 -24 L66 0 Z" fill="#241b11"/>
      <rect x="21" y="15" width="16" height="18" fill="#f6b567"/>
      <rect x="21" y="15" width="16" height="18" fill="none" stroke="#0c0805" stroke-width="2.4"/>
    </g>
  </svg>
</div>
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">nochetropical.es</a> · Hoteles en refugios climáticos</nav>
  <div class="kick">Turismo climático · Datos AEMET 2017–2026</div>
  __EJEMPLO__
  <h1>Hoteles donde se duerme con <em>manta</em> en verano</h1>
  <p class="intro">Mientras la ola de calor asa el país y las noches tropicales impiden dormir en la costa, hay una <b>España que no arde</b>: valles y sierras donde la mínima nocturna baja sistemáticamente de los 20&nbsp;°C. Hemos cruzado 10 veranos de <b>datos de AEMET</b> con la oferta hotelera para reunir hoteles en <b>refugios climáticos naturales</b>, de __FRIO__ para arriba. Se duerme fresco, sin depender del aire acondicionado.</p>
  <p class="disc"><b>Divulgación:</b> esta página contiene enlaces de afiliado de Booking.com. Si reservas a través de ellos, podemos recibir una comisión <b>sin coste adicional para ti</b>. La certificación climática se basa en datos oficiales de AEMET y es independiente de la relación de afiliación: certifica el clima de la zona, no el interior del establecimiento.</p>
</div></header>

<section class="edwrap"><div class="wrap ed">
  <p class="lead">El verano no se mide por la temperatura del día.<br><b>Se mide por cómo has dormido esta noche.</b></p>
  <p>Durante años nos enseñaron a mirar el tiempo de una forma sencilla: ¿cuál será la máxima?, ¿llegaremos a 40 grados?, ¿habrá ola de calor? Pero casi nadie hace la pregunta más importante —<b>¿a cuánto bajará la temperatura mientras duermes?</b>—, y esa respuesta puede cambiar por completo tus vacaciones.</p>
  <p>Porque el verdadero problema del verano no siempre es el calor del día. Empieza cuando llega la noche… y el calor nunca se va. El enemigo no es el sol: es <b>una noche que nunca refresca</b>.</p>
  <p>Anoche, miles de personas volvieron a dormir con 28&nbsp;°C. Con la ventana abierta esperando una brisa que no llegó, el ventilador funcionando durante horas, buscando el lado frío de la almohada, levantándose una y otra vez, esperando que amaneciera. Y hoy dirán simplemente: «estoy cansado». Pero quizá el problema no sea el trabajo, ni el estrés, ni siquiera el calor del día. Quizá lleven semanas <b>sin una verdadera noche de descanso</b>.</p>
  <h2>Dormir bien no es un lujo: es una necesidad biológica</h2>
  <p>Nuestro organismo lleva miles de generaciones esperando la misma señal: que al caer la noche <b>la temperatura descienda</b>. Entonces el cuerpo se relaja, baja su temperatura interna y se prepara para un sueño reparador. Es en esas horas cuando el cerebro ordena los recuerdos y recuperamos energía. La noche no es un tiempo muerto: es <b>el taller donde el cuerpo se repara</b>.</p>
  <p>Pero el calor no termina cuando se pone el sol. Las calles, las fachadas, las paredes, los muebles, el colchón… todo sigue irradiando el calor acumulado durante toda la madrugada. Y aunque duermas ocho horas, puede que <b>no hayas descansado</b>.</p>
  <h2>Y entonces, una noche, la ventana</h2>
  <p>Viajas. Quizá a un pequeño pueblo de montaña, porque unos amigos insistieron o encontraste una oferta. Y esa primera noche ocurre algo que casi habías olvidado: abres la ventana y entra aire fresco. No enciendes el aire acondicionado. No necesitas ventilador. Buscas una sábana; de madrugada, tal vez una rebeca. A la mañana siguiente no piensas en grados: piensas algo mucho más simple, <b>«hacía tiempo que no dormía tan bien»</b>. Y casualmente, la noche siguiente se repite, vuelves a percibir la misma sensación. Y al final te das cuenta de que es el sitio: tiene <a href="__SITE__/microclimas/">su propio microclima</a>, al que la ola de calor le afecta, <b>pero menos</b>.</p>
  <p>Llamas a un amigo y te cuenta que siguen encerrados, que fuera hay 33 grados, que el aire lleva desde el mediodía. Miras por la ventana, respiras el aire fresco de la mañana y piensas: <b>«¿eso también es verano?»</b></p>
  <h2>La geografía del descanso</h2>
  <p>Durante décadas elegimos destino por la playa, la gastronomía, los monumentos, la cercanía. Quizá ha llegado el momento de añadir un criterio mucho más importante: <b>¿cómo se duerme aquí en verano?</b> Porque la temperatura nocturna también es calidad de vida, salud, bienestar y sostenibilidad —y quizá el lujo más valioso que nos queda—.</p>
  <p>El verdadero lujo del verano no es una piscina infinita, ni cinco estrellas, ni un spa. Es <b>despertarte y darte cuenta de que has dormido tan bien que ni siquiera has pensado en el calor</b>. En estos pueblos, una manta ligera en agosto deja de ser una rareza para convertirse en un privilegio; el silencio sustituye al zumbido de los compresores; y el cuerpo reencuentra el descanso que llevaba semanas buscando.</p>
  <p class="firma">Estos son los hoteles de esa geografía. Bienvenido al lugar donde el verano <b>todavía te deja dormir</b>.</p>
</div></section>

<section><div class="wrap">
  <div class="buscar" id="cerca">
    <h2>¿Dónde se duerme fresco cerca de ti?</h2>
    <p class="sub">Comparte tu ubicación y te ordenamos estos hoteles-refugio del más cercano al más lejano, con la distancia en línea recta. Todos en zonas donde la mínima de verano baja de 20&nbsp;°C, medido con 10 años de datos de AEMET.</p>
    <button class="geobtn" id="geoh">📍 Usar mi ubicación</button>
    <p class="ghint" id="ghinth">Funciona mejor desde el <b>móvil</b>: en el ordenador el navegador puede no tener activada la ubicación. No la guardamos — el cálculo ocurre en tu propio navegador.</p>
    <div class="prov-pick"><select id="provh" aria-label="Elegir provincia"><option value="">O elige por provincia…</option></select></div>
    <p class="msg" id="hmsgh"></p>
    <ul class="hres" id="hresh"></ul>
  </div>

  <p class="dirnote">Abajo, el <b>directorio completo</b> de hoteles-refugio agrupado <b>por regiones</b> (no por distancia): esa lista es igual para todo el mundo. Para ordenarla por <b>cercanía a ti</b>, usa el buscador de aquí arriba.</p>

  __LISTADO__

  <div class="cta">
    <b>¿Tienes un hotel o casa rural en un sitio fresco? ¿O conoces alguno que debería figurar en esta lista?</b>
    <p>Auditamos gratis los registros históricos de AEMET de ese municipio. Si cumple el criterio de confort nocturno, entra en el directorio con su <b>sello de Refugio Climático Natural</b>.</p>
    <div class="botones">
      <a class="b2 pri" href="__SITE__/tu-hotel/">Solicitar auditoría para mi hotel →</a>
      <a class="b2 sec" href="__SITE__/la-espana-que-nunca-se-colorea/">Ver el estudio del calor →</a>
    </div>
  </div>

  <h2 class="reg" style="color:var(--teja)">Preguntas frecuentes</h2>
  <div class="faq">__FAQ__</div>
</div></section>
__FOOTER__
<script>
const HOT=__HOTELES__, SITE="__SITE__";
function hav(la1,lo1,la2,lo2){var R=6371,r=Math.PI/180,dLa=(la2-la1)*r,dLo=(lo2-lo1)*r;
 var x=Math.sin(dLa/2)**2+Math.cos(la1*r)*Math.cos(la2*r)*Math.sin(dLo/2)**2;return 2*R*Math.asin(Math.sqrt(x));}
function km(d){return d<10?d.toFixed(1).replace(".",","):Math.round(d)+"";}
function d1(x){return x.toFixed(1).replace(".",",");}
function ntTxt(nt){return nt<0.05?"0 noches tropicales/año":(nt<1?"<1 noche tropical/año":d1(nt)+" noches/año");}
function fila(h,distTxt,first){
 var li=document.createElement("li"); li.className=first?"first":"";
 var acc="<a class='pri' href='"+h.u+"'"+(h.rel?" target='_blank' rel='"+h.rel+"'":"")+">"+h.ut+"</a>"
   +"<a href='"+SITE+"/hoteles-refugio-climatico/"+h.s+"/'>Ficha y datos</a>";
 li.innerHTML="<div class='hr-top'><span class='hr-n'>"+h.n+"</span>"+(distTxt?"<span class='hr-km'>"+distTxt+"</span>":"")+"</div>"
   +"<div class='hr-loc'>"+h.m+" · "+h.p+" · "+h.a+"&nbsp;m · <span class='b'>"+d1(h.t)+"° mín. agosto · "+ntTxt(h.nt)+"</span></div>"
   +"<div class='hr-acc'>"+acc+"</div>";
 return li;
}
function msg(t){document.getElementById("hmsgh").textContent=t;}
function pinta(la,lo,origen){
 var L=HOT.map(function(h){return {h:h,d:hav(la,lo,h.la,h.lo)};}).sort(function(a,b){return a.d-b.d;});
 var ol=document.getElementById("hresh"); ol.innerHTML="";
 L.forEach(function(o,i){ol.appendChild(fila(o.h,km(o.d)+" km",i===0));});
 msg("Los "+L.length+" hoteles-refugio, del más cercano al más lejano"+(origen?" a "+origen:"")+":");
 document.getElementById("hmsgh").scrollIntoView({behavior:"smooth",block:"nearest"});
}
function pintaProv(p){
 var L=HOT.filter(function(h){return h.p===p;}).sort(function(a,b){return a.nt-b.nt;});
 var ol=document.getElementById("hresh"); ol.innerHTML="";
 L.forEach(function(h,i){ol.appendChild(fila(h,"",i===0));});
 msg("Hoteles-refugio en "+p+" (del más fresco al menos):");
}
(function(){
 var gb=document.getElementById("geoh"), gh=document.getElementById("ghinth");
 gb.addEventListener("click",function(){
  if(!navigator.geolocation){gh.textContent="Tu navegador no permite la geolocalización. Elige tu provincia aquí abajo.";return;}
  gb.disabled=true; gb.textContent="Buscando tu ubicación…";
  navigator.geolocation.getCurrentPosition(function(p){
   gb.disabled=false; gb.textContent="📍 Usar mi ubicación";
   pinta(p.coords.latitude,p.coords.longitude,"tu ubicación");
  },function(){
   gb.disabled=false; gb.textContent="📍 Usar mi ubicación";
   gh.textContent="No se pudo obtener tu ubicación (¿permiso denegado?). Elige tu provincia aquí abajo.";
  },{timeout:9000});
 });
 var sel=document.getElementById("provh");
 HOT.map(function(h){return h.p;}).filter(function(v,i,a){return a.indexOf(v)===i;})
   .forEach(function(p){var o=document.createElement("option");o.value=p;o.textContent=p;sel.appendChild(o);});
 sel.addEventListener("change",function(){ if(sel.value) pintaProv(sel.value); });
})();
</script>
</body></html>
"""


def construir_pagina_hoteles(hoteles: list, site: str) -> str:
    total = len(hoteles)
    # Agrupa por provincia manteniendo el orden del CSV (ya viene por regiones).
    orden_prov = []
    for h in hoteles:
        if h["provincia"] not in orden_prov:
            orden_prov.append(h["provincia"])
    tmin_min = min((h["tmin"] for h in hoteles), default=0)
    frescos = [h for h in hoteles if h["tmin"] < tmin_min + 0.05]
    hotel_frio = frescos[0] if frescos else (hoteles[0] if hoteles else None)
    desc = ("El verano no se mide por el día, sino por cómo duermes. Hoteles en refugios "
            "climáticos naturales de España donde la noche baja de 20 °C y se duerme "
            "fresco —con manta y sin aire acondicionado—, medido con 10 años de datos de "
            "AEMET. La geografía del descanso.")
    # Imagen DESTACADA de la página: el sello de refugio climático, en alta
    # resolución (>=1200 px), RÁSTER (Google no usa SVG como miniatura) y con
    # fondo transparente. Se sirve en tres relaciones de aspecto (1:1, 4:3,
    # 16:9) para el array "image" del schema, tal y como recomienda Google para
    # optimizar la miniatura del resultado. Los ficheros se renderizan aparte y
    # se commitean en docs/ (la Action no tiene navegador); si aún no están,
    # degradamos al sello de un hotel con PNG y a la og.png del sitio.
    feat = {r: f"sello-refugio-climatico-{r}.png" for r in ("1x1", "4x3", "16x9")}
    feat_ok = all((DOCS_DIR / f).exists() for f in feat.values())
    if feat_ok:
        og_img = f"{site}/{feat['1x1']}"
        schema_image = [f"{site}/{feat[r]}" for r in ("1x1", "4x3", "16x9")]
        destacada_src, destacada_w, destacada_h = og_img, "1200", "1200"
        destacada_alt = ("Sello Refugio Climático Natural: el certificado que otorgamos, "
                         "con datos de AEMET — mínima media de agosto y noches tropicales de la zona")
    else:
        ej = next((h for h in hoteles if h["nivel"] == "A" and h["nt"] < 0.05
                   and (DOCS_DIR / "badges" / f'{h["slug"]}.png').exists()), None)
        ej = ej or next((h for h in hoteles
                         if (DOCS_DIR / "badges" / f'{h["slug"]}.png').exists()), None)
        destacada_src = f'{site}/badges/{ej["slug"]}.png' if ej else ""
        destacada_w = destacada_h = "210"
        destacada_alt = (f'Sello Refugio Climático Natural con datos de AEMET — '
                         f'{ej["municipio"]} ({ej["provincia"]})' if ej else "")
        og_img = f"{site}/og.png"
        schema_image = ([destacada_src, f"{site}/og.png"] if destacada_src
                        else f"{site}/og.png")
    if destacada_src:
        ejemplo_html = (
            '<figure class="sello-ej">'
            f'<img src="{destacada_src}" width="{destacada_w}" height="{destacada_h}" '
            f'loading="eager" fetchpriority="high" alt="{destacada_alt}">'
            '<figcaption>El sello que otorgamos a cada refugio: acredita el clima '
            'nocturno de la zona con 10 años de datos de AEMET. '
            f'<a href="{site}/tu-hotel/">Certifica el tuyo →</a></figcaption></figure>')
    else:
        ejemplo_html = ""

    def tarjeta(h: dict) -> str:
        niv = h["nivel"]
        badge = ("🛡️ Refugio Certificado" if niv == "A" else "📍 Zona Verificada")
        nt_txt = "0" if h["nt"] < 0.05 else _n_es(h["nt"])
        ref = (f'<div class="ref">Dato de la {h["ref_desc"]}</div>' if niv == "B" and h["ref_desc"] else "")
        # Acción según disponibilidad: Booking (afiliado) > web oficial > sin
        # enlace (el hotel figura igual: le da visibilidad y es puerta de entrada
        # a la certificación aunque aún no venda online).
        if h["slug_booking"]:
            cj = cj_deeplink(h["slug_booking"], h["slug"])
            accion = (f'<a class="btn" href="{cj}" target="_blank" rel="sponsored nofollow noopener">'
                      'Ver disponibilidad en Booking →</a>')
        elif h.get("web"):
            accion = (f'<a class="btn web" href="{h["web"]}" target="_blank" rel="nofollow noopener">'
                      'Web oficial del alojamiento →</a>')
        else:
            accion = ('<div class="noweb">Alojamiento local · sin reserva online. '
                      f'<a href="{site}/tu-hotel/">¿Eres tú? Añade tu enlace →</a></div>')
        return (
            f'<article class="hcard n{niv}">'
            f'<div class="htop"><span class="niv">{badge}</span>'
            f'<a class="sello" href="{site}/hoteles-refugio-climatico/{h["slug"]}/" '
            f'title="Ficha y certificado de {h["hotel"]}">ficha y certificado →</a></div>'
            f'<h3><a href="{site}/hoteles-refugio-climatico/{h["slug"]}/">{h["hotel"]}</a></h3>'
            f'<div class="loc">{h["municipio"]} · {h["provincia"]} · {miles(h["alt"])}&nbsp;m</div>'
            f'<div class="stats"><div class="st"><span class="v">{_n_es(h["tmin"])}°</span>'
            f'<span class="k">mín. media agosto</span></div>'
            f'<div class="st"><span class="v tj">{nt_txt}</span>'
            f'<span class="k">noches tropicales/año</span></div></div>'
            f'{ref}{accion}'
            f'</article>')

    secciones = []
    for prov in orden_prov:
        cards = "".join(tarjeta(h) for h in hoteles if h["provincia"] == prov)
        secciones.append(f'<h2 class="reg">{prov}</h2><div class="hgrid">{cards}</div>')
    listado = "".join(secciones)

    # Payload del BUSCADOR "cerca de mí": mismo dataset que la lista (así un hotel
    # nuevo en hoteles.csv aparece a la vez en la lista y en el buscador). La
    # ubicación de cada hotel es la de su estación de AEMET de referencia; para el
    # enlace de acción se prioriza Booking (afiliado) > web oficial > ficha.
    def _accion_hotel(h: dict) -> tuple[str, str, str]:
        if h["slug_booking"]:
            return (cj_deeplink(h["slug_booking"], h["slug"]),
                    "Ver disponibilidad en Booking →", "sponsored nofollow noopener")
        if h.get("web"):
            return (h["web"], "Web oficial →", "nofollow noopener")
        return (f'{site}/hoteles-refugio-climatico/{h["slug"]}/', "Ver ficha y datos →", "")

    hoteles_js = json.dumps([
        dict(n=h["hotel"], m=h["municipio"], p=h["provincia"], la=h["lat"], lo=h["lon"],
             t=h["tmin"], nt=h["nt"], a=h["alt"], s=h["slug"], niv=h["nivel"],
             u=_accion_hotel(h)[0], ut=_accion_hotel(h)[1], rel=_accion_hotel(h)[2])
        for h in hoteles], ensure_ascii=False)

    faq = [
        ("¿De verdad se duerme sin aire acondicionado en estos hoteles?",
         "El sello certifica el CLIMA de la zona, no el interior del edificio: en la "
         "estación de AEMET más representativa, la mínima de verano baja de 20 °C casi "
         "todas las noches, así que el entorno refresca de madrugada y se duerme fresco "
         "de forma natural. Cada hotel decide su equipamiento."),
        ("¿Cómo se eligen los hoteles?",
         "Cruzamos 10 veranos de datos de AEMET (2017–2026) con la oferta hotelera y "
         "seleccionamos alojamientos en zonas con mínimas nocturnas por debajo de 20 °C "
         "casi todo el verano. El dato de cada ficha sale de una estación real."),
        ("¿Qué diferencia hay entre «Refugio Certificado» y «Zona Verificada»?",
         "«Refugio Certificado» es cuando hay estación de AEMET en el propio municipio. "
         "«Zona Verificada» es cuando usamos la estación fiable más cercana; en ese caso "
         "la ficha indica de qué estación procede el dato. En ambos, la cifra es real."),
        ("¿Tienes un hotel o casa rural en un sitio fresco?",
         "Auditamos gratis los registros de AEMET de tu municipio. Si la mínima media de "
         "verano baja de 18 °C y no hay noches tropicales sostenidas, entras en el "
         "directorio con tu sello. Solicítalo en la página «¿Tienes un hotel?»."),
    ]
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "nochetropical.es", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Hoteles en refugios climáticos",
             "item": site + "/hoteles-refugio-climatico/"}]},
        {"@type": "Article",
         "headline": "Hoteles de España donde se duerme con manta en verano",
         "description": desc,
         "image": schema_image,
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "publisher": {"@type": "Organization", "name": "nochetropical.es",
                       "logo": {"@type": "ImageObject", "url": site + "/favicon.svg"}},
         "datePublished": "2026-07-26", "dateModified": date.today().isoformat(),
         "mainEntityOfPage": site + "/hoteles-refugio-climatico/"},
        {"@type": "ItemList", "name": "Hoteles en refugios climáticos naturales de España",
         "numberOfItems": total, "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": f"{h['hotel']} ({h['municipio']}, {h['provincia']})"}
            for i, h in enumerate(hoteles)]},
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq]},
    ]}, ensure_ascii=False)

    frio_txt = (f"{hotel_frio['municipio']} ({_n_es(hotel_frio['tmin'])}°)" if hotel_frio else "la montaña interior")
    return (PAGINA_HOTELES
            .replace("__NAVCSS__", CSS_NAV_ESCUETO)
            .replace("__FOOTERCSS__", CSS_FOOTER_ESCUETO)
            .replace("__NAV__", nav_escueto_html(site))
            .replace("__FOOTER__", footer_escueto_html(site))
            .replace("__SCHEMA__", schema)
            .replace("__DESC__", desc)
            .replace("__TOTAL__", str(total))
            .replace("__EJEMPLO__", ejemplo_html)
            .replace("__OGIMG__", og_img)
            .replace("__FRIO__", frio_txt)
            .replace("__LISTADO__", listado)
            .replace("__HOTELES__", hoteles_js)
            .replace("__FAQ__", faq_html(faq))
            .replace("__SITE__", site)
            .replace("__HOME__", site + "/"))


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ===========================================================================
# EL OBSERVATORIO DEL DESCANSO — "¿Cómo has dormido esta noche?"
# Producto de ciencia ciudadana: cada mañana, en 10 s, la gente cuenta cómo ha
# dormido y entre todos construyen el mapa del descanso. Filosofía: medimos la
# EXPERIENCIA humana, no la temperatura (que es contexto). Honestidad: la
# credibilidad es el activo — NADA de votos falsos ni contadores inflados. El
# mapa nunca está vacío porque se SIEMBRA con la expectativa real de AEMET
# (etiquetada como tal); los votos reales se superponen ("AEMET esperaba X, la
# gente dice Y"), que es la tesis del proyecto. Backend Apps Script (fase 2).
# ===========================================================================
_OBS_NA = str.maketrans("áàäâéèëêíìïîóòöôúùüûñ", "aaaaeeeeiiiioooouuuun")


def _obs_baseline(tmin: float) -> float:
    """Descanso ESPERADO 0-10 desde la Tmin media de verano (dato AEMET). Se
    muestra etiquetado como expectativa, no como voto."""
    return max(1.0, min(9.9, round(10 - (tmin - 9) * 0.52, 1)))


def _obs_frase(tmin: float) -> str:
    return ("Aquí la noche casi siempre refresca." if tmin < 12 else
            "Suele refrescar de madrugada." if tmin < 16 else
            "La noche afloja, pero no del todo." if tmin < 19 else
            "Aquí la noche no perdona.")


def publicar_lugares() -> int:
    """Publica docs/datos/lugares.json — [[id, nombre, lat, lon], ...] — desde
    datos/lugares.csv: 7.157 poblaciones españolas con coordenadas.

    Para qué: el Observatorio guarda la noche con el nombre del PUEBLO donde se
    ha dormido, no con el de la estación de AEMET más cercana. Quien vota en
    Dénia aparece como Dénia (y no como Pego, que es su estación de referencia
    climática). La detección es automática desde la ubicación del móvil: no se
    pregunta nada, no hay pasos extra.

    Origen de los datos: GeoNames (CC BY 4.0) vía el espejo lutangar/cities.json,
    con la grafía oficial del nomenclátor del INE cuando el nombre coincide. Se
    sirve aparte y se descarga solo al votar, para no engordar la página.
    Devuelve 0 si aún no está el CSV (la web sigue funcionando igual)."""
    origen = AEMET_DIR / "datos" / "lugares.csv"
    if not origen.exists():
        return 0
    filas = []
    with origen.open(encoding="utf-8", newline="") as fh:
        for f in csv.DictReader(fh):
            try:
                filas.append([f["id"], f["nombre"],
                              round(float(f["lat"]), 4), round(float(f["lon"]), 4)])
            except (KeyError, ValueError):
                continue
    destino = DOCS_DIR / "datos"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "lugares.json").write_text(
        json.dumps(filas, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    return len(filas)


def seed_observatorio(estaciones: list) -> list:
    """Semilla del mapa: zonas reconocibles repartidas por España con su índice
    de descanso ESPERADO según AEMET (para que el mapa nazca vivo, sin mentir)."""
    frags = ["cedrillas", "albarrac", "benasque", "canfranc", "torla", "rascafr",
             "sanabria", "reinosa", "alto campoo", "cervera de pisuerga", "vinuesa",
             "molina de aragon", "puerto del pico", "navacerrada", "isaba", "villablino",
             "riano", "formigal", "valencia aero", "palma", "cartagena", "alicante",
             "malaga aero", "murcia", "sevilla aero", "zaragoza", "barcelona", "bilbao",
             "madrid, retiro", "valladolid", "cordoba aero", "granada aero", "santander",
             "coruna", "caceres", "badajoz", "albacete", "toledo", "almeria aero", "gijon"]
    porloc = [(e, e["loc"].lower().translate(_OBS_NA)) for e in estaciones]
    seen, out = set(), []
    for fr in frags:
        f = fr.translate(_OBS_NA)
        m = next((e for e, ln in porloc if f in ln), None)
        if not m or m["id"] in seen or m.get("tmin") is None:
            continue
        seen.add(m["id"])
        out.append({"n": m["loc"].split(",")[0][:22], "p": m["prov"],
                    "la": round(m["lat"], 3), "lo": round(m["lon"], 3),
                    "d": _obs_baseline(m["tmin"]), "t": round(m["tmin"], 1),
                    "f": _obs_frase(m["tmin"]), "id": m["id"]})
    return out


# Silueta de España para el mapa del Observatorio: SOLO el contorno —costa y
# frontera—, sin las rayas de las provincias, y ya proyectada al lienzo de
# 300x190 con la misma fórmula con la que proj() coloca los puntos. Se calculó
# una vez desde datos/spain-provinces.geojson (pintando el país en una rejilla
# fina y trazando su contorno: el geojson no es topológicamente limpio y unir
# los polígonos por sus tramos devolvía las 52 provincias) y se escribe aquí
# hecha, para no arrastrar 1,4 MB de geojson hasta el navegador. Si algún día
# cambia la proyección del mapa, hay que volver a generarla.
SILUETA_ES = (
    "M102.0 189.9L105.0 188.3L105.1 186.2L105.9 185.7L107.0 186.0L109.1 181.0L110.0 180.0L1"
    "14.5 178.0L115.7 177.8L118.0 178.4L119.5 177.9L120.5 176.5L122.1 175.7L124.5 172.6L128"
    ".5 172.8L130.4 172.0L132.5 172.5L134.4 171.9L136.7 172.6L138.5 172.0L141.9 173.4L143.8"
    " 172.3L146.5 171.8L151.3 172.0L152.8 173.2L155.3 173.5L157.0 172.5L158.3 170.3L159.4 1"
    "69.9L160.6 170.4L161.8 169.8L163.1 170.4L164.9 172.6L165.8 172.5L168.4 169.8L168.6 168"
    ".7L169.5 167.6L170.2 167.2L172.1 160.7L174.5 157.4L177.9 155.6L178.6 154.2L181.0 152.4"
    "L183.2 152.2L184.3 153.0L185.4 152.0L187.1 151.8L188.2 152.6L191.9 151.4L192.2 150.6L1"
    "90.4 150.0L189.6 148.2L190.7 146.5L191.4 146.6L191.4 144.6L193.3 141.9L193.7 138.2L194"
    ".4 137.5L195.7 137.0L196.0 134.0L197.7 133.2L198.5 131.2L202.2 129.2L203.5 129.2L205.0"
    " 126.9L206.6 126.5L209.4 124.0L208.6 122.5L207.5 121.5L204.4 120.6L201.6 116.3L200.9 1"
    "14.4L201.1 113.0L199.2 108.0L199.5 105.1L201.4 102.1L203.4 97.8L205.2 95.7L206.2 93.2L"
    "207.9 91.8L208.8 89.8L212.7 85.3L215.6 79.7L216.8 78.8L219.0 78.6L221.2 77.1L221.3 76."
    "3L219.4 75.0L218.7 75.1L218.4 74.4L222.2 69.9L224.3 68.4L225.9 68.0L226.8 68.3L227.7 6"
    "7.2L229.3 66.6L230.9 66.6L233.1 65.5L243.9 62.9L247.0 58.8L256.3 54.2L257.2 53.3L258.9"
    " 52.7L261.4 50.9L262.4 49.5L263.7 49.0L264.7 46.9L264.2 45.3L264.3 44.0L262.9 42.5L262"
    ".8 40.6L263.5 39.5L264.4 39.9L265.3 39.7L266.0 37.8L263.8 37.3L263.5 35.3L262.0 35.3L2"
    "61.0 34.3L257.7 34.7L256.9 35.5L254.6 35.9L254.2 37.4L252.9 37.1L251.7 37.7L249.9 36.2"
    "L247.0 35.2L244.8 35.7L243.7 36.9L242.4 37.3L241.5 36.5L240.9 34.9L238.4 33.9L236.2 33"
    ".7L233.7 35.2L232.4 35.2L231.7 34.2L232.2 33.4L231.7 32.6L231.8 31.1L230.0 28.5L226.8 "
    "28.6L225.2 26.8L222.4 26.6L218.5 25.1L217.5 25.7L217.5 29.0L213.2 29.1L211.9 28.4L210."
    "6 29.4L209.7 28.3L208.5 28.0L205.0 29.2L203.4 28.3L202.3 26.7L199.5 25.3L197.9 26.5L19"
    "6.0 25.9L195.0 26.8L193.0 24.7L192.0 24.2L191.4 22.6L187.9 22.7L183.0 20.5L182.0 20.5L"
    "181.4 20.1L181.4 18.9L180.8 19.2L180.2 20.9L178.7 20.5L178.3 19.5L179.8 17.0L179.5 15."
    "3L177.0 14.6L175.8 15.6L175.1 14.3L173.5 14.3L172.1 12.3L169.9 13.6L166.1 14.7L164.4 1"
    "4.2L162.1 14.4L160.0 13.6L158.8 12.5L155.3 11.7L154.4 10.8L153.4 11.3L151.2 11.2L149.5"
    " 12.6L149.6 13.6L148.8 13.0L147.1 13.1L143.8 11.6L142.2 11.7L141.4 11.3L141.9 10.9L141"
    ".8 10.5L139.2 9.3L135.7 10.8L135.3 11.7L135.0 11.0L135.8 10.3L135.4 9.9L129.8 11.2L128"
    ".0 12.1L120.5 12.1L114.8 10.6L109.3 10.2L107.8 8.9L106.1 8.8L105.3 8.3L100.6 8.5L97.7 "
    "6.0L95.6 7.6L94.3 7.6L92.7 8.3L90.5 7.4L87.8 8.5L86.2 8.1L84.4 8.5L83.1 7.9L80.0 8.3L7"
    "7.5 7.9L75.7 8.4L71.6 8.2L69.7 5.5L66.4 4.0L65.3 5.3L64.5 3.8L63.8 3.6L63.8 2.9L61.0 4"
    ".8L60.5 4.7L60.2 5.4L60.4 3.4L59.9 3.1L58.0 4.5L56.8 4.6L56.4 5.8L53.2 8.1L52.3 8.2L51"
    ".8 10.5L53.0 11.5L54.3 11.6L53.8 13.3L52.1 12.0L51.6 12.2L51.2 13.4L50.7 12.6L49.8 12."
    "6L48.2 14.0L46.7 13.9L44.9 14.6L43.4 14.4L42.4 13.6L40.9 14.7L39.8 14.9L40.3 16.1L39.2"
    " 16.3L38.1 17.3L36.3 17.2L35.7 18.2L36.4 18.4L36.3 19.1L35.5 19.1L34.2 20.5L34.6 21.6L"
    "34.2 23.6L36.2 23.1L36.9 24.0L36.8 24.9L37.4 25.9L36.9 26.6L37.7 27.8L38.7 26.6L39.5 2"
    "6.9L41.0 26.6L39.0 28.8L38.1 31.8L39.2 33.1L41.2 30.4L42.0 30.9L42.4 29.5L43.1 30.3L43"
    ".9 30.1L42.6 32.4L42.7 34.5L42.1 34.7L41.7 33.8L40.7 34.5L41.6 34.9L42.4 36.3L43.6 36."
    "3L45.1 35.4L45.3 35.7L43.8 37.6L42.8 37.8L42.7 38.8L42.1 38.8L42.1 39.4L43.3 39.7L44.3"
    " 38.9L45.4 39.0L42.9 41.3L42.6 42.7L41.4 43.0L41.8 48.7L43.7 47.5L46.2 44.7L48.3 43.9L"
    "51.5 43.7L53.6 42.3L54.2 42.4L54.5 43.8L55.7 43.8L56.3 44.7L53.9 47.8L55.4 50.2L57.6 4"
    "9.8L58.3 48.8L59.2 48.6L59.8 47.6L60.2 49.2L61.0 48.5L63.3 47.9L65.3 48.6L65.3 49.7L67"
    ".6 48.9L68.6 50.1L69.5 49.3L70.6 49.4L72.6 48.6L73.4 46.0L74.4 46.2L75.3 46.9L76.7 46."
    "4L77.8 47.1L79.0 47.1L80.1 46.0L81.8 47.3L84.0 46.6L84.5 47.0L84.4 48.4L85.1 49.0L84.3"
    " 51.7L84.9 53.4L85.6 53.8L86.8 53.3L89.0 53.7L91.1 55.9L88.6 60.3L87.7 60.5L86.5 62.4L"
    "84.4 63.8L82.6 64.0L80.7 66.5L80.7 67.4L79.9 68.8L77.8 69.2L79.9 73.0L79.5 75.7L80.0 7"
    "7.8L79.3 79.9L80.0 81.3L79.1 83.2L80.2 85.3L78.6 87.3L77.3 87.6L75.9 88.8L76.2 90.7L77"
    ".4 91.1L78.7 93.4L78.0 96.9L76.6 98.4L76.0 101.6L73.7 102.2L71.7 101.8L70.3 102.4L66.6"
    " 102.1L67.2 103.7L70.7 106.9L70.4 109.0L71.9 110.9L72.0 112.8L73.7 113.7L74.1 115.4L76"
    ".2 115.3L77.1 117.1L75.5 119.8L75.5 121.1L71.6 124.5L71.7 127.1L70.7 129.0L70.3 131.3L"
    "71.3 132.0L74.7 137.7L77.2 136.8L77.4 137.1L76.2 141.3L74.4 140.9L73.8 141.8L71.7 142."
    "3L71.0 145.2L68.5 148.1L66.8 153.1L67.9 155.0L68.4 160.0L68.9 161.6L75.3 160.9L78.4 16"
    "2.1L84.9 166.3L86.5 168.2L87.4 170.4L88.1 170.8L86.7 172.3L87.5 174.6L90.3 176.1L90.4 "
    "177.7L91.3 177.5L90.1 179.2L94.0 185.4L96.2 185.6L98.1 187.7L100.9 188.6ZM261.4 111.3L"
    "264.7 109.2L266.0 105.9L268.7 102.1L269.0 100.7L268.9 100.0L267.2 99.1L265.1 100.2L263"
    ".1 99.0L262.9 97.9L263.9 97.5L264.1 96.7L262.6 97.1L262.1 96.5L263.8 95.3L263.8 94.9L2"
    "62.2 95.6L259.5 95.8L257.7 97.1L256.6 97.3L248.6 103.8L249.3 105.1L250.7 105.1L251.4 1"
    "06.8L252.3 105.1L254.5 104.4L255.7 105.5L255.8 108.0L256.4 108.9L259.8 109.2ZM283.7 98"
    ".3L284.4 97.6L284.3 95.9L283.7 94.2L282.2 93.1L281.9 92.3L276.8 92.4L275.3 93.1L275.3 "
    "93.8L275.9 94.0L275.9 95.6L278.4 95.4ZM230.6 121.7L231.8 120.0L232.6 119.8L234.9 117.3"
    "L234.6 115.7L233.4 115.1L230.0 116.3L229.2 117.1L229.0 118.4L227.8 118.6L228.0 121.1L2"
    "29.0 120.8ZM230.9 126.1L231.9 125.5L233.4 126.2L234.3 125.7L233.0 125.4L231.7 123.8L23"
    "0.8 124.6Z"
)

PAGINA_OBSERVATORIO = r"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>El Observatorio del Descanso · ¿Cómo has dormido esta noche? | nochetropical.es</title>
<meta name="description" content="__DESC__">
<link rel="canonical" href="__SITE__/observatorio-del-descanso/">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="website">
<meta property="og:title" content="El Observatorio del Descanso · Así se siente España">
<meta property="og:description" content="__DESC__">
<meta property="og:url" content="__SITE__/observatorio-del-descanso/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&family=Lora:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#100b06;--bg2:#1a130b;--panel:#241a10;--line:#3a2c1c;--paper:#f3ece0;--muted:#b3a48c;
--teja:#e0834f;--teja2:#eda877;--teal:#8fc0cf;--verde:#8fb07a;--rojo:#d9604a;--oro:#e8b45c;
--fd:"Fraunces",Georgia,serif;--fb:"Lora",Georgia,serif}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.6;-webkit-font-smoothing:antialiased;overflow-x:hidden}
.wrap{max-width:560px;margin:0 auto;padding:0 22px}
button{font-family:inherit;cursor:pointer;border:0}
a{color:var(--teal);text-decoration:none}
.hero{min-height:calc(100svh - 54px);display:flex;flex-direction:column;justify-content:center;text-align:center;padding:36px 0;background:radial-gradient(130% 90% at 50% 0,#241a10,var(--bg) 65%)}
.brandmini{font:600 12px/1 var(--fb);letter-spacing:.22em;text-transform:uppercase;color:var(--teja);margin-bottom:22px}
.hero h1{font-family:var(--fd);font-weight:900;font-size:clamp(32px,8vw,52px);line-height:1.05;letter-spacing:-.02em}
.hero h1 em{font-style:italic;color:var(--teja2)}
.hero .sub{color:var(--muted);font-size:clamp(15.5px,3vw,18px);margin:18px auto 0;max-width:30ch}
.cta{margin-top:30px;background:var(--teja);color:#160f08;font-weight:700;font-size:17px;padding:17px 30px;border-radius:16px;box-shadow:0 10px 30px rgba(224,131,79,.28);transition:.15s}
.cta:hover{transform:translateY(-2px);background:var(--teja2)}
.loc{margin-top:15px;font-size:13px;color:var(--muted)}.loc b{color:var(--paper)}
.loc select{background:var(--bg2);color:var(--paper);border:1px solid var(--line);border-radius:8px;padding:5px 8px;font-family:var(--fb);font-size:13px}
.scrollhint{margin-top:40px;font-size:12.5px;color:var(--muted);letter-spacing:.05em;animation:bob 2s ease-in-out infinite}
@keyframes bob{0%,100%{transform:translateY(0);opacity:.6}50%{transform:translateY(5px);opacity:1}}
.public{padding:44px 0 20px;border-top:1px solid var(--line);background:var(--bg2)}
.public h2{font-family:var(--fd);font-weight:600;font-size:clamp(21px,4vw,27px);text-align:center;margin-bottom:6px}
.public .when{text-align:center;color:var(--muted);font-size:12.5px;margin-bottom:20px}
.mapbox{background:#0c0805;border:1px solid var(--line);border-radius:18px;padding:14px;margin-bottom:22px}
.mapbox svg{width:100%;height:auto;display:block}
/* Silueta del país: solo insinuada. Tiene que leerse como el papel sobre el que
   se posan los puntos, nunca competir con ellos. */
.silueta{fill:none;stroke:#6b5b45;stroke-width:.7;stroke-linejoin:round;stroke-linecap:round;opacity:.5}
.dot{cursor:pointer}
.dot:hover,.dot:focus{stroke:#f3ece0;stroke-width:1.3;outline:none}
/* En el mapa del resultado los puntos son decorado: ni cursor ni clic. */
#rmap .dot{cursor:default;pointer-events:none}
.rankcols{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.rankcol h3{font:600 11px/1 var(--fb);letter-spacing:.12em;text-transform:uppercase;margin-bottom:10px}
.rankcol.best h3{color:var(--verde)}.rankcol.worst h3{color:var(--rojo)}
.rk{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--line)}
.rk .idx{font-family:var(--fd);font-weight:900;font-size:18px;width:42px;text-align:center;border-radius:9px;padding:4px 0}
.rk .nm{font-size:14px;flex:1}.rk .nm small{display:block;color:var(--muted);font-size:12.5px}
.legend{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;margin:24px 0 0;font-size:13px;color:var(--muted)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.ldot{width:11px;height:11px;border-radius:50%;display:inline-block}
.flow{position:fixed;inset:0;z-index:100;background:var(--bg);display:flex;flex-direction:column;opacity:0;pointer-events:none;transition:opacity .25s}
.flow.on{opacity:1;pointer-events:auto}
.flowtop{display:flex;align-items:center;gap:14px;padding:18px 22px}
.bar{flex:1;height:4px;background:var(--line);border-radius:3px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--teja);width:0;transition:width .35s cubic-bezier(.4,0,.2,1)}
.close{background:transparent;color:var(--muted);font-size:22px;line-height:1}
.step{flex:1;display:flex;flex-direction:column;justify-content:center;padding:10px 0 30px}
.step .q{font-family:var(--fd);font-weight:600;font-size:clamp(24px,6vw,34px);text-align:center;line-height:1.12;padding:0 18px;margin-bottom:24px}
.opts{display:flex;flex-direction:column;gap:11px;max-width:440px;margin:0 auto;width:100%;padding:0 22px}
.opt{display:flex;align-items:center;gap:16px;background:var(--bg2);border:1.5px solid var(--line);border-radius:16px;padding:16px 18px;color:var(--paper);font-size:17px;text-align:left;transition:.12s}
.opt:hover{border-color:var(--teja);background:var(--panel)}
.opt .em{font-size:27px;line-height:1}
.opt.sel{border-color:var(--teja);background:rgba(224,131,79,.14)}
.reward{position:fixed;inset:0;z-index:110;background:var(--bg);overflow-y:auto;opacity:0;pointer-events:none;transition:opacity .3s}
.reward.on{opacity:1;pointer-events:auto}
.rwrap{max-width:520px;margin:0 auto;padding:26px 22px 70px;min-height:100svh}
.mapglow{position:relative;margin:6px 0}
.rw-say{text-align:center;margin:16px 0}
.rw-say .big{font-family:var(--fd);font-weight:600;font-size:clamp(23px,5.5vw,30px);line-height:1.18}
.rw-say .small{color:var(--muted);font-size:14.5px;margin-top:10px}
.morehint{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);z-index:111;background:rgba(224,131,79,.16);border:1px solid var(--teja);color:var(--teja2);font-size:12.5px;padding:8px 16px;border-radius:20px;animation:bob 1.6s ease-in-out infinite;transition:opacity .3s}
/* Dos accesos fijos a lo que se viene a hacer aquí: contar tu noche y mirar
   otro pueblo. Aparecen al pasar la portada y se apartan mientras se vota o se
   lee el resultado. No mueven ninguna sección: solo llevan hasta ellas. */
.fabs{position:fixed;left:50%;transform:translateX(-50%) translateY(14px);bottom:calc(14px + env(safe-area-inset-bottom));z-index:90;display:flex;gap:9px;padding:0 12px;max-width:100%;opacity:0;pointer-events:none;transition:opacity .25s,transform .25s}
.fabs.on{opacity:1;pointer-events:auto;transform:translateX(-50%) translateY(0)}
.fab{background:rgba(36,26,16,.94);border:1px solid var(--line);color:var(--paper);font-family:var(--fb);font-size:13px;padding:11px 16px;border-radius:22px;backdrop-filter:blur(6px);box-shadow:0 8px 24px rgba(0,0,0,.45);white-space:nowrap}
.fab-pri{background:var(--teja);border-color:var(--teja);color:#160f08;font-weight:700}
@media (prefers-reduced-motion:reduce){.fabs{transition:opacity .25s}}
.card{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:20px;padding:22px;margin:18px 0}
.card h3{font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;color:var(--teja);margin-bottom:16px}
.yourgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.mini{display:flex;align-items:center;gap:11px}.mini .em{font-size:24px}.mini .l{font-size:12.5px;color:var(--muted)}.mini .v{font-size:15px;font-weight:600}
.tuidx{text-align:center;margin-top:18px;padding-top:16px;border-top:1px solid var(--line)}
.tuidx .n{font-family:var(--fd);font-weight:900;font-size:38px}
.thesis{text-align:center}.thesis .row{display:flex;justify-content:center;gap:30px;margin-top:6px}
.thesis .row .c .n{font-family:var(--fd);font-weight:900;font-size:32px}
.thesis .row .c small{display:block;color:var(--muted);font-size:12.5px;margin-top:2px}
.contrast{background:radial-gradient(120% 100% at 50% 0,#2a1a10,var(--bg2));border:1px solid var(--teja);border-radius:20px;padding:26px 22px;margin:22px 0;text-align:center}
.contrast .pre{color:var(--teja2);font-size:14px;letter-spacing:.04em}
.contrast .km{font-family:var(--fd);font-weight:900;font-size:clamp(30px,8vw,42px);color:var(--paper);margin:8px 0;line-height:1.1}
.contrast .txt{font-size:16px;color:var(--paper)}.contrast .txt b{color:var(--verde)}
.contrast .vs{display:flex;justify-content:center;gap:26px;margin-top:18px}
.contrast .vs .c .n{font-family:var(--fd);font-weight:900;font-size:26px}.contrast .vs .c small{display:block;color:var(--muted);font-size:12.5px;margin-top:2px}
.nearby .row{display:flex;align-items:center;gap:13px;padding:12px 0;border-bottom:1px solid var(--line)}.nearby .row:last-child{border:0}
.nearby .idx{font-family:var(--fd);font-weight:900;font-size:20px;width:46px;text-align:center;border-radius:9px;padding:4px 0}
.nearby .info .n{font-weight:600;font-size:15px}.nearby .info .p{color:var(--muted);font-size:13.5px;font-style:italic}
.share{width:100%;background:var(--teja);color:#160f08;font-weight:700;font-size:16px;padding:16px;border-radius:15px;margin-top:8px}.share:hover{background:var(--teja2)}
.again{width:100%;background:transparent;border:1px solid var(--line);color:var(--muted);font-weight:600;font-size:14px;padding:13px;border-radius:14px;margin-top:11px}
.disc-o{text-align:center;color:var(--muted);font-size:13px;margin-top:20px;line-height:1.6}
.fade{opacity:0;transform:translateY(14px);animation:rise .5s forwards}@keyframes rise{to{opacity:1;transform:none}}
.pinp{animation:ping 1.6s ease-out infinite}@keyframes ping{0%{r:4;opacity:1}100%{r:16px;opacity:0}}
.hidden{display:none!important}
.desktoponly{margin:8px auto 0;max-width:34ch;background:var(--bg2);border:1px solid var(--line);border-radius:14px;padding:16px 18px;color:var(--muted);font-size:14.5px;line-height:1.55}
.desktoponly b{color:var(--paper)}
.back{background:transparent;color:var(--muted);font-size:15px;line-height:1;padding:6px 4px;white-space:nowrap}
.back:hover{color:var(--paper)}
.curioso{margin:30px auto 0;max-width:520px;background:var(--bg2);border:1px solid var(--line);border-radius:16px;padding:20px 20px 22px}
.curioso h3{font-family:var(--fd);font-weight:600;font-size:clamp(17px,3.4vw,21px);color:var(--paper);margin:0 0 6px}
.cursub{color:var(--muted);font-size:14.5px;line-height:1.55;margin:0 0 14px}
.cursub b{color:var(--paper)}
#curbusca{width:100%;background:#2c2216;border:1.5px solid #5f5138;border-radius:11px;color:var(--paper);font-size:15px;padding:12px 14px;font-family:inherit}
#curbusca:focus{outline:2px solid var(--teja);outline-offset:1px}
.cursug{list-style:none;margin:8px 0 0;padding:0;max-height:230px;overflow:auto}
.cursug li{padding:11px 13px;border:1px solid var(--line);border-radius:10px;margin-bottom:6px;cursor:pointer;font-size:14.5px;background:var(--bg)}
.cursug li:hover{border-color:var(--teja);color:var(--teja2)}
.curfuente{font-size:13.5px;color:var(--muted);line-height:1.55;margin-top:12px;padding-top:11px;border-top:1px dashed var(--line)}
.curfuente b{color:var(--paper)}
.curfuente.vot{color:#cfe0c2}
.curped{width:100%;margin-top:11px;background:var(--teja);color:#160f08;border:0;border-radius:11px;font-weight:700;font-size:14px;padding:12px;cursor:pointer;font-family:inherit;line-height:1.35}
.curped:hover{background:var(--teja2)}
.curout{margin-top:14px}
.curcard{background:var(--bg);border:1px solid var(--line);border-radius:14px;padding:16px 18px;text-align:center}
.curz-n{font-family:var(--fd);font-weight:600;font-size:17px;color:var(--paper)}
.curz-n small{color:var(--muted);font-weight:400;font-size:13.5px;font-style:italic;margin-left:5px}
.curz-idx{font-family:var(--fd);font-weight:700;font-size:40px;line-height:1.1;margin:4px 0}
.curz-idx span{font-size:16px;color:var(--muted)}
.curz-f{color:var(--muted);font-size:14.5px;font-style:italic}
.curcmp{display:flex;justify-content:center;align-items:center;gap:12px;margin-top:14px;font-size:14px;color:var(--muted);flex-wrap:wrap}
.curcmp .vs{font-size:12.5px}
.curmsg{color:var(--paper);font-size:14px;margin-top:9px}
.lugarchip{display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:center;margin:0 0 16px;font-size:13px;color:var(--muted);min-height:22px}
.lugarchip b{color:var(--paper)}
.lc-fix{background:transparent;border:1px solid var(--line);color:var(--teja2);font-size:12.5px;padding:5px 11px;border-radius:999px;cursor:pointer;font-family:inherit}
.lc-fix:hover{border-color:var(--teja)}
.lc-form{width:100%;display:flex;gap:8px;align-items:flex-end}
.lc-form label{flex:1;font-size:12.5px;color:var(--muted);text-align:left}
.lc-form input{width:100%;margin-top:5px;background:#2c2216;border:1.5px solid #5f5138;border-radius:10px;color:var(--paper);font-size:15px;padding:10px 12px;font-family:inherit}
.lc-form input:focus{outline:2px solid var(--teja);outline-offset:1px}
.lc-ok{background:var(--teja);color:#160f08;border:0;border-radius:10px;font-weight:700;font-size:14px;padding:11px 15px;cursor:pointer;font-family:inherit;white-space:nowrap}
.wsub2{color:var(--muted);font-size:13.5px;line-height:1.55;margin:-4px 0 14px}
.wsub2 b{color:var(--paper)}
.wfields{display:grid;gap:12px;margin-bottom:16px}
.wfields label{display:block;font-size:13px;color:var(--muted)}
.wfields input{width:100%;margin-top:6px;background:#2c2216;border:1.5px solid #5f5138;border-radius:11px;color:var(--paper);font-size:17px;padding:12px 14px;font-family:inherit}
.wfields input:focus{outline:2px solid var(--teja);outline-offset:1px}
.sleepdebt .dgrid{margin:6px 0 10px}
.sleepdebt .dbar{height:10px;background:#0c0906;border:1px solid var(--line);border-radius:999px;overflow:hidden}
.sleepdebt .dbar i{display:block;height:100%;border-radius:999px}
.sleepdebt .dlab{font-weight:700;font-size:14px;margin-top:7px;text-align:center}
.sleepdebt .dtxt{color:var(--muted);font-size:13.5px;line-height:1.6;margin:0}
.sleepdebt .dtxt b{color:var(--paper)}
.wcmp{margin-top:14px;border-top:1px dashed var(--line);padding-top:13px}
.wtit{font-size:12.5px;color:var(--teja);letter-spacing:.08em;text-transform:uppercase;margin-bottom:9px}
.wcmp .wrow{display:flex;gap:10px;justify-content:space-around;text-align:center}
.wcmp .wrow .n{font-family:var(--fd);font-weight:700;font-size:26px;color:var(--paper);line-height:1.1}
.wcmp .wrow small{color:var(--muted);font-size:12.5px}
.obsdemo{margin:14px auto 0;max-width:34ch;text-align:center;font-size:12.5px;color:var(--muted);background:var(--bg2);border:1px dashed var(--line);border-radius:12px;padding:11px 14px;line-height:1.55}
.obsdemo b{color:var(--paper)}
.obsestado{margin:14px auto 0;max-width:36ch;text-align:center;font-size:13px;border-radius:12px;padding:12px 15px;line-height:1.55}
.obsestado b{font-weight:700}
.obsestado.ok{color:#cfe0c2;background:rgba(143,176,122,.14);border:1px solid #8fb07a}
.obsestado.ko{color:#f0c9bd;background:rgba(217,96,74,.14);border:1px solid #d9604a}
.again.pri2{border-color:var(--teja);color:var(--teja2);font-weight:700}
.again.pri2:hover{background:rgba(217,116,78,.12)}
.preg{margin:34px auto 0;max-width:640px;border-top:1px dashed var(--line);padding-top:26px}
.preg h2{font-family:var(--fd);font-weight:600;font-size:clamp(18px,3.4vw,24px);color:var(--paper);margin:0 0 10px;line-height:1.22;text-align:left}
.preg h2+p{margin-top:0}
.preg p{color:var(--muted);font-size:clamp(14.5px,2.3vw,16px);line-height:1.72;margin:0 0 16px;text-align:left}
.preg p b{color:var(--paper)}
.preg a{color:var(--teja2)}
.preg .cajaref{background:var(--bg2);border:1px solid var(--line);border-left:3px solid var(--teal);border-radius:14px;padding:16px 18px;margin:0 0 26px}
.preg .cajaref p{font-size:14px;margin:0 0 13px}
.btnref{display:inline-block;background:var(--teja);color:#160f08!important;font-weight:700;font-size:14px;padding:11px 16px;border-radius:11px;text-decoration:none}
.btnref:hover{background:var(--teja2)}
.deudasec{padding:6px 0 30px}
.votabox{background:radial-gradient(120% 90% at 50% 0,#241a10,var(--bg) 72%);border-top:1px solid var(--line);padding:34px 0 40px;text-align:center}
.votabox h2{font-family:var(--fd);font-weight:700;font-size:clamp(21px,4.4vw,30px);color:var(--paper);margin:0 0 8px;line-height:1.15}
.votasub{color:var(--muted);font-size:clamp(14px,2.3vw,16px);line-height:1.65;max-width:44ch;margin:0 auto 18px}
.votasub b{color:var(--paper)}
.deuda-ed{margin:30px auto 0;max-width:640px}
.deuda-ed h3{font-family:var(--fd);font-weight:600;font-size:clamp(19px,3.6vw,25px);color:var(--paper);margin:0 0 12px;line-height:1.2}
.deuda-ed p{color:var(--muted);font-size:clamp(14.5px,2.3vw,16px);line-height:1.75;margin:0 0 14px}
.deuda-ed p b{color:var(--paper)}
.deuda-ed a{color:var(--teja2)}
.wear-note{background:var(--bg2);border:1px solid var(--line);border-left:3px solid var(--teja);border-radius:12px;padding:14px 16px;font-size:13.5px!important;line-height:1.65!important}
.maphint{text-align:center;color:var(--muted);font-size:12.5px;margin:11px 0 0}
/* ESCRITORIO. La página nació para el móvil y en horizontal se quedaba en una
   columna estrecha con la pantalla vacía a los lados. A partir de 900px el
   bloque público se ensancha y el mapa y los rankings se ponen en paralelo, que
   es lo que pide una pantalla apaisada. El texto largo NO se ensancha: una
   línea de mil píxeles no hay quien la lea. Por debajo de 900px no cambia nada:
   el móvil sigue exactamente igual que hasta ahora. */
@media(min-width:900px){
 .public{padding:54px 0 30px}
 .public .wrap{max-width:1060px}
 .pubgrid{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:36px;align-items:start}
 .curioso{max-width:none;margin:26px 0 0}
 .rk{padding:11px 0}
 .legend{margin-top:18px}
 .public .disc-o{max-width:68ch;margin-left:auto;margin-right:auto}
 .hero .sub{max-width:36ch}
 .votabox{padding:44px 0 50px}
 .preg{margin-top:44px}
}
 __NAVCSS__
 __FOOTERCSS__
</style></head><body>
__NAV__
<section class="hero"><div class="wrap">
  <div class="brandmini">El Observatorio del Descanso</div>
  <h1>Así se <em>duerme</em><br>en España</h1>
  <p class="sub">El mapa del <b>sueño profundo</b>: dónde el cuerpo se repara de verdad, según diez veranos de AEMET y las noches que cuenta la gente.</p>
</div></section>
<section class="public"><div class="wrap">
  <h2>El mapa del descanso, población por población</h2>
  <div class="when" id="when">Índice de descanso · <b>esperado según AEMET</b> · aún sin votos — sé el primero</div>
  <!-- Dos bloques: el mapa con su leyenda, y al lado los rankings y el buscador.
       En móvil van uno detrás de otro, tal cual; en pantalla ancha se ponen en
       paralelo (ver .pubgrid), que es lo que pide una pantalla horizontal. -->
  <div class="pubgrid">
   <div class="pg-mapa">
    <div class="mapbox"><svg id="map" viewBox="0 0 300 190" aria-label="Mapa del descanso de España"></svg></div>
    <div class="legend">
      <span><i class="ldot" style="background:#8fb07a"></i>Excelente</span>
      <span><i class="ldot" style="background:#b9c47a"></i>Bueno</span>
      <span><i class="ldot" style="background:#e8b45c"></i>Regular</span>
      <span><i class="ldot" style="background:#e0834f"></i>Malo</span>
      <span><i class="ldot" style="background:#d9604a"></i>Muy malo</span>
    </div>
    <p class="maphint">Toca cualquier punto del mapa para ver cómo se duerme allí.</p>
   </div>
   <div class="pg-lado">
    <div class="rankcols">
      <div class="rankcol best"><h3>😴 Mejor descanso</h3><div id="best"></div></div>
      <div class="rankcol worst"><h3>🥵 Peor descanso</h3><div id="worst"></div></div>
    </div>
    <div class="curioso" id="curioso">
    <h3>¿Quieres saber cómo se duerme en otra población española?</h3>
    <p class="cursub">Busca cualquier pueblo o ciudad de España. Si allí ya se han contado noches, verás lo que dice la gente; si no, verás lo que <b>cabe esperar según AEMET</b> — y te lo decimos claramente.</p>
    <input id="curbusca" type="search" autocomplete="off" placeholder="Escribe tu pueblo… (Dénia, Cedrillas, Gijón…)" aria-label="Buscar una población">
    <ul class="cursug" id="cursug"></ul>
    <div class="curout" id="curout"></div>
    </div>
   </div>
  </div>


__PREGUNTAS__

  <p class="disc-o" style="margin-top:22px">Aún estamos empezando. El mapa nace con la <b>expectativa de AEMET</b> (10 veranos de datos); cada noche que votas lo hace más real: veremos <b>lo que dicen los datos frente a lo que dice la gente</b>. Sin predicciones, sin temperatura de protagonista: solo cómo se ha vivido la noche.</p>
</div></section>

<section class="votabox"><div class="wrap">
  <h2>¿Y tú, cómo has dormido esta noche?</h2>
  <p class="votasub">Cuéntalo en 10 segundos y tu noche entra en el mapa. Es anónimo, y así sabremos <b>dónde se descansa de verdad</b> en España.</p>
  <button class="cta" id="cta" onclick="startFlow()">Contar cómo he dormido</button>
  <div class="loc" id="loc">📍 Detectando tu zona…</div>
  <div class="desktoponly hidden" id="desknote">📱 Para contar tu noche hace falta el <b>móvil</b>: necesitamos tu ubicación para situarla en el mapa. Ábrelo en tu teléfono — el mapa de arriba se ve igual desde aquí.</div>
</div></section>

<section class="deudasec"><div class="wrap">
  <div class="deuda-ed">
    <h3>La deuda de sueño: lo que pagas al día siguiente</h3>
    <p>Dormir mal una noche se nota; dormir mal <b>varias seguidas</b> se acumula. Eso es la <b>deuda de sueño</b>: el déficit que arrastras y que no se salda con echarle horas el fin de semana. Y hay un matiz que casi nadie cuenta: <b>puedes dormir las mismas horas y descansar mucho menos</b>. Cuando la noche no baja de 20&nbsp;°C, el cuerpo no consigue soltar calor, el sueño se fragmenta y <b>la fase profunda —la reparadora— se acorta</b>. El reloj marca ocho horas; el cuerpo, al levantarse, dice otra cosa.</p>
    <p>Por eso este observatorio no mide la temperatura: mide <b>el descanso</b>. Si entrenas, ya sabes que la sesión no te hace mejor — <b>te hace mejor lo que recuperas mientras duermes</b>: ahí se libera la hormona del crecimiento, se repara el músculo y se consolida el aprendizaje. Un verano de noches tropicales es un verano de recuperación a medias. Y un <a href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/">refugio climático natural</a> —donde la madrugada refresca sin aire acondicionado— es, sencillamente, <b>el mejor sitio para dormir profundo</b>.</p>
    <p class="wear-note">⌚ <b>¿Llevas pulsera o reloj de sueño?</b> Al contar tu noche puedes añadir, si quieres, <b>las horas y la puntuación</b> que te dio tu dispositivo. Así cruzamos tres cosas que casi nunca se miran juntas: <b>lo que midió AEMET</b> fuera, <b>lo que midió tu aparato</b> y <b>lo que sentiste tú</b>. Es opcional y anónimo: no conectamos con ninguna cuenta ni servicio, lo escribes tú.</p>
  </div>
</div></section>
__FOOTER__

<div class="flow" id="flow">
  <div class="flowtop"><button class="back" id="backbtn" onclick="back()">‹ Atrás</button><div class="bar"><i id="barfill"></i></div><span id="stepn" style="font-size:12.5px;color:var(--muted);width:34px;text-align:right">1/5</span></div>
  <div class="step"><div class="lugarchip" id="lugarchip"></div><div id="stepbody"></div></div>
</div>
<div class="reward" id="reward"><div class="rwrap" id="rbody"></div></div>
<div class="morehint hidden" id="morehint">↓ sigue, hay más</div>
<div class="fabs" id="fabs">
  <button class="fab fab-pri" onclick="irAVotar()">🌙 Contar mi noche</button>
  <button class="fab" onclick="irACurioso()">🔎 Otro pueblo</button>
</div>

<script>
var SEED=__SEED__;
var ALL=__ALLZ__.map(function(a){return {la:a[0],lo:a[1],n:a[2],d:a[3],id:a[4],p:a[5]};}); /* 848 estaciones para el geoposicionamiento exacto */
var URL_OBS="__OBS_URL__";   /* buzón de noches; vacío = modo demostración */
function obsUid(){try{var u=localStorage.getItem("obs_uid");if(!u){u=Math.random().toString(36).slice(2)+Date.now().toString(36);localStorage.setItem("obs_uid",u);}return u;}catch(e){return "anon";}}
function colorFor(d){return d>=8?"#8fb07a":d>=6?"#b9c47a":d>=4?"#e8b45c":d>=2.5?"#e0834f":"#d9604a";}
function bgFor(d){return d>=8?"rgba(143,176,122,.18)":d>=6?"rgba(185,196,122,.18)":d>=4?"rgba(232,180,92,.18)":d>=2.5?"rgba(224,131,79,.18)":"rgba(217,96,74,.18)";}
function km(a,b){var R=6371,dLa=(b.la-a.la)*Math.PI/180,dLo=(b.lo-a.lo)*Math.PI/180,la1=a.la*Math.PI/180,la2=b.la*Math.PI/180;var h=Math.sin(dLa/2)**2+Math.cos(la1)*Math.cos(la2)*Math.sin(dLo/2)**2;return Math.round(2*R*Math.asin(Math.sqrt(h)));}
/* Un grado de longitud es más corto que uno de latitud (a 40° de latitud, un
   77% de largo). Sin corregirlo España salía ensanchada; mientras el mapa eran
   solo puntos sueltos no se notaba, pero con la silueta dibujada detrás sí. Se
   corrige y el dibujo se centra en el mismo lienzo de 300x190: los puntos se
   desplazan un poco y el país queda con su forma. OJO: SILUETA_ES se generó con
   esta misma fórmula — si se toca aquí, hay que volver a generarla. */
var MAPK=Math.cos(40*Math.PI/180),MAPS=190/7.9,MAPDX=(300-12.8*MAPK*MAPS)/2;
function proj(z){return[MAPDX+(z.lo+9.4)*MAPK*MAPS,(43.9-z.la)*MAPS];}
/* El mapa: la silueta del país al fondo y encima un punto por zona. Cada punto
   lleva a la ficha de su población — el cursor de mano ya prometía un clic, y
   ahora existe. No se hacen tabulables los 40 puntos para no plantar 40 paradas
   de teclado delante del resto: quien navegue así tiene el buscador, que lleva
   exactamente a la misma ficha. */
function renderMap(sel){
  var svg=document.getElementById("map"),h='<path class="silueta" d="__SILUETA__"/>';
  SEED.forEach(function(z,i){var p=proj(z);h+='<circle class="dot" role="button" onclick="verEnMapa('+i+')" cx="'+p[0].toFixed(1)+'" cy="'+p[1].toFixed(1)+'" r="'+(4+z.d/3.2)+'" fill="'+colorFor(z.d)+'" fill-opacity=".9"><title>'+z.n+' · '+z.d+'/10 — toca para verlo</title></circle>';});
  if(sel){var p=proj(sel);h+='<circle cx="'+p[0].toFixed(1)+'" cy="'+p[1].toFixed(1)+'" r="4" fill="none" stroke="#f3ece0" stroke-width="1.5"/><circle class="pinp" cx="'+p[0].toFixed(1)+'" cy="'+p[1].toFixed(1)+'" fill="#e0834f"/>';}
  svg.innerHTML=h;
}
function renderRanks(){
  var best=SEED.slice().sort(function(a,b){return b.d-a.d}).slice(0,5);
  var worst=SEED.slice().sort(function(a,b){return a.d-b.d}).slice(0,5);
  function row(m){return '<div class="rk"><span class="idx" style="color:'+colorFor(m.d)+';background:'+bgFor(m.d)+'">'+m.d.toFixed(1)+'</span><span class="nm">'+m.n+'<small>'+m.p+'</small></span></div>';}
  document.getElementById("best").innerHTML=best.map(row).join("");
  document.getElementById("worst").innerHTML=worst.map(row).join("");
}
renderMap();renderRanks();

/* Tocar un punto del mapa = buscar esa población: escribe su nombre en el
   buscador, abre su ficha y marca el punto. En escritorio la ficha ya está al
   lado del mapa, así que solo se desplaza la página si se ha quedado fuera. */
function verEnMapa(i){
 var z=SEED[i];if(!z)return;
 renderMap(z);
 var inp=document.getElementById("curbusca");if(inp)inp.value=z.n;
 var sug=document.getElementById("cursug");if(sug)sug.innerHTML="";
 showCurioso(z);
 var c=document.getElementById("curioso");if(!c)return;
 var r=c.getBoundingClientRect();
 if(r.top<0||r.bottom>window.innerHeight)
  scrollSuaveA(Math.max(0,r.top+window.scrollY-46),700);
}

/* FICHA DEL CURIOSO: comparar cómo se está en otra zona (sin votar). Usa la
   semilla (índice esperado según AEMET); cuando haya backend, mostrará votos. */
function showCurioso(z){
 var out=document.getElementById("curout");
 var h='<div class="curcard"><div class="curz-n">'+z.n+(z.p?' <small>'+z.p+'</small>':'')+'</div>'
  +'<div class="curz-idx" style="color:'+colorFor(z.d)+'">'+z.d.toFixed(1)+'<span>/10</span></div>'
  +'<div class="curz-f">"'+z.f+'"</div>';
 /* De dónde sale el número: de votos reales o de la expectativa de AEMET. Se
    dice SIEMPRE, y si no hay votos se invita a que alguien de allí los aporte. */
 if(z.votos)
  h+='<div class="curfuente vot">🌙 <b>'+z.votos+'</b> noche'+(z.votos>1?'s':'')+' votada'+(z.votos>1?'s':'')+' aquí en las últimas 24 h</div>';
 else{
  h+='<div class="curfuente">📊 Aún <b>no hay noches votadas</b> aquí. Este número es lo que <b>cabe esperar según AEMET</b>'
   +(z.est?' (estación de '+z.est+(z.estkm!=null?', a '+z.estkm+' km':'')+')':'')+', con diez veranos de datos.</div>'
   +'<button type="button" class="curped" onclick="pideVoto(\''+z.n.replace(/'/g,"\\'")+'\')">📲 ¿Conoces a alguien allí? Pídele que cuente su noche</button>';
 }
 if(MY&&MY.d!=null){
  h+='<div class="curcmp"><span>Tu zona ('+MY.n+'): <b style="color:'+colorFor(MY.d)+'">'+MY.d.toFixed(1)+'</b></span>'
    +'<span class="vs">vs</span><span>'+z.n+': <b style="color:'+colorFor(z.d)+'">'+z.d.toFixed(1)+'</b></span></div>';
  var dif=z.d-MY.d;
  h+='<p class="curmsg">'+(Math.abs(dif)<0.8?"Se descansa parecido en los dos sitios.":(dif>0?"Ahí se descansa <b>mejor</b> que en tu zona.":"En tu zona se descansa <b>mejor</b> que ahí."))+'</p>';
 }
 out.innerHTML=h+'</div>';
}
/* Desde el resultado del voto: cerrar la recompensa y llevar al buscador de
   poblaciones, con el cursor puesto (es la pregunta que engancha después). */
function verCurioso(){
 var r=document.getElementById("reward");if(r)r.classList.remove("on");
 var mh=document.getElementById("morehint");if(mh)mh.classList.add("hidden");
 var c=document.getElementById("curioso");
 if(c){c.scrollIntoView({behavior:"smooth",block:"center"});
  setTimeout(function(){var i=document.getElementById("curbusca");if(i)i.focus();},600);}
}
/* Invitación a que alguien de esa población cuente su noche. */
function pideVoto(nombre){
 var url="__SITE__/observatorio-del-descanso/";
 var txt="¿Cómo se duerme en "+nombre+"? Todavía no hay ni una noche contada allí. Si estás por la zona, cuéntalo en 10 segundos (es anónimo) y lo sabremos:";
 if(navigator.share)navigator.share({title:"El Observatorio del Descanso",text:txt,url:url}).catch(function(){});
 else if(navigator.clipboard)navigator.clipboard.writeText(txt+" "+url).then(function(){alert("Copiado: pégaselo a quien esté por allí.");});
 else window.open("https://wa.me/?text="+encodeURIComponent(txt+" "+url),"_blank");
}
/* Lista del curioso = las 40 zonas semilla + TODA zona que reciba votos (si
   alguien vota en Dénia, Dénia entra en la lista). Se resuelve contra las 848
   estaciones para tener nombre, provincia y coordenadas reales. */
var CURZ=SEED.slice();
function addZonasVotadas(d){
 if(!d)return;
 (d.zonas||[]).forEach(function(zv){
  var ya=CURZ.filter(function(z){return z.id===zv.z&&!z.mun;})[0];
  if(ya){ya.votos=zv.n;if(typeof zv.d==="number")ya.d=zv.d;return;}
  var est=ALL.filter(function(a){return a.id===zv.z;})[0];
  if(!est)return;
  CURZ.push({n:est.n,p:est.p,la:est.la,lo:est.lo,id:est.id,votos:zv.n,
             d:(typeof zv.d==="number"?zv.d:est.d),
             f:"Según las noches que ha votado la gente."});
 });
 /* MUNICIPIOS votados: entran con su nombre propio (Dénia), no con el de su
    estación. Se apunta de qué estación de AEMET viene su referencia. */
 (d.municipios||[]).forEach(function(mv){
  if(!mv.nom)return;
  var est=ALL.filter(function(a){return a.id===mv.z;})[0];
  var ya=CURZ.filter(function(z){return z.mun===mv.m;})[0];
  if(ya){ya.votos=mv.n;ya.d=mv.d;return;}
  CURZ.push({n:mv.nom,p:(est?est.p:""),la:(est?est.la:null),lo:(est?est.lo:null),
             id:mv.z,mun:mv.m,votos:mv.n,d:mv.d,
             f:"Según las noches que ha votado la gente"+(est?" · referencia AEMET: "+est.n:"")+"."});
 });
}
/* Buscador sobre las 7.157 poblaciones: se puede consultar CUALQUIER pueblo,
   haya votos o no. Si no los hay se enseña la expectativa de AEMET de su
   estación más cercana, diciéndolo, y se ofrece pedir el voto a alguien de allí. */
var LUG=null;
function na_(s){return s.normalize("NFD").replace(/[̀-ͯ]/g,"").toLowerCase();}
function cargaLugares(cb){
 if(LUG){cb(LUG);return;}
 fetch("__SITE__/datos/lugares.json").then(function(x){return x.json();})
  .then(function(d){LUG=d;cb(d);}).catch(function(){cb(null);});
}
function zonaDeLugar(p){
 /* p = [id, nombre, lat, lon] -> tarjeta lista para showCurioso */
 var votada=CURZ.filter(function(z){return z.mun===p[0]||na_(z.n)===na_(p[1]);})[0];
 if(votada&&votada.votos)return votada;
 var est=null,bd=1e9;
 ALL.forEach(function(a){var d=km({la:p[2],lo:p[3]},a);if(d<bd){bd=d;est=a;}});
 return {n:p[1],p:(est?est.p:""),d:(est?est.d:5),est:(est?est.n:""),estkm:(est?Math.round(bd):null),
         f:"Lo que cabe esperar en esta zona según diez veranos de AEMET."};
}
function pintaSug(lista){
 var ul=document.getElementById("cursug");if(!ul)return;
 ul.innerHTML="";
 lista.forEach(function(p){
  var li=document.createElement("li");
  li.textContent=p[1];
  li.onclick=function(){
   document.getElementById("curbusca").value=p[1];
   ul.innerHTML="";showCurioso(zonaDeLugar(p));
  };
  ul.appendChild(li);
 });
}
(function(){
 var inp=document.getElementById("curbusca");if(!inp)return;
 inp.addEventListener("input",function(){
  var q=na_(inp.value.trim());
  if(q.length<2){document.getElementById("cursug").innerHTML="";return;}
  cargaLugares(function(d){
   if(!d)return;
   var pre=[],con=[];
   for(var i=0;i<d.length&&pre.length<8;i++){var n=na_(d[i][1]);
    if(n.indexOf(q)===0)pre.push(d[i]);else if(con.length<8&&n.indexOf(q)>=0)con.push(d[i]);}
   pintaSug(pre.concat(con).slice(0,8));
  });
 });
 /* Al cargar: si el buzón está desplegado, traemos las zonas con noches
    votadas y las sumamos a la lista (y actualizamos el rótulo del mapa). */
 if(URL_OBS){
  fetch(URL_OBS+"?global=1").then(function(x){return x.json();}).then(function(d){
   if(!d||!d.ok)return;
   addZonasVotadas(d);
   if(d.n>0){var w=document.getElementById("when");
    if(w)w.innerHTML="Índice de descanso · <b>"+d.n+" noches votadas</b> en las últimas 24 h"
     +(d.deuda_media?" · deuda de sueño media "+String(d.deuda_media).replace(".",",")+"/5":"");}
  }).catch(function(){});
 }
})();

/* FICHA DE COMPARTIR: comparte tu resultado (nativo en móvil; si no, copia). */
function shareNoche(){
 var s=window._obsShare||{idx:"",zona:""};
 var url="__SITE__/observatorio-del-descanso/";
 var txt="Esta noche en "+s.zona+" he descansado "+s.idx+"/10 en el Observatorio del Descanso. ¿Y tú, cómo has dormido? Cuéntalo en 10 segundos:";
 if(navigator.share){navigator.share({title:"El Observatorio del Descanso",text:txt,url:url}).catch(function(){});}
 else if(navigator.clipboard){navigator.clipboard.writeText(txt+" "+url).then(function(){alert("Copiado para compartir.");});}
 else{window.open("https://wa.me/?text="+encodeURIComponent(txt+" "+url),"_blank");}
}

/* SOLO móvil + SOLO geoposicionamiento (sin entrada manual, que daba falsos
   positivos como la Valencia de León). La zona = estación AEMET más cercana. */
var MY=null,MYLL=null;
var isMobile=(('ontouchstart' in window)||navigator.maxTouchPoints>0)&&window.matchMedia("(max-width:860px)").matches;
function setZone(z){MY=z;document.getElementById("loc").innerHTML='📍 Estás cerca de <b>'+z.n+'</b>';renderMap(nearSeed(MYLL||z));}
function nearIn(arr,la,lo){var me={la:la,lo:lo},best=arr[0],bd=1e9;arr.forEach(function(z){var d=km(me,z);if(d<bd){bd=d;best=z;}});return best;}
function nearest(la,lo){return nearIn(ALL,la,lo);}   /* estación exacta más cercana (848) */
function nearSeed(p){return p?nearIn(SEED,p.la,p.lo):SEED[0];}  /* semilla reconocible para el mapa */
/* POBLACIÓN donde se ha dormido: la más cercana de las 7.157 con coordenadas
   (GeoNames + grafía del INE). Se detecta SOLA desde la ubicación: sin pasos ni
   preguntas. Da nombre a la noche —Dénia es Dénia—, mientras que la referencia
   climática sigue siendo su estación de AEMET (Pego). Si el fichero no carga,
   simplemente se usa el nombre de la estación, como antes. */
function resuelveLugar(la,lo){
 fetch("__SITE__/datos/lugares.json").then(function(x){return x.json();}).then(function(L){
  var me={la:la,lo:lo},best=null,bd=1e9;
  L.forEach(function(p){var d=km(me,{la:p[2],lo:p[3]});if(d<bd){bd=d;best=p;}});
  if(best&&bd<=25){MUN={id:best[0],n:best[1]};
   var el=document.getElementById("loc");
   if(el&&MY)el.innerHTML='📍 Estás en <b>'+best[1]+'</b> <span style="opacity:.7">· referencia AEMET: '+MY.n+'</span>';}
 }).catch(function(){});
}
function askLoc(cb){if(!navigator.geolocation){cb(false);return;}navigator.geolocation.getCurrentPosition(function(pos){MYLL={la:pos.coords.latitude,lo:pos.coords.longitude};setZone(nearest(MYLL.la,MYLL.lo));resuelveLugar(MYLL.la,MYLL.lo);cb(true);},function(){cb(false);},{enableHighAccuracy:true,timeout:8000});}
function initHero(){
  if(!isMobile){document.getElementById("cta").classList.add("hidden");document.getElementById("loc").classList.add("hidden");document.getElementById("desknote").classList.remove("hidden");return;}
  askLoc(function(ok){if(!ok)document.getElementById("loc").innerHTML='📍 <span style="color:var(--teja2)">Activa la ubicación para participar</span>';});
}
initHero();

/* Al aterrizar, un desplazamiento suave a 1,3 s que asoma el mapa: sin él, la
   portada se queda en el titular y no se ve que hay un mapa debajo. Se anula en
   cuanto la persona toca, hace scroll o usa el teclado — nunca le quitamos el
   control — y no se hace si ya ha bajado por su cuenta o si tiene activado el
   ajuste del sistema de "reducir movimiento". */
(function(){
 var cancelado=false;
 var quieto=window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches;
 function cancela(){cancelado=true;}
 ["wheel","touchstart","keydown","pointerdown"].forEach(function(ev){
  window.addEventListener(ev,cancela,{passive:true,once:true});
 });
 if(quieto)return;
 /* Animación propia en vez del scroll nativo: el del navegador va muy rápido en
    móvil y el salto se siente brusco. Aquí el recorrido dura ~2,2 s con arranque
    y frenada suaves (easeInOutCubic), y se interrumpe en cuanto la persona toca. */
 function bajaSuave(destinoY,dur){
  var ini=window.scrollY,dist=destinoY-ini,t0=null,parar=false;
  var evs=["wheel","touchstart","keydown","pointerdown"];
  function stop(){parar=true;}
  function limpia(){evs.forEach(function(ev){window.removeEventListener(ev,stop);});}
  evs.forEach(function(ev){window.addEventListener(ev,stop,{passive:true});});
  function paso(t){
   if(parar){limpia();return;}
   if(!t0)t0=t;
   var p=Math.min((t-t0)/dur,1);
   var e=0.5*(1-Math.cos(Math.PI*p));   /* easeInOutSine: la más suave */
   window.scrollTo(0,ini+dist*e);
   if(p<1)requestAnimationFrame(paso);else limpia();
  }
  requestAnimationFrame(paso);
 }
 setTimeout(function(){
  if(cancelado||window.scrollY>8)return;
  var destino=document.querySelector(".public");
  if(!destino)return;
  var y=destino.getBoundingClientRect().top+window.scrollY-56;
  bajaSuave(Math.max(0,y),3000);
 },1300);
})();

/* FLUJO */
var Q=[
 {q:"¿Cómo has dormido esta noche?",o:[["😴","He dormido de maravilla",5],["🙂","Bastante bien",4],["😐","Regular",3],["🥵","Con mucho calor",2],["🔥","Apenas he dormido",1]]},
 {q:"¿Cómo se está AHORA mismo?",o:[["😊","Muy agradable",5],["🙂","Bien",4],["😐","Soportable",3],["🥵","Hace calor",2],["🔥","Insoportable",1]]},
 {q:"¿Qué has necesitado para dormir?",o:[["🪟","Nada, tal cual",5],["🌬️","La ventana abierta",4],["💨","El ventilador",3],["❄️","El aire acondicionado",1],["⛺","Dormir fuera de casa",2],["…","Otro",3]]},
 {q:"¿Cómo te has despertado?",o:[["😀","Muy descansado",5],["🙂","Descansado",4],["😐","Normal",3],["😴","Cansado",2],["🥱","Muy cansado",1]]},
 {q:"¿Volverías a dormir aquí esta noche?",o:[["❤️","Sin dudarlo",5],["🙂","Sí",4],["😐","Me da igual",3],["🙁","Preferiría otro sitio",2],["🚗","Si pudiera, me iría",1]]},
 {q:"¿Cuánta deuda de sueño arrastras?",sub:"Si llevas noches durmiendo mal, la deuda se acumula: es lo que te deja fundido al día siguiente.",o:[["✅","Ninguna, estoy a cero",1],["🙂","Poca",2],["😐","Alguna, se nota",3],["😮‍💨","Bastante",4],["🪫","Muchísima, voy fundido",5]]}];
var cur=0,ans=[null,null,null,null,null,null];
var flow=document.getElementById("flow"),reward=document.getElementById("reward");
var NPASOS=Q.length+1;   /* las preguntas + el paso opcional de la pulsera */
var WEAR={h:"",s:""};
var MUN={id:"",n:""};    /* población detectada automáticamente (GeoNames+INE) */
var PROP="";             /* corrección que teclea quien vota, si no acertamos */
var ANCLA=null;          /* punto al que se ancla la noche: el pueblo corregido manda sobre el GPS */
var OBSCONF=false;       /* ya ha confirmado que durmió donde decimos */
var OBSQ=false;          /* la noche se guarda apartada, hasta que otras de allí la respalden */
var OBSINT=0;            /* veces que hemos preguntado por el sitio (no insistimos más de dos) */
var TRASCORREGIR=null;   /* qué hacer al terminar de corregir el pueblo */
function startFlow(){
 if(!isMobile){document.getElementById("desknote").classList.remove("hidden");return;}
 if(!MY){askLoc(function(ok){if(ok)startFlow();else document.getElementById("loc").innerHTML='📍 <span style="color:var(--teja2)">Necesitamos tu ubicación para situar tu noche. Actívala y vuelve a tocar.</span>';});return;}
 cur=0;ans=[null,null,null,null,null,null];WEAR={h:"",s:""};PROP="";
 OBSCONF=false;OBSQ=false;OBSINT=0;TRASCORREGIR=null;
 flow.classList.add("on");renderStep();
}
function closeFlow(){flow.classList.remove("on");}
function back(){if(cur>0){cur--;renderStep();}else closeFlow();}
/* Chip con la población detectada, visible MIENTRAS se vota: así se ve dónde
   se está guardando la noche y se puede corregir si no es el pueblo correcto
   (o si no hemos sabido detectarlo). */
function chipLugar(){
 var el=document.getElementById("lugarchip");if(!el)return;
 if(MUN.n){
  el.innerHTML='<span class="lc-txt">📍 Tu noche se guarda en <b>'+MUN.n+'</b></span>'
   +'<button type="button" class="lc-fix" onclick="abreCorrige()">¿No es aquí?</button>';
 }else{
  el.innerHTML='<span class="lc-txt">📍 No hemos sabido detectar tu pueblo'
   +(MY?' — usaremos <b>'+MY.n+'</b>':'')+'</span>'
   +'<button type="button" class="lc-fix" onclick="abreCorrige()">Decirnos cuál es</button>';
 }
}
function abreCorrige(){
 var el=document.getElementById("lugarchip");if(!el)return;
 el.innerHTML='<div class="lc-form"><label>¿En qué pueblo has dormido?'
  +'<input id="lugarprop" type="text" maxlength="60" placeholder="Escribe el nombre" value="'+(MUN.n||"")+'"></label>'
  +'<button type="button" class="lc-ok" onclick="guardaCorrige()">Guardar</button></div>';
 var i=document.getElementById("lugarprop");if(i)i.focus();
}
/* Corregir el pueblo no es dejar una nota: RE-ANCLA la noche. Si lo que se
   teclea está entre las 7.157 poblaciones, la noche pasa a guardarse allí y su
   referencia climática pasa a ser la estación de AEMET más cercana a ESE
   pueblo, con su valor esperado. Quien durmió en Rascafría y vota de paso por
   Valencia cuenta una noche de Rascafría, medida contra Rascafría. Si el
   nombre no está en la lista no podemos anclar nada: se anota tal cual para
   revisarlo a mano, como antes. */
function buscaLugar(L,txt){
 if(!L||!txt)return null;
 var q=na_(txt),ex=null,pre=null;
 for(var i=0;i<L.length;i++){
  var n=na_(L[i][1]);
  if(n===q)return L[i];
  if(!pre&&n.indexOf(q)===0)pre=L[i];
 }
 return ex||pre;
}
function guardaCorrige(){
 var i=document.getElementById("lugarprop");
 var txt=i?i.value.trim().slice(0,60):"";
 if(!txt){rematarCorrige("",false);return;}
 cargaLugares(function(L){
  var p=buscaLugar(L,txt);
  if(p){
   MUN={id:p[0],n:p[1]};PROP="";
   ANCLA={la:p[2],lo:p[3]};
   MY=nearest(p[2],p[3]);
   var loc=document.getElementById("loc");
   if(loc)loc.innerHTML='📍 Tu noche es de <b>'+MUN.n+'</b> <span style="opacity:.7">· referencia AEMET: '+MY.n+'</span>';
   rematarCorrige('<span class="lc-txt">✅ Tu noche se guarda en <b>'+MUN.n+'</b> <span style="opacity:.7">· referencia AEMET: '+MY.n+'</span></span>',true);
  }else{
   PROP=txt;
   rematarCorrige('<span class="lc-txt">✅ Gracias: anotamos <b>'+PROP+'</b> y lo revisamos. Tu noche cuenta igual.</span>',false);
  }
 });
}
/* Cierra la corrección. Si veníamos de la comprobación de coherencia, seguimos
   con el envío; y si no hemos sabido anclar el pueblo, la noche no puede contar
   como una noche normal del sitio que dice el GPS: se guarda apartada. */
function rematarCorrige(html,anclado){
 var seguir=TRASCORREGIR;TRASCORREGIR=null;
 if(!seguir){
  var el=document.getElementById("lugarchip");
  if(el&&html)el.innerHTML=html;
  return;
 }
 if(!anclado){OBSCONF=true;OBSQ=true;}
 seguir();
}
function renderStep(){
 document.getElementById("barfill").style.width=(cur/NPASOS*100)+"%";
 document.getElementById("stepn").textContent=(cur+1)+"/"+NPASOS;
 document.getElementById("backbtn").textContent=cur===0?"‹ Salir":"‹ Atrás";
 setTimeout(chipLugar,0);
 var b=document.getElementById("stepbody");
 if(cur===Q.length){   /* paso opcional: lo que marcó la pulsera o el reloj */
  b.innerHTML='<div class="q">⌚ ¿Llevas pulsera o reloj de sueño?</div>'
   +'<p class="wsub2">Opcional. Si tu dispositivo te da estos datos, escríbelos: así contrastamos lo que <b>sientes</b> con lo que <b>midió el aparato</b> — y ambos con lo que decía AEMET.</p>'
   +'<div class="wfields"><label>Horas dormidas<input id="wh" type="number" inputmode="decimal" step="0.1" min="0" max="16" placeholder="7,5"></label>'
   +'<label>Puntuación de sueño (0-100)<input id="ws" type="number" inputmode="numeric" step="1" min="0" max="100" placeholder="82"></label></div>'
   +'<div class="opts"><button class="opt" onclick="finishWear(true)"><span class="em">✅</span><span>Enviar con estos datos</span></button>'
   +'<button class="opt" onclick="finishWear(false)"><span class="em">⏭️</span><span>No llevo / omitir</span></button></div>';
  return;
 }
 var s=Q[cur];
 b.innerHTML='<div class="q">'+s.q+'</div>'+(s.sub?'<p class="wsub2">'+s.sub+'</p>':'')
  +'<div class="opts">'+s.o.map(function(o,i){return '<button class="opt'+(ans[cur]&&ans[cur].i===i?' sel':'')+'" onclick="pick('+i+','+o[2]+')"><span class="em">'+o[0]+'</span><span>'+o[1]+'</span></button>';}).join("")+'</div>';
}
function finishWear(usar){
 if(usar){var h=parseFloat(String((document.getElementById("wh")||{}).value||"").replace(",","."));
  var s=parseInt((document.getElementById("ws")||{}).value,10);
  /* un campo vacío no es un 0: si no hay dato, no se manda nada */
  WEAR.h=(isFinite(h)&&h>0&&h<=16)?h:"";WEAR.s=(isFinite(s)&&s>0&&s<=100)?s:"";}
 finish();
}
function pick(i,val){ans[cur]={i:i,val:val};document.querySelectorAll(".opt")[i].classList.add("sel");document.getElementById("barfill").style.width=((cur+1)/NPASOS*100)+"%";setTimeout(function(){cur++;renderStep();},230);}
/* scroll suave con easing (robusto en iOS, sin salto brusco) */
function smoothScroll(el,to,dur){var start=el.scrollTop,ch=to-start,t0=null;function step(t){if(!t0)t0=t;var p=Math.min((t-t0)/dur,1),e=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;el.scrollTop=start+ch*e;if(p<1)requestAnimationFrame(step);}requestAnimationFrame(step);}

/* RECOMPENSA */
var EMO=["🔥","🥵","😐","🙂","😴"],EMOC=["🔥","🥵","😐","🙂","😊"],LBL=["Muy mal","Con calor","Regular","Bien","De maravilla"];
var DEU=["","Ninguna, a cero","Poca","Alguna","Bastante","Muchísima"];
/* Deuda de sueño + contraste con la pulsera: la tarjeta que da sentido al
   estudio para quien cuida su descanso (deportistas, insomnes, curiosos). */
function deudaCard(deuda,descanso,w){
 if(!deuda&&w.h===""&&w.s==="")return "";
 var h='<div class="card fade sleepdebt" style="animation-delay:.75s"><h3>🛌 Tu deuda de sueño</h3>';
 if(deuda){
  var col=deuda<=2?"#8fb07a":deuda===3?"#e8b45c":"#d9604a";
  h+='<div class="dgrid"><div class="dbar"><i style="width:'+(deuda*20)+'%;background:'+col+'"></i></div>'
   +'<div class="dlab" style="color:'+col+'">'+DEU[deuda]+'</div></div>';
  h+='<p class="dtxt">'+(deuda>=4
    ? "Arrastras déficit. La deuda de sueño no se paga con una sola noche: hacen falta <b>varias noches seguidas de sueño profundo</b> — y para eso el cuerpo necesita que la temperatura baje de madrugada."
    : deuda===3
    ? "Empiezas a acumular. Cuando la noche no refresca, el sueño profundo se fragmenta aunque duermas las mismas horas: <b>duermes igual, descansas menos</b>."
    : "Vas bien. Mantener la deuda a cero en verano depende menos de las horas que de <b>la temperatura a la que duermes</b>.")+'</p>';
 }
 if(w.h!==""||w.s!==""){
  h+='<div class="wcmp"><div class="wtit">⌚ Lo que midió tu dispositivo</div><div class="wrow">';
  if(w.h!=="")h+='<div class="c"><div class="n">'+String(w.h).replace(".",",")+'</div><small>horas</small></div>';
  if(w.s!=="")h+='<div class="c"><div class="n" style="color:'+colorFor(w.s/10)+'">'+w.s+'</div><small>puntuación</small></div>';
  h+='<div class="c"><div class="n" style="color:'+colorFor(descanso)+'">'+descanso.toFixed(1)+'</div><small>tu sensación</small></div></div>';
  if(w.s!==""){
   var dif=(w.s/10)-descanso;
   h+='<p class="dtxt" style="margin-top:10px">'+(Math.abs(dif)<1.5
     ? "Tu cuerpo y tu dispositivo <b>coinciden</b>."
     : dif>0
     ? "Tu reloj puntúa <b>mejor</b> de lo que tú sientes: a veces el aparato cuenta horas, pero no lo reparador que fue el sueño."
     : "Tú lo has sentido <b>mejor</b> de lo que marca tu reloj.")+'</p>';
  }
  h+='</div>';
 }
 return h+'</div>';
}
/* COHERENCIA — el caso de quien durmió en la sierra y vota a mediodía desde la
   ciudad: el móvil dice Valencia y la noche fue de Rascafría. NO se rechaza el
   voto: se pregunta por el SITIO. Un voto que se aparta de lo esperado suele
   ser justo el dato que buscamos —el microclima de tu calle— y tirarlo
   convertiría el observatorio en un espejo de AEMET. Por eso el umbral solo
   caza lo imposible: un microclima real se mueve 2-4 grados de mínima; de la
   sierra a la costa hay ocho o diez. Se fija en grados y se traduce al índice
   con la misma constante del baseline (0,52 puntos por grado). */
var OBS_GRADOS=6,OBS_UMBRAL=OBS_GRADOS*0.52;
function incoherente(descanso,zona){return Math.abs(descanso-zona.d)>=OBS_UMBRAL;}
function pideCoherencia(descanso,zona){
 var lugar=MUN.n||zona.n;
 var b=document.getElementById("stepbody");if(!b)return;
 var sn=document.getElementById("stepn");if(sn)sn.textContent="✓";
 b.innerHTML='<div class="q">Antes de guardar, una comprobación</div>'
  +'<p class="wsub2">En <b>'+lugar+'</b> lo normal son <b>'+zona.d.toFixed(1).replace(".",",")+'/10</b> según diez veranos de AEMET'
  +(MUN.n&&MUN.n!==zona.n?' (estación de '+zona.n+')':'')
  +', y nos has contado una noche de <b>'+descanso.toFixed(1).replace(".",",")+'/10</b>. '
  +(descanso>zona.d?'Puede ser: hay sitios que se portan mucho mejor que su estación, y encontrarlos es justo lo que buscamos.'
                  :'Puede ser: hay sitios que se portan mucho peor que su estación, y encontrarlos es justo lo que buscamos.')
  +' Pero si has dormido en otro pueblo y estás votando de paso por aquí, la noche se guardaría en el sitio equivocado.</p>'
  +'<div class="opts"><button class="opt" onclick="confirmaLugar()"><span class="em">🛏️</span><span>Sí, he dormido en '+lugar+'</span></button>'
  +'<button class="opt" onclick="corrigeDesdeCoherencia()"><span class="em">📍</span><span>No, he dormido en otro pueblo</span></button></div>';
}
/* Si confirma, la noche se guarda igual, pero apartada: no entra en el
   certificado ni en el ranking hasta que otras noches de ese pueblo la
   respalden. Si de verdad hay un refugio ahí, aparecerá al repetirse. */
function confirmaLugar(){OBSCONF=true;OBSQ=true;finish();}
function corrigeDesdeCoherencia(){
 var b=document.getElementById("stepbody");if(!b)return;
 TRASCORREGIR=function(){finish();};
 b.innerHTML='<div class="q">¿En qué pueblo has dormido?</div>'
  +'<p class="wsub2">La noche se guardará allí, con la estación de AEMET y el valor esperado de ese pueblo.</p>'
  +'<div class="lc-form"><label><input id="lugarprop" type="text" maxlength="60" placeholder="Escribe el nombre" value=""></label>'
  +'<button type="button" class="lc-ok" onclick="guardaCorrige()">Guardar</button></div>';
 var i=document.getElementById("lugarprop");if(i)i.focus();
}
function finish(){
 var dormir=ans[0].val,confort=ans[1].val,despertar=ans[3].val,perm=ans[4].val;
 var descanso=((dormir-1)/4*10*0.6+(despertar-1)/4*10*0.4);
 var zona=MY||nearSeed(ANCLA||MYLL)||SEED[0];
 /* La comprobación va aquí: con la zona ya re-anclada al pueblo corregido, no
    antes. Se pregunta como mucho dos veces; a la tercera se guarda apartada. */
 if(!OBSCONF&&incoherente(descanso,zona)){
  if(OBSINT<2){OBSINT++;pideCoherencia(descanso,zona);return;}
  OBSQ=true;
 }
 flow.classList.remove("on");
 /* El nombre que se enseña es el del pueblo elegido (Dénia); la referencia
    climática sigue siendo la estación de AEMET (Pego), y se dice cuál es. */
 var nombreLugar=MUN.n||zona.n;
 window._obsShare={idx:descanso.toFixed(1),zona:nombreLugar};
 var ref=ANCLA||MYLL||zona;
 /* Envío de la noche al buzón (si está desplegado). El resultado se enseña
    igual: nunca se bloquea la recompensa por un fallo de red. */
 var deuda=ans[5]?ans[5].val:"";
 if(URL_OBS&&zona.id){
  var pay={z:zona.id,d:dormir,c:confort,r:ans[2]?ans[2].val:"",w:despertar,k:perm,
           sd:deuda,wh:WEAR.h,ws:WEAR.s,m:MUN.id,mn:MUN.n,mp:PROP,u:obsUid(),v:1};
  /* g = dónde estaba el móvil al votar; mc = la noche va anclada a un pueblo
     corregido a mano (g y la zona pueden estar lejísimos, y es correcto);
     q = guardar apartada hasta que otras noches de ese pueblo la respalden. */
  if(MYLL)pay.g=MYLL.la.toFixed(2)+","+MYLL.lo.toFixed(2);
  if(ANCLA)pay.mc=1;
  if(OBSQ)pay.q=1;
  /* El resultado del guardado SIEMPRE se dice. Antes se tragaba los errores en
     silencio y la pantalla daba las gracias aunque la noche se hubiera perdido. */
  var diEstado=function(txt,ok){
   var el=document.getElementById("obsestado");if(!el)return;
   el.className="obsestado "+(ok?"ok":"ko");el.innerHTML=txt;el.style.display="block";
  };
  try{
   fetch(URL_OBS,{method:"POST",body:JSON.stringify(pay)}).then(function(x){return x.json();})
    .then(function(d){
      if(d&&d.ok){window._obsGuardado=true;
       diEstado(OBSQ
        ? "✅ Guardada tu noche en <b>"+nombreLugar+"</b>. Como se aparta mucho de lo normal allí, queda aparte del cálculo hasta que otras noches de "+nombreLugar+" la respalden."
        : "✅ Guardado. Tu noche en <b>"+nombreLugar+"</b> ya cuenta en el estudio.",true);
       fetch(URL_OBS+"?global=1").then(function(x){return x.json();}).then(addZonasVotadas).catch(function(){});
      }
      else if(d&&d.error==="ritmo")
       diEstado("🕗 Ya habías contado una noche hace poco: <b>se admite una cada 8 horas</b> — dormir se vota una vez al día. Esta no se ha guardado.",false);
      else
       diEstado("⚠️ No se ha podido guardar tu noche"+(d&&d.error?" ("+d.error+")":"")+". Vuelve a intentarlo más tarde.",false);
    })
    .catch(function(){diEstado("⚠️ No se ha podido guardar tu noche (sin conexión o el buzón no responde). Tu resultado sí se muestra aquí.",false);});
  }catch(e){diEstado("⚠️ No se ha podido enviar tu noche.",false);}
 }
 var cand=SEED.filter(function(z){return z.d>=7.5;});
 cand.forEach(function(z){z._km=km(ref,z);});
 cand.sort(function(a,b){return a._km-b._km;});
 var contra=cand.filter(function(z){return z._km>4})[0]||cand[0]||SEED.slice().sort(function(a,b){return b.d-a.d})[0];
 var near=SEED.map(function(z){return {z:z,k:km(ref,z)};}).filter(function(o){return o.k>4;}).sort(function(a,b){return a.k-b.k;}).slice(0,3);
 reward.classList.add("on");reward.scrollTop=0;
 document.getElementById("rbody").innerHTML=
  '<div class="mapglow fade"><div class="mapbox" style="margin:0"><svg id="rmap" viewBox="0 0 300 190"></svg></div></div>'+
  '<div class="rw-say fade" style="animation-delay:.15s"><div class="big">Gracias.</div><div class="small">Acabas de sumar tu noche al mapa del descanso de España.</div></div>'+
  '<div class="card fade" style="animation-delay:.3s"><h3>Tu experiencia de esta noche</h3><div class="yourgrid">'+
   '<div class="mini"><span class="em">'+EMO[dormir-1]+'</span><div><div class="l">Dormir</div><div class="v">'+LBL[dormir-1]+'</div></div></div>'+
   '<div class="mini"><span class="em">'+EMOC[confort-1]+'</span><div><div class="l">Confort ahora</div><div class="v">'+LBL[confort-1]+'</div></div></div>'+
   '<div class="mini"><span class="em">'+EMO[despertar-1]+'</span><div><div class="l">Despertar</div><div class="v">'+LBL[despertar-1]+'</div></div></div>'+
   '<div class="mini"><span class="em">'+["🚗","🙁","😐","🙂","❤️"][perm-1]+'</span><div><div class="l">Volverías</div><div class="v">'+["Me iría","Otro sitio","Igual","Sí","Sin dudarlo"][perm-1]+'</div></div></div>'+
   '</div><div class="tuidx"><span style="color:var(--muted);font-size:13px">Tu índice de descanso</span><div class="n" style="color:'+colorFor(descanso)+'">'+descanso.toFixed(1)+'<span style="font-size:16px;color:var(--muted)">/10</span></div></div></div>'+
  '<div class="card fade thesis" style="animation-delay:.45s"><h3>Tú frente a los datos · '+nombreLugar+'</h3>'+
   (MUN.n&&MUN.n!==zona.n?'<p style="text-align:center;color:var(--muted);font-size:12.5px;margin:-4px 0 10px">Referencia climática: estación de AEMET de <b>'+zona.n+'</b></p>':'')+
   '<div class="row">'+
   '<div class="c"><div class="n" style="color:'+colorFor(descanso)+'">'+descanso.toFixed(1)+'</div><small>Tú, esta noche</small></div>'+
   '<div class="c" style="align-self:center;color:var(--muted)">vs</div>'+
   '<div class="c"><div class="n" style="color:'+colorFor(zona.d)+'">'+zona.d.toFixed(1)+'</div><small>Esperado (AEMET)</small></div></div>'+
   '<p style="text-align:center;color:var(--muted);font-size:13.5px;margin-top:14px">'+(Math.abs(descanso-zona.d)<1.5?"Tu noche encaja con lo que AEMET esperaba aquí.":descanso>zona.d?"Has dormido mejor de lo que el clima suele dar aquí.":"Has dormido peor de lo que el clima suele dar aquí.")+'</p></div>'+
  '<div class="contrast fade" style="animation-delay:.6s"><div class="pre">Mientras tú dormías…</div><div class="km">A solo '+contra._km+' km</div><div class="txt">en <b>'+contra.n+'</b> se descansa a <b>'+contra.d.toFixed(1)+'</b>.</div>'+
   '<div class="vs"><div class="c"><div class="n" style="color:'+colorFor(zona.d)+'">'+zona.d.toFixed(1)+'</div><small>'+zona.n+'</small></div><div class="c" style="align-self:center;color:var(--muted)">vs</div><div class="c"><div class="n" style="color:'+colorFor(contra.d)+'">'+contra.d.toFixed(1)+'</div><small>'+contra.n+'</small></div></div>'+
   '<p style="color:var(--muted);font-size:12.5px;margin-top:12px">Según 10 veranos de AEMET. En cuanto haya votos, verás lo que dice la gente.</p></div>'+
  '<div class="card fade" style="animation-delay:.7s"><h3>Cerca de ti, esta madrugada</h3><div class="nearby">'+
   near.map(function(o){return '<div class="row"><span class="idx" style="color:'+colorFor(o.z.d)+';background:'+bgFor(o.z.d)+'">'+o.z.d.toFixed(1)+'</span><div class="info"><div class="n">'+o.z.n+' · '+o.k+' km</div><div class="p">"'+o.z.f+'"</div></div></div>';}).join("")+'</div></div>'+
  deudaCard(deuda,descanso,WEAR)+
  '<button class="share fade" style="animation-delay:.8s" onclick="shareNoche()">📲 Comparte tu noche</button>'+
  '<button class="again pri2" onclick="verCurioso()">🔎 ¿Y cómo se duerme en otra población española?</button>'+
  '<button class="again" onclick="reward.classList.remove(\'on\');document.getElementById(\'morehint\').classList.add(\'hidden\');window.scrollTo(0,0)">Volver al observatorio</button>'+
  '<p class="obsestado" id="obsestado" style="display:none"></p>'+
  (URL_OBS?'':'<p class="obsdemo" id="obsdemo">Modo demostración: el buzón de noches aún no está desplegado, así que <b>esta noche no se ha guardado</b>.</p>')+
  '<p class="disc-o">El Observatorio del Descanso · experiencias reales cruzadas con datos de AEMET · sin predicciones, solo lo ocurrido. Sé de los primeros: cuantos más votemos, más real será el mapa.</p>';
 renderMap();var rm=document.getElementById("rmap");if(rm){var svg=document.getElementById("map");rm.innerHTML=svg.innerHTML;var p=proj(zona);rm.innerHTML+='<circle cx="'+p[0].toFixed(1)+'" cy="'+p[1].toFixed(1)+'" r="4" fill="none" stroke="#f3ece0" stroke-width="1.5"/><circle class="pinp" cx="'+p[0].toFixed(1)+'" cy="'+p[1].toFixed(1)+'" fill="#e0834f"/>';}
 /* auto-scroll: revela que hay más (evita el abandono en la primera pantalla) */
 var mh=document.getElementById("morehint");mh.classList.remove("hidden");
 setTimeout(function(){smoothScroll(reward,Math.round(window.innerHeight*0.52),1100);},1300);
 reward.addEventListener("scroll",function(){if(reward.scrollTop>window.innerHeight*0.45)mh.classList.add("hidden");},{passive:true});
}

/* BOTONES FLOTANTES — desplazamiento con la misma curva suave que usa la
   portada (el scroll nativo va a tirones en iOS). Si el sistema pide reducir
   movimiento, el salto es directo. Ninguna sección cambia de sitio: los
   botones solo llevan hasta ellas. */
function scrollSuaveA(destinoY,dur){
 var quieto=window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches;
 if(quieto||!dur){window.scrollTo(0,destinoY);return;}
 var ini=window.scrollY,dist=destinoY-ini,t0=null,parar=false;
 var evs=["wheel","touchstart","keydown","pointerdown"];
 function stop(){parar=true;}
 function limpia(){evs.forEach(function(ev){window.removeEventListener(ev,stop);});}
 evs.forEach(function(ev){window.addEventListener(ev,stop,{passive:true});});
 function paso(t){
  if(parar){limpia();return;}
  if(!t0)t0=t;
  var p=Math.min((t-t0)/dur,1);
  window.scrollTo(0,ini+dist*(0.5*(1-Math.cos(Math.PI*p))));   /* easeInOutSine */
  if(p<1)requestAnimationFrame(paso);else limpia();
 }
 requestAnimationFrame(paso);
}
function aSeccion(sel,dur){
 var el=document.querySelector(sel);if(!el)return null;
 scrollSuaveA(Math.max(0,el.getBoundingClientRect().top+window.scrollY-46),dur||900);
 return el;
}
function irAVotar(){aSeccion(".votabox",900);}
function irACurioso(){
 aSeccion("#curioso",900);
 setTimeout(function(){var i=document.getElementById("curbusca");if(i)i.focus();},950);
}
(function(){
 var fabs=document.getElementById("fabs");if(!fabs)return;
 function pinta(){
  var tapado=flow.classList.contains("on")||reward.classList.contains("on");
  fabs.classList.toggle("on",window.scrollY>window.innerHeight*0.55&&!tapado);
 }
 window.addEventListener("scroll",pinta,{passive:true});
 window.addEventListener("resize",pinta,{passive:true});
 if(window.MutationObserver){
  var mo=new MutationObserver(pinta);
  mo.observe(flow,{attributes:true,attributeFilter:["class"]});
  mo.observe(reward,{attributes:true,attributeFilter:["class"]});
 }
 pinta();
})();
</script>
</body></html>
"""


def bloque_preguntas_descanso(estaciones: list, site: str) -> str:
    """Bloque de preguntas frecuentes del Observatorio, escrito para las búsquedas
    reales que traen gente a la web («dónde hace menos calor hoy en España»,
    «cuándo termina la ola de calor», «harta del calor»).

    Los ejemplos NO se escriben a mano: salen de las estaciones con la mínima de
    verano más baja, así que el texto se actualiza solo con los datos. Y se habla
    de lo que *suele* pasar, no de esta noche concreta: el dato climatológico de
    AEMET llega con días de retraso y aquí no hacemos predicción."""
    frescas = sorted((e for e in estaciones if e.get("tmin") is not None),
                     key=lambda e: e["tmin"])[:3]
    if not frescas:
        return ""
    ejemplos = ", ".join(
        f'<b>{e["loc"].split(",")[0]}</b> ({e["prov"]}, {_n_es(e["tmin"])}&nbsp;°C de media)'
        for e in frescas[:2])
    umbral = str(int(round(frescas[0]["tmin"] + 3)))  # entero: "10 °C", no "10,0 °C"
    # Las peores: el contraste que busca quien está harto del calor.
    peores = sorted((e for e in estaciones if e.get("tmin") is not None),
                    key=lambda e: -e["tmin"])[:1]
    peor_txt = (f'<b>{peores[0]["loc"].split(",")[0]}</b> ({peores[0]["prov"]}), '
                f'con <b>{_n_es(peores[0]["tmin"])}&nbsp;°C</b> de mínima media'
                if peores else "")
    return f"""
  <section class="preg">
    <h2>¿Dónde hace menos calor hoy en España para poder dormir?</h2>
    <p>Si estás harto del calor y necesitas un respiro, no todo el país sufre igual. Mientras en la costa mediterránea y el sur se encadenan <b>noches tropicales</b> (mínima que no baja de 20&nbsp;°C) y hasta <b>ecuatoriales</b> (por encima de 25&nbsp;°C), hay una España donde <b>la madrugada sigue refrescando por debajo de los {umbral}&nbsp;°C</b>.</p>
    <div class="cajaref">
      <p>❄️ <b>Dónde se duerme fresco:</b> la montaña interior y los valles altos —Pirineo, sistema Ibérico, cordillera Cantábrica y el interior de Galicia—. Con diez veranos de AEMET, las más frescas son {ejemplos}. En el otro extremo, {peor_txt}.</p>
      <a class="btnref" href="{site}/mapa-estaciones/">Consultar el mapa de refugios climáticos →</a>
    </div>
    <h2>¿Cuándo termina la ola de calor y refrescará por la noche?</h2>
    <p>Nadie puede decirte el día exacto —y aquí no hacemos predicción: <b>medimos lo que ya ha pasado</b>—. Lo que sí sabemos es qué hay en juego: cuando se encadenan noches sin bajar de 20&nbsp;°C, el sueño profundo se acorta y <b>la deuda de sueño se acumula</b> noche tras noche. Por eso el alivio no llega cuando baja la máxima del mediodía, sino <b>cuando vuelve a refrescar de madrugada</b>.</p>
    <p>Puedes seguirlo día a día en el <a href="{site}/ola-de-calor/">mapa de la ola de calor en España</a>, con las mínimas de cada noche según AEMET: ahí se ve, jornada a jornada, si la ola afloja o aprieta en tu provincia. Y si necesitas escapar ya, mira <a href="{site}/refugios-climaticos-naturales-cerca-de-mi/">qué refugios climáticos tienes cerca</a>.</p>
  </section>
"""


def construir_pagina_observatorio(estaciones: list, site: str) -> str:
    seed = json.dumps(seed_observatorio(estaciones), ensure_ascii=False, separators=(",", ":"))
    # TODAS las estaciones (compacto [lat,lon,nombre,baseline]) para que el
    # geoposicionamiento resuelva la estación REALMENTE más cercana (exacta),
    # no la más cercana de las 40 semilla. Así "tu zona" nunca se equivoca.
    allz = json.dumps([[round(e["lat"], 3), round(e["lon"], 3),
                        e["loc"].split(",")[0][:22], _obs_baseline(e["tmin"]),
                        e["id"], e["prov"]]
                       for e in estaciones if e.get("tmin") is not None],
                      ensure_ascii=False, separators=(",", ":"))
    desc = ("¿Cómo has dormido esta noche? El Observatorio del Descanso es el mapa "
            "ciudadano del descanso climático de España: no medimos la temperatura, "
            "medimos cómo se duerme. Comparte tu noche en 10 segundos y descubre dónde "
            "se descansa mejor, con datos cruzados con AEMET.")
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "nochetropical.es", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "El Observatorio del Descanso",
             "item": site + "/observatorio-del-descanso/"}]},
        {"@type": "WebApplication", "name": "El Observatorio del Descanso",
         "url": site + "/observatorio-del-descanso/", "applicationCategory": "LifestyleApplication",
         "operatingSystem": "Web", "description": desc,
         "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"}},
        # FAQ con las dos preguntas que trae la gente desde Google, para que
        # pueda mostrarse como respuesta directa en el buscador.
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question",
             "name": "¿Dónde hace menos calor hoy en España para poder dormir?",
             "acceptedAnswer": {"@type": "Answer", "text":
                "Las noches más frescas de España se dan en la montaña interior y los "
                "valles altos: Pirineo, sistema Ibérico, cordillera Cantábrica y el "
                "interior de Galicia, donde la mínima de verano baja de los 15 °C. En "
                "la costa mediterránea y el sur, en cambio, se encadenan noches "
                "tropicales (mínima por encima de 20 °C) y ecuatoriales (por encima de "
                "25 °C). El mapa de estaciones de AEMET muestra el dato de cada zona."}},
            {"@type": "Question",
             "name": "¿Cuándo termina la ola de calor y refrescará por la noche?",
             "acceptedAnswer": {"@type": "Answer", "text":
                "No hacemos predicción: publicamos lo ya medido por AEMET, día a día. "
                "El alivio real no llega cuando baja la máxima del mediodía, sino "
                "cuando la mínima vuelve a bajar de 20 °C de madrugada, que es cuando "
                "el sueño profundo se recupera. En el mapa de la ola de calor se puede "
                "seguir jornada a jornada si afloja o aprieta en cada provincia."}}]}]},
        ensure_ascii=False)
    return (PAGINA_OBSERVATORIO
            .replace("__NAVCSS__", CSS_NAV_ESCUETO)
            .replace("__FOOTERCSS__", CSS_FOOTER_ESCUETO)
            .replace("__NAV__", nav_escueto_html(site))
            .replace("__FOOTER__", footer_escueto_html(site))
            .replace("__SCHEMA__", schema)
            .replace("__DESC__", desc)
            .replace("__SEED__", seed)
            .replace("__SILUETA__", SILUETA_ES)
            .replace("__ALLZ__", allz)
            .replace("__PREGUNTAS__", bloque_preguntas_descanso(estaciones, site))
            .replace("__OBS_URL__", APPS_SCRIPT_OBS_URL)
            .replace("__SITE__", site)
            .replace("__HOME__", site + "/"))


def construir_pagina_hotel(h: dict, site: str) -> str:
    """Ficha individual de un hotel: su certificado (verlo + descargarlo +
    código para embeber), el dato AEMET de la zona, cómo llegar y reservar.
    Es la página que da al hotel un motivo real para enlazarnos (backlink)."""
    from urllib.parse import quote_plus
    sl = h["slug"]
    niv = h["nivel"]
    # Los PNG del sello se renderizan aparte (la Action no tiene navegador) y se
    # commitean; los hoteles recién añadidos aún no lo tienen. Degradamos: el
    # hero visible ya es el SVG; para og:image (redes/Google, que no admiten SVG)
    # caemos a la og.png del sitio, y ocultamos las descargas/embed en PNG hasta
    # que exista. Al renderizar y commitear el PNG, se encienden solas.
    png_ok = (DOCS_DIR / "badges" / f"{sl}.png").exists()
    og_img = f"{site}/badges/{sl}.png" if png_ok else f"{site}/og.png"
    dl_png = ((f'<a href="{site}/badges/{sl}.png" download>⬇ PNG (web, fondo oscuro)</a>'
               f'<a href="{site}/badges/{sl}-imprimir.png" download>⬇ PNG (imprimir, fondo claro)</a>')
              if png_ok else "")
    nt_txt = "0" if h["nt"] < 0.05 else _n_es(h["nt"])
    # Complemento de datos (humedad/viento de la estación de referencia): solo si
    # hay dato; si no, la ficha queda igual que antes del backfill de humedad.
    hum = h.get("hum")
    hum_cards = hum_note = ""
    if hum:
        hum_cards = (f'<div class="st"><div class="v">{hum["hr"]}%</div>'
                     '<div class="k">humedad media agosto</div></div>')
        if hum.get("viento") is not None:
            hum_cards += (f'<div class="st"><div class="v">{hum["viento"]} km/h</div>'
                          '<div class="k">viento medio agosto</div></div>')
        hum_note = ('<p class="muted" style="margin:-4px 0 14px">Sensación nocturna típica en '
                    f'agosto: <b style="color:var(--paper)">{hum["sensacion"]}</b>. '
                    '<span style="opacity:.75">Humedad y viento medios de la estación de '
                    'referencia, según AEMET.</span></p>')
    niv_txt = "Refugio Certificado" if niv == "A" else "Zona Verificada"
    acento = "var(--teja)" if niv == "A" else "var(--teal)"
    ficha_url = f"{site}/hoteles-refugio-climatico/{sl}/"
    fuente_dato = (f"la estación AEMET de {h['municipio']}" if niv == "A"
                   else (f"la {h['ref_desc'][0].lower()}{h['ref_desc'][1:]}" if h.get("ref_desc")
                         else "la estación AEMET más cercana"))
    if h["slug_booking"]:
        reservar = (f'<a class="btn pri" href="{cj_deeplink(h["slug_booking"], sl)}" '
                    'target="_blank" rel="sponsored nofollow noopener">Reservar en Booking · precios y opiniones →</a>')
    elif h.get("web"):
        reservar = (f'<a class="btn pri" href="{h["web"]}" target="_blank" rel="nofollow noopener">'
                    'Web oficial del alojamiento →</a>')
    else:
        reservar = (f'<a class="btn pri" href="{site}/tu-hotel/">¿Gestionas este alojamiento? '
                    'Añade tu web y reservas →</a>')
    tel = h.get("telefono", "").strip()
    tel_btn = (f'<a class="btn sec" href="tel:{tel.replace(" ", "")}">☎ Reservas: {tel}</a>' if tel else "")
    maps = "https://www.google.com/maps/search/?api=1&query=" + quote_plus(
        f'{h["hotel"]} {h["municipio"]} {h["provincia"]}')
    embed_img = f'{site}/badges/{sl}.png' if png_ok else f'{site}/badges/{sl}.svg'
    embed = (f'<a href="{ficha_url}" target="_blank" rel="noopener">\n'
             f'  <img src="{embed_img}" width="180" height="180"\n'
             f'       alt="Refugio Climatico Natural certificado - {h["municipio"]} ({h["provincia"]}) - datos AEMET">\n'
             f'</a>')
    desc = (f"{h['hotel']} ({h['municipio']}, {h['provincia']}) es un refugio climático natural: "
            f"en verano la mínima media baja a {_n_es(h['tmin'])} °C y apenas hay noches "
            f"tropicales, según datos de AEMET. Se duerme fresco, con manta y sin aire "
            f"acondicionado. Certificado, cómo llegar y reservas.")
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "nochetropical.es", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Hoteles en refugios climáticos",
             "item": site + "/hoteles-refugio-climatico/"},
            {"@type": "ListItem", "position": 3, "name": h["hotel"], "item": ficha_url}]},
        {"@type": "LodgingBusiness", "name": h["hotel"], "url": ficha_url,
         "address": {"@type": "PostalAddress", "addressLocality": h["municipio"],
                     "addressRegion": h["provincia"], "addressCountry": "ES"},
         **({"telephone": tel} if tel else {}),
         "description": (f"Alojamiento en un refugio climático natural: mínima media de verano "
                         f"{_n_es(h['tmin'])} °C, {nt_txt} noches tropicales al año (datos de AEMET).")}]},
        ensure_ascii=False)
    css = (
        ':root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;'
        '--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--verde:#8fb07a;'
        '--fd:"Fraunces",Georgia,serif;--fb:"Lora",Georgia,serif;--fm:ui-monospace,monospace}'
        '*{margin:0;padding:0;box-sizing:border-box}'
        'body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.65}'
        '.wrap{max-width:min(94vw,1000px);margin:0 auto;padding:0 24px}'
        'a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}'
        'header.h{padding:44px 0 8px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}'
        '.crumb{font-size:13px;color:var(--muted)}.crumb a{color:var(--muted)}'
        '.kick{font:600 12px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;color:' + acento + ';margin:14px 0 8px}'
        'h1{font-family:var(--fd);font-weight:900;font-size:clamp(26px,4.6vw,40px);line-height:1.08}'
        '.loc{color:var(--muted);font-size:15px;margin:10px 0 0}'
        'section{padding:16px 0}'
        'h2{font-family:var(--fd);font-weight:600;font-size:clamp(19px,3vw,24px);margin:22px 0 12px;color:var(--paper)}'
        'p{color:#d9ccb6;font-size:15.5px;margin:0 0 14px;max-width:70ch}p b{color:var(--paper)}'
        '.hero{display:grid;gap:22px;align-items:center;margin:14px 0 4px}'
        '@media(min-width:760px){.hero{grid-template-columns:230px 1fr}}'
        '.sello{width:100%;max-width:230px;margin:0 auto;display:block}'
        '.stats{display:flex;gap:12px;flex-wrap:wrap;margin:8px 0 16px}'
        '.st{flex:1;min-width:130px;background:var(--bg2);border:1px solid var(--line);border-radius:12px;padding:12px 14px}'
        '.st .v{font-family:var(--fm);font-weight:700;font-size:22px;color:var(--teal)}'
        '.st .v.tj{color:var(--teja2)}.st .k{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-top:3px}'
        '.niv{display:inline-block;font-size:12px;font-weight:700;color:' + acento + ';border:1px solid ' + acento + ';border-radius:20px;padding:3px 12px;margin-bottom:6px}'
        '.acts{display:flex;flex-wrap:wrap;gap:10px;margin:4px 0 6px}'
        '.btn{display:inline-block;padding:12px 18px;border-radius:11px;font-weight:700;font-size:14.5px}'
        '.btn.pri{background:var(--teja);color:#1a1209}.btn.pri:hover{background:var(--teja2);text-decoration:none}'
        '.btn.sec{background:transparent;border:1px solid var(--teja);color:var(--teja2)}.btn.sec:hover{background:rgba(217,116,78,.12);text-decoration:none}'
        '.panel{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:20px 22px;margin:8px 0}'
        '.dl{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0 4px}'
        '.dl a{font-size:13.5px;background:#0c0906;border:1px solid var(--line);border-radius:9px;padding:9px 13px;color:var(--paper)}'
        '.dl a:hover{border-color:var(--teja);text-decoration:none}'
        'pre{background:#0c0906;border:1px solid var(--line);border-radius:10px;padding:14px;overflow-x:auto;'
        'font-family:var(--fm);font-size:12.5px;color:#cbb89a;line-height:1.5;margin:10px 0}'
        '.muted{color:var(--muted);font-size:13px}'
    )
    return (
        '<!doctype html>\n<html lang="es"><head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{h["hotel"]} · Refugio Climático Natural en {h["municipio"]} ({h["provincia"]})</title>\n'
        f'<meta name="description" content="{desc}">\n'
        f'<link rel="canonical" href="{ficha_url}">\n'
        '<meta name="robots" content="index, follow, max-image-preview:large">\n'
        '<meta name="author" content="Ramón J. Lowesting">\n'
        '<meta property="og:type" content="article">\n'
        f'<meta property="og:title" content="{h["hotel"]} · Refugio Climático Natural">\n'
        f'<meta property="og:description" content="{desc}">\n'
        f'<meta property="og:url" content="{ficha_url}">\n'
        f'<meta property="og:image" content="{og_img}">\n'
        '<meta property="og:locale" content="es_ES">\n'
        f'<link rel="icon" type="image/svg+xml" href="{site}/favicon.svg">\n'
        f'<script type="application/ld+json">{schema}</script>\n'
        + _FUENTES_LINK + '\n<style>' + css + CSS_NAV_ESCUETO + CSS_FOOTER_ESCUETO
        + '</style></head><body>\n' + nav_escueto_html(site)
        + '<header class="h"><div class="wrap">'
        '<nav class="crumb" aria-label="breadcrumb">'
        f'<a href="{site}/">nochetropical.es</a> · '
        f'<a href="{site}/hoteles-refugio-climatico/">Hoteles refugio</a> · {h["municipio"]}</nav>'
        f'<div class="kick" style="margin-top:14px">🛡️ {niv_txt} · Datos AEMET</div>'
        f'<h1>{h["hotel"]}</h1>'
        f'<p class="loc">{h["municipio"]} · {h["provincia"]} · {miles(h["alt"])}&nbsp;m de altitud</p>'
        '</div></header>'
        '<section><div class="wrap"><div class="hero">'
        f'<img class="sello" src="{site}/badges/{sl}.svg" width="230" height="230" '
        f'alt="Sello Refugio Climático Natural de {h["municipio"]} ({h["provincia"]}): mínima media '
        f'de agosto {_n_es(h["tmin"])} grados, {nt_txt} noches tropicales al año, datos de AEMET">'
        '<div>'
        f'<span class="niv">🛡️ {niv_txt}</span>'
        f'<p>En <b>{h["municipio"]}</b> la noche refresca de verdad: según {fuente_dato}, la '
        f'mínima media de verano baja a <b>{_n_es(h["tmin"])}&nbsp;°C</b> y apenas hay noches '
        f'tropicales. Aquí se duerme fresco, <b>con manta en agosto y sin aire acondicionado</b>.</p>'
        '<div class="stats">'
        f'<div class="st"><div class="v">{_n_es(h["tmin"])}°</div><div class="k">mín. media agosto</div></div>'
        f'<div class="st"><div class="v tj">{nt_txt}</div><div class="k">noches tropicales/año</div></div>'
        f'<div class="st"><div class="v">{miles(h["alt"])} m</div><div class="k">altitud</div></div>'
        f'{hum_cards}'
        '</div>'
        f'{hum_note}'
        f'<div class="acts">{reservar}{tel_btn}<a class="btn sec" href="{maps}" target="_blank" rel="noopener">📍 Cómo llegar</a></div>'
        '</div></div></div></section>'
        # Certificado
        '<section><div class="wrap"><div class="panel">'
        '<h2 style="margin-top:0">El certificado de refugio climático</h2>'
        f'<p>Este sello acredita que <b>{h["municipio"]}</b> es un refugio climático natural según '
        '10 veranos de datos de AEMET. <b>Certifica el clima de la zona</b> (la noche refresca), no '
        'el interior del establecimiento. Puedes descargarlo y mostrarlo en tu web, recepción o redes.</p>'
        '<div class="dl">'
        f'{dl_png}'
        f'<a href="{site}/badges/{sl}.svg" download>⬇ SVG (vectorial)</a>'
        '</div>'
        '<p class="muted" style="margin-top:14px">Para incrustarlo en tu web con enlace de vuelta '
        '(recomendado):</p>'
        f'<pre>{_esc(embed)}</pre>'
        '</div></div></section>'
        # Reservar / cómo llegar
        '<section><div class="wrap">'
        '<h2>Reservar y cómo llegar</h2>'
        f'<p>Consulta precios, disponibilidad y las opiniones de otros huéspedes, o abre la '
        f'ubicación en el mapa para calcular tu ruta hasta <b>{h["municipio"]}</b>.</p>'
        f'<div class="acts">{reservar}{tel_btn}<a class="btn sec" href="{maps}" target="_blank" rel="noopener">📍 Ver en el mapa</a></div>'
        '</div></section>'
        # Sigue
        '<section><div class="wrap"><div class="panel">'
        '<h2 style="margin-top:0">Explora más refugios</h2>'
        f'<div class="acts"><a class="btn sec" href="{site}/hoteles-refugio-climatico/">🏨 Los 25 hoteles refugio</a>'
        f'<a class="btn sec" href="{site}/{slug(h["provincia"])}/">Noches tropicales en {h["provincia"]}</a>'
        f'<a class="btn sec" href="{site}/dormir-con-manta-en-verano/">Dormir con manta en verano</a></div>'
        '</div></div></section>'
        + footer_escueto_html(site) + '</body></html>\n')


PAGINA_TUHOTEL = r"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Certifica tu hotel como Refugio Climático Natural (gratis, datos AEMET)</title>
<meta name="description" content="¿Tienes un hotel o casa rural en un pueblo fresco? Auditamos gratis los registros de AEMET de tu municipio. Si la noche refresca, entras en el directorio con tu sello de Refugio Climático Natural. Un argumento de venta con aval de datos oficiales.">
<link rel="canonical" href="__SITE__/tu-hotel/">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="website">
<meta property="og:title" content="Certifica tu hotel como Refugio Climático Natural">
<meta property="og:description" content="Auditamos gratis los datos de AEMET de tu municipio. Si la noche refresca, entras en el directorio con tu sello.">
<meta property="og:url" content="__SITE__/tu-hotel/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900&family=Lora:ital,wght@0,400;0,600&display=swap" rel="stylesheet">
<style>
 :root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--verde:#8fb07a;--fd:"Fraunces",Georgia,serif;--fb:"Lora",Georgia,serif;--fm:ui-monospace,monospace}
 *{margin:0;padding:0;box-sizing:border-box}
 body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.65}
 .wrap{max-width:min(92vw,720px);margin:0 auto;padding:0 24px}
 a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}
 header.h{padding:46px 0 10px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}
 .crumb{font-size:13px;color:var(--muted)}.crumb a{color:var(--muted)}
 .kick{font:600 12px/1 var(--fb);letter-spacing:.15em;text-transform:uppercase;color:var(--teja);margin:16px 0 8px}
 h1{font-family:var(--fd);font-weight:900;font-size:clamp(28px,5.2vw,42px);line-height:1.06}
 h1 em{font-style:italic;color:var(--teja2)}
 .intro{color:var(--muted);font-size:clamp(15.5px,2.4vw,17.5px);margin:16px 0 0}.intro b{color:var(--paper)}
 section{padding:18px 0}
 h2{font-family:var(--fd);font-weight:600;font-size:clamp(19px,3vw,24px);margin:14px 0 12px}
 p{color:#d9ccb6;font-size:15.5px;margin:0 0 14px}p b{color:var(--paper)}
 ul{margin:0 0 16px;padding-left:0;list-style:none}
 li{position:relative;padding:8px 0 8px 30px;color:#d9ccb6;font-size:15.5px;border-bottom:1px solid var(--line)}
 li::before{content:"✓";position:absolute;left:4px;color:var(--verde);font-weight:700}
 li b{color:var(--paper)}
 .capture{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:24px;margin:18px 0}
 .capture h2{margin:0 0 4px}
 .capture .sub{color:var(--muted);font-size:14px;margin:0 0 16px}
 form{display:grid;gap:11px}
 input,select,textarea{width:100%;background:#0c0906;border:1px solid var(--line);color:var(--paper);padding:12px 14px;border-radius:10px;font-size:15px;font-family:var(--fb)}
 textarea{min-height:84px;resize:vertical}
 .rgpd{display:flex;gap:9px;align-items:flex-start;font-size:13px;color:var(--muted)}
 .rgpd input{width:auto;margin-top:3px}
 button{background:var(--teja);color:#1a1209;border:0;font-weight:700;font-size:15px;padding:13px 18px;border-radius:11px;cursor:pointer;font-family:var(--fb)}
 button:hover{background:var(--teja2)}
 .ok{font-family:var(--fd);font-size:19px;text-align:center;color:var(--verde);padding:20px 0}
 .honesto{font-size:13px;color:var(--muted);background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-top:8px}
 __NAVCSS__
 __FOOTERCSS__
</style></head><body>
__NAV__
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__HOME__">nochetropical.es</a> · Certifica tu hotel</nav>
  <div class="kick">Para hoteles y casas rurales · Datos AEMET</div>
  <h1>Tu hotel está en un <em>refugio climático</em>. Demuéstralo.</h1>
  <p class="intro">Si tu alojamiento está en un pueblo donde <b>la noche refresca de verdad</b>, tienes un argumento de venta buenísimo y —a diferencia de casi todos— <b>se puede demostrar con datos oficiales de AEMET</b>. Lo auditamos <b>gratis</b> y, si cumple, entras en nuestro directorio con tu sello.</p>
</div></header>

<section><div class="wrap">
  <h2>Qué consigues</h2>
  <ul>
    <li><b>Tu ficha</b> en el directorio de hoteles refugio, con el dato de AEMET de tu zona.</li>
    <li><b>El sello «Refugio Climático Natural»</b> descargable (web e impresión) para tu web, recepción y redes.</li>
    <li><b>Un argumento con aval</b>: «aquí se duerme fresco, avalado por 10 años de datos de AEMET».</li>
    <li><b>Gratis.</b> Si aún no tienes web ni reservas online, también entras — eres de los primeros.</li>
  </ul>

  <div class="capture">
    <h2>Solicita tu auditoría meteorológica</h2>
    <p class="sub">Rellena esto y comprobamos los registros de AEMET de tu municipio. Si la mínima media de verano baja de 18&nbsp;°C y no hay noches tropicales sostenidas, te certificamos.</p>
    <form id="leadf">
      <input type="text" id="hnombre" placeholder="Nombre del hotel o casa rural" required>
      <input type="text" id="hmun" placeholder="Municipio y provincia (p. ej. Bronchales, Teruel)" required>
      <input type="text" id="hweb" placeholder="Web o perfil de Booking (si tienes)">
      <input type="email" id="hemail" placeholder="Email de contacto" required>
      <input type="text" id="htel" placeholder="Teléfono (opcional)">
      <textarea id="hmsg" placeholder="Cuéntanos algo de tu alojamiento (opcional)"></textarea>
      <label class="rgpd"><input type="checkbox" id="hrgpd" required> Acepto que me contactéis sobre la certificación. Sin spam.</label>
      <button type="submit">Solicitar auditoría gratis</button>
    </form>
    <p class="honesto"><b>Honestidad primero:</b> certificamos el <b>clima de la zona</b> (que la noche refresca, medido por AEMET), no el interior de tu edificio. Es lo que lo hace creíble.</p>
  </div>

  <p style="font-size:13px;color:var(--muted)">¿Prefieres escribir? <a href="mailto:lowesting@gmail.com">lowesting@gmail.com</a>. Mira el <a href="__SITE__/hoteles-refugio-climatico/">directorio de hoteles refugio</a> o la <a href="__SITE__/metodologia/">metodología</a>.</p>
</div></section>
__FOOTER__
<script>
const APPS_SCRIPT_URL="__APPS_URL__";
const lf=document.getElementById("leadf");
lf.addEventListener("submit",ev=>{
  ev.preventDefault();
  const lead={timestamp:new Date().toISOString(),
    email:document.getElementById("hemail").value.trim(),
    modo:"tu-hotel",
    hotel:document.getElementById("hnombre").value.trim(),
    zona_interes:document.getElementById("hmun").value.trim(),
    web:document.getElementById("hweb").value.trim(),
    telefono:document.getElementById("htel").value.trim(),
    peticion:document.getElementById("hmsg").value.trim(),
    estacion:"",provincia:"",noches_trop:"",veredicto:"",
    rgpd:document.getElementById("hrgpd").checked?"si":"",
    source:"tu-hotel",user_agent:navigator.userAgent};
  const gracias=()=>{lf.outerHTML='<p class="ok">¡Gracias! Auditamos tu zona y te escribimos pronto.</p>';};
  fetch(APPS_SCRIPT_URL,{method:"POST",headers:{"Content-Type":"text/plain;charset=utf-8"},body:JSON.stringify(lead)}).then(gracias).catch(gracias);
});
</script>
</body></html>
"""


def construir_pagina_tuhotel(site: str) -> str:
    url = site + "/tu-hotel/"
    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "nochetropical.es", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "Certifica tu hotel", "item": url}]},
        {"@type": "WebPage", "name": "Certifica tu hotel como Refugio Climático Natural", "url": url,
         "isPartOf": {"@type": "WebSite", "name": "nochetropical.es", "url": site + "/"}}]},
        ensure_ascii=False)
    return (PAGINA_TUHOTEL
            .replace("__NAVCSS__", CSS_NAV_ESCUETO)
            .replace("__FOOTERCSS__", CSS_FOOTER_ESCUETO)
            .replace("__NAV__", nav_escueto_html(site))
            .replace("__FOOTER__", footer_escueto_html(site))
            .replace("__SCHEMA__", schema)
            .replace("__APPS_URL__", APPS_SCRIPT_URL)
            .replace("__SITE__", site)
            .replace("__HOME__", site + "/"))


# Indicador de scroll reutilizable ("↓ sigue, hay más"): aparece si la página
# tiene contenido bajo el pliegue, hace un empujón suave una sola vez (si el
# usuario no ha hecho scroll) y al tocarlo baja con animación. Mejora la
# usabilidad revelando que hay más, sin secuestrar la lectura. Autónomo (namespace
# propio), se inyecta antes de </body> en la portada y las páginas del menú.
SCROLL_CUE = (
    '<style>@keyframes _scb{0%,100%{transform:translateX(-50%) translateY(0)}'
    '50%{transform:translateX(-50%) translateY(5px)}}'
    '#scue{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);z-index:60;'
    'background:rgba(217,116,78,.18);border:1px solid #d9744e;color:#e89a73;'
    'font:600 12.5px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;'
    'padding:9px 16px;border-radius:20px;cursor:pointer;display:none;'
    'backdrop-filter:blur(4px);animation:_scb 1.6s ease-in-out infinite}</style>'
    '<div id="scue" aria-hidden="true">↓ sigue, hay más</div>'
    '<script>(function(){var c=document.getElementById("scue");'
    'function ease(to,d){var s=window.scrollY,ch=to-s,t0=null;function st(t){if(!t0)t0=t;'
    'var p=Math.min((t-t0)/d,1),e=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;'
    'window.scrollTo(0,s+ch*e);if(p<1)requestAnimationFrame(st);}requestAnimationFrame(st);}'
    'function able(){return document.body.scrollHeight-window.innerHeight>window.innerHeight*.5;}'
    'if(able()){c.style.display="block";setTimeout(function(){if(window.scrollY<20&&able())'
    'ease(Math.round(window.innerHeight*.42),900);},2200);}'
    'c.addEventListener("click",function(){ease(Math.min(window.scrollY+Math.round(window.innerHeight*.82),'
    'document.body.scrollHeight),700);});'
    'window.addEventListener("scroll",function(){var b=window.innerHeight+window.scrollY>=document.body.scrollHeight-40;'
    'c.style.display=(!b&&window.scrollY<window.innerHeight*.6&&able())?"block":"none";},{passive:true});})();</script>'
)


def main() -> int:
    estaciones, total = cargar_estaciones()
    datos = construir_datos(estaciones, total)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    site = SITE_URL.rstrip("/")
    provnav = "".join(f'<a href="{site}/{slug(p)}/">{p}</a>' for p in datos["provincias"])
    # PORTADA: el nuevo diseño (el que se validó en /beta/) es ahora la home,
    # indexable. El TEMPLATE antiguo queda como referencia por si portamos piezas
    # (calculadora con badge de certificado, barras refugios/infiernos, FAQ).
    OUT_HTML.write_text(construir_pagina_beta(datos, site, es_portada=True),
                        encoding="utf-8")
    # Ficheros SEO: desactivar Jekyll y robots.
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (DOCS_DIR / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {site}/sitemap.xml\n", encoding="utf-8")
    (DOCS_DIR / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")
    # Capa 3: una página indexable por provincia. La tendencia de 10 años se
    # calcula una sola vez (lee los CSV diarios) y da a cada landing contenido
    # ÚNICO —clave para que Google no las trate como plantilla en serie—.
    fecha_mod = date.fromtimestamp(RANKING_CSV.stat().st_mtime)
    fecha_mod_iso, fecha_mod_txt = fecha_mod.isoformat(), fecha_es(fecha_mod)
    tendencias = cargar_tendencia_provincias(estaciones)
    print(f"   tendencia 10 años: {len(tendencias)} provincias con serie")
    # Complemento de datos por estación: humedad y viento medios de agosto
    # (leídos de diarios_humedad_*.csv). Degrada a {} hasta el primer backfill
    # de humedad; entonces aparece solo en las estaciones con dato.
    humedad = cargar_humedad_estaciones(estaciones)
    if humedad:
        print(f"   complemento humedad/viento: {len(humedad)} estaciones con dato de agosto")
    else:
        print("   complemento humedad/viento: sin datos aún (lanza el backfill para poblarlo)")
    # Widget "registro nocturno" de cada provincia: última noche con dato de AEMET
    # (rolling) y noches tropicales del verano en curso. Complemento honesto: si no
    # hay datos recientes, el widget no aparece y la página queda igual.
    ultima_noche = cargar_ultima_noche(estaciones)
    verano = cargar_verano_actual(estaciones)
    if ultima_noche:
        print(f"   registro nocturno: última noche en {len(ultima_noche)} estaciones · "
              f"verano en curso en {len(verano)}")
    else:
        print("   registro nocturno: sin datos recientes (no se pinta el widget)")
    titulos_prov = []  # (provincia, título) para la tabla de control móvil
    for prov, lista in datos["provincias"].items():
        sl = slug(prov)
        carpeta = DOCS_DIR / sl
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "index.html").write_text(
            construir_pagina_provincia(prov, lista, site, provnav, fecha_mod_iso,
                                       fecha_mod_txt, tendencias.get(prov), humedad,
                                       ultima_noche, verano),
            encoding="utf-8")
        (carpeta / "datos.csv").write_text(csv_provincia(lista), encoding="utf-8")
        pt = PROV_TITULO_CORTO.get(prov, prov)
        titulos_prov.append(f"Noches tropicales en {pt}: dónde se duerme fresco")
    # Control de longitud del <title> en móvil (Google corta ~50-55 car.):
    # marca con ! las que se pasen de 52 para revisarlas de un vistazo.
    print("   títulos de provincia (nº car. · ! si >52):")
    for t in sorted(titulos_prov, key=len, reverse=True):
        print(f"     {'!' if len(t) > 52 else ' '} {len(t):3} {t}")
    # Páginas complementarias data-driven: sala de prensa, ranking y ola de calor.
    # aplicar_menu_escueto: sus plantillas aún no traen menú propio.
    (DOCS_DIR / "prensa").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "prensa" / "index.html").write_text(
        aplicar_menu_escueto(
            construir_pagina_prensa(datos, estaciones, site, fecha_mod_iso, fecha_mod_txt),
            site),
        encoding="utf-8")
    (DOCS_DIR / "ranking-noches-tropicales").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "ranking-noches-tropicales" / "index.html").write_text(
        aplicar_menu_escueto(
            construir_pagina_ranking(estaciones, site, fecha_mod_iso, fecha_mod_txt, provnav),
            site),
        encoding="utf-8")
    (DOCS_DIR / "ola-de-calor").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "ola-de-calor" / "index.html").write_text(
        construir_pagina_ola(site, fecha_mod_iso, fecha_mod_txt), encoding="utf-8")
    # Herramienta: los refugios climáticos más cercanos (geolocalización).
    (DOCS_DIR / "refugios-climaticos-naturales-cerca-de-mi").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "refugios-climaticos-naturales-cerca-de-mi" / "index.html").write_text(
        construir_pagina_cerca(estaciones, datos, site, humedad), encoding="utf-8")
    # El confortómetro (ciencia ciudadana) + tmin-zonas.json: la última mínima
    # por estación, que es la referencia con la que el backend (Apps Script)
    # contrasta la coherencia de los votos.
    tmin_rec = cargar_termometro_reciente()
    (DOCS_DIR / "confortometro").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "confortometro" / "index.html").write_text(
        construir_pagina_confortometro(estaciones, site, tmin_rec), encoding="utf-8")
    # Estudio "La España que nunca se colorea": solo si scripts/estudio_colores.py
    # ya generó las imágenes y el JSON con las cifras (data-driven, idempotente).
    estudio_json = DOCS_DIR / "estudios" / "estudio-datos.json"
    datos_estudio = None
    if estudio_json.exists():
        datos_estudio = json.loads(estudio_json.read_text(encoding="utf-8"))
        (DOCS_DIR / "la-espana-que-nunca-se-colorea").mkdir(parents=True, exist_ok=True)
        (DOCS_DIR / "la-espana-que-nunca-se-colorea" / "index.html").write_text(
            construir_pagina_estudio(site, datos_estudio), encoding="utf-8")
        print("   estudio 'nunca se colorea': landing generada")
    else:
        print("   estudio 'nunca se colorea': sin datos (ejecuta estudio_colores.py); se omite")
    # Versión en inglés (fase 1): home /en/ + guía /en/coolest-towns-spain/.
    # SEO propio, hreflang bidireccional y navegación con tarjetas/botones.
    (DOCS_DIR / "en").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "en" / "index.html").write_text(
        construir_pagina_en_home(site, datos_estudio), encoding="utf-8")
    (DOCS_DIR / "en" / "coolest-towns-spain").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "en" / "coolest-towns-spain" / "index.html").write_text(
        construir_pagina_en_pueblos(estaciones, site), encoding="utf-8")
    print("   versión EN (fase 1): /en/ + /en/coolest-towns-spain/ generadas")
    # Hoteles en refugios climáticos (afiliación Booking) + sello por hotel.
    hoteles = cargar_hoteles(estaciones)
    for h in hoteles:  # complemento de datos: humedad/viento de su estación ref
        h["hum"] = humedad.get(h.get("est_id", ""))
    if hoteles:
        (DOCS_DIR / "hoteles-refugio-climatico").mkdir(parents=True, exist_ok=True)
        (DOCS_DIR / "hoteles-refugio-climatico" / "index.html").write_text(
            construir_pagina_hoteles(hoteles, site), encoding="utf-8")
        badges = DOCS_DIR / "badges"
        badges.mkdir(parents=True, exist_ok=True)
        for h in hoteles:
            (badges / f"{h['slug']}.svg").write_text(
                sello_svg(h["municipio"], h["provincia"], h["tmin"], h["nt"],
                          h["nivel"], h["ref_desc"]), encoding="utf-8")
            # Ficha individual por hotel (la página que el hotel querrá enlazar).
            carpeta = DOCS_DIR / "hoteles-refugio-climatico" / h["slug"]
            carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / "index.html").write_text(
                construir_pagina_hotel(h, site), encoding="utf-8")
        # Captación de hoteles (formulario a Apps Script, mismo backend que /tu-pueblo/).
        (DOCS_DIR / "tu-hotel").mkdir(parents=True, exist_ok=True)
        (DOCS_DIR / "tu-hotel" / "index.html").write_text(
            construir_pagina_tuhotel(site), encoding="utf-8")
        print(f"   hoteles-refugio-climatico: {len(hoteles)} fichas + sellos + /tu-hotel/")
    # El Observatorio del Descanso ("¿cómo has dormido esta noche?"): ciencia
    # ciudadana. Se siembra con la expectativa real de AEMET (nunca vacío).
    (DOCS_DIR / "observatorio-del-descanso").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "observatorio-del-descanso" / "index.html").write_text(
        construir_pagina_observatorio(estaciones, site), encoding="utf-8")
    nlug = publicar_lugares()
    print(f"   observatorio-del-descanso: generado (semilla AEMET) · "
          f"{nlug} poblaciones publicadas" if nlug else
          "   observatorio-del-descanso: generado (semilla AEMET) · sin lugares.csv")
    # Página SEO de destinos frescos / turismo climático.
    (DOCS_DIR / "dormir-con-manta-en-verano").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "dormir-con-manta-en-verano" / "index.html").write_text(
        construir_pagina_manta(estaciones, site), encoding="utf-8")
    (DOCS_DIR / "aviso-legal").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "aviso-legal" / "index.html").write_text(
        construir_pagina_aviso_legal(site), encoding="utf-8")
    (DOCS_DIR / "sobre-el-proyecto").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "sobre-el-proyecto" / "index.html").write_text(
        construir_pagina_sobre(site), encoding="utf-8")
    # Consola interna del generador de informes (noindex, fuera del sitemap):
    # buscador de estaciones + lista de informes ya publicados. Se reconstruye
    # cada build escaneando docs/informes/.
    (DOCS_DIR / "informes").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "informes" / "index.html").write_text(
        construir_consola_informes(estaciones, site), encoding="utf-8")
    (DOCS_DIR / "datos").mkdir(parents=True, exist_ok=True)
    # Referencia de coherencia por estación: dato reciente del feed diario si lo
    # hay; si la estación dejó de publicar, media histórica del mes en curso.
    clima_mes = cargar_climatologia_mes(date.today().month)
    ref_tmin: dict[str, float] = {}
    ref_tmax: dict[str, float] = {}
    for e in estaciones:
        i = e["id"]
        if i in tmin_rec:
            _, tn, tx = tmin_rec[i]
            ref_tmin[i] = tn
            if tx is not None:
                ref_tmax[i] = tx
            elif clima_mes.get(i) and clima_mes[i][1] is not None:
                ref_tmax[i] = clima_mes[i][1]
        elif i in clima_mes:  # estación sin dato reciente: respaldo climático
            tn, tx = clima_mes[i]
            ref_tmin[i] = tn
            if tx is not None:
                ref_tmax[i] = tx
    (DOCS_DIR / "datos" / "tmin-zonas.json").write_text(
        json.dumps({"actualizado": max((f for f, _, _ in tmin_rec.values()), default=""),
                    "tmin": {i: ref_tmin[i] for i in sorted(ref_tmin)},
                    "tmax": {i: ref_tmax[i] for i in sorted(ref_tmax)}},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    # /beta/ YA es la portada: dejamos una redirección a la home (noindex; fuera
    # del sitemap por el filtro de REDIRECCIONES). Así no hay duplicado y quien
    # tuviera guardado /beta/ acaba en la web nueva.
    escribir_redireccion(site, "beta", site + "/",
                         "El nuevo diseño ya es la portada.", noindex=True)
    # La herramienta vivía en /refugios-cerca/ (slug flojo). Al mudarla NO se
    # pone noindex: GitHub Pages no hace 301 de verdad, así que el meta-refresh
    # + canonical es todo lo que tiene Google para pasar la señal a la URL nueva
    # — y un noindex la mataría en vez de traspasarla.
    escribir_redireccion(site, "refugios-cerca", site + "/" + SLUG_CERCA + "/",
                         "Esta herramienta se ha mudado.")
    # /refugio-climatico-natural/microclimas/ era un DUPLICADO de /microclimas/
    # (mismo título, H1 y contenido) heredado de la migración, con canonical al
    # dominio viejo. Se redirige a la versión buena para consolidar la señal y
    # quitar el contenido duplicado del índice.
    escribir_redireccion(site, "refugio-climatico-natural/microclimas",
                         site + "/microclimas/",
                         "Este artículo se ha unificado en /microclimas/.")
    (DOCS_DIR / "metodologia").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "metodologia" / "index.html").write_text(
        aplicar_menu_escueto(
            construir_pagina_metodologia(estaciones, total, site, fecha_mod_iso, fecha_mod_txt),
            site),
        encoding="utf-8")
    (DOCS_DIR / "tu-pueblo").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "tu-pueblo" / "index.html").write_text(
        aplicar_menu_escueto(construir_pagina_tupueblo(site), site), encoding="utf-8")
    (DOCS_DIR / "refugios-y-espana-vaciada").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "refugios-y-espana-vaciada" / "index.html").write_text(
        aplicar_menu_escueto(
            construir_pagina_vaciada(estaciones, site, fecha_mod_iso, fecha_mod_txt),
            site),
        encoding="utf-8")
    # Dominio propio: fija el CNAME de GitHub Pages (sobrevive a los builds) y
    # migra los enlaces del dominio antiguo en las páginas ESTÁTICAS de docs/
    # (las que no genera este script, p. ej. microclimas).
    (DOCS_DIR / "CNAME").write_text(SITE_URL.split("//")[1] + "\n", encoding="utf-8")
    # Páginas ESTÁTICAS de docs/ (las que no genera ningún script): además de
    # migrar el dominio, se les inyecta el menú escueto si no traen ninguno
    # (mismo precedente que la migración de dominio: retoque in situ,
    # idempotente). parte/ y certificados/ NO: los regeneran sus propios
    # scripts y el retoque se perdería — su menú se añade en esos generadores.
    # "en": la versión inglesa la genera ESTE script con su propio chrome
    # (nav_en_html/footer_en_html). Reutiliza la clase .nav-e, así que si pasara
    # por aplicar_menu_escueto le sustituiría el menú inglés por el español.
    OTROS_GENERADORES = {"parte", "certificados", "en"}
    migradas = con_menu = con_footer = 0
    for f in DOCS_DIR.glob("*/index.html"):
        carpeta = f.parent.name
        html_est = f.read_text(encoding="utf-8")
        nuevo = html_est
        if DOMINIO_ANTIGUO in nuevo:
            nuevo = nuevo.replace(DOMINIO_ANTIGUO, site)
            migradas += 1
        if carpeta not in OTROS_GENERADORES and carpeta not in REDIRECCIONES:
            con_nav = aplicar_menu_escueto(nuevo, site)
            if con_nav != nuevo:
                nuevo, con_menu = con_nav, con_menu + 1
            con_pie = enriquecer_estatica(nuevo, site, carpeta)
            if con_pie != nuevo:
                nuevo, con_footer = con_pie, con_footer + 1
        if nuevo != html_est:
            f.write_text(nuevo, encoding="utf-8")
    # Certificados: las ~218 páginas individuales (una por estación) son finas y
    # casi calcadas. Ante Google, tanta página en serie lastra la calidad media
    # del sitio y frena la indexación de lo que importa (las provincias). Se
    # dejan en NOINDEX todas salvo el Top 25 (la vitrina, con tarjeta PNG). El
    # índice /certificados/ sigue indexable. Post-proceso in situ para que el
    # cambio se publique regenerando solo este script; al quedar noindex, el
    # sitemap las excluye automáticamente (abajo).
    cert_noindex = 0
    cert_dir = DOCS_DIR / "certificados"
    if cert_dir.exists():
        for f in cert_dir.glob("*/index.html"):
            h = f.read_text(encoding="utf-8")
            if "· Top 25 ·" in h or 'content="noindex' in h:
                continue  # el Top 25 se indexa; lo ya-noindex no se re-toca
            nuevo = h.replace(
                '<meta name="robots" content="index,follow,max-image-preview:large">',
                '<meta name="robots" content="noindex,follow">')
            if nuevo != h:
                f.write_text(nuevo, encoding="utf-8")
                cert_noindex += 1
    # El parte de la noche: la portada /parte/ se indexa, pero los archivos
    # diarios /parte/AAAA-MM-DD/ son efímeros (uno por noche, cientos al año) y
    # solo existen para el permalink del tuit → noindex. Mismo post-proceso in
    # situ que los certificados; el sitemap los excluye al quedar noindex.
    parte_noindex = 0
    parte_dir = DOCS_DIR / "parte"
    if parte_dir.exists():
        for f in parte_dir.glob("*/index.html"):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.parent.name):
                continue
            h = f.read_text(encoding="utf-8")
            if 'content="noindex' in h:
                continue
            nuevo = h.replace(
                '<meta name="robots" content="index,follow,max-image-preview:large">',
                '<meta name="robots" content="noindex,follow">')
            if nuevo != h:
                f.write_text(nuevo, encoding="utf-8")
                parte_noindex += 1
    # Indicador de scroll ("↓ sigue, hay más"): en móvil, tras las páginas de
    # una sola pantalla-aparente, mucha gente no descubre que hay más contenido
    # abajo. Se inyecta en la portada y en las páginas que cuelgan del menú
    # principal (las de más tráfico). El Observatorio ya trae el suyo (con su
    # propio scroll suave tras la secuencia de respuesta), así que se excluye.
    PAGINAS_SCROLL_CUE = [
        "index.html",
        "hoteles-refugio-climatico/index.html",
        "ola-de-calor/index.html",
        "ranking-noches-tropicales/index.html",
        SLUG_CERCA + "/index.html",
        "dormir-con-manta-en-verano/index.html",
        "la-espana-que-nunca-se-colorea/index.html",
    ]
    con_scue = 0
    for rel in PAGINAS_SCROLL_CUE:
        f = DOCS_DIR / rel
        if not f.exists():
            continue
        h = f.read_text(encoding="utf-8")
        if 'id="scue"' in h or "</body>" not in h:
            continue  # ya lo tiene, o la página no cierra <body> (raro)
        f.write_text(h.replace("</body>", SCROLL_CUE + "\n</body>", 1),
                     encoding="utf-8")
        con_scue += 1
    if con_scue:
        print(f"   indicador de scroll inyectado en {con_scue} páginas")
    # Sitemap AUTOMÁTICO: descubre todas las páginas publicadas escaneando docs/.
    # Excluye redirecciones y CUALQUIER página noindex (informes, consola,
    # certificados finos, beta…) leyendo su meta robots — así nunca anuncia a
    # Google una URL que le pedimos no indexar.
    hoy = date.today().isoformat()

    def _es_noindex(f: Path) -> bool:
        try:
            return 'content="noindex' in f.read_text(encoding="utf-8")
        except OSError:
            return False

    urls = [site + "/"] + sorted(
        f"{site}/{rel}/"
        for patron in ("*/index.html", "*/*/index.html")
        for f in DOCS_DIR.glob(patron)
        if (rel := f.parent.relative_to(DOCS_DIR).as_posix()) not in REDIRECCIONES
        and not _es_noindex(f))
    filas = "\n".join(
        f'  <url><loc>{u}</loc><lastmod>{hoy}</lastmod><changefreq>weekly</changefreq>'
        f'<priority>{"1.0" if u == site + "/" else "0.7"}</priority></url>' for u in urls)
    (DOCS_DIR / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + filas + "\n</urlset>\n", encoding="utf-8")
    print(f"   sitemap automático: {len(urls)} URLs (escaneo de docs/)"
          + (f" · {migradas} páginas estáticas migradas de dominio" if migradas else "")
          + (f" · menú escueto inyectado en {con_menu} páginas estáticas" if con_menu else "")
          + (f" · pie unificado en {con_footer} páginas estáticas" if con_footer else "")
          + (f" · {cert_noindex} certificados a noindex" if cert_noindex else "")
          + (f" · {parte_noindex} partes diarios a noindex" if parte_noindex else ""))
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
