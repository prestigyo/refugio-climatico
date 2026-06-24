#!/usr/bin/env python3
"""
Genera los datos del calendario de calor: un JSON por provincia con la Tmín y
Tmáx diarias de verano (1 may – 30 sep) de cada estación, en todos los años, +
el recuento de noches tropicales por año. Lo consume el renderer canvas de la
calculadora (docs/index.html) bajo demanda al elegir provincia.

Salida: docs/datos/{slug-provincia}.json
Requiere: pandas. Lee los diarios_*.csv de AEMET.
"""
from pathlib import Path
from datetime import date
import json
import pandas as pd
import generar_calculadora as g   # reutiliza PROVINCIAS, slug, RANKING_CSV, DOCS_DIR

ANIOS = list(range(2017, 2027))
NDIAS = 153  # 1 may – 30 sep

SCRIPT_DIR = Path(__file__).resolve().parent
AEMET_DIR = SCRIPT_DIR.parent
# datos en el repo (CI) o en la carpeta de pruebas local
DATOS_DIR = next((p for p in [AEMET_DIR / "datos",
                              AEMET_DIR.parent / "_resiliencia"]
                  if (p / "diarios_2024.csv").exists()), AEMET_DIR / "datos")
OUT_DIR = g.DOCS_DIR / "datos"


def canon(prov_raw: str) -> str:
    return g.PROVINCIAS.get(str(prov_raw).strip().upper(), g.titular(str(prov_raw)))


def main() -> int:
    # 1) universo de estaciones del calculador + su provincia canónica
    rank = pd.read_csv(g.RANKING_CSV, usecols=["indicativo", "provincia"])
    prov_de = {r.indicativo: canon(r.provincia) for r in rank.itertuples()}
    validos = set(prov_de)

    # 2) cargar diarios (solo verano y solo estaciones del calculador)
    trozos = []
    for a in ANIOS:
        f = DATOS_DIR / f"diarios_{a}.csv"
        if not f.exists():
            continue
        d = pd.read_csv(f, usecols=["fecha", "indicativo", "tmin", "tmax"])
        d = d[d["indicativo"].isin(validos)]
        trozos.append(d)
    df = pd.concat(trozos, ignore_index=True)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha"])
    df = df[df["fecha"].dt.month.between(5, 9)].copy()
    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    df["off"] = df["fecha"].apply(lambda x: (x.date() - date(x.year, 5, 1)).days)
    df = df[(df["off"] >= 0) & (df["off"] < NDIAS)]
    df["prov"] = df["indicativo"].map(prov_de)

    # 3) por estación: matrices tmin/tmax [año][día] + nt por año
    est = {}
    for (ind, anio), grp in df.groupby(["indicativo", "anio"]):
        e = est.setdefault(ind, {"tmin": [[None] * NDIAS for _ in ANIOS],
                                 "tmax": [[None] * NDIAS for _ in ANIOS],
                                 "nt": [0] * len(ANIOS)})
        yi = ANIOS.index(int(anio))
        nt = 0
        for off, mes, tn, tx in zip(grp["off"], grp["mes"], grp["tmin"], grp["tmax"]):
            o = int(off)
            if pd.notna(tn):
                e["tmin"][yi][o] = round(float(tn), 1)
                if 6 <= mes <= 8 and tn >= 20:
                    nt += 1
            if pd.notna(tx):
                e["tmax"][yi][o] = round(float(tx), 1)
        e["nt"][yi] = nt

    # 4) agrupar por provincia y volcar un JSON por provincia
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    porprov = {}
    for ind, e in est.items():
        porprov.setdefault(prov_de[ind], {})[ind] = e
    total = 0
    for prov, estaciones in porprov.items():
        payload = {"anios": ANIOS, "ndias": NDIAS, "est": estaciones}
        (OUT_DIR / f"{g.slug(prov)}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        total += 1
    tam = sum(f.stat().st_size for f in OUT_DIR.glob("*.json")) / 1024 / 1024
    print(f"OK -> {total} JSON en {OUT_DIR} ({tam:.1f} MB en total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
