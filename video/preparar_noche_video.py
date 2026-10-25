#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preparar_noche_video.py — la noche MEDIDA que dibuja la escena 2 del vídeo pilar.

La escena explica qué es una noche tropical con la curva de temperatura de una
noche. Esa curva no se inventa: sale del archivo horario de AEMET
(aemet-temperaturas/datos/horarias/), leída con las funciones de
analisis_curva_nocturna.py (ventana de sueño 23:00-07:00 hora local, nueve
lecturas; Canarias en su huso).

Antes de escribir nada comprueba que la frase del guion («no baja de veinte grados
en ningún momento») es verdad para esa noche:
  1. las nueve lecturas existen y ninguna baja de 20,0 °C («tropical cerrada»);
  2. la mínima DENTRO de cada hora (tamin) tampoco baja de 20,0 °C;
  3. la mínima diaria validada de AEMET (diarios_*.csv) es >= 20,0 °C, el criterio
     de la web. Hace falta: hay noches que pasan 1 y 2 y AEMET valida después una
     mínima de 19,2 °C (Cádiz, 29-8-2026). Si AEMET aún no la ha publicado, el
     script se niega salvo --permitir-provisional, y el rótulo lo dice.

Uso (desde la raíz del repo):
    python video/preparar_noche_video.py --buscar
    python video/preparar_noche_video.py --estacion 7178I --noche 2026-09-10

Salida: video/datos/noche_video.json
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / "aemet-temperaturas" / "scripts"
DATOS = RAIZ / "aemet-temperaturas" / "datos"
SALIDA = Path(__file__).resolve().parent / "datos" / "noche_video.json"

sys.path.insert(0, str(SCRIPTS))
import analisis_curva_nocturna as acn  # noqa: E402  (ventana, husos, métricas)
import generar_calculadora as g        # noqa: E402  (nombres legibles, como la web)

UMBRAL = acn.UMBRALES[0]   # 20,0 °C, el de todo el proyecto


