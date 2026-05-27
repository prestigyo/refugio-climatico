#!/usr/bin/env python3
"""
Descarga diaria de los mapas de temperaturas máximas y mínimas de AEMET.

Recorre las páginas de Península/Baleares y Canarias para los días "hoy", "mna"
(mañana) y "pmna" (pasado mañana) y descarga las imágenes de temperaturas
máximas, mínimas y sus variaciones respecto al día anterior.

Las imágenes se guardan en `images/<zona>/<tipo>/YYYY-MM-DD.png` y los detalles
se registran en `metadata.csv` para poder construir series temporales.

Uso:
    python scripts/descarga_aemet.py

Dependencias:
    requests, beautifulsoup4
"""

from __future__ import annotations

import csv
import hashlib
import logging
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

BASE_URL = "https://www.aemet.es/es/eltiempo/prediccion/temperaturas"

# Zonas y tipos de mapa a descargar.
ZONAS = ["penyb", "can"]  # península+baleares, canarias
TIPOS = ["maxima", "minima", "variacionmax", "variacionmin"]

# Sólo nos interesa "hoy" para el archivo histórico; las previsiones de "mna" y
# "pmna" se pueden activar si se quiere comparar predicción vs realidad.
DIAS = ["hoy"]

# Carpeta raíz del repo (este script vive en scripts/, así que subimos un nivel).
ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = ROOT / "images"
METADATA_FILE = ROOT / "metadata.csv"

HEADERS = {
    # AEMET rechaza User-Agents poco habituales con 403, así que usamos uno
    # estándar de navegador. La descarga es de uso personal y respetuosa
    # (1 vez al día, pausa entre peticiones).
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://www.aemet.es/",
}

# Mapeo zona+canarias -> nombre carpeta legible.
NOMBRE_ZONA = {"penyb": "peninsula", "can": "canarias"}

# Timeout (segundos) para las peticiones HTTP.
TIMEOUT = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("aemet")


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------


@dataclass
class Descarga:
    zona: str
    tipo: str
    dia: str
    url_pagina: str
    url_imagen: str | None
    ruta_local: Path | None
    estado: str            # "ok", "ya_existia", "error", "sin_imagen"
    sha256: str | None
    bytes: int
    timestamp_utc: str
    detalle: str = ""


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------


def crear_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def url_pagina(zona: str, tipo: str, dia: str) -> str:
    return f"{BASE_URL}?dia={dia}&zona={zona}&img={tipo}"


