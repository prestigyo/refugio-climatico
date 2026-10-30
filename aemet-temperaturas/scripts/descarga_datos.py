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

# `requests` se importa donde se usa, no aquí: `--solo-consolidar` promete no
# tocar la API, y un modo que no sale a la red no debe fallar por no tener
# instalada la librería HTTP.

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("AEMET_API_KEY")
# `--solo-consolidar` no sale a la red: vuelca el rolling en los anuales y sale.
# Exigirle la clave sería pedir una credencial para reordenar ficheros locales.
if not API_KEY and "--solo-consolidar" not in sys.argv:
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
    import requests
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


def consolidar_anuales() -> dict[str, int]:
    """Vuelca el rolling en los `diarios_AAAA.csv`, que son el registro bueno.

    POR QUÉ HACE FALTA. `descargar_diarios()` solo añade al rolling
    (`diarios_estaciones.csv`), y los anuales los escribía únicamente el
    backfill. Resultado: `diarios_2026.csv` se quedó en el 26 de mayo de 2026
    mientras el rolling ya traía hasta el 26 de octubre. Tres de los cuatro
    análisis leen los DOS ficheros y no se enteraron, pero `analisis_estancia.py`
    lee solo los anuales: la herramienta por pueblo y la de «find your winter
    address» llevaban cinco meses mirando un 2026 que acababa en mayo, sin que
    nada avisara. Un fichero que se llama `diarios_2026.csv` tiene que contener
    2026 entero.

    Es idempotente: la clave es (fecha, indicativo). Si AEMET corrige un valor
    ya publicado, **gana el del rolling**, que es la descarga más reciente, y se
    cuenta aparte para que la corrección no pase desapercibida.
    """
    if not CSV_DIARIOS.exists():
        return {}
    por_anio: dict[str, dict[tuple[str, str], dict]] = {}
    with CSV_DIARIOS.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fecha = (r.get("fecha") or "").strip()
            if len(fecha) < 4 or not fecha[:4].isdigit():
                continue
            por_anio.setdefault(fecha[:4], {})[(fecha, r.get("indicativo", ""))] = r

    resumen: dict[str, int] = {}
    for anio, filas in sorted(por_anio.items()):
        destino = DATOS_DIR / f"diarios_{anio}.csv"
        previas: dict[tuple[str, str], dict] = {}
        if destino.exists():
            with destino.open(newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    previas[((r.get("fecha") or ""), r.get("indicativo", ""))] = r
        nuevas = corregidas = 0
        for clave, fila in filas.items():
            anterior = previas.get(clave)
            if anterior is None:
                nuevas += 1
            elif any((anterior.get(c) or "") != (fila.get(c) or "")
                     for c in ("tmin", "tmax", "tmed", "prec")):
                corregidas += 1
            else:
                continue
            previas[clave] = fila
        if not (nuevas or corregidas):
            continue
        # Se reescribe ordenado por (fecha, indicativo): así el diff del commit
        # es legible y dos ejecuciones seguidas dan el mismo fichero.
        tmp = destino.with_suffix(".csv.tmp")
        with tmp.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=HEADERS_DIARIOS, extrasaction="ignore")
            w.writeheader()
            for clave in sorted(previas):
                w.writerow(previas[clave])
        tmp.replace(destino)
        resumen[anio] = nuevas
        log.info("%s: +%d filas nuevas, %d corregidas (total %d)",
                 destino.name, nuevas, corregidas, len(previas))
    if not resumen:
        log.info("Anuales ya al día: nada que consolidar.")
    return resumen


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
    fallo: Exception | None = None
    nuevas = 0
    try:
        nuevas = descargar_diarios()
    except Exception as exc:  # noqa: BLE001
        log.error("Error en descarga de diarios: %s", exc)
        fallo = exc

    # El rolling no basta: los anuales son el registro que leen los análisis.
    # Va SIEMPRE, también si la descarga ha fallado: no sale a la red, y el
    # rolling que dejó la pasada anterior puede traer días que los anuales aún
    # no tengan. Si esto se cuelga detrás de un `return 1` —como estaba— un mal
    # día de AEMET deja los anuales atrás sin que nada avise, que es exactamente
    # el defecto que esta función venía a arreglar.
    try:
        consolidar_anuales()
    except Exception as exc:  # noqa: BLE001
        log.error("Error consolidando los anuales: %s", exc)

    if fallo is not None:
        return 1
    actualizar_estaciones()
    log.info("Resumen: %d filas nuevas añadidas.", nuevas)
    return 0


if __name__ == "__main__":
    # `--solo-consolidar` vuelca el rolling en los anuales y sale, sin tocar la
    # API: sirve para poner al día un año que se quedó corto sin gastar cuota ni
    # necesitar AEMET_API_KEY.
    if "--solo-consolidar" in sys.argv:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        consolidar_anuales()
        sys.exit(0)
    sys.exit(main())
