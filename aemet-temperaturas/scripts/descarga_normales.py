#!/usr/bin/env python3
"""
Descarga valores climatológicos NORMALES (periodo 1991-2020) por estación AEMET.

Para cada estación AEMET disponible solicita el endpoint
/valores/climatologicos/normales/estacion/{indicativo} que devuelve 13 filas:
una por mes (1-12) + una "anual" (mes=13), cada una con valores medios
mensuales de temperatura, precipitación, etc., calculados sobre 1991-2020.

Resultado: datos/normales_1991_2020.csv

Es idempotente: si se relanza, salta las estaciones ya descargadas.
Se ejecuta UNA VEZ (los normales no cambian mes a mes).
"""
from __future__ import annotations

import csv
import logging
import os
import sys
import time
from pathlib import Path

import requests

API_KEY = os.environ.get("AEMET_API_KEY")
if not API_KEY:
    print("ERROR: falta AEMET_API_KEY", file=sys.stderr)
    sys.exit(1)

BASE = "https://opendata.aemet.es/opendata/api"
PAUSA_ENTRE_LLAMADAS = 1.0
PAUSA_RATELIMIT = 60.0

ROOT = Path(__file__).resolve().parent.parent
DATOS_DIR = ROOT / "datos"
DATOS_DIR.mkdir(exist_ok=True)
CSV_OUT = DATOS_DIR / "normales_1991_2020.csv"
CSV_ESTACIONES = DATOS_DIR / "estaciones.csv"

CAMPOS = [
    "indicativo", "mes",
    "tm_mes", "tm_max", "tm_min",         # temperaturas medias mensuales
    "ta_max", "ta_min",                   # extremas absolutas
    "p_mes", "p_max",                     # precipitación
    "hr", "n_llu", "n_nie", "n_tor",     # otros
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("normales")


def aemet_get(endpoint: str, retries: int = 4):
    url = f"{BASE}{endpoint}"
    for intento in range(1, retries + 1):
        try:
            r = requests.get(
                url, params={"api_key": API_KEY},
                timeout=30, headers={"Accept": "application/json"},
            )
            if r.status_code == 429:
                log.warning("Rate limit, esperando %.0fs", PAUSA_RATELIMIT)
                time.sleep(PAUSA_RATELIMIT)
                continue
            r.raise_for_status()
            meta = r.json()
            estado = meta.get("estado")
            if estado == 404:
                return None  # no hay datos para esa estación
            if estado != 200:
                raise RuntimeError(
                    f"AEMET estado={estado}: {meta.get('descripcion', '')}"
                )
            r2 = requests.get(meta["datos"], timeout=60)
            r2.raise_for_status()
            if not r2.encoding or r2.encoding.lower() == "iso-8859-1":
                r2.encoding = "iso-8859-15"
            return r2.json()
        except Exception as exc:
            log.warning("Intento %d/%d fallido: %s", intento, retries, exc)
            if intento == retries:
                raise
            time.sleep(5 * intento)


def cargar_estaciones() -> list[dict]:
    if not CSV_ESTACIONES.exists():
        log.error("No existe %s. Lanza primero el workflow diario.", CSV_ESTACIONES)
        sys.exit(1)
    with CSV_ESTACIONES.open(newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row.get("indicativo")]


def cargar_ya_hechas() -> set[str]:
    if not CSV_OUT.exists():
        return set()
    with CSV_OUT.open(newline="", encoding="utf-8") as f:
        return {row["indicativo"] for row in csv.DictReader(f)
                if row.get("indicativo")}


def main() -> int:
    estaciones = cargar_estaciones()
    log.info("Inventario: %d estaciones", len(estaciones))

    ya = cargar_ya_hechas()
    pendientes = [e for e in estaciones if e["indicativo"] not in ya]
    log.info("Ya descargadas: %d. Pendientes: %d", len(ya), len(pendientes))

    if not pendientes:
        log.info("Nada que hacer.")
        return 0

    es_nuevo = not CSV_OUT.exists()
    fallidas = 0
    sin_datos = 0
    ok = 0

    with CSV_OUT.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        if es_nuevo:
            writer.writeheader()

        for i, est in enumerate(pendientes, 1):
            ind = est["indicativo"]
            nombre = est.get("nombre", "")[:30]
            try:
                datos = aemet_get(f"/valores/climatologicos/normales/estacion/{ind}")
            except Exception as exc:
                log.warning("[%d/%d] %s (%s) ERROR: %s",
                            i, len(pendientes), ind, nombre, exc)
                fallidas += 1
                continue

            if not datos:
                log.info("[%d/%d] %s (%s) sin normales",
                         i, len(pendientes), ind, nombre)
                sin_datos += 1
                # Guardamos una fila "vacía" para no reintentar esta estación
                writer.writerow({"indicativo": ind, "mes": "0"})
                f.flush()
                time.sleep(PAUSA_ENTRE_LLAMADAS)
                continue

            for fila in datos:
                row = {"indicativo": ind, "mes": fila.get("mes", "")}
                for campo in CAMPOS[2:]:
                    val = fila.get(campo, "")
                    # AEMET puede devolver valores como "(45)" o "23.4" con parens
                    if isinstance(val, str):
                        val = val.replace("(", "").replace(")", "").strip()
                    row[campo] = val
                writer.writerow(row)
            f.flush()
            ok += 1
            log.info("[%d/%d] %s (%s) OK %d filas",
                     i, len(pendientes), ind, nombre, len(datos))
            time.sleep(PAUSA_ENTRE_LLAMADAS)

    log.info("Resumen: %d OK, %d sin datos, %d fallidas", ok, sin_datos, fallidas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