def extraer_url_imagen(html: str, base: str) -> str | None:
    """Devuelve la URL absoluta del mapa de temperaturas que aparece en la página.

    AEMET inserta la imagen dentro de un <img> cuyo src apunta a
    /imagenes_d/eltiempo/prediccion/temperaturas/<timestamp>+<offset>_ww_<...>.png
    El timestamp cambia cada día y a veces a lo largo del día (varias pasadas
    del modelo), así que es importante leerlo de la página y no construirlo.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Buscamos cualquier <img> en /imagenes_d/.../temperaturas/...
    patron = re.compile(r"/imagenes_d/eltiempo/prediccion/temperaturas/[^\"'\s]+\.png", re.I)
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if patron.search(src):
            return urljoin(base, src)
    # Fallback por si la imagen llega como atributo de fondo, etc.
    m = patron.search(html)
    if m:
        return urljoin(base, m.group(0))
    return None


def descargar_imagen(session: requests.Session, url: str, referer: str) -> bytes:
    """Descarga la imagen. Lanza excepción si falla."""
    r = session.get(url, headers={"Referer": referer}, timeout=TIMEOUT)
    r.raise_for_status()
    if not r.content:
        raise ValueError("Imagen vacía")
    return r.content


def ruta_destino(zona: str, tipo: str, fecha: str) -> Path:
    # Algunas combinaciones (variaciones) sólo existen para penyb, está bien:
    # si la imagen no existe la marcamos en metadata como "sin_imagen".
    return IMAGES_DIR / NOMBRE_ZONA[zona] / tipo / f"{fecha}.png"


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def procesar(
    session: requests.Session,
    zona: str,
    tipo: str,
    dia: str,
    fecha_hoy: str,
) -> Descarga:
    url_p = url_pagina(zona, tipo, dia)
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    destino = ruta_destino(zona, tipo, fecha_hoy)

    base = Descarga(
        zona=zona, tipo=tipo, dia=dia, url_pagina=url_p,
        url_imagen=None, ruta_local=None, estado="error",
        sha256=None, bytes=0, timestamp_utc=ahora,
    )

    if destino.exists():
        # Idempotente: si la GH Action se ejecuta dos veces el mismo día no
        # sobreescribimos. Aun así calculamos el hash para tener registro.
        data = destino.read_bytes()
        base.estado = "ya_existia"
        base.ruta_local = destino
        base.sha256 = hash_bytes(data)
        base.bytes = len(data)
        log.info("%-9s %-14s %-4s ya existía (%s)", zona, tipo, dia, destino.name)
        return base

    try:
        r = session.get(url_p, timeout=TIMEOUT)
        r.raise_for_status()
        # AEMET usa ISO-8859-15; requests a veces no la detecta bien.
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = "iso-8859-15"
        url_img = extraer_url_imagen(r.text, base=BASE_URL)
        base.url_imagen = url_img
        if not url_img:
            base.estado = "sin_imagen"
            base.detalle = "No se encontró <img> de temperaturas en la página."
            log.warning("%-9s %-14s %-4s sin imagen", zona, tipo, dia)
            return base

        data = descargar_imagen(session, url_img, referer=url_p)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(data)

        base.estado = "ok"
        base.ruta_local = destino
        base.sha256 = hash_bytes(data)
        base.bytes = len(data)
        log.info(
            "%-9s %-14s %-4s OK  %6.1f KB -> %s",
            zona, tipo, dia, len(data) / 1024, destino.relative_to(ROOT),
        )
    except Exception as exc:  # noqa: BLE001 - registramos cualquier fallo
        base.estado = "error"
        base.detalle = f"{type(exc).__name__}: {exc}"
        log.error("%-9s %-14s %-4s ERROR %s", zona, tipo, dia, base.detalle)

    return base


def append_metadata(rows: list[Descarga]) -> None:
    cabeceras = [
        "timestamp_utc", "fecha_local", "zona", "tipo", "dia",
        "estado", "url_pagina", "url_imagen", "ruta_local",
        "bytes", "sha256", "detalle",
    ]
    nuevo = not METADATA_FILE.exists()
    with METADATA_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(cabeceras)
        for d in rows:
            w.writerow([
                d.timestamp_utc,
                datetime.now().strftime("%Y-%m-%d"),
                d.zona,
                d.tipo,
                d.dia,
                d.estado,
                d.url_pagina,
                d.url_imagen or "",
                str(d.ruta_local.relative_to(ROOT)) if d.ruta_local else "",
                d.bytes,
                d.sha256 or "",
                d.detalle,
            ])


def main() -> int:
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    log.info("Inicio descarga AEMET - fecha objetivo: %s", fecha_hoy)
    session = crear_session()

    descargas: list[Descarga] = []
    for zona in ZONAS:
        for tipo in TIPOS:
            for dia in DIAS:
                # Variaciones sólo se muestran en la web; existen para ambas
                # zonas pero por si acaso capturamos "sin_imagen" sin error.
                d = procesar(session, zona, tipo, dia, fecha_hoy)
                descargas.append(d)
                # Pequeña pausa para no martillear AEMET.
                time.sleep(1.5)

    append_metadata(descargas)

    # Resumen final + código de salida según éxito mínimo (al menos 1 ok).
    ok = sum(1 for d in descargas if d.estado == "ok")
    existian = sum(1 for d in descargas if d.estado == "ya_existia")
    err = sum(1 for d in descargas if d.estado == "error")
    sin_img = sum(1 for d in descargas if d.estado == "sin_imagen")
    log.info(
        "Resumen: %d nuevas, %d ya existían, %d sin imagen, %d errores",
        ok, existian, sin_img, err,
    )
    # Devolvemos 0 si bajamos al menos las dos imágenes principales de península.
    criticos = [
        d for d in descargas
        if d.zona == "penyb" and d.tipo in {"maxima", "minima"}
    ]
    if all(d.estado in {"ok", "ya_existia"} for d in criticos):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
