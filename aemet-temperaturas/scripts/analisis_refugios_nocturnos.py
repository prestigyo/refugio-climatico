#!/usr/bin/env python3
"""
Análisis de refugios climáticos NOCTURNOS de verano.

¿Dónde se duerme "tapadito" en verano? Identifica estaciones con:
- Tmin de verano (jun-ago) baja respecto a su geografía
- Tendencia de Tmin estable o negativa
- Pocas "noches tropicales" (Tmin > 20°C) y "ecuatoriales" (Tmin > 25°C)

Outputs en analisis/:
- refugios_nocturnos_ranking.csv
- refugios_nocturnos_mapa.png
- refugios_nocturnos_top20.png
- noches_tropicales_mapa.png
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATOS = ROOT / "datos"
SALIDA = ROOT / "analisis"
SALIDA.mkdir(exist_ok=True)

UMBRAL_NOCHE_TROPICAL = 20.0      # OMS / meteorología clásica
UMBRAL_NOCHE_ECUATORIAL = 25.0
MIN_ANIOS = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nocturno")


def dms_a_decimal(s):
    if not isinstance(s, str):
        return np.nan
    s = s.strip().upper()
    if not s:
        return np.nan
    hemi = s[-1]
    if hemi not in "NSEW":
        try:
            return float(s)
        except ValueError:
            return np.nan
    nums = s[:-1]
    if len(nums) < 5:
        return np.nan
    try:
        secs = int(nums[-2:])
        mins = int(nums[-4:-2])
        degs = int(nums[:-4])
        dec = degs + mins / 60 + secs / 3600
        return -dec if hemi in "SW" else dec
    except (ValueError, IndexError):
        return np.nan


def cargar_estaciones() -> pd.DataFrame:
    path = DATOS / "estaciones.csv"
    if not path.exists():
        log.error("Falta %s", path)
        sys.exit(1)
    df = pd.read_csv(path, dtype=str)
    df["lat"] = df["latitud"].apply(dms_a_decimal)
    df["lon"] = df["longitud"].apply(dms_a_decimal)
    df["altitud_m"] = pd.to_numeric(df["altitud"], errors="coerce")
    return df[["indicativo", "nombre", "provincia", "lat", "lon", "altitud_m"]]


def cargar_diarios() -> pd.DataFrame:
    archivos = sorted(DATOS.glob("diarios_[0-9]*.csv"))
    rolling = DATOS / "diarios_estaciones.csv"
    if rolling.exists():
        archivos.append(rolling)
    if not archivos:
        log.error("No hay archivos diarios.")
        sys.exit(1)
    log.info("Cargando %d archivos diarios", len(archivos))
    dfs = []
    for f in archivos:
        d = pd.read_csv(f, dtype={"indicativo": str})
        dfs.append(d)
    df = pd.concat(dfs, ignore_index=True)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha", "indicativo"])
    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    df["tmin"] = pd.to_numeric(df["tmin"], errors="coerce")
    df = df.drop_duplicates(subset=["fecha", "indicativo"], keep="last")
    log.info("Tras dedup: %d filas, %d estaciones, %d-%d",
             len(df), df["indicativo"].nunique(),
             int(df["anio"].min()), int(df["anio"].max()))
    return df


def slope_lineal(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = ~(np.isnan(x) | np.isnan(y))
    if mask.sum() < 3:
        return np.nan
    return float(np.polyfit(x[mask], y[mask], 1)[0])


def stats_estacion_anio(g: pd.DataFrame) -> pd.Series:
    """Para estación-año en verano: tmin media + conteo noches tropicales/ecuatoriales."""
    tmin = g["tmin"].dropna()
    if len(tmin) < 30:  # al menos 30 días con dato en jun-ago
        return pd.Series({"tmin": np.nan, "n_trop": np.nan,
                          "n_ecua": np.nan, "n_dias": len(tmin)})
    return pd.Series({
        "tmin": tmin.mean(),
        "n_trop": int((tmin > UMBRAL_NOCHE_TROPICAL).sum()),
        "n_ecua": int((tmin > UMBRAL_NOCHE_ECUATORIAL).sum()),
        "n_dias": len(tmin),
    })


def agregar_estacion(g: pd.DataFrame) -> pd.Series:
    """Por estación: medias multianuales + tendencia."""
    g = g.dropna(subset=["tmin"])
    if len(g) < MIN_ANIOS:
        return pd.Series({
            "tmin_media_verano": np.nan,
            "tmin_tendencia": np.nan,
            "noches_trop_anio": np.nan,
            "noches_ecua_anio": np.nan,
            "n_anios": len(g),
        })
    return pd.Series({
        "tmin_media_verano": g["tmin"].mean(),
        "tmin_tendencia": slope_lineal(g["anio"].values, g["tmin"].values),
        "noches_trop_anio": g["n_trop"].mean(),
        "noches_ecua_anio": g["n_ecua"].mean(),
        "n_anios": len(g),
    })


def reg_multivariada(X, y):
    Xm = np.column_stack([np.ones(len(X)), X])
    coefs, *_ = np.linalg.lstsq(Xm, y, rcond=None)
    return coefs, Xm @ coefs


# ---------------------------------------------------------------------------
# NOCHES POR AÑO — el año natural entero, sin medias y sin ventana astronómica
# ---------------------------------------------------------------------------
# El resto de este script mira junio-agosto y publica medias de diez veranos.
# Las dos cosas ocultan datos:
#
#   1. La ventana. El 19,4 % de todas las noches tropicales del histórico cae
#      FUERA de junio-agosto y se descartaba antes de contar. Septiembre (13,9 %
#      del total) tiene MÁS noches tropicales que junio (12,1 %). En Canarias la
#      ventana astronómica no captura ni la mitad: Hierro Aeropuerto sale con 83
#      noches/año contando jun-ago y tiene 170 contando el año; en 2023 tuvo 204,
#      del 3 de enero al 20 de diciembre. El verano TÉRMICO ya lo calcula
#      analisis_estaciones_termicas.py y en Las Palmas va del 30 de junio al 15
#      de noviembre: 139 días. El calendario astronómico no describe esto.
#      (Comprobado: la ventana no se está DESPLAZANDO de forma detectable —las
#      tendencias del reparto mensual salen con R² de 0,01 a 0,11 en nueve años,
#      que es ruido—. El problema no es una deriva futura: es que ya está fuera.)
#
#   2. La media. Promediar diez veranos reparte el calor de agosto entre las
#      noches frescas de junio y suaviza los veranos malos con los buenos. El
#      salto entre la mínima media y el percentil 95 es de 4,3 °C: 367 estaciones
#      tienen un P95 por encima de 20 °C publicando una media por debajo.
#
# Estas dos tablas son la alternativa: una fila por estación y AÑO NATURAL, y un
# resumen por estación con peor año, racha y percentiles en vez de promedios.
# No tocan refugios_nocturnos_ranking.csv, del que vive toda la web.
MIN_DIAS_ANIO = 300     # un año natural "casi completo"


def racha_maxima(fechas, tmins) -> int:
    """Noches tropicales consecutivas más largas, exigiendo días contiguos.

    Sin comprobar la fecha, un hueco en la serie se cuenta como continuidad: en
    San Sebastián de la Gomera daba 153 noches seguidas saltando por encima de
    los días sin dato, cuando la racha real contigua es de 148. Una racha que
    atraviesa un hueco es una racha inventada, así que el hueco la rompe.
    """
    mejor = actual = 0
    prev = None
    for fecha, tmin in zip(fechas, tmins):
        seguida = prev is not None and (fecha - prev).days == 1
        actual = (actual + 1 if seguida else 1) if tmin > UMBRAL_NOCHE_TROPICAL else 0
        mejor = max(mejor, actual)
        prev = fecha
    return mejor


def noches_por_anio(diarios: pd.DataFrame, estaciones: pd.DataFrame) -> pd.DataFrame:
    """Una fila por estación y año natural. Cuenta el año entero, no el verano."""
    d = diarios.dropna(subset=["tmin"]).copy()
    filas = []
    for (ind, anio), g in d.groupby(["indicativo", "anio"]):
        if len(g) < MIN_DIAS_ANIO:
            continue
        g = g.sort_values("fecha")
        trop = g["tmin"] > UMBRAL_NOCHE_TROPICAL
        t = g[trop]
        i_frio, i_calido = g["tmin"].idxmin(), g["tmin"].idxmax()
        filas.append({
            "indicativo": ind, "anio": int(anio), "dias_con_dato": len(g),
            "noches_trop": int(trop.sum()),
            "noches_trop_jja": int((trop & g["mes"].isin([6, 7, 8])).sum()),
            "noches_ecua": int((g["tmin"] > UMBRAL_NOCHE_ECUATORIAL).sum()),
            "noches_sobre_22": int((g["tmin"] > 22).sum()),
            "racha_max": racha_maxima(g["fecha"].tolist(), g["tmin"].tolist()),
            "tmin_minima": round(float(g["tmin"].min()), 1),
            "tmin_minima_fecha": g.loc[i_frio, "fecha"].date().isoformat(),
            "tmin_maxima": round(float(g["tmin"].max()), 1),
            "tmin_maxima_fecha": g.loc[i_calido, "fecha"].date().isoformat(),
            "tmin_p95": round(float(g["tmin"].quantile(0.95)), 1),
            "primera_trop": t["fecha"].min().date().isoformat() if len(t) else "",
            "ultima_trop": t["fecha"].max().date().isoformat() if len(t) else "",
        })
    out = pd.DataFrame(filas)
    if out.empty:
        return out
    return out.merge(estaciones[["indicativo", "nombre", "provincia", "altitud_m"]],
                     on="indicativo", how="left")


def racha_historica(diarios: pd.DataFrame) -> dict:
    """Racha más larga de noches tropicales de toda la serie, por estación.

    La de noches_por_anio.csv se corta el 31 de diciembre, que es una frontera
    del calendario y no del clima: en Canarias las rachas cruzan el fin de año y
    contarlas por año natural las parte por la mitad. Aquí se recorre la serie
    entera. Un hueco sin dato rompe la racha (no se rellena nada).
    """
    d = diarios.dropna(subset=["tmin"]).sort_values(["indicativo", "fecha"])
    return {ind: racha_maxima(g["fecha"].tolist(), g["tmin"].tolist())
            for ind, g in d.groupby("indicativo")}


def resumen_sin_medias(por_anio: pd.DataFrame, rachas: dict) -> pd.DataFrame:
    """Resumen por estación con extremos y percentiles, no con promedios.

    La única cifra promediada que se conserva es `noches_trop_anio_medio`, y va
    ahí solo para poder comparar con lo que hoy publica la web (que es la media
    de jun-ago). Todo lo demás son datos puntuales.
    """
    filas = []
    for ind, g in por_anio.groupby("indicativo"):
        if len(g) < MIN_ANIOS:
            continue
        peor = g.loc[g["noches_trop"].idxmax()]
        filas.append({
            "indicativo": ind, "nombre": peor["nombre"], "provincia": peor["provincia"],
            "altitud_m": peor["altitud_m"], "anios": len(g),
            "noches_trop_peor_anio": int(g["noches_trop"].max()),
            "peor_anio": int(peor["anio"]),
            "noches_trop_mejor_anio": int(g["noches_trop"].min()),
            "noches_trop_ultimo_anio": int(g.sort_values("anio").iloc[-1]["noches_trop"]),
            "noches_trop_anio_medio": round(g["noches_trop"].mean(), 1),
            # De la serie continua, no del máximo por año natural.
            "racha_max_historica": int(rachas.get(ind, g["racha_max"].max())),
            "racha_max_en_un_anio": int(g["racha_max"].max()),
            "noches_ecua_peor_anio": int(g["noches_ecua"].max()),
            "tmin_p95": round(g["tmin_p95"].max(), 1),
            "peor_noche": round(g["tmin_maxima"].max(), 1),
            "peor_noche_fecha": g.loc[g["tmin_maxima"].idxmax(), "tmin_maxima_fecha"],
            "noche_mas_fria": round(g["tmin_minima"].min(), 1),
            # Cuánto se pierde por mirar solo jun-ago, en noches/año.
            "noches_fuera_jja_anio": round(
                (g["noches_trop"] - g["noches_trop_jja"]).mean(), 1),
        })
    return pd.DataFrame(filas)


def analizar() -> int:
    log.info("=" * 64)
    log.info("REFUGIOS NOCTURNOS DE VERANO - ¿dónde se duerme tapadito?")
    log.info("=" * 64)

    estaciones = cargar_estaciones()
    log.info("Estaciones con metadatos: %d", len(estaciones))

    diarios = cargar_diarios()

    log.info("[0/4] Noches por AÑO NATURAL (sin ventana de verano, sin medias)...")
    por_anio = noches_por_anio(diarios, estaciones)
    if not por_anio.empty:
        cols_a = ["indicativo", "nombre", "provincia", "altitud_m", "anio",
                  "dias_con_dato", "noches_trop", "noches_trop_jja", "noches_ecua",
                  "noches_sobre_22", "racha_max", "tmin_minima", "tmin_minima_fecha",
                  "tmin_maxima", "tmin_maxima_fecha", "tmin_p95",
                  "primera_trop", "ultima_trop"]
        por_anio[cols_a].sort_values(["indicativo", "anio"]).to_csv(
            SALIDA / "noches_por_anio.csv", index=False)
        resumen = resumen_sin_medias(por_anio, racha_historica(diarios))
        resumen.sort_values("noches_trop_peor_anio").to_csv(
            SALIDA / "noches_por_estacion.csv", index=False)
        fuera = por_anio["noches_trop"].sum() - por_anio["noches_trop_jja"].sum()
        total = max(int(por_anio["noches_trop"].sum()), 1)
        log.info("  noches_por_anio.csv: %d pares estacion-anio", len(por_anio))
        log.info("  noches_por_estacion.csv: %d estaciones", len(resumen))
        log.info("  noches tropicales fuera de jun-ago: %d de %d (%.1f%%)",
                 fuera, total, 100 * fuera / total)

    verano = diarios[diarios["mes"].isin([6, 7, 8])].copy()

    log.info("[1/4] Calculando stats nocturnas por estación-año...")
    sa = (verano.groupby(["indicativo", "anio"])
                .apply(stats_estacion_anio, include_groups=False)
                .reset_index())
    sa = sa.dropna(subset=["tmin"])
    log.info("  Pares estación-año válidos: %d", len(sa))

    log.info("[2/4] Agregando por estación...")
    stats = (sa.groupby("indicativo")
               .apply(agregar_estacion, include_groups=False)
               .reset_index())

    df = stats.merge(estaciones, on="indicativo", how="left")
    apto = df.dropna(subset=["lat", "lon", "altitud_m",
                              "tmin_media_verano", "tmin_tendencia"]).copy()
    apto = apto[apto["n_anios"] >= MIN_ANIOS]
    log.info("  Estaciones aptas: %d", len(apto))

    log.info("[3/4] Modelo geográfico de Tmin de verano...")
    X = apto[["altitud_m", "lat", "lon"]].values
    y = apto["tmin_media_verano"].values
    coefs, preds = reg_multivariada(X, y)
    apto["tmin_esperada"] = preds
    apto["residual"] = apto["tmin_media_verano"] - apto["tmin_esperada"]
    log.info("  tmin ~ %.2f + %.4f·alt + %.3f·lat + %.3f·lon",
             coefs[0], coefs[1], coefs[2], coefs[3])

    log.info("[4/4] Score compuesto...")
    for col, z in [("residual", "z_residual"),
                   ("tmin_tendencia", "z_tendencia"),
                   ("noches_trop_anio", "z_noches_trop")]:
        apto[z] = (apto[col] - apto[col].mean()) / apto[col].std()
    apto["score_refugio_noche"] = (apto["z_residual"]
                                    + apto["z_tendencia"]
                                    + apto["z_noches_trop"])

    ranking = apto.sort_values("score_refugio_noche").reset_index(drop=True)
    ranking["rank"] = ranking.index + 1

    cols = ["rank", "indicativo", "nombre", "provincia", "altitud_m", "lat", "lon",
            "n_anios", "tmin_media_verano", "noches_trop_anio", "noches_ecua_anio",
            "tmin_tendencia", "tmin_esperada", "residual", "score_refugio_noche"]
    ranking[cols].to_csv(SALIDA / "refugios_nocturnos_ranking.csv",
                         index=False, float_format="%.3f")
    log.info("  Guardado refugios_nocturnos_ranking.csv (%d filas)", len(ranking))

    # ============ Visualizaciones ============
    log.info("Generando mapas y gráficos...")
    top20 = ranking.head(20)

    # Mapa de refugios nocturnos
    fig, ax = plt.subplots(figsize=(13, 9))
    norm = plt.Normalize(
        vmin=ranking["score_refugio_noche"].quantile(0.05),
        vmax=ranking["score_refugio_noche"].quantile(0.95),
    )
    sc = ax.scatter(ranking["lon"], ranking["lat"],
                    c=ranking["score_refugio_noche"], cmap="RdYlGn_r",
                    norm=norm, s=38, alpha=0.85,
                    edgecolor="black", linewidth=0.3)
    cb = plt.colorbar(sc, ax=ax, shrink=0.75)
    cb.set_label("Score refugio nocturno (verde = mejor para dormir tapadito)")
    for _, r in top20.iterrows():
        ax.annotate(str(int(r["rank"])), (r["lon"], r["lat"]),
                    fontsize=9, fontweight="bold", color="darkgreen",
                    xytext=(4, 4), textcoords="offset points")
    ax.set_title("Refugios climáticos NOCTURNOS\n"
                 "¿Dónde se duerme tapadito en verano en España?", fontsize=12)
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    ax.grid(alpha=0.3)
    ax.set_aspect(1.3)
    plt.tight_layout()
    plt.savefig(SALIDA / "refugios_nocturnos_mapa.png", dpi=130, bbox_inches="tight")
    plt.close()

    # Mapa de noches tropicales
    fig, ax = plt.subplots(figsize=(13, 9))
    valores = ranking["noches_trop_anio"].clip(upper=80)
    sc = ax.scatter(ranking["lon"], ranking["lat"], c=valores,
                    cmap="hot_r", vmin=0, vmax=80,
                    s=38, alpha=0.85, edgecolor="black", linewidth=0.3)
    cb = plt.colorbar(sc, ax=ax, shrink=0.75)
    cb.set_label("Noches tropicales al año (Tmin > 20°C en jun-ago, max 92)")
    ax.set_title("Noches tropicales al año en España\n"
                 "(noches en que no refresca lo suficiente para dormir bien)",
                 fontsize=12)
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    ax.grid(alpha=0.3)
    ax.set_aspect(1.3)
    plt.tight_layout()
    plt.savefig(SALIDA / "noches_tropicales_mapa.png", dpi=130, bbox_inches="tight")
    plt.close()

    # Top 20 barras (con Tmin + noches tropicales en la etiqueta)
    fig, ax = plt.subplots(figsize=(13, 9))
    ax.barh(range(len(top20)), -top20["score_refugio_noche"].values,
            color="#1f4e7a", alpha=0.88, edgecolor="navy")
    ax.set_yticks(range(len(top20)))
    labels = [
        f"{int(r['rank']):>2}. {r['nombre'][:26]:<26} "
        f"({r['provincia'][:11]:<11} {int(r['altitud_m']):>4}m) "
        f"Tmin {r['tmin_media_verano']:>4.1f}°C  trop/año {r['noches_trop_anio']:>4.1f}"
        for _, r in top20.iterrows()
    ]
    ax.set_yticklabels(labels, fontsize=8, family="monospace")
    ax.invert_yaxis()
    ax.set_xlabel("Magnitud refugio nocturno (z-score combinado, mayor = mejor)")
    ax.set_title("Top 20 lugares donde se duerme tapadito en verano")
    ax.grid(axis="x", alpha=0.3)
    plt.tight_layout()
    plt.savefig(SALIDA / "refugios_nocturnos_top20.png", dpi=130, bbox_inches="tight")
    plt.close()
    log.info("  refugios_nocturnos_mapa.png, noches_tropicales_mapa.png, refugios_nocturnos_top20.png")

    # ============ Consola ============
    log.info("=" * 76)
    log.info("TOP 15 — DONDE SE DUERME TAPADITO EN VERANO")
    log.info("=" * 76)
    log.info("%3s  %-32s %-13s %5s  %6s  %8s  %s",
             "#", "ESTACIÓN", "PROVINCIA", "ALT", "TMIN", "TROP/AÑO", "TEND/AÑO")
    for _, r in ranking.head(15).iterrows():
        log.info("%3d  %-32s %-13s %4.0fm  %5.1f°C  %5.1f n.t.  %+.3f°C",
                 int(r["rank"]), r["nombre"][:32], r["provincia"][:13],
                 r["altitud_m"], r["tmin_media_verano"],
                 r["noches_trop_anio"], r["tmin_tendencia"])

    log.info("=" * 76)
    log.info("BOTTOM 10 — donde es casi imposible dormir sin aire en verano")
    log.info("=" * 76)
    for _, r in ranking.tail(10).iterrows():
        log.info("%3d  %-32s %-13s %4.0fm  %5.1f°C  %5.1f n.t.  %+.3f°C",
                 int(r["rank"]), r["nombre"][:32], r["provincia"][:13],
                 r["altitud_m"], r["tmin_media_verano"],
                 r["noches_trop_anio"], r["tmin_tendencia"])
    log.info("=" * 76)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(analizar())
    except Exception:
        log.exception("Error en el análisis")
        sys.exit(1)
