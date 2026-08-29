#!/usr/bin/env python3
"""
Gradiente térmico NOCTURNO de verano, medido con pares de estaciones de AEMET.

Pregunta: ¿cuánto baja de verdad la temperatura mínima de verano por cada 100 m
de altitud en España?

El coeficiente de manual (0,6 °C/100 m) es el gradiente vertical de la atmósfera
libre y describe razonablemente el día. La noche es otra cosa: con cielo despejado
y sin viento el aire frío drena por las laderas y se embalsa en los fondos de
valle (inversión térmica), de modo que el punto bajo puede amanecer MÁS FRÍO que
el alto. Aplicar 0,6 °C/100 m a las mínimas puede corregir con el signo cambiado.

Método: cada pareja de estaciones próximas con desnivel apreciable es un
experimento natural ya hecho. Se emparejan estaciones a <= 15 km y >= 100 m de
desnivel con al menos 3 veranos solapados, y se regresa el salto térmico contra
el salto de altitud.

Análisis manual. No genera ninguna página web ni entra en el workflow diario.

Salidas:
  datos/gradiente_nocturno.json
  datos/pares_estaciones.csv
  resumen por consola

Fuente: AEMET (valores climatológicos diarios, red de ~848 estaciones).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import date
from itertools import combinations
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Reutilizamos los cargadores del análisis nocturno en vez de reimplementarlos:
# ahí viven el dedup por (fecha, indicativo), el parseo de fechas y la conversión
# DMS -> decimal de las coordenadas del catálogo.
import analisis_refugios_nocturnos as arn  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATOS = ROOT / "datos"

FUENTE = "AEMET"

MESES_VERANO = (6, 7, 8, 9)
COBERTURA_MIN = 0.80        # como máximo un 20 % de días ausentes en un verano
MIN_VERANOS = 3             # veranos completos mínimos por estación
MIN_VERANOS_COMUNES = 3     # veranos solapados mínimos por par
DIST_MAX_KM = 15.0
DESNIVEL_MIN_M = 100.0
DIST_COSTA_KM = 30.0
GRADIENTE_MANUAL = 0.6      # °C/100 m, gradiente vertical de manual

CORTES_ALTITUD = ((None, 400.0, "<400"), (400.0, 800.0, "400-800"), (800.0, None, ">800"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gradiente")


# ---------------------------------------------------------------- geometría

def km(la1: float, lo1: float, la2: float, lo2: float) -> float:
    """Distancia haversine en km. Sin geopandas ni nada parecido."""
    la1, lo1, la2, lo2 = map(radians, (la1, lo1, la2, lo2))
    a = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 12742 * asin(sqrt(a))


# Provincias con litoral, en la grafía del catálogo de estaciones de AEMET
# (que arrastra duplicados tipo BALEARES / ILLES BALEARS).
PROVINCIAS_LITORAL = {
    "A CORUÑA", "ALICANTE", "ALMERIA", "ALMERÍA", "ASTURIAS", "BALEARES",
    "ILLES BALEARS", "BARCELONA", "BIZKAIA", "CADIZ", "CÁDIZ", "CANTABRIA",
    "CASTELLON", "CASTELLÓN", "CEUTA", "GIPUZKOA", "GIRONA", "GRANADA",
    "HUELVA", "LAS PALMAS", "LUGO", "MALAGA", "MÁLAGA", "MELILLA", "MURCIA",
    "PONTEVEDRA", "SANTA CRUZ DE TENERIFE", "STA. CRUZ DE TENERIFE",
    "TARRAGONA", "VALENCIA", "VALÈNCIA",
}

# Las mismas provincias en la grafía del geojson de contornos.
GEOJSON_LITORAL = {
    "Illes Balears", "Asturias", "A Coruña", "Girona", "Las Palmas",
    "Pontevedra", "Santa Cruz De Tenerife", "Cantabria", "Málaga", "Almería",
    "Murcia", "Alacant/Alicante", "Barcelona", "Cádiz", "Castelló/Castellón",
    "Gipuzkoa/Guipúzcoa", "Granada", "Huelva", "Lugo", "Tarragona",
    "València/Valencia", "Bizkaia/Vizcaya", "Ceuta", "Melilla",
}


def _dilata(m, n=1):
    import numpy as np
    for _ in range(n):
        q = np.pad(m, 1, constant_values=False)
        m = (q[:-2, 1:-1] | q[2:, 1:-1] | q[1:-1, :-2] | q[1:-1, 2:] | q[1:-1, 1:-1] |
             q[:-2, :-2] | q[:-2, 2:] | q[2:, :-2] | q[2:, 2:])
    return m


def _erosiona(m, n=1):
    import numpy as np
    for _ in range(n):
        q = np.pad(m, 1, constant_values=False)
        m = (q[:-2, 1:-1] & q[2:, 1:-1] & q[1:-1, :-2] & q[1:-1, 2:] & q[1:-1, 1:-1] &
             q[:-2, :-2] & q[:-2, 2:] & q[2:, :-2] & q[2:, 2:])
    return m


def puntos_de_costa():
    """
    Línea de costa aproximada, sacada de datos/spain-provinces.geojson.

    El geojson no es topológicamente limpio (provincias vecinas no comparten
    vértices), así que unir polígonos por tramos no funciona — el mismo problema
    que ya documenta generar_silueta.py. Se hace por lo bruto: se pinta el país
    en una rejilla de ~1 km, se cierran las rendijas entre provincias con una
    apertura morfológica, se toma el borde del país y se queda solo con el tramo
    que cae en provincias con litoral.

    Devuelve (lista de (lat, lon), etiqueta del método) o (None, etiqueta) si no
    se puede construir.
    """
    geo = DATOS / "spain-provinces.geojson"
    if not geo.exists():
        return None, "provincias con litoral (falta spain-provinces.geojson)"
    try:
        import numpy as np
        from matplotlib.path import Path as MplPath
    except ImportError:
        return None, "provincias con litoral (falta numpy/matplotlib)"

    d = json.loads(geo.read_text(encoding="utf-8"))
    LO0, LO1, LA0, LA1, PASO = -18.4, 4.7, 27.4, 44.1, 0.01
    xs = np.arange(LO0, LO1, PASO)
    ys = np.arange(LA0, LA1, PASO)
    tierra = np.zeros((len(ys), len(xs)), dtype=bool)
    litoral = np.zeros_like(tierra)

    def pinta(m, anillo):
        i0 = max(0, int((anillo[:, 0].min() - LO0) / PASO) - 1)
        i1 = min(len(xs), int((anillo[:, 0].max() - LO0) / PASO) + 2)
        j0 = max(0, int((anillo[:, 1].min() - LA0) / PASO) - 1)
        j1 = min(len(ys), int((anillo[:, 1].max() - LA0) / PASO) + 2)
        if i0 >= i1 or j0 >= j1:
            return
        gx, gy = np.meshgrid(xs[i0:i1], ys[j0:j1])
        dentro = MplPath(anillo).contains_points(
            np.column_stack([gx.ravel(), gy.ravel()])).reshape(gx.shape)
        m[j0:j1, i0:i1] |= dentro

    for f in d["features"]:
        nombre = f["properties"]["name"]
        g = f["geometry"]
        polis = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poli in polis:
            anillo = np.asarray(poli[0])
            pinta(tierra, anillo)
            if nombre in GEOJSON_LITORAL:
                pinta(litoral, anillo)

    cerrado = _erosiona(_dilata(tierra, 2), 2)          # tapa las rendijas interprovinciales
    p = np.pad(cerrado, 1, constant_values=False)
    interior = p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    borde = cerrado & ~interior
    costa = borde & _dilata(litoral, 4)
    jj, ii = np.nonzero(costa)
    pts = [(float(ys[j]), float(xs[i])) for j, i in zip(jj, ii)]
    if len(pts) < 500:
        return None, "provincias con litoral (contorno insuficiente)"
    return pts, ("contorno costero rasterizado desde spain-provinces.geojson (~1 km), "
                 "limitado a provincias con litoral. LIMITACIÓN: el geojson solo cubre "
                 "España, así que el tramo de frontera con Francia y Portugal de las "
                 "provincias litorales (Girona, Gipuzkoa, Pontevedra, Huelva) cuenta "
                 "como si fuera costa; afecta a un puñado de estaciones pirenaicas y "
                 "del Miño y no cambia las conclusiones (mueve la pendiente de interior "
                 "de -0,222 a -0,231 °C/100 m)")


def indexa_costa(pts, celda=0.5):
    idx = {}
    for la, lo in pts:
        idx.setdefault((int(la // celda), int(lo // celda)), []).append((la, lo))
    return idx


def distancia_a_costa(la, lo, idx, celda=0.5, radio_max=14):
    """
    Distancia mínima en km a la costa, buscando en anillos de celdas.

    Se para cuando el mejor candidato encontrado ya está más cerca que el borde
    de lo ya explorado; la cota usa el grado de longitud (más corto que el de
    latitud), que es la dirección restrictiva.
    """
    ci, cj = int(la // celda), int(lo // celda)
    paso_km = celda * 111.0 * max(cos(radians(la)), 0.1)
    mejor = None
    for r in range(radio_max + 1):
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if max(abs(di), abs(dj)) != r:
                    continue
                for cla, clo in idx.get((ci + di, cj + dj), ()):
                    d = km(la, lo, cla, clo)
                    if mejor is None or d < mejor:
                        mejor = d
        if mejor is not None and mejor <= r * paso_km:
            break
    return mejor


# ---------------------------------------------------------------- regresión

def ols(xs, ys):
    """Mínimos cuadrados con ordenada en el origen. Aritmética pura."""
    n = len(xs)
    if n < 3:
        return None
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    den = n * sxx - sx * sx
    if den == 0:
        return None
    b = (n * sxy - sx * sy) / den
    a = (sy - b * sx) / n
    my = sy / n
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    se = sqrt((ss_res / (n - 2)) / (sxx - sx * sx / n)) if n > 2 else float("nan")
    return {"pendiente": b, "ordenada": a, "r2": r2, "error_std": se, "n": n}


def ols_origen(xs, ys):
    """Mínimos cuadrados forzando el paso por el origen: sin desnivel, sin salto."""
    n = len(xs)
    if n < 2:
        return None
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    if sxx == 0:
        return None
    b = sxy / sxx
    ss_res = sum((y - b * x) ** 2 for x, y in zip(xs, ys))
    my = sum(ys) / n
    ss_tot = sum((y - my) ** 2 for y in ys)
    # R² frente a la media, para que sea comparable con el modelo con ordenada
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    se = sqrt((ss_res / (n - 1)) / sxx) if n > 1 else float("nan")
    return {"pendiente": b, "r2": r2, "error_std": se, "n": n}


def resumen_ajuste(pares, etiqueta=""):
    """Ajusta delta_tmin (°C) contra delta_altitud (en unidades de 100 m)."""
    if len(pares) < 3:
        return {"n_pares": len(pares), "pendiente_c_por_100m": None,
                "r2": None, "error_std": None, "nota": "muestra insuficiente"}
    xs = [p["delta_altitud_m"] / 100.0 for p in pares]
    ys = [p["delta_tmin_c"] for p in pares]
    org = ols_origen(xs, ys)
    con = ols(xs, ys)
    out = {
        "n_pares": len(pares),
        "pendiente_c_por_100m": round(org["pendiente"], 4),
        "descenso_c_por_100m": round(-org["pendiente"], 4),
        "r2": round(org["r2"], 4),
        "error_std": round(org["error_std"], 4),
        "con_ordenada": {
            "pendiente_c_por_100m": round(con["pendiente"], 4),
            "ordenada_c": round(con["ordenada"], 4),
            "r2": round(con["r2"], 4),
            "error_std": round(con["error_std"], 4),
        } if con else None,
    }
    if etiqueta:
        out["grupo"] = etiqueta
    return out


# ---------------------------------------------------------------- paso 1

def medias_estivales(df, esperados):
    """
    Media estival de tmin por estación y año, y filtro de calidad.

    Devuelve (validas, descartes) donde validas es
        {indicativo: {"por_anio": {anio: media}, "media": float, "veranos": int}}
    y descartes es {indicativo: motivo}.
    """
    verano = df[df["mes"].isin(MESES_VERANO)].dropna(subset=["tmin"])
    g = verano.groupby(["indicativo", "anio"])["tmin"].agg(["mean", "count"])

    validas, descartes = {}, {}
    por_estacion = {}
    for (ind, anio), fila in g.iterrows():
        por_estacion.setdefault(str(ind), {})[int(anio)] = (float(fila["mean"]), int(fila["count"]))

    for ind in sorted(set(df["indicativo"].astype(str).unique()) - set(por_estacion)):
        descartes[ind] = "sin_tmin_de_verano"

    for ind, anios in por_estacion.items():
        completos = {}
        for anio, (media, n) in anios.items():
            esperado = esperados.get(anio)
            if not esperado:
                continue
            if n / esperado >= COBERTURA_MIN:
                completos[anio] = media
        if len(anios) < MIN_VERANOS:
            descartes[ind] = "menos_de_3_veranos"
        elif len(completos) < MIN_VERANOS:
            descartes[ind] = "veranos_incompletos"   # >20 % de días ausentes
        else:
            validas[ind] = {
                "por_anio": completos,
                "media": sum(completos.values()) / len(completos),
                "veranos": len(completos),
            }
    return validas, descartes


def dias_esperados(df):
    """Días de calendario jun-sep de cada año dentro del rango cubierto por los datos."""
    fmin = df["fecha"].min().date()
    fmax = df["fecha"].max().date()
    out = {}
    for anio in range(fmin.year, fmax.year + 1):
        ini = max(date(anio, 6, 1), fmin)
        fin = min(date(anio, 9, 30), fmax)
        n = (fin - ini).days + 1
        if n > 0:
            out[anio] = n
    return out


# ---------------------------------------------------------------- paso 2

def grupo_altitud(alt):
    for lo, hi, etiqueta in CORTES_ALTITUD:
        if (lo is None or alt >= lo) and (hi is None or alt < hi):
            return etiqueta
    return ">800"


def forma_pares(validas, meta, idx_costa, dist_max):
    inds = [i for i in validas if i in meta]
    inds.sort()
    pares = []
    for a, b in combinations(inds, 2):
        ma, mb = meta[a], meta[b]
        if abs(ma["altitud_m"] - mb["altitud_m"]) < DESNIVEL_MIN_M:
            continue
        d = km(ma["lat"], ma["lon"], mb["lat"], mb["lon"])
        if d > dist_max:
            continue
        comunes = sorted(set(validas[a]["por_anio"]) & set(validas[b]["por_anio"]))
        if len(comunes) < MIN_VERANOS_COMUNES:
            continue
        alta, baja = (a, b) if ma["altitud_m"] > mb["altitud_m"] else (b, a)
        m_alta, m_baja = meta[alta], meta[baja]
        # El salto se mide SOLO en los veranos que comparten, si no estaríamos
        # comparando años distintos en vez de altitudes.
        t_alta = sum(validas[alta]["por_anio"][y] for y in comunes) / len(comunes)
        t_baja = sum(validas[baja]["por_anio"][y] for y in comunes) / len(comunes)
        dalt = m_alta["altitud_m"] - m_baja["altitud_m"]
        dt = t_alta - t_baja
        dc_baja = distancia_a_costa(m_baja["lat"], m_baja["lon"], idx_costa) if idx_costa else None
        dc_alta = distancia_a_costa(m_alta["lat"], m_alta["lon"], idx_costa) if idx_costa else None
        if idx_costa:
            es_litoral = dc_baja is not None and dc_baja <= DIST_COSTA_KM
        else:
            es_litoral = m_baja["provincia"].strip().upper() in PROVINCIAS_LITORAL
        pares.append({
            "indicativo_alta": alta, "nombre_alta": m_alta["nombre"],
            "provincia_alta": m_alta["provincia"], "altitud_alta_m": m_alta["altitud_m"],
            "lat_alta": m_alta["lat"], "lon_alta": m_alta["lon"],
            "indicativo_baja": baja, "nombre_baja": m_baja["nombre"],
            "provincia_baja": m_baja["provincia"], "altitud_baja_m": m_baja["altitud_m"],
            "lat_baja": m_baja["lat"], "lon_baja": m_baja["lon"],
            "distancia_km": round(d, 2),
            "delta_altitud_m": round(dalt, 1),
            "delta_tmin_c": round(dt, 3),
            "gradiente_c_por_100m": round(dt / (dalt / 100.0), 3),
            "veranos_comunes": len(comunes),
            "anio_ini": comunes[0], "anio_fin": comunes[-1],
            "tmin_alta_comun_c": round(t_alta, 2),
            "tmin_baja_comun_c": round(t_baja, 2),
            "tmin_alta_serie_c": round(validas[alta]["media"], 2),
            "tmin_baja_serie_c": round(validas[baja]["media"], 2),
            "dist_costa_baja_km": round(dc_baja, 1) if dc_baja is not None else "",
            "dist_costa_alta_km": round(dc_alta, 1) if dc_alta is not None else "",
            "grupo_altitud": grupo_altitud(m_baja["altitud_m"]),
            "grupo_costa": "litoral" if es_litoral else "interior",
        })
    return pares


# ---------------------------------------------------------------- salida

COLUMNAS = [
    "indicativo_alta", "nombre_alta", "provincia_alta", "altitud_alta_m", "lat_alta", "lon_alta",
    "indicativo_baja", "nombre_baja", "provincia_baja", "altitud_baja_m", "lat_baja", "lon_baja",
    "distancia_km", "delta_altitud_m", "delta_tmin_c", "gradiente_c_por_100m",
    "veranos_comunes", "anio_ini", "anio_fin",
    "tmin_alta_comun_c", "tmin_baja_comun_c", "tmin_alta_serie_c", "tmin_baja_serie_c",
    "dist_costa_baja_km", "dist_costa_alta_km", "grupo_altitud", "grupo_costa",
    "delta_esperado_c", "anomalia_c", "inversion_pura", "fuente",
]


def escribe_csv(pares, destino):
    with open(destino, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        for p in pares:
            w.writerow(p)


def main() -> int:
    ap = argparse.ArgumentParser(description="Gradiente térmico nocturno por pares de estaciones (AEMET)")
    ap.add_argument("--dist", type=float, default=DIST_MAX_KM,
                    help=f"distancia máxima entre estaciones del par, en km (por defecto {DIST_MAX_KM:g})")
    ap.add_argument("--top", type=int, default=10, help="cuántas inversiones listar por consola")
    args = ap.parse_args()

    est = arn.cargar_estaciones()
    meta = {}
    for r in est.itertuples():
        if r.lat != r.lat or r.lon != r.lon or r.altitud_m != r.altitud_m:
            continue
        meta[str(r.indicativo)] = {
            "nombre": r.nombre, "provincia": r.provincia,
            "lat": float(r.lat), "lon": float(r.lon), "altitud_m": float(r.altitud_m),
        }
    log.info("Catálogo: %d estaciones con altitud y coordenadas utilizables", len(meta))

    df = arn.cargar_diarios()
    esperados = dias_esperados(df)
    log.info("Veranos (jun-sep) cubiertos: %s", ", ".join(
        f"{a}:{n}d" for a, n in sorted(esperados.items())))

    validas, descartes = medias_estivales(df, esperados)
    sin_meta = sorted(i for i in validas if i not in meta)
    for i in sin_meta:
        descartes[i] = "sin_metadatos"
        validas.pop(i)

    motivos = {}
    for m in descartes.values():
        motivos[m] = motivos.get(m, 0) + 1

    pts_costa, metodo_costa = puntos_de_costa()
    idx_costa = indexa_costa(pts_costa) if pts_costa else None
    log.info("Costa: %s", metodo_costa)

    pares = forma_pares(validas, meta, idx_costa, args.dist)

    global_ = resumen_ajuste(pares)
    pend = global_["pendiente_c_por_100m"]

    for p in pares:
        esperado = (pend * p["delta_altitud_m"] / 100.0) if pend is not None else 0.0
        p["delta_esperado_c"] = round(esperado, 3)
        p["anomalia_c"] = round(p["delta_tmin_c"] - esperado, 3)
        p["inversion_pura"] = "si" if p["delta_tmin_c"] > 0 else "no"
        p["fuente"] = FUENTE

    por_altitud = {et: resumen_ajuste([p for p in pares if p["grupo_altitud"] == et], et)
                   for _, _, et in CORTES_ALTITUD}
    por_costa = {et: resumen_ajuste([p for p in pares if p["grupo_costa"] == et], et)
                 for et in ("litoral", "interior")}

    inversiones = sorted([p for p in pares if p["anomalia_c"] > 0],
                         key=lambda p: -p["anomalia_c"])
    puras = [p for p in inversiones if p["inversion_pura"] == "si"]

    claves_inv = ("indicativo_alta", "nombre_alta", "provincia_alta", "altitud_alta_m",
                  "indicativo_baja", "nombre_baja", "provincia_baja", "altitud_baja_m",
                  "distancia_km", "delta_altitud_m", "delta_tmin_c", "delta_esperado_c",
                  "anomalia_c", "inversion_pura", "veranos_comunes")

    DATOS.mkdir(exist_ok=True)
    escribe_csv(pares, DATOS / "pares_estaciones.csv")

    salida = {
        "generado": date.today().isoformat(),
        "fuente": FUENTE,
        "metodo": (f"pares de estaciones a <={args.dist:g} km y >={DESNIVEL_MIN_M:g} m de "
                   "desnivel, veranos jun-sep; el salto térmico se mide solo en los "
                   "veranos que ambas estaciones comparten"),
        "criterios": {
            "meses_verano": list(MESES_VERANO),
            "cobertura_minima_verano": COBERTURA_MIN,
            "veranos_minimos_estacion": MIN_VERANOS,
            "veranos_comunes_minimos": MIN_VERANOS_COMUNES,
            "distancia_maxima_km": args.dist,
            "desnivel_minimo_m": DESNIVEL_MIN_M,
            "umbral_costa_km": DIST_COSTA_KM,
            "signo": ("delta_tmin = tmin(estación alta) - tmin(estación baja); "
                      "pendiente negativa = enfría al subir"),
            "metodo_costa": metodo_costa,
        },
        "estaciones": {
            "validas": len(validas),
            "descartadas": len(descartes),
            "descartes_por_motivo": motivos,
        },
        "global": global_,
        "por_altitud": por_altitud,
        "por_costa": por_costa,
        "inversiones": [{k: p[k] for k in claves_inv} for p in inversiones],
        "n_inversiones": len(inversiones),
        "n_inversiones_puras": len(puras),
    }
    (DATOS / "gradiente_nocturno.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------- consola
    L = log.info
    L("=" * 78)
    L("GRADIENTE TÉRMICO NOCTURNO DE VERANO (jun-sep) — Fuente: AEMET")
    L("=" * 78)
    L("Estaciones válidas ..... %d", len(validas))
    L("Estaciones descartadas . %d", len(descartes))
    for m, n in sorted(motivos.items(), key=lambda kv: -kv[1]):
        L("    %-22s %4d", m, n)
    L("Pares formados ......... %d  (<=%g km, >=%g m de desnivel, >=%d veranos comunes)",
      len(pares), args.dist, DESNIVEL_MIN_M, MIN_VERANOS_COMUNES)
    if len(pares) < 30:
        L("")
        L("!! AVISO: menos de 30 pares. El análisis NO tiene potencia estadística")
        L("!! suficiente. Antes de sacar conclusiones hay que relajar el criterio")
        L("!! de distancia a 20 km:  python scripts/analisis_gradiente.py --dist 20")
    L("-" * 78)
    if pend is None:
        L("Muestra insuficiente para ajustar nada.")
        return 1
    L("AJUSTE GLOBAL (por el origen)")
    L("    pendiente ..... %+.3f °C/100 m   (= %.3f °C de descenso por cada 100 m)",
      pend, -pend)
    L("    R² ............ %.3f", global_["r2"])
    L("    error estándar  %.3f °C/100 m", global_["error_std"])
    L("    n pares ....... %d", global_["n_pares"])
    co = global_["con_ordenada"]
    L("    (con ordenada: %+.3f °C/100 m, ordenada %+.3f °C, R² %.3f)",
      co["pendiente_c_por_100m"], co["ordenada_c"], co["r2"])
    L("-" * 78)
    L("POR ALTITUD DE LA ESTACIÓN BAJA")
    for _, _, et in CORTES_ALTITUD:
        s = por_altitud[et]
        if s["pendiente_c_por_100m"] is None:
            L("    %-10s n=%-4d  muestra insuficiente", et, s["n_pares"])
        else:
            L("    %-10s n=%-4d  %+.3f °C/100 m   R²=%.3f   ee=%.3f",
              et, s["n_pares"], s["pendiente_c_por_100m"], s["r2"], s["error_std"])
    L("POR PROXIMIDAD AL MAR (umbral %g km, estación baja del par)", DIST_COSTA_KM)
    for et in ("litoral", "interior"):
        s = por_costa[et]
        if s["pendiente_c_por_100m"] is None:
            L("    %-10s n=%-4d  muestra insuficiente", et, s["n_pares"])
        else:
            L("    %-10s n=%-4d  %+.3f °C/100 m   R²=%.3f   ee=%.3f",
              et, s["n_pares"], s["pendiente_c_por_100m"], s["r2"], s["error_std"])
    L("    método: %s", metodo_costa)
    L("-" * 78)
    L("PARES CON INVERSIÓN: %d de %d (%.0f %%); inversión pura (la baja amanece",
      len(inversiones), len(pares), 100 * len(inversiones) / max(1, len(pares)))
    L("más fría en términos absolutos): %d", len(puras))
    L("")
    L("TOP %d por anomalía (la alta amanece más cálida de lo que predice el gradiente)", args.top)
    for i, p in enumerate(inversiones[:args.top], 1):
        L("%2d. %s (%s, %.0f m)  vs  %s (%s, %.0f m)",
          i, p["nombre_alta"][:30], p["indicativo_alta"], p["altitud_alta_m"],
          p["nombre_baja"][:30], p["indicativo_baja"], p["altitud_baja_m"])
        L("    %s | %.1f km | Δalt %+.0f m | Δtmin obs %+.2f °C | esperado %+.2f °C | "
          "anomalía %+.2f °C%s",
          p["provincia_baja"], p["distancia_km"], p["delta_altitud_m"],
          p["delta_tmin_c"], p["delta_esperado_c"], p["anomalia_c"],
          "  <-- INVERSIÓN PURA" if p["inversion_pura"] == "si" else "")
    L("-" * 78)
    dif = GRADIENTE_MANUAL - (-pend)
    if abs(dif) < 0.05:
        L("El coeficiente medido (%.2f °C/100 m) es indistinguible del %.2f de manual.",
          -pend, GRADIENTE_MANUAL)
    elif dif > 0:
        L("El coeficiente medido (%.2f °C/100 m) es %.2f °C/100 m MENOR que el %.2f de",
          -pend, dif, GRADIENTE_MANUAL)
        L("manual: de noche la temperatura cae con la altura MUCHO menos que de día.")
        L("Aplicar 0,6 °C/100 m a las mínimas sobreestima el frescor del punto alto")
        L("en un %.0f %%.", 100 * dif / GRADIENTE_MANUAL)
    else:
        L("El coeficiente medido (%.2f °C/100 m) es %.2f °C/100 m MAYOR que el %.2f de manual.",
          -pend, -dif, GRADIENTE_MANUAL)
    L("=" * 78)
    L("Escrito: %s", DATOS / "gradiente_nocturno.json")
    L("Escrito: %s", DATOS / "pares_estaciones.csv")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log.exception("Error en el análisis del gradiente")
        sys.exit(1)
