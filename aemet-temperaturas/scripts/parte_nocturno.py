#!/usr/bin/env python3
"""
El parte de la noche: ¿quién durmió fresco anoche en España?

Lee la OBSERVACIÓN en tiempo real de AEMET OpenData (últimas 24 h, ~800
estaciones; sin el retraso de 3-5 días de los datos climatológicos), calcula
la mínima de esta pasada noche por estación y publica:

  docs/parte/index.html   la página del parte (fecha visible, para Discover)
  docs/parte/parte.txt    el texto listo para tuitear / WhatsApp
  docs/parte/parte.json   los datos en crudo por si hacen falta

La ejecuta el workflow parte-nocturno.yml cada mañana (~09:15 hora española).
Los datos de observación son PROVISIONALES (sin validar) y así se indica.

Requiere: requests + variable de entorno AEMET_API_KEY.
Uso local sin clave:  python parte_nocturno.py --demo   (datos sintéticos)
"""
from __future__ import annotations

import csv
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import generar_calculadora as g  # SITE_URL, DOCS_DIR, PROVINCIAS, slug, titular

BASE = "https://opendata.aemet.es/opendata/api"
URL_OBS = BASE + "/observacion/convencional/todas"
OUT_DIR = g.DOCS_DIR / "parte"
ESTACIONES_CSV = g.AEMET_DIR / "datos" / "estaciones.csv"

# La "noche" que se evalúa: de las 18:00 UTC de ayer a las 08:00 UTC de hoy.
# Cubre de sobra la madrugada, que es cuando se registra la mínima.
H_INICIO, H_FIN = 18, 8
MIN_ESTACIONES = 200      # si hay menos con datos, algo falló: no publicar
MIN_LECTURAS = 5          # lecturas mínimas por estación en la ventana

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def canon_provincia(raw: str) -> str:
    return g.PROVINCIAS.get(str(raw).strip().upper(), g.titular(str(raw)))


