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


def analizar() -> int:
    log.info("=" * 64)
    log.info("REFUGIOS NOCTURNOS DE VERANO - ¿dónde se duerme tapadito?")
    log.info("=" * 64)

    estaciones = cargar_estaciones()
    log.info("Estaciones con metadatos: %d", len(estaciones))

    diarios = cargar_diarios()
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
