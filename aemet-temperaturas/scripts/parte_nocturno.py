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
    # AEMET sirve este JSON en codificación latina a veces: probar utf-8 y caer a latin-1
    try:
        return json.loads(r2.content.decode("utf-8"))
    except UnicodeDecodeError:
        return json.loads(r2.content.decode("latin-1"))


def observaciones_demo() -> list[dict]:
    """Datos sintéticos para probar el render en local sin clave de la API.
    Los fint caen SIEMPRE dentro de la ventana nocturna, sea la hora que sea."""
    random.seed(5)
    hoy = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    inicio = hoy - timedelta(days=1) + timedelta(hours=H_INICIO)
    obs = []
    nombres = [("CABO DE GATA", "B000"), ("PUERTO DEL PICO", "D001"),
               ("CEDRILLAS", "9381X"), ("VALENCIA AEROPUERTO", "8414A")]
    nombres += [(f"ESTACION {i}", f"S{i:03d}") for i in range(300)]
    for nombre, idema in nombres:
        base = random.uniform(9, 27)
        for h in range(13):    # 18:00 de ayer a 07:00 de hoy, hora a hora
            t = inicio + timedelta(hours=h)
            obs.append({"idema": idema, "ubi": nombre,
                        "fint": t.strftime("%Y-%m-%dT%H:%M:%S"),
                        "ta": round(base + random.uniform(-1.5, 4), 1)})
    return obs


def parsear_fint(s: str) -> datetime | None:
    """Tolerante con los formatos de fecha de la API (con/sin zona, con 'Z')."""
    try:
        t = datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc)
    except (ValueError, AttributeError, TypeError):
        return None


