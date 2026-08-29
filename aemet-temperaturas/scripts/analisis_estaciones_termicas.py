#!/usr/bin/env python3
"""
Las estaciones del año según el termómetro, no según el calendario.

¿Empieza el frío el 21 de diciembre? ¿Deja de hacerlo el 20 de marzo? El
calendario astronómico marca los solsticios y equinoccios por la posición del
Sol, pero la temperatura no responde a la vez: la tierra, y sobre todo el mar,
tardan en soltar y en absorber el calor. A ese retraso se le llama DESFASE
ESTACIONAL, y este script lo mide estación por estación con los datos de AEMET.

De paso define las estaciones TÉRMICAS de cada sitio —cuándo empieza y acaba de
verdad su verano y su invierno— usando su propio rango anual como referencia,
que es lo único que permite comparar Burgos con Almería sin que el umbral
elegido decida el resultado.

Hipótesis de partida: el mar tiene mucha más inercia que el interior seco, así
que el litoral debería ir MÁS retrasado respecto al calendario.

Análisis manual. No genera ninguna página web.

Salidas:
  datos/estaciones_termicas.csv     una fila por estación
  datos/estaciones_termicas.json    agregados por altitud, costa y provincia
  resumen por consola

Fuente: AEMET (valores climatológicos diarios).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analisis_refugios_nocturnos as arn  # noqa: E402  (cargadores)
import analisis_gradiente as ag            # noqa: E402  (línea de costa)

ROOT = Path(__file__).resolve().parent.parent
DATOS = ROOT / "datos"
FUENTE = "AEMET"

DIAS = 365                  # el 29 de febrero se descarta: marco fijo de 365
VENTANA = 31                # suavizado circular, ±15 días
MIN_ANIOS = 6               # años completos mínimos por estación
MIN_DIAS_CUBIERTOS = 355    # de los 365 huecos del ciclo anual
MIN_ANIOS_POR_DIA = 3       # observaciones mínimas en cada hueco
DIST_COSTA_KM = 30.0

# Umbrales de estación térmica, en temperatura media diaria. Son absolutos a
# propósito: la primera versión de este script definía el verano como "el 25 %
# de días más cálidos de cada sitio", y eso daba 91 días EN TODAS PARTES — un
# ciclo sinusoidal pasa por construcción una cuarta parte del año por encima de
# su propio percentil 75. Medía la forma de la curva, no el calor.
#
# Con umbral absoluto la duración vuelve a significar algo, y que Sanabria
# tenga cero días de verano térmico no es un fallo: es el dato.
UMBRAL_VERANO = 22.0
UMBRAL_INVIERNO = 6.0

# Referencias astronómicas, en día del año sobre un marco de 365
SOLSTICIO_INVIERNO = 355    # 21 de diciembre
SOLSTICIO_VERANO = 172      # 21 de junio
EQUINOCCIO_PRIMAVERA = 79   # 20 de marzo
EQUINOCCIO_OTONO = 265      # 22 de septiembre

FRANJAS = ((None, 200.0, "<200"), (200.0, 500.0, "200-500"), (500.0, 800.0, "500-800"),
           (800.0, 1200.0, "800-1200"), (1200.0, None, ">1200"))

NORMALIZA_PROV = {"ILLES BALEARS": "BALEARES",
                  "STA. CRUZ DE TENERIFE": "SANTA CRUZ DE TENERIFE"}

# Canarias tiene el océano abierto al lado y un desfase enorme: mete casi un mes
# de retraso extra y arrastra la media del grupo "litoral". Se separa para poder
# comprobar que el efecto del mar se sostiene también en la península.
CANARIAS = {"LAS PALMAS", "SANTA CRUZ DE TENERIFE"}
BALEARES = {"BALEARES"}


def region(prov: str) -> str:
    if prov in CANARIAS:
        return "canarias"
    if prov in BALEARES:
        return "baleares"
    return "peninsula"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("termicas")


# ---------------------------------------------------------------- utilidades

def fecha_de(doy: int) -> str:
    """Día del año (1-365) -> '21 de junio', sobre un año no bisiesto."""
    d = date(2025, 1, 1) + timedelta(days=int(doy) - 1)
    meses = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre")
    return f"{d.day} de {meses[d.month - 1]}"


def desfase(observado: int, astronomico: int) -> int:
    """Diferencia circular con signo, en días. Positivo = el termómetro va DETRÁS."""
    return int((observado - astronomico + DIAS // 2) % DIAS - DIAS // 2)


def suavizar(serie: np.ndarray, ventana: int = VENTANA) -> np.ndarray:
    """Media móvil CIRCULAR: diciembre y enero son vecinos, no extremos."""
    r = ventana // 2
    extendida = np.concatenate([serie[-r:], serie, serie[:r]])
    nucleo = np.ones(ventana) / ventana
    return np.convolve(extendida, nucleo, mode="valid")


def racha_circular(mask: np.ndarray) -> tuple[int, int, int]:
    """Racha contigua más larga de True, dando la vuelta al año.

    Devuelve (inicio, fin, longitud) en días del año 1-365, o (0,0,0)."""
    n = len(mask)
    if mask.all():
        return 1, n, n
    if not mask.any():
        return 0, 0, 0
    doble = np.concatenate([mask, mask])
    mejor = (0, 0)
    i = 0
    while i < 2 * n:
        if doble[i]:
            j = i
            while j < 2 * n and doble[j]:
                j += 1
            if j - i > mejor[1] and i < n:
                mejor = (i, min(j - i, n))
            i = j
        else:
            i += 1
    ini, largo = mejor
    return int(ini % n) + 1, int((ini + largo - 1) % n) + 1, int(largo)


def franja(alt: float) -> str:
    for lo, hi, et in FRANJAS:
        if (lo is None or alt >= lo) and (hi is None or alt < hi):
            return et
    return ">1200"


# ---------------------------------------------------------------- climatología

def ciclos_anuales(df):
    """{indicativo: {'tmed': array(365), 'tmin': ..., 'tmax': ..., 'n': array(365)}}

    Solo con AÑOS COMPLETOS: un año truncado sesgaría el ciclo, porque los días
    que le faltan pesarían menos que el resto.
    """
    dias_por_anio = df.groupby("anio")["fecha"].apply(lambda s: s.dt.date.nunique())
    completos = sorted(a for a, n in dias_por_anio.items() if n >= 365)
    log.info("Años completos usados: %s", ", ".join(str(a) for a in completos))
    d = df[df["anio"].isin(completos)].copy()

    bisiesto = d["fecha"].dt.is_leap_year
    doy = d["fecha"].dt.dayofyear
    d = d[~(bisiesto & (doy == 60))]                      # fuera el 29 de febrero
    bisiesto = d["fecha"].dt.is_leap_year
    doy = d["fecha"].dt.dayofyear
    d["doy"] = doy - (bisiesto & (doy > 60)).astype(int)  # marco fijo de 365

    for col in ("tmed", "tmin", "tmax"):
        d[col] = d[col].astype(float)
    g = d.groupby(["indicativo", "doy"]).agg(
        tmed=("tmed", "mean"), tmin=("tmin", "mean"),
        tmax=("tmax", "mean"), n=("tmed", "count"))

    ciclos = {}
    for (ind, dd), fila in g.iterrows():
        c = ciclos.setdefault(str(ind), {k: np.full(DIAS, np.nan) for k in
                                         ("tmed", "tmin", "tmax", "n")})
        i = int(dd) - 1
        if 0 <= i < DIAS:
            c["tmed"][i] = fila["tmed"]
            c["tmin"][i] = fila["tmin"]
            c["tmax"][i] = fila["tmax"]
            c["n"][i] = fila["n"]
    return ciclos, completos


# ---------------------------------------------------------------- análisis

def analizar(ciclos, meta, idx_costa):
    filas, descartes = [], {}
    for ind, c in ciclos.items():
        cubiertos = int(np.sum(~np.isnan(c["tmed"]) & (np.nan_to_num(c["n"]) >= MIN_ANIOS_POR_DIA)))
        if cubiertos < MIN_DIAS_CUBIERTOS:
            descartes[ind] = "ciclo_anual_incompleto"
            continue
        if ind not in meta:
            descartes[ind] = "sin_metadatos"
            continue
        m = meta[ind]

        curvas, extremos = {}, {}
        for var in ("tmed", "tmin", "tmax"):
            serie = c[var].copy()
            if np.isnan(serie).any():                      # rellenar huecos sueltos
                idx = np.arange(DIAS)
                ok = ~np.isnan(serie)
                if ok.sum() < MIN_DIAS_CUBIERTOS:
                    break
                serie = np.interp(idx, idx[ok], serie[ok], period=DIAS)
            s = suavizar(serie)
            curvas[var] = s
            extremos[var] = (int(np.argmin(s)) + 1, int(np.argmax(s)) + 1)
        if len(curvas) < 3:
            descartes[ind] = "serie_insuficiente"
            continue

        s = curvas["tmed"]
        # Estaciones térmicas por umbral absoluto: duración comparable entre sitios.
        v_ini, v_fin, v_dur = racha_circular(s >= UMBRAL_VERANO)
        i_ini, i_fin, i_dur = racha_circular(s <= UMBRAL_INVIERNO)
        # Y la ventana del cuartil más cálido, que dura ~91 días en todas partes
        # pero cuyas FECHAS sí informan: dice CUÁNDO cae el trimestre cálido.
        p75 = float(np.percentile(s, 75))
        c_ini, c_fin, _ = racha_circular(s > p75)

        dmin_med, dmax_med = extremos["tmed"]
        dmin_min, dmax_min = extremos["tmin"]
        dmin_max, dmax_max = extremos["tmax"]

        dc = ag.distancia_a_costa(m["lat"], m["lon"], idx_costa) if idx_costa else None
        filas.append({
            "indicativo": ind, "nombre": m["nombre"],
            "provincia": NORMALIZA_PROV.get(m["provincia"].strip().upper(),
                                            m["provincia"].strip().upper()),
            "altitud_m": m["altitud_m"], "lat": round(m["lat"], 4), "lon": round(m["lon"], 4),
            "dist_costa_km": round(dc, 1) if dc is not None else "",
            "grupo_costa": "litoral" if (dc is not None and dc <= DIST_COSTA_KM) else "interior",
            "franja_altitud": franja(m["altitud_m"]),
            "region": region(NORMALIZA_PROV.get(m["provincia"].strip().upper(),
                                                m["provincia"].strip().upper())),
            "dia_mas_frio": fecha_de(dmin_med),
            "dia_mas_calido": fecha_de(dmax_med),
            "desfase_invierno_dias": desfase(dmin_med, SOLSTICIO_INVIERNO),
            "desfase_verano_dias": desfase(dmax_med, SOLSTICIO_VERANO),
            "desfase_invierno_tmin": desfase(dmin_min, SOLSTICIO_INVIERNO),
            "desfase_verano_tmin": desfase(dmax_min, SOLSTICIO_VERANO),
            "desfase_invierno_tmax": desfase(dmin_max, SOLSTICIO_INVIERNO),
            "desfase_verano_tmax": desfase(dmax_max, SOLSTICIO_VERANO),
            "verano_termico_ini": fecha_de(v_ini) if v_dur else "",
            "verano_termico_fin": fecha_de(v_fin) if v_dur else "",
            "verano_termico_dias": v_dur,
            "invierno_termico_ini": fecha_de(i_ini) if i_dur else "",
            "invierno_termico_fin": fecha_de(i_fin) if i_dur else "",
            "invierno_termico_dias": i_dur,
            "cuartil_calido_ini": fecha_de(c_ini), "cuartil_calido_fin": fecha_de(c_fin),
            "amplitud_anual_c": round(float(s.max() - s.min()), 2),
            "tmed_min_c": round(float(s.min()), 2), "tmed_max_c": round(float(s.max()), 2),
            "fuente": FUENTE,
        })
    return filas, descartes


def agrega(filas, clave, campos):
    out = {}
    for f in filas:
        out.setdefault(f[clave], []).append(f)
    res = {}
    for k, v in sorted(out.items()):
        r = {"n_estaciones": len(v)}
        for campo in campos:
            xs = [f[campo] for f in v]
            r[campo] = {"media": round(sum(xs) / len(xs), 2), "mediana": round(median(xs), 1)}
        res[k] = r
    return res


COLUMNAS = ["indicativo", "nombre", "provincia", "altitud_m", "lat", "lon",
            "dist_costa_km", "grupo_costa", "franja_altitud", "region",
            "dia_mas_frio", "dia_mas_calido",
            "desfase_invierno_dias", "desfase_verano_dias",
            "desfase_invierno_tmin", "desfase_verano_tmin",
            "desfase_invierno_tmax", "desfase_verano_tmax",
            "verano_termico_ini", "verano_termico_fin", "verano_termico_dias",
            "invierno_termico_ini", "invierno_termico_fin", "invierno_termico_dias",
            "cuartil_calido_ini", "cuartil_calido_fin",
            "amplitud_anual_c", "tmed_min_c", "tmed_max_c", "fuente"]

CAMPOS_AGREGADOS = ["desfase_invierno_dias", "desfase_verano_dias",
                    "verano_termico_dias", "invierno_termico_dias", "amplitud_anual_c"]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Estaciones térmicas y desfase estacional (Fuente: AEMET)")
    ap.add_argument("--top", type=int, default=12, help="cuántas estaciones listar")
    args = ap.parse_args()

    est = arn.cargar_estaciones()
    meta = {}
    for r in est.itertuples():
        if r.lat != r.lat or r.lon != r.lon or r.altitud_m != r.altitud_m:
            continue
        meta[str(r.indicativo)] = {"nombre": r.nombre, "provincia": r.provincia,
                                   "lat": float(r.lat), "lon": float(r.lon),
                                   "altitud_m": float(r.altitud_m)}

    df = arn.cargar_diarios()
    ciclos, anios = ciclos_anuales(df)
    pts, metodo_costa = ag.puntos_de_costa()
    idx_costa = ag.indexa_costa(pts) if pts else None

    filas, descartes = analizar(ciclos, meta, idx_costa)
    filas.sort(key=lambda f: -f["desfase_verano_dias"])

    motivos = {}
    for m in descartes.values():
        motivos[m] = motivos.get(m, 0) + 1

    di = [f["desfase_invierno_dias"] for f in filas]
    dv = [f["desfase_verano_dias"] for f in filas]

    resumen = {
        "generado": date.today().isoformat(),
        "fuente": FUENTE,
        "metodo": (f"ciclo anual medio por día del año sobre {len(anios)} años completos "
                   f"({anios[0]}-{anios[-1]}), suavizado circular de {VENTANA} días; "
                   f"verano térmico = tmed >= {UMBRAL_VERANO:g} °C, invierno térmico = "
                   f"tmed <= {UMBRAL_INVIERNO:g} °C, sobre el ciclo suavizado"),
        "criterios": {
            "anios_completos": anios,
            "dias_marco": DIAS,
            "nota_29_febrero": "descartado, para tener un marco fijo de 365 días",
            "ventana_suavizado": VENTANA,
            "referencias_astronomicas": {
                "solsticio_invierno": "21 de diciembre", "solsticio_verano": "21 de junio",
                "equinoccio_primavera": "20 de marzo", "equinoccio_otono": "22 de septiembre"},
            "signo_desfase": "positivo = el termómetro va DETRÁS del calendario",
            "umbral_verano_c": UMBRAL_VERANO,
            "umbral_invierno_c": UMBRAL_INVIERNO,
            "nota_cuartil": ("cuartil_calido_* marca el trimestre más cálido de cada "
                             "sitio; dura ~91 días en todas partes por construcción, "
                             "así que solo sus FECHAS son informativas, no su duración"),
            "metodo_costa": metodo_costa,
        },
        "estaciones": {"validas": len(filas), "descartadas": len(descartes),
                       "descartes_por_motivo": motivos},
        "global": {
            "desfase_invierno_medio": round(sum(di) / len(di), 2) if di else None,
            "desfase_invierno_mediana": median(di) if di else None,
            "desfase_verano_medio": round(sum(dv) / len(dv), 2) if dv else None,
            "desfase_verano_mediana": median(dv) if dv else None,
            "verano_termico_dias_medio": round(
                sum(f["verano_termico_dias"] for f in filas) / len(filas), 1) if filas else None,
        },
        "por_altitud": agrega(filas, "franja_altitud", CAMPOS_AGREGADOS),
        "por_costa": agrega(filas, "grupo_costa", CAMPOS_AGREGADOS),
        "por_region": agrega(filas, "region", CAMPOS_AGREGADOS),
        "por_costa_peninsula": agrega(
            [f for f in filas if f["region"] == "peninsula"], "grupo_costa", CAMPOS_AGREGADOS),
        "por_provincia": agrega(filas, "provincia", CAMPOS_AGREGADOS),
    }

    DATOS.mkdir(exist_ok=True)
    with open(DATOS / "estaciones_termicas.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        for f in filas:
            w.writerow(f)
    (DATOS / "estaciones_termicas.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------- consola
    L = log.info
    L("=" * 88)
    L("LAS ESTACIONES DEL AÑO SEGÚN EL TERMÓMETRO — Fuente: AEMET")
    L("=" * 88)
    L("Ciclo anual medio de %d años completos (%d-%d), suavizado a %d días.",
      len(anios), anios[0], anios[-1], VENTANA)
    L("Estaciones válidas %d · descartadas %d %s", len(filas), len(descartes),
      dict(motivos) if motivos else "")
    L("-" * 88)
    L("EL DESFASE: cuántos días va el termómetro DETRÁS del calendario")
    L("    día más frío  vs 21 de diciembre .... %+.1f días de media (mediana %+.0f)",
      resumen["global"]["desfase_invierno_medio"], resumen["global"]["desfase_invierno_mediana"])
    L("    día más cálido vs 21 de junio ....... %+.1f días de media (mediana %+.0f)",
      resumen["global"]["desfase_verano_medio"], resumen["global"]["desfase_verano_mediana"])
    L("")
    L("Es decir: el frío de verdad llega hacia el %s y el calor hacia el %s.",
      fecha_de((SOLSTICIO_INVIERNO + round(resumen["global"]["desfase_invierno_medio"])) % DIAS or DIAS),
      fecha_de((SOLSTICIO_VERANO + round(resumen["global"]["desfase_verano_medio"])) % DIAS or DIAS))
    L("-" * 88)
    L("POR PROXIMIDAD AL MAR — la hipótesis: el mar tiene más inercia")
    L("    %-10s %5s %12s %12s %11s %11s", "grupo", "n", "desf.inv", "desf.ver",
      "verano(d)", "amplitud")
    for et in ("litoral", "interior"):
        s = resumen["por_costa"].get(et)
        if s:
            L("    %-10s %5d %+12.1f %+12.1f %11.0f %11.1f", et, s["n_estaciones"],
              s["desfase_invierno_dias"]["media"], s["desfase_verano_dias"]["media"],
              s["verano_termico_dias"]["media"], s["amplitud_anual_c"]["media"])
    L("    -- y solo en la península, para descartar que sea cosa de Canarias --")
    for et in ("litoral", "interior"):
        s2 = resumen["por_costa_peninsula"].get(et)
        if s2:
            L("    %-10s %5d %+12.1f %+12.1f %11.0f %11.1f", et, s2["n_estaciones"],
              s2["desfase_invierno_dias"]["media"], s2["desfase_verano_dias"]["media"],
              s2["verano_termico_dias"]["media"], s2["amplitud_anual_c"]["media"])
    L("")
    L("POR REGIÓN")
    L("    %-10s %5s %12s %12s %11s %11s", "region", "n", "desf.inv", "desf.ver",
      "verano(d)", "amplitud")
    for et in ("peninsula", "baleares", "canarias"):
        s2 = resumen["por_region"].get(et)
        if s2:
            L("    %-10s %5d %+12.1f %+12.1f %11.0f %11.1f", et, s2["n_estaciones"],
              s2["desfase_invierno_dias"]["media"], s2["desfase_verano_dias"]["media"],
              s2["verano_termico_dias"]["media"], s2["amplitud_anual_c"]["media"])
    L("")
    L("POR FRANJA DE ALTITUD")
    L("    %-10s %5s %12s %12s %11s %11s", "franja", "n", "desf.inv", "desf.ver",
      "verano(d)", "amplitud")
    for _, _, et in FRANJAS:
        s = resumen["por_altitud"].get(et)
        if s:
            L("    %-10s %5d %+12.1f %+12.1f %11.0f %11.1f", et, s["n_estaciones"],
              s["desfase_invierno_dias"]["media"], s["desfase_verano_dias"]["media"],
              s["verano_termico_dias"]["media"], s["amplitud_anual_c"]["media"])
    L("-" * 88)
    L("¿LA NOCHE VA A OTRO RITMO QUE EL DÍA?")
    for var, et in (("tmin", "mínimas (la noche)"), ("tmax", "máximas (el día)")):
        vi = [f[f"desfase_invierno_{var}"] for f in filas]
        vv = [f[f"desfase_verano_{var}"] for f in filas]
        L("    %-22s invierno %+6.1f d · verano %+6.1f d", et,
          sum(vi) / len(vi), sum(vv) / len(vv))
    L("-" * 88)
    L("LAS %d MÁS RETRASADAS EN VERANO (su calor máximo llega más tarde)", args.top)
    for f in filas[:args.top]:
        L("    %-28s %-12s %5.0fm  máx el %-16s (%+3d d)  costa %s",
          f["nombre"][:28], f["provincia"][:12], f["altitud_m"], f["dia_mas_calido"],
          f["desfase_verano_dias"], f["dist_costa_km"])
    L("")
    L("LAS %d MÁS ADELANTADAS", args.top)
    for f in filas[-args.top:][::-1]:
        L("    %-28s %-12s %5.0fm  máx el %-16s (%+3d d)  costa %s",
          f["nombre"][:28], f["provincia"][:12], f["altitud_m"], f["dia_mas_calido"],
          f["desfase_verano_dias"], f["dist_costa_km"])
    L("-" * 88)
    vd = sorted(filas, key=lambda f: -f["verano_termico_dias"])
    sin_verano = [f for f in filas if f["verano_termico_dias"] == 0]
    sin_invierno = [f for f in filas if f["invierno_termico_dias"] == 0]
    L("VERANO TÉRMICO (tmed >= %.0f °C) — el más largo", UMBRAL_VERANO)
    for f in vd[:6]:
        L("    %-28s %-12s %5.0fm  %3d días · del %s al %s", f["nombre"][:28],
          f["provincia"][:12], f["altitud_m"], f["verano_termico_dias"],
          f["verano_termico_ini"], f["verano_termico_fin"])
    L("    ...")
    L("    %d estaciones NO alcanzan nunca los %.0f °C de media: no tienen verano térmico.",
      len(sin_verano), UMBRAL_VERANO)
    for f in sorted(sin_verano, key=lambda f: -f["altitud_m"])[:5]:
        L("        %-28s %-12s %5.0fm  (máx del año %.1f °C)", f["nombre"][:28],
          f["provincia"][:12], f["altitud_m"], f["tmed_max_c"])
    L("")
    L("INVIERNO TÉRMICO (tmed <= %.0f °C) — el más largo", UMBRAL_INVIERNO)
    idl = sorted(filas, key=lambda f: -f["invierno_termico_dias"])
    for f in idl[:6]:
        L("    %-28s %-12s %5.0fm  %3d días · del %s al %s", f["nombre"][:28],
          f["provincia"][:12], f["altitud_m"], f["invierno_termico_dias"],
          f["invierno_termico_ini"], f["invierno_termico_fin"])
    L("    %d estaciones no bajan nunca de %.0f °C: no tienen invierno térmico.",
      len(sin_invierno), UMBRAL_INVIERNO)
    L("=" * 88)
    L("Escrito: %s", DATOS / "estaciones_termicas.csv")
    L("Escrito: %s", DATOS / "estaciones_termicas.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log.exception("Error en el análisis de estaciones térmicas")
        sys.exit(1)