def leer_horarias(fecha: str) -> dict:
    """{idema: {datetime_utc: (ta, tamin)}} del fichero de esa noche.

    Mismo fichero y mismo parseo que acn.leer_noche(), que solo guarda ta; aquí
    hace falta también tamin, la mínima dentro de la hora.
    """
    ruta = acn.DIR_HORARIAS / fecha[:4] / f"{fecha}.csv.gz"
    out: dict = {}
    if not ruta.exists():
        return out
    with gzip.open(ruta, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                ta = float(r["ta"])
                t = datetime.strptime(r["fint"], "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)
            except (ValueError, KeyError):
                continue
            try:
                tamin = float(r["tamin"])
            except (ValueError, KeyError):
                tamin = None
            out.setdefault(r["idema"], {})[t] = (ta, tamin)
    return out


def cargar_diarias(anios: set) -> dict:
    """{(indicativo, fecha): tmin} validada. El rolling se lee el último y manda."""
    rutas = [DATOS / f"diarios_{a}.csv" for a in sorted(anios)]
    rutas.append(DATOS / "diarios_estaciones.csv")
    out = {}
    for ruta in rutas:
        if not ruta.exists():
            continue
        with ruta.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    out[(r["indicativo"], r["fecha"])] = float(r["tmin"])
                except (ValueError, KeyError):
                    pass
    return out


def evaluar(ind: str, fecha: str, serie: dict, meta: dict, diarias: dict) -> dict | None:
    off = meta["utc_offset"]
    ta = acn.curva_de_sueno({t: v[0] for t, v in serie.items()}, fecha, off)
    if ta is None:
        return None
    tamin = acn.curva_de_sueno({t: v[1] for t, v in serie.items()}, fecha, off)
    m = acn.metricas(ta)
    tmin_dia = diarias.get((ind, fecha))
    return {
        "ta": ta,
        "tamin": tamin,
        "metricas": m,
        "tipo": acn.clasificar(m),
        "forma": acn.forma(ta),
        "ok_lecturas": min(ta) >= UMBRAL,
        "ok_tamin": all(x is not None for x in tamin) and min(tamin) >= UMBRAL,
        "tmin_diaria": tmin_dia,
        "ok_diaria": tmin_dia is not None and tmin_dia >= UMBRAL,
    }


def rotulo(ind: str, meta: dict) -> tuple[str, str]:
    """Nombre y provincia con las mismas correcciones que usa la web."""
    prov_raw = meta["provincia"]
    return (g.CORRECCIONES.get(ind, g.titular(meta["nombre"])),
            g.PROVINCIAS.get(prov_raw, g.titular(prov_raw)))


def buscar(fechas: list, est: dict, diarias: dict, tope: int = 40) -> int:
    filas = []
    for fecha in fechas:
        for ind, serie in leer_horarias(fecha).items():
            meta = est.get(ind)
            if not meta:
                continue
            ev = evaluar(ind, fecha, serie, meta, diarias)
            if ev and ev["ok_lecturas"] and ev["ok_tamin"] and ev["ok_diaria"]:
                filas.append((fecha, ind, meta, ev))
    print(f"Noches que cumplen las tres comprobaciones: {len(filas)}")
    # Primero las que mejor cuentan «no enfría»: rozan los 20 °C y apenas caen.
    filas.sort(key=lambda x: (min(x[3]["ta"]), x[3]["metricas"]["caida"]))
    for fecha, ind, meta, ev in filas[:tope]:
        nombre, prov = rotulo(ind, meta)
        print(f"  {fecha} {ind:6} {nombre[:32]:32} {prov[:16]:16} "
              f"mín {min(ev['ta']):.1f} · caída {ev['metricas']['caida']:.1f} · "
              f"diaria {ev['tmin_diaria']:.1f} · {ev['forma']:11} | "
              + " ".join(f"{t:.1f}" for t in ev["ta"]))
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--estacion", help="indicativo AEMET, p. ej. 7178I")
    p.add_argument("--noche", help="AAAA-MM-DD de la mañana en que termina la noche")
    p.add_argument("--buscar", action="store_true",
                   help="lista las noches que cumplen las tres comprobaciones")
    p.add_argument("--permitir-provisional", action="store_true",
                   help="acepta una noche sin mínima diaria validada todavía")
    a = p.parse_args()

    est = acn.cargar_estaciones()
    fechas = acn.noches_disponibles()
    diarias = cargar_diarias({f[:4] for f in fechas})

    if a.buscar:
        return buscar(fechas, est, diarias)
    if not (a.estacion and a.noche):
        p.error("indica --estacion y --noche, o usa --buscar")

    meta = est.get(a.estacion)
    serie = leer_horarias(a.noche).get(a.estacion)
    if not meta or not serie:
        raise SystemExit(f"No hay lecturas horarias de {a.estacion} para la noche {a.noche}.")
    ev = evaluar(a.estacion, a.noche, serie, meta, diarias)
    if ev is None:
        raise SystemExit("Faltan lecturas en la ventana 23:00-07:00: no se dibuja una curva "
                         "con huecos rellenados.")

    fallos = []
    if not ev["ok_lecturas"]:
        fallos.append(f"alguna lectura horaria baja de {UMBRAL:g} °C (mínima {min(ev['ta'])})")
    if not ev["ok_tamin"]:
        fallos.append(f"la mínima dentro de alguna hora baja de {UMBRAL:g} °C o falta: {ev['tamin']}")
    if ev["tmin_diaria"] is not None and not ev["ok_diaria"]:
        fallos.append(f"la mínima diaria validada de AEMET es {ev['tmin_diaria']} °C")
    if ev["tmin_diaria"] is None and not a.permitir_provisional:
        fallos.append("AEMET aún no ha publicado la mínima diaria validada "
                      "(--permitir-provisional para usarla igualmente)")
    if fallos:
        raise SystemExit("Esta noche no sirve para la frase del guion:\n  - " + "\n  - ".join(fallos))

    nombre, prov = rotulo(a.estacion, meta)
    salida = {
        "generado": date.today().isoformat(),
        "fuente": "AEMET",
        "estacion": {"indicativo": a.estacion, "nombre": nombre, "provincia": prov,
                     "altitud": meta["altitud"]},
        "noche": a.noche,
        "ventana": "23:00-07:00 hora local",
        "horas_locales": [f"{(acn.HORA_INICIO_LOCAL + h) % 24:02d}:00"
                          for h in range(acn.HORAS_VENTANA)],
        "ta": ev["ta"],
        "tamin": ev["tamin"],
        "tmin_diaria_validada": ev["tmin_diaria"],
        "provisional": ev["tmin_diaria"] is None,
        "tipo": ev["tipo"],
        "forma": ev["forma"],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{nombre} ({prov}), noche {a.noche}: " + " ".join(f"{t:.1f}" for t in ev["ta"]))
    print(f"  mínima horaria {min(ev['ta']):.1f} · mínima dentro de las horas {min(ev['tamin']):.1f}"
          f" · mínima diaria validada {ev['tmin_diaria']} · {ev['tipo']}, {ev['forma']}")
    print(f"Escrito {SALIDA.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