def _num(v) -> float | None:
    """Valor numérico venga como venga (12.3, '12.3' o '12,3')."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "."))
        except ValueError:
            return None
    return None


def minimas_de_la_noche(obs: list[dict]) -> dict[str, dict]:
    """Por estación, la mínima registrada en la ventana nocturna."""
    hoy = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    ini = hoy - timedelta(days=1) + timedelta(hours=H_INICIO)
    fin = hoy + timedelta(hours=H_FIN)
    est: dict[str, dict] = {}
    for o in obs:
        if not isinstance(o, dict):
            continue
        t = parsear_fint(o.get("fint", ""))
        if t is None or not (ini <= t <= fin):
            continue
        candidatos = [x for x in (_num(o.get("tamin")), _num(o.get("ta"))) if x is not None]
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


# --- Histórico: una línea por noche, para la curva del verano y los récords ---
HISTORIAL_CSV = OUT_DIR / "historial.csv"
DIARIOS_CSV = g.AEMET_DIR / "datos" / "diarios_estaciones.csv"
CAMPOS_HIST = ["fecha", "total", "tropicales", "ecuatoriales",
               "peor", "peor_prov", "peor_min", "mejor", "mejor_prov", "mejor_min"]


def backfill_desde_diarios(historial: list[dict], hoy_iso: str) -> list[dict]:
    """Completa y AFINA el histórico con los datos climatológicos VALIDADOS de
    AEMET (diarios_estaciones.csv, llegan con 3-5 días de retraso): las noches
    pasadas se sobrescriben con el dato consolidado cuando está disponible.
    El parte de hoy (observación provisional) no se toca aquí."""
    if not DIARIOS_CSV.exists():
        return historial
    por_fecha: dict[str, list] = {}
    with open(DIARIOS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fecha = r.get("fecha", "")
            if not fecha or fecha >= hoy_iso:
                continue
            try:
                tmin = float(r["tmin"])
            except (KeyError, TypeError, ValueError):
                continue
            por_fecha.setdefault(fecha, []).append((tmin, r))
    filas = {h["fecha"]: h for h in historial}
    for fecha, lst in por_fecha.items():
        if len(lst) < MIN_ESTACIONES:
            continue
        trop = sum(1 for t, _ in lst if t >= 20)
        ecua = sum(1 for t, _ in lst if t >= 25)
        tp, rp = max(lst, key=lambda x: x[0])
        tm, rm = min(lst, key=lambda x: x[0])
        filas[fecha] = {"fecha": fecha, "total": len(lst),
                        "tropicales": trop, "ecuatoriales": ecua,
                        "peor": g.titular(rp["nombre"]), "peor_prov": canon_provincia(rp["provincia"]),
                        "peor_min": tp,
                        "mejor": g.titular(rm["nombre"]), "mejor_prov": canon_provincia(rm["provincia"]),
                        "mejor_min": tm}
    return sorted(filas.values(), key=lambda x: x["fecha"])


def cargar_historial() -> list[dict]:
    if not HISTORIAL_CSV.exists():
        return []
    with open(HISTORIAL_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def guardar_historial(filas: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORIAL_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_HIST)
        w.writeheader()
        for fila in sorted(filas, key=lambda x: x["fecha"]):
            w.writerow(fila)


def svg_historial(filas: list[dict]) -> str:
    """La curva del verano: una barra por noche = estaciones en noche tropical."""
    if not filas:
        return ""
    filas = sorted(filas, key=lambda x: x["fecha"])[-70:]   # hasta ~10 semanas
    vals = [int(f["tropicales"]) for f in filas]
    vmax = max(max(vals), 1)
    W, H, mB = 700, 150, 22
    n = len(filas)
    paso = W / n
    bw = max(2.0, paso - 2)
    barras, etiquetas = [], []
    cada = max(1, n // 7)      # ~7 etiquetas de fecha
    for i, (f, v) in enumerate(zip(filas, vals)):
        h = (H - mB - 14) * v / vmax
        x = i * paso + (paso - bw) / 2
        record = ' class="rec"' if v == vmax else ""
        barras.append(f'<rect{record} x="{x:.1f}" y="{H - mB - h:.1f}" '
                      f'width="{bw:.1f}" height="{max(h, 1):.1f}" rx="1"/>')
        if i % cada == 0 or i == n - 1:
            d = f["fecha"][8:10].lstrip("0") + "/" + f["fecha"][5:7].lstrip("0")
            etiquetas.append(f'<text x="{x + bw / 2:.1f}" y="{H - 6}">{d}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="Estaciones en noche tropical, noche a noche">'
            f'<text class="ymax" x="2" y="12">máx {vmax}</text>'
            f'<g class="barras">{"".join(barras)}</g>'
            f'<g class="ejes">{"".join(etiquetas)}</g></svg>')


# --- Análisis de la temporada en curso (desde los diarios VALIDADOS) -----------
def _fecha_corta(iso: str) -> str:
    return f"{int(iso[8:10])} {MESES[int(iso[5:7]) - 1][:3]}"


def analisis_temporada() -> dict | None:
    """Recuento por estación desde diarios_estaciones.csv (validado, una fila por
    estación y noche): noches tropicales acumuladas, racha más larga de noches
    tropicales seguidas, récord de calor y nº de refugios (0 NT). Solo recuentos
    y récords —nunca medias—. Devuelve None si aún no hay datos suficientes."""
    if not DIARIOS_CSV.exists():
        return None
    por_est: dict[str, list] = {}
    fechas: set[str] = set()
    with open(DIARIOS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                tmin = float(r["tmin"])
            except (KeyError, TypeError, ValueError):
                continue
            fechas.add(r["fecha"])
            por_est.setdefault(r["indicativo"], []).append(
                (r["fecha"], tmin, g.titular(r.get("nombre", "")),
                 canon_provincia(r.get("provincia", ""))))
    if len(fechas) < 10:
        return None

    def dias(a: str, b: str) -> int:
        return (datetime.fromisoformat(a) - datetime.fromisoformat(b)).days

    rank = []
    for regs in por_est.values():
        regs.sort()
        trop = sum(1 for _, t, *_ in regs if t >= 20)
        nombre, prov = regs[-1][2], regs[-1][3]
        mejor = cur = 0
        prev = None
        for fe, t, *_ in regs:
            if t >= 20:
                cur = cur + 1 if (prev is not None and dias(fe, prev) == 1) else 1
                mejor = max(mejor, cur)
                prev = fe
            else:
                cur, prev = 0, None
        rank.append({"trop": trop, "racha": mejor, "nombre": nombre, "prov": prov})
    rank.sort(key=lambda x: -x["trop"])
    hot = max(((t, g.titular(n), canon_provincia(p), fe)
               for regs in por_est.values() for fe, t, n, p in regs), default=None)
    return {"desde": min(fechas), "hasta": max(fechas), "noches": len(fechas),
            "estaciones": len(rank),
            "top": [r for r in rank if r["trop"] > 0][:12],
            "racha": max(rank, key=lambda x: x["racha"]),
            "refugios": sum(1 for r in rank if r["trop"] == 0),
            "hot": hot}


def seccion_temporada_html(a: dict | None, site: str) -> str:
    """La sección 'La temporada en curso': ranking de noches tropicales, la racha
    más larga, el récord de calor y el contador de refugios (mensaje positivo)."""
    if not a or not a["top"]:
        return ""
    filas = "".join(
        f'<tr><td class="loc">{r["nombre"]}</td>'
        f'<td><a href="{site}/{g.slug(r["prov"])}/">{r["prov"]}</a></td>'
        f'<td class="n">{r["trop"]}</td></tr>'
        for r in a["top"])
    racha, hot = a["racha"], a["hot"]
    hot_html = ""
    if hot and hot[0] >= 20:
        hot_html = (f'<p class="hist-nota"><b>Récord de calor</b> de la temporada: '
                    f'{hot[1]} ({hot[2]}) no bajó de <b>{dec(hot[0])} °C</b> '
                    f'la noche del {_fecha_corta(hot[3])}.</p>')
    pct = round(100 * a["refugios"] / a["estaciones"]) if a["estaciones"] else 0
    return (
        '<h2>La temporada en curso</h2>'
        f'<p class="hist-nota">Recuento con datos <b>validados</b> de AEMET, del '
        f'{_fecha_corta(a["desde"])} al {_fecha_corta(a["hasta"])} '
        f'({a["noches"]} noches, {a["estaciones"]} estaciones). Noches tropicales '
        f'(mínima ≥ 20 °C) acumuladas por estación:</p>'
        '<table><thead><tr><th>Estación</th><th>Provincia</th>'
        '<th style="text-align:right">Noches</th></tr></thead>'
        f'<tbody>{filas}</tbody></table>'
        f'<p class="hist-nota"><b>La racha más larga:</b> {racha["nombre"]} '
        f'({racha["prov"]}) encadenó <b>{racha["racha"]} noches tropicales seguidas</b>.</p>'
        f'{hot_html}'
        '<div class="mision"><div class="mt">Los refugios resisten</div>'
        f'<p><b>{a["refugios"]} de {a["estaciones"]}</b> estaciones ({pct} %) no han '
        f'tenido <b>ni una sola noche tropical</b> esta temporada: siguen durmiendo '
        f'fresco. Son los <a href="{site}/refugios-y-espana-vaciada/">refugios '
        f'climáticos</a> que el calor no ha rendido.</p></div>')


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
 .num.fresco .v{color:var(--verde)} .num.trop .v{color:var(--teja2)} .num.ecua .v{color:#cf4b34} .num.tot .v{color:var(--muted)}
 .duelo{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:6px 0 26px}
 .card{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:16px 18px}
 .card .t{font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;margin-bottom:8px}
 .card.calor .t{color:#e0705a}.card.fresco .t{color:var(--verde)}
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
 .histwrap{background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:14px 14px 8px;margin:6px 0 8px}
 .histwrap svg{width:100%;height:auto;display:block}
 .histwrap .barras rect{fill:var(--teja)}
 .histwrap .barras rect.rec{fill:var(--teja2)}
 .histwrap .ejes text{fill:var(--muted);font-family:var(--fm);font-size:10px;text-anchor:middle}
 .histwrap .ymax{fill:var(--muted);font-family:var(--fm);font-size:10px}
 .hist-nota{font-size:13.5px;color:var(--muted);margin:0 0 10px}
 .hist-nota b{color:#e7dcc8}
 .comparte{margin:34px 0;background:linear-gradient(180deg,var(--bg2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:18px 20px}
 .comparte .t{font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;color:var(--teja);margin-bottom:10px}
 .comparte pre{white-space:pre-wrap;font-family:var(--fm);font-size:13px;color:#e3d8c4;background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
 .comparte .acciones{display:flex;gap:10px;margin-top:12px;flex-wrap:wrap}
 .comparte button,.comparte a.b{background:transparent;border:1px solid var(--teja);color:var(--teja2);font-weight:700;font-size:13.5px;padding:9px 16px;border-radius:9px;cursor:pointer;text-decoration:none}
 .comparte button:hover,.comparte a.b:hover{background:var(--teja);color:#1a1209}
 .nota{font-size:12.5px;color:var(--muted);margin:22px 0}
 .mision{margin:26px 0;background:linear-gradient(180deg,rgba(143,176,122,.10),transparent);border:1px solid var(--line);border-left:3px solid var(--verde);border-radius:0 14px 14px 0;padding:16px 20px}
 .mision .mt{font:600 11px/1 var(--fb);letter-spacing:.14em;text-transform:uppercase;color:var(--verde);margin-bottom:8px}
 .mision p{font-size:14.5px;color:#e3d8c4;margin:0;line-height:1.6}.mision p b{color:var(--paper)}
 .archivo{font-size:13px;color:var(--muted);margin:18px 0 0}
 .archivo a{font-family:var(--fm);font-size:12.5px}
 .cta{margin:26px 0;text-align:center}
 .cta a{display:inline-block;background:var(--teja);color:#1a1209;font-weight:700;padding:13px 22px;border-radius:12px}
 .cta a:hover{background:var(--teja2);text-decoration:none}
 footer{border-top:1px solid var(--line);padding:28px 0 60px;color:#9a8a6f;font-size:12.5px;margin-top:24px}
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
    <div class="num fresco"><div class="v">__FRESCAS__</div><div class="l">estaciones donde <b>se durmió fresco</b> (mínima &lt; 20 °C)</div></div>
    <div class="num trop"><div class="v">__TROP__</div><div class="l">en <b>noche tropical</b> (mínima ≥ 20 °C)</div></div>
    <div class="num ecua"><div class="v">__ECUA__</div><div class="l">en <b>noche ecuatorial</b> (mínima ≥ 25 °C)</div></div>
  </div>
  <p class="nota" style="margin-top:-14px">De __TOTAL__ estaciones con datos esta noche.</p>

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

  <div class="mision">
    <div class="mt">Aún hay refugios</div>
    <p>Incluso en plena ola de calor, en estos pueblos —casi todos de montaña interior— se sigue durmiendo tapado. Son la España que el calor no ha rendido. Muchos coinciden con la <b>España vaciada</b>: el frío que un día los despobló es hoy su mayor activo. → <a href="__SITE__/refugios-y-espana-vaciada/">Refugios climáticos y España vaciada</a></p>
  </div>

  __SECCION_HISTORIAL__

  __SECCION_TEMPORADA__

  <div class="comparte">
    <div class="t">Comparte el parte</div>
    <pre id="txt">__TUIT__</pre>
    <div class="acciones">
      <button id="copiar">Copiar</button>
      <a class="b" id="wa" href="#" target="_blank" rel="noopener">WhatsApp</a>
      <a class="b" id="tw" href="#" target="_blank" rel="noopener">X / Twitter</a>
      <button id="nativo" hidden>Compartir…</button>
    </div>
  </div>

  __ARCHIVO__

  <p class="nota">Datos de la red de observación de AEMET (últimas 24 h, provisionales y sin validar; ventana nocturna 18:00–08:00 UTC). La media histórica, pueblo a pueblo y con diez veranos validados, está en la <a href="__SITE__/">calculadora</a>.</p>

  <div class="cta"><a href="__SITE__/">¿Y tu pueblo? Míralo en la calculadora →</a></div>

  <p class="nota">¿Mala noche? <a href="__SITE__/dormir-con-calor/">Qué funciona de verdad para dormir con calor</a> —sin comprar nada—, y <a href="__SITE__/vacaciones-sin-calor/">dónde se duerme fresco</a> si lo que quieres es escaparte.</p>
</div></section>

<footer><div class="wrap">
  Fuente: <a href="https://opendata.aemet.es" target="_blank" rel="noopener">AEMET OpenData</a> (observación) · proyecto <a href="__SITE__/">Refugio Climático</a> · datos bajo <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">CC&nbsp;BY&nbsp;4.0</a>.
</div></footer>

<script>
const txt=document.getElementById("txt").textContent;
document.getElementById("copiar").addEventListener("click",e=>{navigator.clipboard?.writeText(txt);e.target.textContent="¡Copiado!";setTimeout(()=>e.target.textContent="Copiar",1500);});
const pageurl=location.href.split("#")[0];
document.getElementById("wa").href="https://wa.me/?text="+encodeURIComponent(txt);
document.getElementById("tw").href="https://twitter.com/intent/tweet?text="+encodeURIComponent(txt);
const nativo=document.getElementById("nativo");
if(nativo&&navigator.share){nativo.hidden=false;nativo.addEventListener("click",()=>{navigator.share({text:txt,url:pageurl}).catch(()=>{});});}
</script>
</body>
</html>
"""