def cargar_provincias() -> dict[str, str]:
    """indicativo -> provincia canónica, desde datos/estaciones.csv."""
    prov = {}
    if ESTACIONES_CSV.exists():
        with open(ESTACIONES_CSV, encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                prov[fila["indicativo"].strip()] = canon_provincia(fila["provincia"])
    return prov


def obtener_observaciones() -> list[dict]:
    import requests
    api_key = os.environ.get("AEMET_API_KEY")
    if not api_key:
        print("ERROR: falta AEMET_API_KEY (o usa --demo)", file=sys.stderr)
        sys.exit(1)
    r = requests.get(URL_OBS, params={"api_key": api_key}, timeout=60)
    r.raise_for_status()
    datos_url = r.json().get("datos")
    if not datos_url:
        print("ERROR: la API no devolvió 'datos':", r.text[:200], file=sys.stderr)
        sys.exit(1)
    r2 = requests.get(datos_url, timeout=120)
    r2.raise_for_status()
    r2.encoding = "utf-8"
    return r2.json()


def observaciones_demo() -> list[dict]:
    """Datos sintéticos para probar el render en local sin clave de la API."""
    random.seed(5)
    ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    obs = []
    nombres = [("CABO DE GATA", "B000"), ("PUERTO DEL PICO", "D001"),
               ("CEDRILLAS", "9381X"), ("VALENCIA AEROPUERTO", "8414A")]
    nombres += [(f"ESTACION {i}", f"S{i:03d}") for i in range(300)]
    for nombre, idema in nombres:
        base = random.uniform(9, 27)
        for h in range(14):
            t = ahora - timedelta(hours=h)
            obs.append({"idema": idema, "ubi": nombre,
                        "fint": t.strftime("%Y-%m-%dT%H:%M:%S"),
                        "ta": round(base + random.uniform(-1.5, 4), 1)})
    return obs


def parsear_fint(s: str) -> datetime | None:
    try:
        limpio = s.strip().replace("Z", "").split("+")[0]
        return datetime.fromisoformat(limpio).replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def minimas_de_la_noche(obs: list[dict]) -> dict[str, dict]:
    """Por estación, la mínima registrada en la ventana nocturna."""
    hoy = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    ini = hoy - timedelta(days=1) + timedelta(hours=H_INICIO)
    fin = hoy + timedelta(hours=H_FIN)
    est: dict[str, dict] = {}
    for o in obs:
        t = parsear_fint(o.get("fint", ""))
        if t is None or not (ini <= t <= fin):
            continue
        candidatos = [o.get(k) for k in ("tamin", "ta") if isinstance(o.get(k), (int, float))]
        if not candidatos:
            continue
        v = min(candidatos)
        if not -35 <= v <= 45:      # descartar lecturas absurdas
            continue
        e = est.setdefault(o.get("idema", "?"),
                           {"nombre": g.titular(str(o.get("ubi", "—"))),
                            "min": v, "n": 0})
        e["min"] = min(e["min"], v)
        e["n"] += 1
    return {k: v for k, v in est.items() if v["n"] >= MIN_LECTURAS}


def dec(v: float) -> str:
    """26.5 -> '26,5' (decimal español)."""
    return f"{v:.1f}".replace(".", ",")


def fila_html(e: dict, site: str) -> str:
    prov = e["prov"]
    enlace = (f'<a href="{site}/{g.slug(prov)}/">{prov}</a>' if prov else "—")
    return (f'<tr><td class="loc">{e["nombre"]}</td><td>{enlace}</td>'
            f'<td class="n">{dec(e["min"])}&nbsp;°C</td></tr>')


PLANTILLA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>El parte de la noche: __TROP__ estaciones no bajaron de 20 °C | Noche Tropical</title>
<meta name="description" content="El parte diario de las noches tropicales en España, con la observación de AEMET de anoche: cuántas estaciones no bajaron de 20 °C, la más tórrida y la más fresca. Actualizado cada mañana.">
<link rel="canonical" href="__SITE__/parte/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="author" content="Ramón J. Lowesting">
<meta property="og:type" content="article">
<meta property="og:title" content="El parte de la noche · __FECHA_CORTA__">
<meta property="og:description" content="__TROP__ estaciones de AEMET no bajaron de 20 °C anoche. La más tórrida: __PEOR_LOC__ (__PEOR_MIN__ °C).">
<meta property="og:url" content="__SITE__/parte/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__/og.png">
<link rel="icon" type="image/svg+xml" href="__SITE__/favicon.svg">
<script type="application/ld+json">__SCHEMA__</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,600&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
 :root{--bg:#161009;--bg2:#1f1810;--panel:#241b11;--line:#3a2c1c;--paper:#efe6d6;--muted:#b3a48c;--teja:#d9744e;--teja2:#e89a73;--teal:#96b6c4;--verde:#8fb07a;--fd:"Fraunces",Georgia,serif;--fb:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--fm:"JetBrains Mono",monospace}
 *{margin:0;padding:0;box-sizing:border-box}
 body{background:var(--bg);color:var(--paper);font-family:var(--fb);line-height:1.65;-webkit-font-smoothing:antialiased}
 .wrap{max-width:760px;margin:0 auto;padding:0 22px}
 a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}
 header.h{padding:44px 0 10px;background:radial-gradient(120% 80% at 50% -10%,#2a1d10,var(--bg) 60%)}
 .crumb{font-size:13px;color:var(--muted)}.crumb a{color:var(--muted)}
 .kick{font:600 12px/1 var(--fb);letter-spacing:.16em;text-transform:uppercase;color:var(--teja);margin:18px 0 10px}
 h1{font-family:var(--fd);font-weight:900;font-size:clamp(27px,5.4vw,42px);line-height:1.08;letter-spacing:-.01em}
 .fecha{font-family:var(--fm);font-size:14px;color:var(--teja2);margin:14px 0 0}
 .nums{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:26px 0}
 .num{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:16px 12px;text-align:center}
 .num .v{font-family:var(--fm);font-weight:700;font-size:clamp(26px,5.5vw,38px);line-height:1.1}
 .num .l{font-size:12.5px;color:var(--muted);margin-top:4px}
 .num.trop .v{color:var(--teja2)} .num.ecua .v{color:#cf4b34} .num.tot .v{color:var(--muted)}
 .duelo{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:6px 0 26px}
 .card{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:16px 18px}
 .card .t{font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;margin-bottom:8px}
 .card.calor .t{color:#cf4b34}.card.fresco .t{color:var(--verde)}
 .card .loc{font-family:var(--fd);font-weight:600;font-size:19px;line-height:1.2}
 .card .m{font-family:var(--fm);font-weight:700;font-size:30px;margin-top:4px}
 .card.calor .m{color:var(--teja2)}.card.fresco .m{color:var(--teal)}
 .card .p{font-size:13px;color:var(--muted);margin-top:2px}
 h2{font-family:var(--fd);font-weight:700;font-size:clamp(19px,3.4vw,24px);margin:30px 0 10px}
 table{width:100%;border-collapse:collapse;font-size:14px}
 th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
 th{font:600 10.5px/1 var(--fb);letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
 td.n{text-align:right;font-family:var(--fm);font-weight:700}
 td.loc{font-weight:600}
 .comparte{margin:34px 0;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:18px 20px}
 .comparte .t{font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;color:var(--teja);margin-bottom:10px}
 .comparte pre{white-space:pre-wrap;font-family:var(--fm);font-size:13px;color:#e3d8c4;background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
 .comparte .acciones{display:flex;gap:10px;margin-top:12px;flex-wrap:wrap}
 .comparte button,.comparte a.b{background:transparent;border:1px solid var(--teja);color:var(--teja2);font-weight:700;font-size:13.5px;padding:9px 16px;border-radius:9px;cursor:pointer;text-decoration:none}
 .comparte button:hover,.comparte a.b:hover{background:var(--teja);color:#1a1209}
 .nota{font-size:12.5px;color:var(--muted);margin:22px 0}
 .cta{margin:26px 0;text-align:center}
 .cta a{display:inline-block;background:var(--teja);color:#1a1209;font-weight:700;padding:13px 22px;border-radius:12px}
 .cta a:hover{background:var(--teja2);text-decoration:none}
 footer{border-top:1px solid var(--line);padding:28px 0 60px;color:#82745d;font-size:12.5px;margin-top:24px}
 footer a{color:#9a8a6f}
 @media(max-width:560px){.nums{grid-template-columns:1fr 1fr}.duelo{grid-template-columns:1fr}}
</style>
</head>
<body>
<header class="h"><div class="wrap">
  <nav class="crumb" aria-label="breadcrumb"><a href="__SITE__/">Refugio Climático</a> · El parte de la noche</nav>
  <div class="kick">El parte de la noche · se actualiza cada mañana</div>
  <h1>¿Quién durmió fresco anoche en España?</h1>
  <p class="fecha">Noche del __FECHA_LARGA__ · observación de AEMET</p>
</div></header>

<section><div class="wrap">
  <div class="nums">
    <div class="num trop"><div class="v">__TROP__</div><div class="l">estaciones en <b>noche tropical</b> (mínima ≥ 20 °C)</div></div>
    <div class="num ecua"><div class="v">__ECUA__</div><div class="l">en <b>noche ecuatorial</b> (mínima ≥ 25 °C)</div></div>
    <div class="num tot"><div class="v">__TOTAL__</div><div class="l">estaciones con datos esta noche</div></div>
  </div>

  <div class="duelo">
    <div class="card calor"><div class="t">🥵 La más tórrida</div><div class="loc">__PEOR_LOC__</div><div class="m">__PEOR_MIN__ °C</div><div class="p">de mínima · __PEOR_PROV__</div></div>
    <div class="card fresco"><div class="t">🥶 La más fresca</div><div class="loc">__MEJOR_LOC__</div><div class="m">__MEJOR_MIN__ °C</div><div class="p">de mínima · __MEJOR_PROV__</div></div>
  </div>

  <h2>Donde peor se durmió</h2>
  <table><thead><tr><th>Estación</th><th>Provincia</th><th style="text-align:right">Mínima</th></tr></thead>
  <tbody>__TOP_CALOR__</tbody></table>

  <h2>Donde mejor se durmió</h2>
  <table><thead><tr><th>Estación</th><th>Provincia</th><th style="text-align:right">Mínima</th></tr></thead>
  <tbody>__TOP_FRESCO__</tbody></table>

  <div class="comparte">
    <div class="t">Comparte el parte</div>
    <pre id="txt">__TUIT__</pre>
    <div class="acciones">
      <button id="copiar">Copiar</button>
      <a class="b" id="wa" href="#" target="_blank" rel="noopener">WhatsApp</a>
      <a class="b" id="tw" href="#" target="_blank" rel="noopener">X / Twitter</a>
    </div>
  </div>

  <p class="nota">Datos de la red de observación de AEMET (últimas 24 h, provisionales y sin validar; ventana nocturna 18:00–08:00 UTC). La media histórica, pueblo a pueblo y con diez veranos validados, está en la <a href="__SITE__/">calculadora</a>.</p>

  <div class="cta"><a href="__SITE__/">¿Y tu pueblo? Míralo en la calculadora →</a></div>
</div></section>

<footer><div class="wrap">
  Fuente: <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a> (observación) · proyecto <a href="__SITE__/">Refugio Climático</a> · datos bajo <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">CC&nbsp;BY&nbsp;4.0</a>.
</div></footer>

<script>
const txt=document.getElementById("txt").textContent;
document.getElementById("copiar").addEventListener("click",e=>{navigator.clipboard?.writeText(txt);e.target.textContent="¡Copiado!";setTimeout(()=>e.target.textContent="Copiar",1500);});
document.getElementById("wa").href="https://wa.me/?text="+encodeURIComponent(txt);
document.getElementById("tw").href="https://twitter.com/intent/tweet?text="+encodeURIComponent(txt);
</script>
</body>
</html>
"""


def main() -> int:
    demo = "--demo" in sys.argv
    obs = observaciones_demo() if demo else obtener_observaciones()
    minimas = minimas_de_la_noche(obs)
    if len(minimas) < MIN_ESTACIONES:
        print(f"ERROR: solo {len(minimas)} estaciones con datos; no se publica el parte.",
              file=sys.stderr)
        return 1

    prov_de = cargar_provincias()
    lista = [{"id": k, "nombre": v["nombre"], "min": v["min"],
              "prov": prov_de.get(k, "")} for k, v in minimas.items()]
    lista.sort(key=lambda e: -e["min"])

    total = len(lista)
    trop = sum(1 for e in lista if e["min"] >= 20)
    ecua = sum(1 for e in lista if e["min"] >= 25)
    peor, mejor = lista[0], lista[-1]
    top_calor = lista[:10]
    top_fresco = sorted(lista, key=lambda e: e["min"])[:10]

    ahora = datetime.now(timezone.utc)
    ayer = ahora - timedelta(days=1)
    if ayer.month == ahora.month:
        fecha_larga = f"{ayer.day} al {ahora.day} de {MESES[ahora.month - 1]} de {ahora.year}"
    else:
        fecha_larga = (f"{ayer.day} de {MESES[ayer.month - 1]} al "
                       f"{ahora.day} de {MESES[ahora.month - 1]} de {ahora.year}")
    fecha_corta = f"{ahora.day} {MESES[ahora.month - 1][:3]}"

    site = g.SITE_URL.rstrip("/")
    dominio = site.split("//")[1]
    pp = f" ({peor['prov']})" if peor["prov"] else ""
    mp = f" ({mejor['prov']})" if mejor["prov"] else ""
    tuit = (f"🌙 El parte de la noche · {fecha_corta}\n"
            f"{trop} estaciones de AEMET no bajaron de 20 °C anoche"
            + (f" ({ecua} ni de 25 °C)." if ecua else ".") + "\n"
            f"🥵 La más tórrida: {peor['nombre']}{pp}, mínima {dec(peor['min'])} °C.\n"
            f"🥶 La más fresca: {mejor['nombre']}{mp}, {dec(mejor['min'])} °C.\n"
            f"Tu pueblo, noche a noche → {dominio}")

    schema = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Refugio Climático", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": "El parte de la noche", "item": site + "/parte/"}]},
        {"@type": "Article",
         "headline": f"El parte de la noche: {trop} estaciones no bajaron de 20 °C",
         "description": f"El parte diario de las noches tropicales en España con la observación de AEMET. La más tórrida: {peor['nombre']} ({dec(peor['min'])} °C).",
         "image": site + "/og.png",
         "author": {"@type": "Person", "name": "Ramón J. Lowesting"},
         "publisher": {"@type": "Organization", "name": "Refugio Climático",
                       "logo": {"@type": "ImageObject", "url": site + "/favicon.svg"}},
         "datePublished": "2026-07-06",
         "dateModified": ahora.strftime("%Y-%m-%d"),
         "mainEntityOfPage": site + "/parte/"}]}, ensure_ascii=False)

    html = (PLANTILLA
            .replace("__SCHEMA__", schema)
            .replace("__FECHA_LARGA__", fecha_larga)
            .replace("__FECHA_CORTA__", fecha_corta)
            .replace("__TROP__", str(trop))
            .replace("__ECUA__", str(ecua))
            .replace("__TOTAL__", str(total))
            .replace("__PEOR_LOC__", peor["nombre"])
            .replace("__PEOR_MIN__", dec(peor["min"]))
            .replace("__PEOR_PROV__", peor["prov"] or "—")
            .replace("__MEJOR_LOC__", mejor["nombre"])
            .replace("__MEJOR_MIN__", dec(mejor["min"]))
            .replace("__MEJOR_PROV__", mejor["prov"] or "—")
            .replace("__TOP_CALOR__", "".join(fila_html(e, site) for e in top_calor))
            .replace("__TOP_FRESCO__", "".join(fila_html(e, site) for e in top_fresco))
            .replace("__TUIT__", tuit)
            .replace("__SITE__", site))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    (OUT_DIR / "parte.txt").write_text(tuit + "\n", encoding="utf-8")
    (OUT_DIR / "parte.json").write_text(json.dumps(
        {"fecha": ahora.strftime("%Y-%m-%d"), "total": total, "tropicales": trop,
         "ecuatoriales": ecua, "peor": peor, "mejor": mejor,
         "top_calor": top_calor, "top_fresco": top_fresco},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK -> {OUT_DIR} · {total} estaciones · {trop} tropicales ({ecua} ecuatoriales)"
          + (" · [DEMO]" if demo else ""))
    print(tuit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
