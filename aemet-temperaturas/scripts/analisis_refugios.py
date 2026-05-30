#!/usr/bin/env python3
"""
Análisis de refugios climáticos en la península y Baleares.

Cruza:
- Datos diarios históricos (diarios_YYYY.csv + diarios_estaciones.csv)
- Normales climáticos 1991-2020 (normales_1991_2020.csv)
- Metadatos de estaciones (estaciones.csv)

Para cada estación apta calcula:
- Tmax media de verano (jun-ago) de los últimos años disponibles
- Tendencia (°C/año) de la tmax de verano
- Anomalía respecto al normal 1991-2020
- Residual respecto al modelo geográfico (altitud+latitud+longitud)
- Score compuesto (z_residual + z_tendencia)

Outputs (en analisis/):
- refugios_ranking.csv: ranking de candidatos a refugio
- refugios_mapa.png: mapa de España con todos los puntos
- refugios_top20.png: barra horizontal con los 20 mejores
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("refugios")


def dms_a_decimal(s):
    """Coordenada AEMET '414145N' → grados decimales."""
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
        log.info("  %s: %d filas", f.name, len(d))
    df = pd.concat(dfs, ignore_index=True)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha", "indicativo"])
    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    df["tmax"] = pd.to_numeric(df["tmax"], errors="coerce")
    df = df.drop_duplicates(subset=["fecha", "indicativo"], keep="last")
    log.info("Total tras dedup: %d filas, %d estaciones, %d-%d",
             len(df), df["indicativo"].nunique(),
             int(df["anio"].min()), int(df["anio"].max()))
    return df


def cargar_normales() -> pd.DataFrame:
    path = DATOS / "normales_1991_2020.csv"
    if not path.exists():
        log.error("Falta %s", path)
        sys.exit(1)
    df = pd.read_csv(path, dtype={"indicativo": str})
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce")
    if "tm_max" in df.columns:
        df["tm_max"] = pd.to_numeric(df["tm_max"], errors="coerce")
    df = df[(df["mes"] >= 1) & (df["mes"] <= 12)]
    return df


def slope_lineal(x, y):
    """Pendiente de regresión lineal y~x (None si NaN o <3 puntos)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = ~(np.isnan(x) | np.isnan(y))
    if mask.sum() < 3:
        return np.nan
    return float(np.polyfit(x[mask], y[mask], 1)[0])


def stats_por_estacion(g: pd.DataFrame) -> pd.Series:
    """Para cada estación: tmax_media de verano y tendencia (°C/año)."""
    n = len(g)
    if g["tmax"].notna().sum() < 3:
        return pd.Series({"tmax_media_verano": np.nan,
                          "tmax_tendencia": np.nan,
                          "n_anios": n})
    return pd.Series({
        "tmax_media_verano": g["tmax"].mean(),
        "tmax_tendencia": slope_lineal(g["anio"].values, g["tmax"].values),
        "n_anios": n,
    })


def regresion_multivariada(X, y):
    """OLS sencillo: y = b0 + B·X. Devuelve (coefs, predicciones)."""
    Xm = np.column_stack([np.ones(len(X)), X])
    coefs, *_ = np.linalg.lstsq(Xm, y, rcond=None)
    return coefs, Xm @ coefs


