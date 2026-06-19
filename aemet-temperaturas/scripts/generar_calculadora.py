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
from pathlib import Path


def clave_orden(texto: str) -> str:
    """Clave de ordenación insensible a acentos (Cáceres antes que Ciudad Real)."""
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------------------
# Rutas (este script vive en aemet-temperaturas/scripts/)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
AEMET_DIR = SCRIPT_DIR.parent                 # aemet-temperaturas/
REPO_ROOT = AEMET_DIR.parent                  # raíz del repo
RANKING_CSV = AEMET_DIR / "analisis" / "refugios_nocturnos_ranking.csv"
DOCS_DIR = REPO_ROOT / "docs"                 # GitHub Pages sirve /docs en raíz
OUT_HTML = DOCS_DIR / "index.html"

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
        estaciones.append({
            "id": f["indicativo"],
            "loc": titular(f["nombre"]),
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
        },
        "provincias": provincias,
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
  .wrap{max-width:680px;margin:0 auto;padding:0 22px}
  .kicker{font:600 12px/1 var(--fb);letter-spacing:.18em;text-transform:uppercase;color:var(--teja)}
  h2.st{font-family:var(--fd);font-weight:900;font-size:clamp(26px,5.5vw,40px);line-height:1.06;
    letter-spacing:-.01em;margin:0 0 6px}
  h2.st em{font-style:italic;color:var(--teja2)}
  .lead{color:var(--muted);font-size:clamp(15px,2.4vw,17px);margin:14px 0 0}
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
  .cue{margin-top:auto;padding-top:40px;color:var(--muted);font-size:12px;letter-spacing:.14em;
    text-transform:uppercase;display:flex;align-items:center;gap:10px}
  .cue span{display:inline-block;width:1px;height:34px;background:linear-gradient(var(--teja),transparent);
    animation:cue 1.8s ease-in-out infinite}
  @keyframes cue{0%,100%{opacity:.3;transform:scaleY(.6)}50%{opacity:1;transform:scaleY(1)}}

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

  /* MAPA */
  #map{width:100%;height:auto;display:block;margin-top:26px;
    filter:drop-shadow(0 20px 60px rgba(0,0,0,.5))}
  #map circle{transition:opacity .5s}
  .legend{display:flex;align-items:center;gap:14px;margin-top:16px;font-size:12.5px;color:var(--muted);
    flex-wrap:wrap}
  .legend .bar{flex:1;min-width:160px;height:9px;border-radius:6px;
    background:linear-gradient(90deg,#86b0c4,#d9a05e,#d9744e,#bf3b22)}
  .foehn{margin-top:34px;background:linear-gradient(180deg,var(--bg2),var(--panel));
    border:1px solid #4a2a1d;border-radius:16px;padding:24px 22px}
  .foehn .tag{font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;color:var(--teja)}
  .foehn h3{font-family:var(--fd);font-weight:600;font-size:22px;margin:8px 0 10px;line-height:1.15}
  .foehn p{color:var(--muted);font-size:15px}
  .foehn b{color:var(--paper)}

  /* CALCULADORA */
  .calc{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);
    border-radius:20px;padding:30px 26px 24px;margin-top:28px;box-shadow:0 30px 80px -30px #000}
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
  .cmp{font-size:14px;background:var(--bg);border:1px dashed var(--line);border-radius:12px;padding:13px 15px;margin-top:14px}
  .cmp b{color:var(--teja2)}
  .share{display:flex;gap:9px;flex-wrap:wrap;margin-top:18px}
  .share a,.share button{flex:1;min-width:96px;text-align:center;text-decoration:none;border:1px solid var(--line);
    background:var(--bg);color:var(--paper);font-size:13px;font-weight:600;padding:11px 8px;border-radius:11px;cursor:pointer;transition:.15s}
  .share a:hover,.share button:hover{border-color:var(--teja);color:var(--teja2)}
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
    <div class="cue"><span></span> Desliza para descubrirlo</div>
  </div>
</header>

<section>
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

<section>
  <div class="wrap reveal">
    <div class="secnum">03 — Búscalo tú</div>
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

const cr=M.contraste.refugio, ch=M.contraste.horno;
$("#c-ref-loc").textContent=cr.loc; $("#c-ref-meta").textContent=`${cr.prov} · ${cr.alt.toLocaleString("es")} m`;
$("#c-ref-nt").textContent=ntTxt(cr.nt);
$("#c-hor-loc").textContent=ch.loc; $("#c-hor-meta").textContent=`${ch.prov} · ${ch.alt.toLocaleString("es")} m`;
$("#c-hor-nt").textContent=ntTxt(ch.nt);
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
  const pctMejor=Math.round((T-e.rank)/(T-1)*100);
  const txt=e.nt<1?"menos de 1":(e.nt<10?e.nt.toFixed(1):Math.round(e.nt));
  const bigT=e.nt<1?"&lt;1":txt;
  const pos=Math.min(100,e.nt/90*100);
  let cmp;const v=M.valencia;
  if(v&&e.nt>=1&&v.nt/e.nt>=2) cmp=`Por cada noche tropical aquí, <b>${v.loc}</b> sufre <b>${Math.round(v.nt/e.nt)}</b>.`;
  else if(e.nt<1) cmp=`Prácticamente <b>cero</b> noches tropicales: de los mejores sitios de España para dormir en verano.`;
  else if(pctMejor>=50) cmp=`Se duerme mejor aquí que en el <b>${pctMejor}%</b> de las estaciones de España.`;
  else cmp=`El <b>${100-pctMejor}%</b> de España duerme mejor que aquí: de los sitios donde peor se pasa la noche en verano.`;
  const distTxt=distKm?`<div class="res-meta">📍 Estación más cercana a ${distKm.toFixed(0)} km de ti</div>`:"";
  const url="https://prestigyo.github.io/refugio-climatico/";
  const shareTxt=`En ${e.loc} (${e.prov}) se sufren ${txt} noches tropicales al año — puesto ${e.rank} de ${T} de España. ¿Y en tu pueblo?`;
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
    <div class="cmp">${cmp}</div>
    <div class="share">
      <a href="https://wa.me/?text=${encodeURIComponent(shareTxt+" "+url)}" target="_blank" rel="noopener">WhatsApp</a>
      <a href="https://twitter.com/intent/tweet?text=${encodeURIComponent(shareTxt)}&url=${encodeURIComponent(url)}" target="_blank" rel="noopener">X / Twitter</a>
      <button type="button" id="copy">Copiar enlace</button></div>`;
  $("#res").classList.add("show");
  $("#copy").addEventListener("click",()=>{navigator.clipboard?.writeText(shareTxt+" "+url);
    $("#copy").textContent="¡Copiado!";setTimeout(()=>{const b=$("#copy");if(b)b.textContent="Copiar enlace";},1800);});
}

// ---------- Scroll reveal ----------
const io=new IntersectionObserver((es)=>{es.forEach(x=>{if(x.isIntersecting){x.target.classList.add("in");io.unobserve(x.target);}});},{threshold:.15});
document.querySelectorAll(".reveal").forEach(el=>io.observe(el));
</script>
</body>
</html>
"""


def main() -> int:
    estaciones, total = cargar_estaciones()
    datos = construir_datos(estaciones, total)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    html = TEMPLATE.replace("__DATA__", payload)
    OUT_HTML.write_text(html, encoding="utf-8")
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
