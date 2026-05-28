#!/usr/bin/env python3
"""
Descarga datos numéricos diarios de temperatura por estación desde AEMET OpenData.

Cada ejecución solicita los últimos N días de valores climatológicos diarios
(tmin, tmax, tmed, precipitación) de TODAS las estaciones meteorológicas, y
los acumula en datos/diarios_estaciones.csv evitando duplicados.

AEMET publica los datos diarios con 3-5 días de retraso, así que pedimos
los últimos 20 días para capturar lo que se haya consolidado nuevo.

Requiere variable de entorno AEMET_API_KEY.
"""
from __future__ import annotations

import csv
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("AEMET_API_KEY")
if not API_KEY:
    print("ERROR: falta variable de entorno AEMET_API_KEY", file=sys.stderr)
    sys.exit(1)

BASE = "https://opendata.aemet.es/opendata/api"
DIAS_RETROCESO = 14

ROOT = Path(__file__).resolve().parent.parent
DATOS_DIR = ROOT / "datos"
DATOS_DIR.mkdir(exist_ok=True)
CSV_DIARIOS = DATOS_DIR / "diarios_estaciones.csv"
CSV_ESTACIONES = DATOS_DIR / "estaciones.csv"

HEADERS_DIARIOS = [
    "fecha", "indicativo", "nombre", "provincia", "altitud",
    "tmin", "tmax", "tmed", "prec", "horatmin", "horatmax",
]
HEADERS_ESTACIONES = [
    "indicativo", "nombre", "provincia", "indsinop",
    "latitud", "longitud", "altitud",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("opendata")


# ---------------------------------------------------------------------------
# Cliente OpenData
# ---------------------------------------------------------------------------

def aemet_get(endpoint: str, retries: int = 4):
    """Llama a OpenData. AEMET responde con un JSON intermedio cuyo campo
    "datos" apunta a la URL real con el payload; hay que hacer 2 peticiones.
    """
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
                espera = 30 * intento
                log.warning("Rate limit, esperando %ds", espera)
                time.sleep(espera)
                continue
            r.raise_for_status()
            meta = r.json()
            if meta.get("estado") != 200:
                raise RuntimeError(f"AEMET respondió estado={meta.get('estado')}: {meta.get('descripcion')}")
            datos_url = meta["datos"]
            r2 = requests.get(datos_url, timeout=90)
            r2.raise_for_status()
            # A veces AEMET devuelve el JSON con encoding ISO-8859-15
            if not r2.encoding or r2.encoding.lower() == "iso-8859-1":
                r2.encoding = "iso-8859-15"
            return r2.json()
        except Exception as exc:
            log.warning("Intento %d/%d falló: %s", intento, retries, exc)
            if intento == retries:
                raise
            time.sleep(5 * intento)


def num(valor) -> float | None:
    """Normaliza un valor numérico de AEMET (decimales con coma) a float."""
    if valor is None or valor == "" or str(valor).strip().lower() == "ip":
        # "Ip" = precipitación inapreciable; lo convertimos a 0.0
        return 0.0 if str(valor).strip().lower() == "ip" else None
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).replace(",", ".").strip())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Lógica
# ---------------------------------------------------------------------------

def cargar_claves_existentes() -> set[tuple[str, str]]:
    """Devuelve el conjunto (fecha, indicativo) ya presentes en el CSV."""
    if not CSV_DIARIOS.exists():
        return set()
    existentes: set[tuple[str, str]] = set()
    with CSV_DIARIOS.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existentes.add((row["fecha"], row["indicativo"]))
    return existentes


def descargar_diarios() -> int:
    hoy = date.today()
    fecha_fin = hoy - timedelta(days=1)
    fecha_ini = fecha_fin - timedelta(days=DIAS_RETROCESO)

    def fmt(d: date) -> str:
        return d.strftime("%Y-%m-%dT00:00:00UTC")

    log.info("Solicitando diarios de %s a %s", fecha_ini, fecha_fin)
    endpoint = (
        f"/valores/climatologicos/diarios/datos/"
        f"fechaini/{fmt(fecha_ini)}/fechafin/{fmt(fecha_fin)}/todasestaciones"
    )
    datos = aemet_get(endpoint)
    log.info("AEMET devolvió %d registros", len(datos))

    existentes = cargar_claves_existentes()
    log.info("CSV actual: %d filas únicas", len(existentes))

    nuevos = []
    for d in datos:
        fecha = (d.get("fecha") or "").strip()
        ind = (d.get("indicativo") or "").strip()
        if not fecha or not ind:
            continue
        if (fecha, ind) in existentes:
            continue
        nuevos.append({
            "fecha": fecha,
            "indicativo": ind,
            "nombre": d.get("nombre", ""),
            "provincia": d.get("provincia", ""),
            "altitud": d.get("altitud", ""),
            "tmin": num(d.get("tmin")),
            "tmax": num(d.get("tmax")),
            "tmed": num(d.get("tmed")),
            "prec": num(d.get("prec")),
            "horatmin": d.get("horatmin", ""),
            "horatmax": d.get("horatmax", ""),
        })

    if not nuevos:
        log.info("Sin filas nuevas.")
        return 0

    es_nuevo_archivo = not CSV_DIARIOS.exists()
    with CSV_DIARIOS.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS_DIARIOS)
        if es_nuevo_archivo:
            w.writeheader()
        for row in nuevos:
            w.writerow(row)
    log.info("Añadidas %d filas nuevas a %s", len(nuevos), CSV_DIARIOS.relative_to(ROOT))
    return len(nuevos)


def actualizar_estaciones() -> None:
    """Refresca el inventario de estaciones (lat/lon/altitud). Se ejecuta
    cada día pero ocupa poco; tener los metadatos al día es útil para mapas."""
    try:
        log.info("Actualizando inventario de estaciones...")
        estaciones = aemet_get(
            "/valores/climatologicos/inventarioestaciones/todasestaciones"
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo actualizar estaciones: %s", exc)
        return

    with CSV_ESTACIONES.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS_ESTACIONES)
        w.writeheader()
        for e in estaciones:
            w.writerow({h: e.get(h, "") for h in HEADERS_ESTACIONES})
    log.info(
        "Guardadas %d estaciones en %s",
        len(estaciones), CSV_ESTACIONES.relative_to(ROOT),
    )


def main() -> int:
    try:
        nuevas = descargar_diarios()
    except Exception as exc:  # noqa: BLE001
        log.error("Error en descarga de diarios: %s", exc)
        return 1
    actualizar_estaciones()
    log.info("Resumen: %d filas nuevas añadidas.", nuevas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
