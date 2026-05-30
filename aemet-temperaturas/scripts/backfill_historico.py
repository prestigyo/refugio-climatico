#!/usr/bin/env python3
"""
Descarga masiva de datos históricos diarios de AEMET OpenData.

Pensado para ejecutarse pocas veces (idealmente una sola). Trocea el rango
de fechas en bloques de 14 días (límite de la API "todasestaciones") y
guarda los resultados en datos/diarios_YYYY.csv (un archivo por año).

Es idempotente: si se vuelve a lanzar, salta los registros ya presentes.

Uso:
    python scripts/backfill_historico.py --desde 2024-01-01 --hasta 2024-12-31
    python scripts/backfill_historico.py --anios 5
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

API_KEY = os.environ.get("AEMET_API_KEY")
if not API_KEY:
    print("ERROR: falta variable de entorno AEMET_API_KEY", file=sys.stderr)
    sys.exit(1)

BASE = "https://opendata.aemet.es/opendata/api"
DIAS_POR_CHUNK = 14
PAUSA_ENTRE_CHUNKS = 2.0
PAUSA_RATELIMIT = 60.0

ROOT = Path(__file__).resolve().parent.parent
DATOS_DIR = ROOT / "datos"
DATOS_DIR.mkdir(exist_ok=True)

HEADERS = [
    "fecha", "indicativo", "nombre", "provincia", "altitud",
    "tmin", "tmax", "tmed", "prec", "horatmin", "horatmax",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("backfill")


def aemet_get(endpoint: str, retries: int = 5):
    """Lectura robusta de OpenData (doble salto: metadatos -> datos)."""
    url = f"{BASE}{endpoint}"
    for intento in range(1, retries + 1):
        try:
            r = requests.get(
                url,
                params={"api_key": API_KEY},
                timeout=30,
                headers={"Accept": "application/json"},
            )
            if r.status_code == 429:
                log.warning("Rate limit, esperando %.0fs", PAUSA_RATELIMIT)
                time.sleep(PAUSA_RATELIMIT)
                continue
            r.raise_for_status()
            meta = r.json()
            estado = meta.get("estado")
            if estado == 404:
                # No hay datos para ese tramo: no es un error, devolvemos vacío
                return []
            if estado != 200:
                raise RuntimeError(
                    f"AEMET estado={estado}: {meta.get('descripcion', '')}"
                )
            r2 = requests.get(meta["datos"], timeout=120)
            r2.raise_for_status()
            if not r2.encoding or r2.encoding.lower() == "iso-8859-1":
                r2.encoding = "iso-8859-15"
            return r2.json()
        except Exception as exc:
            log.warning("Intento %d/%d fallido: %s", intento, retries, exc)
            if intento == retries:
                raise
            time.sleep(5 * intento)


def num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s.lower() == "ip":
        return 0.0
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def archivo_anio(anio: int) -> Path:
    return DATOS_DIR / f"diarios_{anio}.csv"


def cargar_claves(path: Path):
    if not path.exists():
        return set()
    keys = set()
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            keys.add((row["fecha"], row["indicativo"]))
    return keys


def iter_chunks(ini: date, fin: date, dias: int):
    actual = ini
    while actual <= fin:
        chunk_fin = min(actual + timedelta(days=dias - 1), fin)
        yield actual, chunk_fin
        actual = chunk_fin + timedelta(days=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--anios", type=int, default=1,
                        help="Cuántos años hacia atrás (si no se da --desde)")
    parser.add_argument("--desde", help="Fecha inicio YYYY-MM-DD (anula --anios)")
    parser.add_argument("--hasta", help="Fecha fin YYYY-MM-DD (default: ayer)")
    args = parser.parse_args()

    hoy = date.today()
    fecha_fin = (datetime.strptime(args.hasta, "%Y-%m-%d").date()
                 if args.hasta else hoy - timedelta(days=1))
    fecha_fin = min(fecha_fin, hoy - timedelta(days=1))  # nunca futuro

    if args.desde:
        fecha_ini = datetime.strptime(args.desde, "%Y-%m-%d").date()
    else:
        try:
            fecha_ini = fecha_fin.replace(year=fecha_fin.year - args.anios)
        except ValueError:
            # 29 de febrero
            fecha_ini = fecha_fin.replace(month=2, day=28,
                                          year=fecha_fin.year - args.anios)

    if fecha_ini > fecha_fin:
        log.error("Rango inválido: %s > %s", fecha_ini, fecha_fin)
        return 1

    log.info("Backfill %s a %s", fecha_ini, fecha_fin)

    # Precarga de claves por año
    claves = {a: cargar_claves(archivo_anio(a))
              for a in range(fecha_ini.year, fecha_fin.year + 1)}

    chunks = list(iter_chunks(fecha_ini, fecha_fin, DIAS_POR_CHUNK))
    log.info("Total chunks: %d (~%.1f min estimados)", len(chunks),
             len(chunks) * 4 / 60)

    total = 0
    for i, (ini, fin) in enumerate(chunks, 1):
        log.info("[%d/%d] %s a %s", i, len(chunks), ini, fin)
        fmt = lambda d: d.strftime("%Y-%m-%dT00:00:00UTC")
        endpoint = (
            f"/valores/climatologicos/diarios/datos/"
            f"fechaini/{fmt(ini)}/fechafin/{fmt(fin)}/todasestaciones"
        )
        try:
            datos = aemet_get(endpoint)
        except Exception as exc:
            log.error("  Chunk fallido: %s (sigo con el siguiente)", exc)
            continue

        if not datos:
            log.info("  vacío")
            time.sleep(PAUSA_ENTRE_CHUNKS)
            continue

        # Agrupar por año
        por_anio = {}
        for d in datos:
            fecha = (d.get("fecha") or "").strip()
            ind = (d.get("indicativo") or "").strip()
            if not fecha or not ind:
                continue
            try:
                anio = int(fecha[:4])
            except ValueError:
                continue
            cache = claves.setdefault(anio, set())
            if (fecha, ind) in cache:
                continue
            cache.add((fecha, ind))
            por_anio.setdefault(anio, []).append({
                "fecha": fecha, "indicativo": ind,
                "nombre": d.get("nombre", ""),
                "provincia": d.get("provincia", ""),
                "altitud": d.get("altitud", ""),
                "tmin": num(d.get("tmin")), "tmax": num(d.get("tmax")),
                "tmed": num(d.get("tmed")), "prec": num(d.get("prec")),
                "horatmin": d.get("horatmin", ""),
                "horatmax": d.get("horatmax", ""),
            })

        for anio, filas in por_anio.items():
            path = archivo_anio(anio)
            es_nuevo = not path.exists()
            with path.open("a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=HEADERS)
                if es_nuevo:
                    w.writeheader()
                for row in filas:
                    w.writerow(row)
            log.info("  +%d filas en diarios_%d.csv", len(filas), anio)
            total += len(filas)

        time.sleep(PAUSA_ENTRE_CHUNKS)

    log.info("Backfill terminado: %d filas añadidas", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
