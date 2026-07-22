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
    ("Refugios cerca de mí", "/refugios-climaticos-naturales-cerca-de-mi/"),
    ("Mapa interactivo", "/mapa-estaciones/"),
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
    'font-size:12.5px;color:#82745d}'
    '.f2bar a{color:#9a8a6f}'
    '@media(max-width:640px){.f2grid{grid-template-columns:1fr}}'
)


def footer_escueto_html(site: str, extra: str = "") -> str:
    c1 = [("Refugios climáticos cerca de mí", "/refugios-climaticos-naturales-cerca-de-mi/"),
          ("El Confortómetro: vota tu zona", "/confortometro/"),
          ("Mapa interactivo de estaciones", "/mapa-estaciones/"),
          ("¿Cuándo acaba la ola de calor?", "/ola-de-calor/"),
          ("Ranking nacional de noches tropicales", "/ranking-noches-tropicales/"),
          ("El parte de la noche", "/parte/"),
          ("Certificados de refugio climático", "/certificados/")]
    c2 = [("Pueblos para dormir con manta en verano", "/dormir-con-manta-en-verano/"),
          ("Cómo crear un refugio climático natural", "/refugio-climatico-natural/"),
          ("Microclimas: los refugios de la naturaleza", "/microclimas/"),
          ("Refugios y España vaciada", "/refugios-y-espana-vaciada/"),
          ("La hipoteca térmica", "/hipoteca-termica/"),
          ("¿Tu pueblo no aparece? Ayúdanos", "/tu-pueblo/")]
    c3 = [("La calculadora de tu pueblo", "/"),
          ("Sobre el proyecto", "/sobre-el-proyecto/"),
          ("Metodología y glosario", "/metodologia/"),
          ("Sala de prensa", "/prensa/"),
          ("Licencia y aviso legal", "/aviso-legal/")]

    def col(titulo: str, items: list) -> str:
        enlaces = "".join(f'<a href="{site}{h}">{t}</a>' for t, h in items)
        return f'<div class="f2col"><h4>{titulo}</h4>{enlaces}</div>'

    return ('<footer class="f2"><div class="wrap"><div class="f2grid">'
            + col("Explora los datos", c1)
            + col("Guías y artículos", c2)
            + col("Proyecto", c3)
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
 footer{border-top:1px solid var(--line);margin-top:30px;padding:22px 0 60px;color:#82745d;font-size:12.5px}
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
 footer{border-top:1px solid var(--line);padding:30px 0 60px;color:#82745d;font-size:12.5px;margin-top:18px}
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

<section><div class="wrap"><div class="dcols">
  <div><div class="prose">__PROSA__</div></div>

  <div>
  <table>
    <caption>__CAPTION__</caption>
    <thead><tr><th>Localidad</th><th class="hide">Altitud</th><th class="r">Noches tropicales/año</th><th>Cómo se duerme</th></tr></thead>
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
    return f"{nt:.1f}" if nt < 10 else f"{round(nt)}"


def nt_prosa(nt: float) -> str:
    """Como ntfmt pero para texto plano (meta description): sin entidades HTML."""
    if nt < 1:
        return "menos de 1"
    return f"{nt:.1f}" if nt < 10 else f"{round(nt)}"


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


def construir_pagina_provincia(prov: str, lista: list, site: str, provnav: str,
                                fecha_mod: str, fecha_mod_txt: str,
                                tendencia: dict | None = None) -> str:
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
    if n <= 1:
        intro = (f'En <b>{prov}</b>, en su única estación de AEMET con datos suficientes — '
                 f'<b>{mejor["loc"]}</b> ({alt_mejor} m) — {mtxt}.')
    else:
        intro = (f'En <b>{prov}</b>, en <b>{mejor["loc"]}</b> ({alt_mejor} m) {mtxt}, '
                 f'mientras que en <b>{peor["loc"]}</b> se cuentan unas <b>{round(peor["nt"])}</b>. '
                 f'Estas son sus {n} estaciones de AEMET, de la más fresca a la más calurosa.')
    # Title/H1/description orientados a CTR (Search Console: el patrón ganador
    # es "noches tropicales + provincia"; Google reescribe titles mostrando el
    # H1, así que se trabajan como pareja: keyword+gancho / pregunta+promesa).
    title = f"Noches tropicales en {prov}: qué pueblos se libran y dónde no se pega ojo"
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
    prosa = (prosa_contraste(prov, mejor, peor, n)
             + prosa_tendencia(prov, tendencia or {})
             + prosa_refugios(prov, refugios)
             + cta_refugio
             + (prosa_peores(prov, peores, mejor) if peores else "")
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
    'footer{border-top:1px solid var(--line);padding:28px 0 60px;color:#82745d;font-size:12.5px;margin-top:24px}'
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
    ("cerca", "__SITE__/refugios-climaticos-naturales-cerca-de-mi/", "Refugios cerca de mí"),
    ("mapa", "__SITE__/mapa-estaciones/", "Mapa interactivo"),
    ("ola", "__SITE__/ola-de-calor/", "Ola de calor"),
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
    logo = _LOGO.format(px=26, hueco="--bg")
    return ('<nav class="nav"><div class="in">\n'
            '    <a class="brand" href="__HOME__" aria-label="nochetropical.es">' + logo + '</a>\n'
            '    <div class="menu">\n'
            '      ' + enlaces + '\n'
            '    </div>\n'
            '  </div></nav>')


FOOTER_HTML = (
    '<footer>\n'
    '    <div class="in fgrid">\n'
    '      <div class="fcol">\n'
    '        <a class="brand" href="__HOME__" style="margin-bottom:12px">'
    + _LOGO.format(px=24, hueco="--surface") + '</a>\n'
    '        <p class="fabout">Diez veranos de datos de AEMET para responder una pregunta: '
    '¿dónde se duerme fresco en España?</p>\n'
    '      </div>\n'
    '      <div class="fcol"><h4>Explora</h4><a href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/">Refugios cerca de ti</a>'
    '<a href="__SITE__/confortometro/">El confortómetro</a>'
    '<a href="__SITE__/mapa-estaciones/">Mapa de estaciones</a>'
    '<a href="__SITE__/ranking-noches-tropicales/">Ranking nacional</a>'
    '<a href="__SITE__/parte/">El parte de la noche</a>'
    '<a href="__SITE__/certificados/">Certificados</a></div>\n'
    '      <div class="fcol"><h4>Datos</h4><a href="__SITE__/metodologia/">Metodología</a>'
    '<a href="__SITE__/prensa/">Sala de prensa</a>'
    '<a href="https://opendata.aemet.es" target="_blank" rel="noopener">Fuente: AEMET</a>'
    '<a href="__SITE__/aviso-legal/">Licencia y aviso legal</a></div>\n'
    '      <div class="fcol"><h4>Proyecto</h4><a href="__SITE__/sobre-el-proyecto/">Sobre el proyecto</a>'
    '<a href="__SITE__/metodologia/">Metodología</a>'
    '<a href="__SITE__/tu-pueblo/">¿Y tu pueblo?</a>'
    '<a href="__SITE__/refugios-y-espana-vaciada/">Refugios y España vaciada</a>'
    '<a href="https://x.com/nochetropicales" target="_blank" rel="noopener">@nochetropicales</a></div>\n'
    '    </div>\n'
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
 .card span{display:block;color:var(--muted);font-weight:400;font-size:12px;margin-top:3px}
 .cita{font-family:var(--fm);font-size:13px;background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:14px;color:#e3d8c4;line-height:1.5}
 ul.medios{list-style:none;margin:6px 0 0;padding:0}
 ul.medios li{padding:14px 0;border-bottom:1px solid var(--line)}
 ul.medios li:last-child{border-bottom:none}
 ul.medios a{display:block;color:var(--teja2);font-family:var(--fd);font-weight:600;font-size:clamp(16px,2.4vw,18.5px);line-height:1.3;text-decoration:none}
 ul.medios a:hover{text-decoration:underline}
 ul.medios .meta{display:block;font-family:var(--fm);font-size:12px;color:var(--muted);margin-top:6px}
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
<title>¿Cuándo acaba la ola de calor? Mapa AEMET de hoy: máximas y mínimas</title>
<meta name="description" content="Míralo día a día en el mapa animado de AEMET: las temperaturas máximas de hoy, las mínimas de esta noche y cómo evoluciona la ola de calor. Y si no da tregua, dónde refugiarte.">
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
 .aviso{font-size:13.5px;color:var(--muted);line-height:1.65;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:15px 18px;margin:8px auto 24px;max-width:600px}
 .aviso b{color:var(--ink)}
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
  <h1>¿Cuándo acaba la ola de calor? Míralo en el mapa, <em>día y noche</em></h1>
  <p class="lede">Los <b>mapas de temperaturas de AEMET</b>, animados: las <b>máximas de hoy</b> y las <b>mínimas de esta noche</b>, un fotograma por jornada — la forma más rápida de ver si la ola <b>afloja o aprieta</b>. De día arde el 98 % del país. De noche, España se parte en dos: <b>una quinta parte del territorio no cruza los 20 °C ni una sola noche</b>. Ahí es donde se duerme. Pulsa el botón para ver <b>dónde están algunos de los mejores refugios</b>.</p>
</div></header>

<section><div class="wrap">
  <button class="toggle-refugios" id="toggle" aria-pressed="false">📍 Mostrar refugios climáticos</button>

  <div class="mapa">
    <h2>De noche · temperaturas mínimas</h2>
    <div class="gifwrap">
      <img src="__SITE__/ola-minimas.gif" width="630" height="546" alt="Mapa animado de AEMET de las temperaturas mínimas (de noche) sobre España durante la ola de calor" loading="lazy">
      <svg class="capa oculta" viewBox="0 0 630 546" aria-label="Refugios climáticos señalados sobre el mapa">__MARCADORES__</svg>
    </div>
  </div>

  <div class="mapa">
    <h2>De día · temperaturas máximas</h2>
    <div class="gifwrap">
      <img src="__SITE__/ola-maximas.gif" width="630" height="546" alt="Mapa animado de AEMET de las temperaturas máximas (de día) sobre España durante la ola de calor" loading="lazy">
      <svg class="capa oculta" viewBox="0 0 630 546" aria-label="Refugios climáticos señalados sobre el mapa">__MARCADORES__</svg>
    </div>
  </div>

  <div class="mapa">
    <h2>Canarias · mínimas de noche</h2>
    <div class="gifwrap">
      <img src="__SITE__/ola-canarias-minimas.gif" alt="Mapa animado de las temperaturas mínimas nocturnas de Canarias (AEMET)" loading="lazy" style="width:100%;height:auto;display:block">
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

  <p class="aviso"><b>Las flechas son orientativas.</b> A esta escala tan grande no marcan un punto exacto, sino la zona. Cada punto es la <b>estación meteorológica</b> y la población donde está; eso <b>no significa que los pueblos de alrededor no pertenezcan a ese mismo refugio climático</b> —el fresco no entiende de límites municipales—. <b>Cedrillas</b>, por ejemplo, abarca también Gúdar, Cabra de Mora, Alcalá de la Selva, Valdelinares, Allepuz o El Castellar. Señalan zonas donde, durante la ola, los colores se mantienen <b>lejos del lima<span class="mu" style="background:#CCFF00" aria-hidden="true"></span> y del amarillo<span class="mu" style="background:#FFFF00" aria-hidden="true"></span></b>: la prueba visual de que en España hay <b>refugios climáticos naturales</b> con margen de sobra para aguantar el calor sin artificios ni aire acondicionado. Pasa el ratón —o tócalas en el móvil— para ver el nombre; púlsalas para abrir su provincia. Los datos, pueblo a pueblo, están en la <a href="__HOME__">calculadora</a>.</p>

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
      <img src="__SITE__/ola-minimas.gif" alt="Mapa animado de las temperaturas mínimas nocturnas de AEMET durante la ola de calor" loading="lazy">
      <div class="gm-b"><a href="__SITE__/ola-de-calor/">Ver el mapa animado completo, con Canarias y las flechas a los refugios →</a></div>
    </div>
    <div class="leer">
      <h3>Cómo leer el mapa para encontrar un refugio</h3>
      <p>La clave está en el <b>color</b>, y se resume en una frase: busca las zonas que <b>nunca llegan a ponerse lima<span class="mu" style="background:#CCFF00" aria-hidden="true"></span> ni amarillas<span class="mu" style="background:#FFFF00" aria-hidden="true"></span></b>. No es una interpretación nuestra: en la escala de AEMET el verde<span class="mu" style="background:#66FF66" aria-hidden="true"></span> acaba <b>exactamente</b> en 20&nbsp;°C y el lima<span class="mu" style="background:#CCFF00" aria-hidden="true"></span> empieza <b>exactamente</b> en 20. Ese salto de color <i>es</i> la raya de la noche tropical.</p>
      <p>Un <b>refugio climático natural</b> es justo eso: una zona que <b>no cruza los 20&nbsp;°C</b> ninguna noche, ni en plena ola de calor. Por debajo de 20 se duerme, aunque sean 19,5 a las tres de la madrugada; a partir de 20 ya no baja en toda la noche. Que toque el verde<span class="mu" style="background:#66FF66" aria-hidden="true"></span> en su peor noche no la descalifica — lo que la descalifica es <b>pasar al lima</b><span class="mu" style="background:#CCFF00" aria-hidden="true"></span>. Superponiendo todas las noches del verano, <b>una quinta parte de España no lo hace nunca</b>.</p>
    </div>
    <h2 class="sec-h">Explora los datos</h2>
    <div class="mods">
      <a class="card2" href="__SITE__/refugios-climaticos-naturales-cerca-de-mi/"><h3>Refugios cerca de ti</h3><p>Los refugios climáticos más cercanos, con la distancia y la ruta.</p></a>
      <a class="card2" href="__SITE__/confortometro/"><h3>El Confortómetro</h3><p>El estudio participativo: vota cómo se siente el clima en tu zona.</p></a>
      <a class="card2" href="__SITE__/mapa-estaciones/"><h3>Mapa interactivo</h3><p>Las 848 estaciones de AEMET sobre el mapa de España.</p></a>
      <a class="card2" href="__SITE__/ranking-noches-tropicales/"><h3>Ranking nacional</h3><p>Dónde se duerme mejor y peor de toda España.</p></a>
      <a class="card2" href="__SITE__/parte/"><h3>El parte de la noche</h3><p>Quién durmió fresco anoche. Cada mañana.</p></a>
      <a class="card2" href="__SITE__/certificados/"><h3>Certificados</h3><p>Los pueblos acreditados como refugio climático.</p></a>
    </div>
    <h2 class="sec-h" id="articulos">Artículos</h2>
    <div class="mods">
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


def construir_pagina_cerca(estaciones: list, datos: dict, site: str) -> str:
    """Los 218 refugios (nt<1) con coordenadas + todas las estaciones para poder
    elegir origen sin geolocalización. El cálculo (Haversine) va en el navegador."""
    refs = [{"n": e["loc"], "p": e["prov"], "a": e["alt"], "nt": e["nt"],
             "la": e["lat"], "lo": e["lon"], "c": slug(e["loc"]), "s": slug(e["prov"])}
            for e in sorted(estaciones, key=lambda x: (x["nt"], -x["alt"])) if e["nt"] < 1]
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
APPS_SCRIPT_CONFORT_URL = ("https://script.google.com/macros/s/AKfycbzpBift9lGy5j"
                           "gilf3nxvcGDhD4zOP7LR17GgKgUOLzG4yI43gZrM4D1CvhcNp7T135qQ/exec")

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
 .niveles{display:grid;grid-template-columns:1fr;gap:8px}
 .nvl{display:flex;align-items:center;gap:12px;background:var(--bg);border:1px solid var(--line);border-radius:11px;padding:11px 14px;cursor:pointer;font-size:14.5px;color:var(--paper);text-align:left;width:100%}
 .nvl:hover{border-color:var(--teja)}
 .nvl.sel{border-color:var(--teja);background:rgba(217,116,78,.14);font-weight:700}
 .nvl .em{font-size:20px}
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
 .wstage{position:relative;display:flex;flex-direction:column;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:20px;padding:24px 20px 18px;max-width:640px;margin:0 auto;min-height:min(68vh,540px)}
 .wbar{height:5px;background:var(--bg);border-radius:99px;overflow:hidden;margin-bottom:22px;flex:0 0 auto}
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
      <p class="wsub">Del frío helador al calor insoportable. Elige lo que sienta tu cuerpo, no lo que marque el termómetro.</p>
      <div class="niveles" id="niveles">__NIVELES__</div>
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
var sel={zona:null,celda:null,nivel:null,boch:null,viento:null,lugar:null,clima:null,cielo:null,entorno:null};
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
var ORDEN=["zona","nivel","boch","viento","cielo","lugar","clima","entorno","enviar"];
var pasoAct="zona";
function visiblePaso(s){return s==="clima"?!!INTERIOR[sel.lugar]:true;}
function pasosVis(){return ORDEN.filter(visiblePaso);}
function resumen(){
 var ETQ=["","Helador","Frío","Fresco","Muy a gusto","Cómodo","Templado","Caluroso","Mucho calor","Insoportable"];
 var t="Votas «<b>"+(ETQ[sel.nivel]||"—")+"</b>»"+(sel.zona?" desde <b>"+sel.zona[3]+"</b>":"")+".";
 var extra=[sel.boch!==null,sel.viento,sel.cielo,sel.lugar,sel.clima,sel.entorno].filter(Boolean).length;
 t+=extra?" Con "+extra+" dato"+(extra>1?"s":"")+" de contexto para afinar el mapa.":" Sin contexto adicional: rápido y anónimo.";
 document.getElementById("resumen").innerHTML=t;
}
function irPaso(s){
 pasoAct=s;
 ORDEN.forEach(function(x){var el=document.getElementById("s-"+x);if(el)el.classList.toggle("on",x===s);});
 var vis=pasosVis(),i=vis.indexOf(s);
 document.getElementById("wfill").style.width=Math.round(100*i/(vis.length-1))+"%";
 var nav=document.getElementById("wnav"),opt=document.getElementById("s-"+s).classList.contains("opt");
 nav.style.display=(s==="zona"||s==="enviar")?"none":"flex";
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
 var p={z:sel.zona[0],g:sel.celda,s:sel.nivel,b:sel.boch,w:sel.viento,l:sel.lugar,c:sel.clima,o:sel.cielo,e:sel.entorno,u:uid(),v:1};
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
    if(d&&d.n>=5)
     r.innerHTML+="<br>Ahora mismo en tu zona: <b>"+d.mediana_txt+"</b> (mediana de <span class=\"num\">"+d.n+"</span> votos en 24 h"+(d.pct_bochorno!==null?", "+d.pct_bochorno+" % con bochorno":"")+").";
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
    niveles = "".join(
        f'<button class="nvl" type="button" data-v="{v}">'
        f'<span class="em">{em}</span><span>{txt}</span></button>'
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
    <p>Y si buscas <b>hoteles rurales frescos</b> — o ese «hotel sin aire acondicionado pero fresco» que promete la búsqueda —, la regla es simple: no tenemos datos de hoteles, pero sí del clima que los rodea; busca alojamiento en estos términos municipales y el aire acondicionado sobrará.</p>
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
    for prov, lista in datos["provincias"].items():
        sl = slug(prov)
        carpeta = DOCS_DIR / sl
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "index.html").write_text(
            construir_pagina_provincia(prov, lista, site, provnav, fecha_mod_iso,
                                       fecha_mod_txt, tendencias.get(prov)),
            encoding="utf-8")
        (carpeta / "datos.csv").write_text(csv_provincia(lista), encoding="utf-8")
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
        construir_pagina_cerca(estaciones, datos, site), encoding="utf-8")
    # El confortómetro (ciencia ciudadana) + tmin-zonas.json: la última mínima
    # por estación, que es la referencia con la que el backend (Apps Script)
    # contrasta la coherencia de los votos.
    tmin_rec = cargar_termometro_reciente()
    (DOCS_DIR / "confortometro").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "confortometro" / "index.html").write_text(
        construir_pagina_confortometro(estaciones, site, tmin_rec), encoding="utf-8")
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
    (DOCS_DIR / "datos" / "tmin-zonas.json").write_text(
        json.dumps({"actualizado": max((f for f, _, _ in tmin_rec.values()), default=""),
                    "tmin": {i: t for i, (_, t, _) in sorted(tmin_rec.items())},
                    "tmax": {i: t for i, (_, _, t) in sorted(tmin_rec.items())
                             if t is not None}},
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
    OTROS_GENERADORES = {"parte", "certificados"}
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
