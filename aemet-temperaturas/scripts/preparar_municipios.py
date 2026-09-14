#!/usr/bin/env python3
"""Cruce municipios (IGN/CNIG, NGMEP) ↔ estaciones AEMET, y noches frías de invierno.

Ejecución MANUAL, una vez al año (en abril, con el invierno ya cerrado). No entra
en el workflow diario: el NGMEP se descarga a mano del Centro de Descargas del
CNIG y se deja en aemet-temperaturas/datos/BD_Municipios-Entidades/.

Qué hace
  1. Lee los municipios del NGMEP (MUNICIPIOS.csv: cp1252, separador «;»,
     decimales con coma) y se queda con los de población >= 500 y coordenadas.
  2. Cruza cada municipio con las estaciones del ranking (que ya traen lat/lon y
     altitud) por haversine, y le asigna la de mejor nivel de confianza:
        alta         <= 15 km y |desnivel| <= 100 m
        media        <= 25 km y |desnivel| <= 200 m
        orientativa  <= 35 km y |desnivel| <= 300 m
     A igualdad de nivel, la de menor desnivel; después, la más cercana. El
     desnivel manda: 0,6 °C por cada 100 m aproximadamente.
  3. Para cada estación y cada INVIERNO (1 de noviembre – 31 de marzo; el invierno
     2025 va de noviembre de 2025 a marzo de 2026) cuenta cuántas noches tuvieron
     la mínima a o por debajo de cada grado entero de UMBRALES (-4 a 20 °C). Un
     invierno solo cuenta si tiene al menos el 90 % de los días con dato.
  4. Criterio «sin heladas», invierno a invierno (el mismo espíritu que los
     certificados anuales): un invierno está libre de heladas si ninguna noche
     bajó de 0,0 °C. Cada año se evalúa de nuevo; se publica la serie.

Dirección del análisis: de la estación al municipio. El dato es de la estación;
el municipio solo hereda la estación de referencia con su distancia y desnivel.

Salidas (en aemet-temperaturas/datos/)
  municipios_estaciones.json   el cruce, común a verano e invierno
  municipios_sin_heladas.json  el cruce + las series de invierno por estación

Uso:  python aemet-temperaturas/scripts/preparar_municipios.py
Solo biblioteca estándar (el CI no tiene pandas).
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import generar_calculadora as g

DATOS = g.AEMET_DIR / "datos"
NGMEP = DATOS / "BD_Municipios-Entidades" / "MUNICIPIOS.csv"
SALIDA_CRUCE = DATOS / "municipios_estaciones.json"
SALIDA_INVIERNO = DATOS / "municipios_sin_heladas.json"

POBLACION_MINIMA = 500
NIVELES = (("alta", 15.0, 100), ("media", 25.0, 200), ("orientativa", 35.0, 300))
RADIO_MAX_KM = NIVELES[-1][1]
UMBRALES = list(range(-4, 21))          # grados enteros: tmin <= umbral
MESES_INVIERNO = {"11", "12", "01", "02", "03"}
COBERTURA_MINIMA = 0.90
INVIERNOS_MINIMOS = 5
FUENTES = {"clima": "AEMET", "municipios": "IGN (CNIG) — NGMEP"}


def km(la1: float, lo1: float, la2: float, lo2: float) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (la1, lo1, la2, lo2))
    a = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def num(txt: str) -> float | None:
    txt = (txt or "").strip().replace(".", "").replace(",", ".") if "," in (txt or "") else (txt or "").strip()
    try:
        return float(txt)
    except ValueError:
        return None


def leer_municipios() -> tuple[list[dict], dict]:
    if not NGMEP.exists():
        sys.exit(f"No encuentro el NGMEP en {NGMEP}. Descárgalo del CNIG y déjalo ahí.")
    log = {"leidos": 0, "sin_coordenadas": 0, "menos_de_500": 0}
    out = []
    with NGMEP.open(encoding="cp1252", newline="") as fh:
        for f in csv.DictReader(fh, delimiter=";"):
            log["leidos"] += 1
            lat, lon = num(f["LATITUD_ETRS89_REGCAN95"]), num(f["LONGITUD_ETRS89_REGCAN95"])
            if lat is None or lon is None:
                log["sin_coordenadas"] += 1
                continue
            pob = int(num(f["POBLACION_MUNI"]) or 0)
            if pob < POBLACION_MINIMA:
                log["menos_de_500"] += 1
                continue
            alt = num(f["ALTITUD"])
            out.append({"ine": f["COD_INE"][:5], "nombre": f["NOMBRE_ACTUAL"].strip(),
                        "provincia": f["PROVINCIA"].strip(), "poblacion": pob,
                        "altitud": int(round(alt)) if alt is not None else None,
                        "lat": lat, "lon": lon})
    return out, log


def dias_invierno(inv: int) -> int:
    sig = inv + 1
    bis = sig % 4 == 0 and (sig % 100 != 0 or sig % 400 == 0)
    return 30 + 31 + 31 + (29 if bis else 28) + 31


def leer_inviernos(ids: set) -> tuple[dict, dict]:
    """dias[id][inv] y noches[id][inv][k] (k = índice de UMBRALES)."""
    rutas = [p for p in sorted(DATOS.glob("diarios_20*.csv")) if re.fullmatch(r"diarios_20\d\d\.csv", p.name)]
    extra = DATOS / "diarios_estaciones.csv"
    if extra.exists():
        rutas.append(extra)
    vistos: set = set()
    dias: dict = defaultdict(lambda: defaultdict(int))
    noches: dict = defaultdict(lambda: defaultdict(lambda: [0] * len(UMBRALES)))
    for ruta in rutas:
        with ruta.open(encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            cab = next(rd, None)
            if not cab:
                continue
            i_f, i_id, i_t = cab.index("fecha"), cab.index("indicativo"), cab.index("tmin")
            for row in rd:
                if len(row) <= i_t or row[i_id] not in ids:
                    continue
                fecha = row[i_f][:10]
                mes = fecha[5:7]
                if mes not in MESES_INVIERNO:
                    continue
                clave = (row[i_id], fecha)
                if clave in vistos:
                    continue
                try:
                    t = float(row[i_t].replace(",", "."))
                except ValueError:
                    continue
                vistos.add(clave)
                inv = int(fecha[:4]) if mes in ("11", "12") else int(fecha[:4]) - 1
                dias[row[i_id]][inv] += 1
                fila = noches[row[i_id]][inv]
                for k, u in enumerate(UMBRALES):
                    if t <= u:
                        fila[k] += 1
    return dias, noches


def nivel(d: float, dz: float) -> int | None:
    for n, (_, dmax, zmax) in enumerate(NIVELES):
        if d <= dmax and abs(dz) <= zmax:
            return n
    return None


def main() -> int:
    estaciones, _ = g.cargar_estaciones()
    municipios, log = leer_municipios()
    print(f"NGMEP: {log['leidos']} municipios leídos · {log['sin_coordenadas']} descartados sin "
          f"coordenadas · {log['menos_de_500']} con menos de {POBLACION_MINIMA} hab. · "
          f"{len(municipios)} en juego")

    ids = {e["id"] for e in estaciones}
    dias, noches = leer_inviernos(ids)
    k0 = UMBRALES.index(0)
    serie: dict = {}
    for e in estaciones:
        completos = sorted(inv for inv, n in dias[e["id"]].items()
                           if n >= COBERTURA_MINIMA * dias_invierno(inv))
        if len(completos) < INVIERNOS_MINIMOS:
            continue
        serie[e["id"]] = {inv: noches[e["id"]][inv] for inv in completos}
    todos_inv = sorted({inv for s in serie.values() for inv in s})
    print(f"Estaciones con >= {INVIERNOS_MINIMOS} inviernos completos (nov–mar): {len(serie)} "
          f"de {len(estaciones)} · inviernos {todos_inv[0]}/{str(todos_inv[0] + 1)[2:]}–"
          f"{todos_inv[-1]}/{str(todos_inv[-1] + 1)[2:]}")

    candidatas = [e for e in estaciones if e["id"] in serie]
    cruce = []
    for m in municipios:
        mejor = None
        for e in candidatas:
            if abs(e["lat"] - m["lat"]) > 0.4 or abs(e["lon"] - m["lon"]) > 0.55:
                continue
            d = km(m["lat"], m["lon"], e["lat"], e["lon"])
            if d > RADIO_MAX_KM:
                continue
            dz = e["alt"] - (m["altitud"] if m["altitud"] is not None else e["alt"])
            n = nivel(d, dz) if m["altitud"] is not None else None
            if n is None:
                continue
            clave = (n, abs(dz), d)
            if mejor is None or clave < mejor[0]:
                mejor = (clave, e, d, dz)
        if not mejor:
            continue
        (n, _, _), e, d, dz = mejor
        s = serie[e["id"]]
        heladas = [s[inv][k0] for inv in sorted(s)]
        ultimo = max(s)
        cruce.append({
            "ine": m["ine"], "nombre": m["nombre"], "provincia": m["provincia"],
            "poblacion": m["poblacion"], "altitud": m["altitud"],
            "lat": round(m["lat"], 4), "lon": round(m["lon"], 4),
            "estacion": e["id"], "estacion_nombre": e["loc"], "estacion_altitud": e["alt"],
            "distancia_km": round(d, 1), "delta_altitud": int(dz),
            "confianza": NIVELES[n][0],
            "veranos": int(round(e.get("anios") or 0)),
            "noches_tropicales_año": e["nt"],
            "inviernos": len(s),
            "heladas_por_año": round(sum(heladas) / len(heladas), 1),
            "inviernos_sin_heladas": sum(1 for h in heladas if h == 0),
            "invierno_evaluado": ultimo,
            "sin_heladas": s[ultimo][k0] == 0,
        })
    cruce.sort(key=lambda x: (g.clave_orden(x["provincia"]), g.clave_orden(x["nombre"])))

    hoy = date.today().isoformat()
    campos_cruce = ("ine", "nombre", "provincia", "poblacion", "altitud", "estacion",
                    "estacion_nombre", "estacion_altitud", "distancia_km", "delta_altitud",
                    "confianza", "veranos", "noches_tropicales_año")
    SALIDA_CRUCE.write_text(json.dumps(
        {"generado": hoy, "fuentes": FUENTES,
         "municipios": [{c: x[c] for c in campos_cruce} for x in cruce]},
        ensure_ascii=False, indent=1), encoding="utf-8")

    usadas = sorted({x["estacion"] for x in cruce})
    info = {e["id"]: e for e in estaciones}
    SALIDA_INVIERNO.write_text(json.dumps(
        {"generado": hoy, "fuentes": FUENTES,
         "criterio": {"ventana": "1 de noviembre – 31 de marzo",
                      "helada": "noche con temperatura mínima <= 0,0 °C",
                      "sin_heladas": "invierno sin ninguna helada; se evalúa invierno a invierno",
                      "cobertura_minima": COBERTURA_MINIMA,
                      "inviernos_minimos": INVIERNOS_MINIMOS},
         "umbrales": UMBRALES,
         "inviernos": todos_inv,
         "municipios": cruce,
         "estaciones": {i: {"nombre": info[i]["loc"], "provincia": info[i]["prov"],
                            "altitud": info[i]["alt"], "lat": info[i]["lat"], "lon": info[i]["lon"],
                            "serie": {str(inv): v for inv, v in sorted(serie[i].items())}}
                        for i in usadas}},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # ---- Resumen ----
    por_nivel = defaultdict(int)
    for x in cruce:
        por_nivel[x["confianza"]] += 1
    provincias = {x["provincia"] for x in cruce}
    print(f"\nMunicipios con estación de referencia: {len(cruce)} "
          f"({', '.join(f'{n}: {por_nivel[n]}' for n, _, _ in NIVELES)}) · {len(provincias)} provincias")
    for inv in todos_inv:
        libres = sum(1 for s in serie.values() if inv in s and s[inv][k0] == 0)
        con = sum(1 for s in serie.values() if inv in s)
        print(f"  invierno {inv}/{str(inv + 1)[2:]}: {libres} de {con} estaciones sin ninguna helada")
    ult = todos_inv[-1]
    print(f"Municipios cuya estación no registró heladas en {ult}/{str(ult + 1)[2:]}: "
          f"{sum(1 for x in cruce if x['sin_heladas'])}")
    for nombre in ("Dénia", "Xàbia/Jávea"):
        x = next((y for y in cruce if y["nombre"] == nombre), None)
        print(f"  {nombre}: " + (f"estación {x['estacion']} {x['estacion_nombre']} · {x['distancia_km']} km · "
                                 f"desnivel {x['delta_altitud']} m · confianza {x['confianza']} · "
                                 f"{x['heladas_por_año']} heladas/invierno · "
                                 f"{x['inviernos_sin_heladas']} de {x['inviernos']} inviernos sin heladas"
                                 if x else "SIN estación dentro de los radios de confianza"))
    print(f"\nEscrito: {SALIDA_CRUCE.name} ({SALIDA_CRUCE.stat().st_size / 1024:.0f} KB) · "
          f"{SALIDA_INVIERNO.name} ({SALIDA_INVIERNO.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