def analizar() -> int:
    log.info("=" * 64)
    log.info("ANÁLISIS DE REFUGIOS CLIMÁTICOS")
    log.info("=" * 64)

    estaciones = cargar_estaciones()
    log.info("Estaciones con metadatos: %d", len(estaciones))

    diarios = cargar_diarios()
    normales = cargar_normales()
    log.info("Normales: %d estaciones con datos 1991-2020",
             normales["indicativo"].nunique())

    # 1) Estadísticas de verano (jun-ago) por estación
    log.info("[1/5] Stats de verano por estación-año...")
    verano = diarios[diarios["mes"].isin([6, 7, 8])].copy()
    log.info("  Filas de verano: %d", len(verano))

    anuales = (verano.groupby(["indicativo", "anio"])
                     .agg(tmax=("tmax", "mean"))
                     .reset_index())
    stats = (anuales.groupby("indicativo")
                    .apply(stats_por_estacion, include_groups=False)
                    .reset_index())

    # 2) Anomalías vs normales
    log.info("[2/5] Anomalías vs normales 1991-2020...")
    normal_verano = (normales[normales["mes"].isin([6, 7, 8])]
                     .groupby("indicativo")["tm_max"].mean()
                     .reset_index()
                     .rename(columns={"tm_max": "tmax_normal_verano"}))
    stats = stats.merge(normal_verano, on="indicativo", how="left")
    stats["tmax_anomalia"] = stats["tmax_media_verano"] - stats["tmax_normal_verano"]

    # 3) Cruce con geografía
    log.info("[3/5] Cruce con geografía...")
    df = stats.merge(estaciones, on="indicativo", how="left")
    apto = df.dropna(subset=["lat", "lon", "altitud_m",
                             "tmax_media_verano", "tmax_tendencia"]).copy()
    apto = apto[apto["n_anios"] >= 5]
    log.info("  Estaciones aptas (>=5 años + geo completa): %d", len(apto))

    # 4) Residual respecto a la geografía
    log.info("[4/5] Modelo geográfico tmax ~ alt + lat + lon...")
    X = apto[["altitud_m", "lat", "lon"]].values
    y = apto["tmax_media_verano"].values
    coefs, preds = regresion_multivariada(X, y)
    apto["tmax_esperada"] = preds
    apto["residual"] = apto["tmax_media_verano"] - apto["tmax_esperada"]
    log.info("  tmax_esperada = %.2f + %.4f·alt + %.3f·lat + %.3f·lon",
             coefs[0], coefs[1], coefs[2], coefs[3])

    # 5) Score compuesto
    log.info("[5/5] Score compuesto y ranking...")
    apto["z_residual"] = (apto["residual"] - apto["residual"].mean()) / apto["residual"].std()
    apto["z_tendencia"] = (apto["tmax_tendencia"] - apto["tmax_tendencia"].mean()) / apto["tmax_tendencia"].std()
    apto["score_refugio"] = apto["z_residual"] + apto["z_tendencia"]

    ranking = apto.sort_values("score_refugio").reset_index(drop=True)
    ranking["rank"] = ranking.index + 1

    cols = ["rank", "indicativo", "nombre", "provincia", "altitud_m",
            "lat", "lon", "n_anios",
            "tmax_media_verano", "tmax_normal_verano", "tmax_anomalia",
            "tmax_tendencia", "tmax_esperada", "residual", "score_refugio"]
    ranking[cols].to_csv(SALIDA / "refugios_ranking.csv",
                         index=False, float_format="%.3f")
    log.info("  Guardado refugios_ranking.csv (%d filas)", len(ranking))

    # Visualizaciones
    log.info("Generando mapas y gráficos...")
    top20 = ranking.head(20)

    # Mapa
    fig, ax = plt.subplots(figsize=(13, 9))
    norm = plt.Normalize(
        vmin=ranking["score_refugio"].quantile(0.05),
        vmax=ranking["score_refugio"].quantile(0.95),
    )
    sc = ax.scatter(ranking["lon"], ranking["lat"],
                    c=ranking["score_refugio"], cmap="RdYlGn_r",
                    norm=norm, s=38, alpha=0.85,
                    edgecolor="black", linewidth=0.3)
    cb = plt.colorbar(sc, ax=ax, shrink=0.75)
    cb.set_label("Score refugio  (verde = mejor refugio)")
    for _, r in top20.iterrows():
        ax.annotate(str(int(r["rank"])), (r["lon"], r["lat"]),
                    fontsize=9, fontweight="bold", color="darkgreen",
                    xytext=(4, 4), textcoords="offset points")
    ax.set_title("Refugios climáticos en la península y Baleares\n"
                 "Estaciones más frescas y estables de lo esperable por su geografía",
                 fontsize=12)
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    ax.grid(alpha=0.3)
    ax.set_aspect(1.3)
    plt.tight_layout()
    plt.savefig(SALIDA / "refugios_mapa.png", dpi=130, bbox_inches="tight")
    plt.close()
    log.info("  refugios_mapa.png")

    # Top 20 horizontal
    fig, ax = plt.subplots(figsize=(11, 9))
    ax.barh(range(len(top20)), -top20["score_refugio"].values,
            color="seagreen", alpha=0.85, edgecolor="darkgreen")
    ax.set_yticks(range(len(top20)))
    labels = [
        f"{int(r['rank']):>2}. {r['nombre'][:28]:<28} "
        f"({r['provincia'][:12]:<12} {int(r['altitud_m']):>4}m)"
        for _, r in top20.iterrows()
    ]
    ax.set_yticklabels(labels, fontsize=9, family="monospace")
    ax.invert_yaxis()
    ax.set_xlabel("Magnitud refugio (z-score combinado, mayor = mejor)")
    ax.set_title("Top 20 candidatos a refugio climático")
    ax.grid(axis="x", alpha=0.3)
    plt.tight_layout()
    plt.savefig(SALIDA / "refugios_top20.png", dpi=130, bbox_inches="tight")
    plt.close()
    log.info("  refugios_top20.png")

    # Resumen por consola
    log.info("=" * 64)
    log.info("TOP 15 REFUGIOS CLIMÁTICOS CANDIDATOS")
    log.info("=" * 64)
    for _, r in ranking.head(15).iterrows():
        log.info("%2d. %-32s (%-14s %4.0fm) "
                 "residual %+.2f°C  tendencia %+.3f°C/año",
                 int(r["rank"]), r["nombre"][:32], r["provincia"][:14],
                 r["altitud_m"], r["residual"], r["tmax_tendencia"])
    log.info("=" * 64)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(analizar())
    except Exception:
        log.exception("Error en el análisis")
        sys.exit(1)
