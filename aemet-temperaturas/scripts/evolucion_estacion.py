#!/usr/bin/env python3
"""
Evolución temporal de una estación AEMET concreta.

Uso (workflow_dispatch):
    --buscar "MOSQUERUELA"     # busca por nombre (case-insensitive, parcial)
    --buscar "8486X"           # o por indicativo exacto

Outputs en analisis/estaciones/<indicativo>_<NOMBRE>/:
- tmin_verano_evolucion.png
- tmax_verano_evolucion.png
- noches_tropicales_evolucion.png
- climate_stripes_tmin.png
- boxplot_tmin_verano.png
- resumen.txt
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATOS = ROOT / "datos"
SALIDA_BASE = ROOT / "analisis" / "estaciones"
SALIDA_BASE.mkdir(parents=True, exist_ok=True)

UMBRAL_TROPICAL = 20.0
UMBRAL_ECUATORIAL = 25.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("evolucion")


def cargar_estaciones() -> pd.DataFrame:
    df = pd.read_csv(DATOS / "estaciones.csv", dtype=str)
    df["altitud_m"] = pd.to_numeric(df["altitud"], errors="coerce")
    return df


def cargar_diarios_de(indicativo: str) -> pd.DataFrame:
    """Carga TODOS los registros de UNA estación a lo largo de los años."""
    archivos = sorted(DATOS.glob("diarios_[0-9]*.csv"))
    rolling = DATOS / "diarios_estaciones.csv"
    if rolling.exists():
        archivos.append(rolling)

    dfs = []
    for f in archivos:
        d = pd.read_csv(f, dtype={"indicativo": str})
        d = d[d["indicativo"] == indicativo]
        if not d.empty:
            dfs.append(d)
    if not dfs:
        return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha"]).drop_duplicates(subset=["fecha"], keep="last")
    df = df.sort_values("fecha")
    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    for c in ("tmin", "tmax", "tmed"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def buscar_estacion(estaciones: pd.DataFrame, query: str) -> pd.Series | None:
    """Busca por indicativo exacto o nombre parcial (case-insensitive).
    Si hay >1 resultados, muestra opciones y aborta para que el usuario refine.
    """
    q = query.strip().upper()
    # Match por indicativo exacto
    exact = estaciones[estaciones["indicativo"].str.upper() == q]
    if len(exact) == 1:
        return exact.iloc[0]
    # Match por nombre parcial
    candidatos = estaciones[estaciones["nombre"].str.upper().str.contains(
        re.escape(q), na=False)]
    if len(candidatos) == 0:
        log.error("No se encontró ninguna estación que contenga '%s'", query)
        return None
    if len(candidatos) == 1:
        return candidatos.iloc[0]
    log.error("Hay %d estaciones que coinciden con '%s'. Concreta más:",
              len(candidatos), query)
    for _, r in candidatos.head(30).iterrows():
        log.error("  %s  %-40s  %s  %sm",
                  r["indicativo"], r["nombre"][:40],
                  r["provincia"], r.get("altitud", ""))
    return None


def slugify(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", s)
    return s.strip("_")[:50]


def slope_lineal(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = ~(np.isnan(x) | np.isnan(y))
    if mask.sum() < 3:
        return np.nan, np.nan
    slope, intercept = np.polyfit(x[mask], y[mask], 1)
    return float(slope), float(intercept)


def analizar_estacion(query: str) -> int:
    estaciones = cargar_estaciones()
    est = buscar_estacion(estaciones, query)
    if est is None:
        return 2

    ind = est["indicativo"]
    nombre = est["nombre"]
    prov = est["provincia"]
    alt = est.get("altitud", "")
    log.info("=" * 64)
    log.info("ESTACIÓN: %s — %s (%s, %s m)", ind, nombre, prov, alt)
    log.info("=" * 64)

    diarios = cargar_diarios_de(ind)
    if diarios.empty:
        log.error("No hay datos diarios para esta estación.")
        return 3
    log.info("Días con datos: %d  (%s → %s)",
             len(diarios),
             diarios["fecha"].min().date(),
             diarios["fecha"].max().date())

    # Resumen anual de verano (jun-ago)
    verano = diarios[diarios["mes"].isin([6, 7, 8])].copy()
    anual = (verano.groupby("anio")
                   .agg(tmin_media=("tmin", "mean"),
                        tmax_media=("tmax", "mean"),
                        tmin_min=("tmin", "min"),
                        tmax_max=("tmax", "max"),
                        n_trop=("tmin", lambda s: int((s > UMBRAL_TROPICAL).sum())),
                        n_ecua=("tmin", lambda s: int((s > UMBRAL_ECUATORIAL).sum())),
                        n_dias=("tmin", lambda s: int(s.notna().sum())))
                   .reset_index())
    # Filtramos años con muy pocos datos
    anual = anual[anual["n_dias"] >= 30]
    log.info("Veranos con suficientes datos: %d (%s-%s)",
             len(anual), anual["anio"].min(), anual["anio"].max())

    # Tendencias
    s_tmin, i_tmin = slope_lineal(anual["anio"].values, anual["tmin_media"].values)
    s_tmax, i_tmax = slope_lineal(anual["anio"].values, anual["tmax_media"].values)
    s_trop, i_trop = slope_lineal(anual["anio"].values, anual["n_trop"].values)

    out_dir = SALIDA_BASE / f"{ind}_{slugify(nombre)}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ============ Gráfico 1: Evolución Tmin de verano ============
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(anual["anio"], anual["tmin_media"], "o-", color="#1f4e7a",
            linewidth=2, markersize=8, label="Tmin media de verano")
    # Línea de tendencia
    if not np.isnan(s_tmin):
        xs = np.array([anual["anio"].min(), anual["anio"].max()])
        ax.plot(xs, i_tmin + s_tmin * xs, "--", color="darkred", alpha=0.7,
                label=f"Tendencia: {s_tmin:+.3f} °C/año")
    ax.axhline(UMBRAL_TROPICAL, color="red", linestyle=":", alpha=0.5,
               label=f"Umbral noche tropical ({UMBRAL_TROPICAL}°C)")
    ax.set_xlabel("Año")
    ax.set_ylabel("Tmin media de verano (°C)")
    ax.set_title(f"Evolución Tmin de verano — {nombre} ({prov}, {alt}m)\n"
                 f"Estación AEMET {ind}", fontsize=11)
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "tmin_verano_evolucion.png", dpi=130, bbox_inches="tight")
    plt.close()

    # ============ Gráfico 2: Evolución Tmax de verano ============
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(anual["anio"], anual["tmax_media"], "o-", color="#a83232",
            linewidth=2, markersize=8, label="Tmax media de verano")
    if not np.isnan(s_tmax):
        xs = np.array([anual["anio"].min(), anual["anio"].max()])
        ax.plot(xs, i_tmax + s_tmax * xs, "--", color="navy", alpha=0.7,
                label=f"Tendencia: {s_tmax:+.3f} °C/año")
    ax.set_xlabel("Año")
    ax.set_ylabel("Tmax media de verano (°C)")
    ax.set_title(f"Evolución Tmax de verano — {nombre} ({prov}, {alt}m)\n"
                 f"Estación AEMET {ind}", fontsize=11)
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "tmax_verano_evolucion.png", dpi=130, bbox_inches="tight")
    plt.close()

    # ============ Gráfico 3: Noches tropicales / ecuatoriales por año ============
    fig, ax = plt.subplots(figsize=(11, 6))
    x = anual["anio"].values
    ax.bar(x, anual["n_trop"], color="orange", alpha=0.85,
           label="Noches tropicales (>20°C)")
    ax.bar(x, anual["n_ecua"], color="darkred", alpha=0.9,
           label="Noches ecuatoriales (>25°C)")
    ax.set_xlabel("Año")
    ax.set_ylabel("Número de noches en verano (jun-ago)")
    ax.set_title(f"Noches calurosas en verano — {nombre} ({prov}, {alt}m)\n"
                 f"De un máximo posible de 92 noches", fontsize=11)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "noches_tropicales_evolucion.png", dpi=130, bbox_inches="tight")
    plt.close()

    # ============ Gráfico 4: Climate stripes de Tmin verano ============
    # Una franja por año, coloreada por la Tmin media de verano
    fig, ax = plt.subplots(figsize=(11, 3.5))
    valores = anual["tmin_media"].values
    vmin = np.nanmin(valores) - 0.5
    vmax = np.nanmax(valores) + 0.5
    norm = plt.Normalize(vmin=vmin, vmax=vmax)
    for i, (anio, v) in enumerate(zip(anual["anio"], valores)):
        ax.axvspan(i - 0.5, i + 0.5, color=plt.cm.RdBu_r(norm(v)))
        ax.text(i, 0.5, str(int(anio)), rotation=90, ha="center", va="center",
                fontsize=9, color="white", fontweight="bold")
    ax.set_xlim(-0.5, len(anual) - 0.5)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_title(f"Climate stripes — Tmin media verano — {nombre} ({prov}, {alt}m)\n"
                 f"Azul = veranos frescos, Rojo = veranos cálidos", fontsize=11)
    plt.tight_layout()
    plt.savefig(out_dir / "climate_stripes_tmin.png", dpi=130, bbox_inches="tight")
    plt.close()

    # ============ Gráfico 5: Boxplot de Tmin de verano por año ============
    fig, ax = plt.subplots(figsize=(11, 6))
    datos_box = [verano[verano["anio"] == a]["tmin"].dropna().values
                 for a in anual["anio"]]
    bp = ax.boxplot(datos_box, tick_labels=anual["anio"].astype(str), patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor("#a8c5e6")
        patch.set_edgecolor("navy")
    ax.axhline(UMBRAL_TROPICAL, color="red", linestyle="--", alpha=0.6,
               label=f"Umbral noche tropical ({UMBRAL_TROPICAL}°C)")
    ax.set_xlabel("Año")
    ax.set_ylabel("Tmin (°C) — distribución de todas las noches del verano")
    ax.set_title(f"Distribución de Tmin de verano — {nombre} ({prov}, {alt}m)",
                 fontsize=11)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "boxplot_tmin_verano.png", dpi=130, bbox_inches="tight")
    plt.close()

    # ============ Resumen narrativo ============
    resumen = []
    resumen.append(f"ESTACIÓN: {ind} — {nombre}")
    resumen.append(f"Provincia: {prov}    Altitud: {alt} m")
    resumen.append(f"Coordenadas: {est.get('latitud','')} {est.get('longitud','')}")
    resumen.append("")
    resumen.append(f"Periodo analizado: {int(anual['anio'].min())} → {int(anual['anio'].max())}")
    resumen.append(f"Veranos completos: {len(anual)}")
    resumen.append("")
    resumen.append("TENDENCIAS DE VERANO (junio-agosto)")
    resumen.append("-" * 40)
    resumen.append(f"  Tmin: {s_tmin:+.3f} °C/año "
                   f"({s_tmin * (anual['anio'].max() - anual['anio'].min()):+.2f} °C en el periodo)")
    resumen.append(f"  Tmax: {s_tmax:+.3f} °C/año "
                   f"({s_tmax * (anual['anio'].max() - anual['anio'].min()):+.2f} °C en el periodo)")
    resumen.append(f"  Noches tropicales: {s_trop:+.2f} /año")
    resumen.append("")
    resumen.append("TABLA AÑO POR AÑO")
    resumen.append("-" * 60)
    resumen.append(f"{'Año':>4}  {'Tmin med':>8}  {'Tmax med':>8}  "
                   f"{'N.trop':>6}  {'N.ecuat':>7}  {'N días':>6}")
    for _, r in anual.iterrows():
        resumen.append(
            f"{int(r['anio']):>4}  {r['tmin_media']:>8.2f}  "
            f"{r['tmax_media']:>8.2f}  {int(r['n_trop']):>6d}  "
            f"{int(r['n_ecua']):>7d}  {int(r['n_dias']):>6d}"
        )

    texto = "\n".join(resumen)
    (out_dir / "resumen.txt").write_text(texto, encoding="utf-8")
    log.info("\n%s", texto)
    log.info("=" * 64)
    log.info("Outputs en: %s/", out_dir.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--buscar", required=True,
                        help="Nombre (parcial) o indicativo de la estación")
    args = parser.parse_args()
    sys.exit(analizar_estacion(args.buscar))