def main() -> int:
    demo = "--demo" in sys.argv
    obs = observaciones_demo() if demo else obtener_observaciones()
    minimas = minimas_de_la_noche(obs)
    if len(minimas) < MIN_ESTACIONES:
        # La API de observación solo conserva ~12 horas: por la tarde-noche la
        # última madrugada ya no está disponible. No es un fallo: simplemente
        # el parte se genera por la mañana (cron de las 07:15 UTC).
        hora = datetime.now(timezone.utc).hour
        if hora >= 12 or hora < 4:
            print(f"AVISO: solo {len(minimas)} estaciones en la ventana nocturna. "
                  "La observación de AEMET conserva ~12 h, así que fuera de la mañana "
                  "la última noche ya no está disponible. No se publica nada ahora; "
                  "el run automático de las 07:15 UTC generará el parte de mañana.")
            return 0
        print(f"ERROR: solo {len(minimas)} estaciones con datos; no se publica el parte.",
              file=sys.stderr)
        # Diagnóstico: qué devuelve la API de verdad, para afinar el parser.
        print(f"DEBUG: {len(obs) if isinstance(obs, list) else type(obs)} observaciones recibidas.",
              file=sys.stderr)
        if isinstance(obs, list) and obs and isinstance(obs[0], dict):
            ej = obs[0]
            muestra = {k: ej.get(k) for k in list(ej)[:14]}
            print("DEBUG ejemplo de observación:", muestra, file=sys.stderr)
            fints = [str(o.get("fint")) for o in obs
                     if isinstance(o, dict) and o.get("fint")]
            if fints:
                print(f"DEBUG rango de fint: {min(fints)} → {max(fints)}", file=sys.stderr)
            print(f"DEBUG ventana buscada: últimas {H_INICIO}:00 UTC de ayer → "
                  f"{H_FIN}:00 UTC de hoy", file=sys.stderr)
        return 1

    prov_de = cargar_provincias()
    lista = [{"id": k, "nombre": v["nombre"], "min": v["min"],
              "prov": prov_de.get(k, "")} for k, v in minimas.items()]
    lista.sort(key=lambda e: -e["min"])

    # Los RECUENTOS usan todas las estaciones; los PROTAGONISTAS (más tórrida,
    # más fresca, tops) solo las de nombre y provincia conocidos, para evitar
    # códigos feos tipo "Evc_noia" en titulares y tuits.
    total = len(lista)
    trop = sum(1 for e in lista if e["min"] >= 20)
    ecua = sum(1 for e in lista if e["min"] >= 25)
    frescas = total - trop
    conocidas = [e for e in lista if e["prov"] and "_" not in e["nombre"]]
    sel = conocidas if len(conocidas) >= 100 else lista
    peor, mejor = sel[0], sel[-1]
    top_calor = sel[:10]
    top_fresco = sorted(sel, key=lambda e: e["min"])[:10]

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
    fecha_iso_tuit = ahora.strftime("%Y-%m-%d")
    # Orden: primero el dato favorable (dónde se durmió fresco), luego lo crítico
    # (las noches tropicales). Sin emojis, para un tono más serio.
    tuit = (f"El parte de la noche · {fecha_corta}\n"
            f"Anoche se durmió fresco en {frescas} estaciones de AEMET "
            f"(mínima por debajo de 20 °C). En {trop} fue noche tropical.\n"
            f"La más fresca: {mejor['nombre']} {dec(mejor['min'])}°. "
            f"La más cálida: {peor['nombre']} {dec(peor['min'])}°.\n"
            f"Aún hay refugios → {dominio}/parte/{fecha_iso_tuit}/")

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
            .replace("__FRESCAS__", str(frescas))
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

    # Histórico: upsert de la noche de hoy + curva del verano + archivo del día.
    fecha_iso = ahora.strftime("%Y-%m-%d")
    fila_hoy = {"fecha": fecha_iso, "total": total, "tropicales": trop,
                "ecuatoriales": ecua,
                "peor": peor["nombre"], "peor_prov": peor["prov"], "peor_min": peor["min"],
                "mejor": mejor["nombre"], "mejor_prov": mejor["prov"], "mejor_min": mejor["min"]}
    base = [f for f in cargar_historial() if f["fecha"] != fecha_iso]
    base = backfill_desde_diarios(base, fecha_iso)
    historial = base + [fila_hoy]
    if not demo:
        guardar_historial(historial)
    if demo and len(historial) < 5:   # datos de relleno SOLO para ver el gráfico en local
        historial = [{"fecha": (ahora - timedelta(days=d)).strftime("%Y-%m-%d"),
                      "tropicales": str(int(100 + 140 * abs((25 - d) / 25) + d % 7 * 9))}
                     for d in range(30, 0, -1)] + [fila_hoy]
    seccion_hist = ""
    if len(historial) >= 2:
        vmax_fila = max(historial, key=lambda x: int(x["tropicales"]))
        rec_txt = ""
        if vmax_fila["fecha"] == fecha_iso:
            rec_txt = " <b>Anoche se marcó el récord del verano.</b>"
        seccion_hist = (
            '<h2>El verano, noche a noche</h2>'
            f'<p class="hist-nota">Cada barra es una noche: cuántas estaciones quedaron en '
            f'noche tropical. Llevamos <b>{len(historial)}</b> noches contadas; el récord, '
            f'<b>{vmax_fila["tropicales"]}</b> estaciones ({vmax_fila["fecha"][8:10].lstrip("0")}/'
            f'{vmax_fila["fecha"][5:7].lstrip("0")}).{rec_txt}</p>'
            f'<div class="histwrap">{svg_historial(historial)}</div>')
    html = html.replace("__SECCION_HISTORIAL__", seccion_hist)
    html = html.replace("__SECCION_TEMPORADA__",
                        seccion_temporada_html(analisis_temporada(), site))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Archivo navegable: enlaces a los últimos partes fechados (más el de hoy).
    fechas_previas = sorted(d.name for d in OUT_DIR.glob("????-??-??") if d.is_dir())
    fechas_arch = sorted(set(fechas_previas + [fecha_iso]))[-12:]
    enlaces_arch = " · ".join(
        f'<a href="{site}/parte/{f}/">{int(f[8:10])} {MESES[int(f[5:7]) - 1][:3]}</a>'
        for f in fechas_arch)
    html = html.replace("__ARCHIVO__",
                        f'<p class="archivo">Archivo del parte: {enlaces_arch}</p>')
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    # Página FECHADA del día: URL propia por noche (/parte/AAAA-MM-DD/), con su
    # canonical/og propios -> cada tuit enlaza a SU noche y X trae tarjeta fresca.
    html_fecha = html.replace(f'{site}/parte/"', f'{site}/parte/{fecha_iso}/"')
    (OUT_DIR / fecha_iso).mkdir(exist_ok=True)
    (OUT_DIR / fecha_iso / "index.html").write_text(html_fecha, encoding="utf-8")
    # Archivo del día = LA MEMORIA DE LO EFÍMERO. La observación de AEMET solo
    # conserva ~12 h; aquí guardamos la mínima de TODAS las estaciones de esta
    # noche para siempre (no solo el top 10). Es la materia prima de los análisis
    # de temporada (rachas, ranking del verano en curso, récords…).
    (OUT_DIR / "dias").mkdir(exist_ok=True)
    (OUT_DIR / "dias" / f"{fecha_iso}.json").write_text(json.dumps(
        {"fecha": fecha_iso, "total": total, "tropicales": trop, "ecuatoriales": ecua,
         "peor": peor, "mejor": mejor, "top_calor": top_calor, "top_fresco": top_fresco,
         "estaciones": [{"id": e["id"], "nombre": e["nombre"], "prov": e["prov"],
                         "min": round(e["min"], 1)} for e in lista]},
        ensure_ascii=False), encoding="utf-8")
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
