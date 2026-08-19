#!/usr/bin/env python3
"""Saca las cifras del Observatorio del Descanso para la página del estudio.

De dónde salen los datos: la hoja de cálculo del Observatorio (la misma que
alimenta apps_script_observatorio.gs). Archivo → Descargar → CSV, y se guarda en
aemet-temperaturas/datos/privado/noches.csv.

ESE CSV NO SE SUBE AL REPO. La hoja es anónima —no hay nombres ni correos— pero
fila a fila lleva fecha, celda de un kilómetro e identificador de navegador, y
en un pueblo de sesenta habitantes eso señala a una casa. Lo que se publica es
el JSON agregado que sale de aquí, no las noches sueltas. Por eso la carpeta se
llama privado/: para que no se cuele en una subida.

Qué escribe: docs/estudios/noches-datos.json, que generar_calculadora.py lee
para construir /deuda-de-sueno/. Mismo patrón que estudio_colores.py con
estudio-datos.json: si el JSON no está, la página sencillamente no se genera.

Cada cuánto: una vez al mes. Con una muestra pequeña, rehacerlo a diario mueve
decimales sin que cambie nada de fondo, y republicar a diario una página que no
cambia es ruido para Google y para quien la lee.

Dos decisiones que condicionan todas las cifras:

  · UNA NOCHE POR DISPOSITIVO Y DÍA. El backend acepta un voto cada 8 horas, y
    con eso alguien puede contar la misma noche a mediodía y otra vez por la
    tarde. Aquí se cuenta una sola vez: se agrupa por dispositivo y fecha y se
    queda la primera. Publicar 27 cuando son 24 noches sería inflar la muestra.

  · LAS APARTADAS CUENTAN AQUÍ. En el mapa no entran hasta que otras noches del
    mismo sitio las respalden —y hacen bien, porque una anomalía suelta no es un
    refugio—, pero este estudio va justo de eso: de lo que la gente dice, no de
    lo que ya hemos dado por bueno. Se cuentan y se dice cuántas son.

    python resumen_noches.py [ruta/al/noches.csv]
"""
import csv
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AEMET_DIR = SCRIPT_DIR.parent
REPO_ROOT = AEMET_DIR.parent
ENTRADA = AEMET_DIR / "datos" / "privado" / "noches.csv"
SALIDA = REPO_ROOT / "docs" / "estudios" / "noches-datos.json"

# Umbral de noche tropical: la mínima no baja de esto. Es el mismo de toda la
# web; si cambiara aquí, las cifras dejarían de ser comparables con el resto.
TROPICAL = 20.0

# Las respuestas de "¿qué has necesitado para dormir?", en el orden del
# cuestionario (ver QBASE en generar_calculadora.py).
RECURSO = {5: "nada", 4: "ventana", 3: "ventilador", 1: "aire", 2: "fuera"}


def num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def pearson(xs, ys):
    """Correlación lineal a mano: aquí no entran dependencias externas."""
    if len(xs) < 3:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    sx = sum((a - mx) ** 2 for a in xs) ** .5
    sy = sum((b - my) ** 2 for b in ys) ** .5
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (sx * sy)


def leer(ruta: Path) -> list:
    with ruta.open(encoding="utf-8-sig", newline="") as fh:
        filas = [f for f in csv.DictReader(fh) if f.get("fecha")]
    # Sin las tres columnas que sostienen el estudio, la fila no sirve.
    return [f for f in filas
            if num(f.get("deuda_sueno")) is not None
            and num(f.get("indice")) is not None
            and num(f.get("ref_aemet")) is not None]


def una_por_noche(filas: list) -> list:
    """Una noche por dispositivo y día natural, la primera que llegó."""
    vistas, fuera = {}, 0
    for f in filas:
        clave = (f.get("dispositivo", ""), f["fecha"][:10])
        if clave in vistas:
            fuera += 1
            continue
        vistas[clave] = f
    return list(vistas.values()), fuera


def grupo(filas: list) -> dict:
    return {"n": len(filas),
            "tmin": round(st.mean([num(f["ref_aemet"]) for f in filas]), 1),
            "deuda": round(st.mean([num(f["deuda_sueno"]) for f in filas]), 1),
            "indice": round(st.mean([num(f["indice"]) for f in filas]), 1)}


def main() -> None:
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else ENTRADA
    if not ruta.exists():
        sys.exit(f"falta {ruta}\n"
                 "Exporta la hoja del Observatorio a CSV y guárdala ahí.")
    todas = leer(ruta)
    N, repetidas = una_por_noche(todas)
    if len(N) < 5:
        sys.exit(f"solo {len(N)} noches utilizables: aún no hay estudio que publicar")

    frescas = [f for f in N if num(f["ref_aemet"]) < TROPICAL]
    tropicales = [f for f in N if num(f["ref_aemet"]) >= TROPICAL]

    # Por población: se publican las que tengan al menos DOS noches. Con una
    # sola, el nombre del pueblo señala a una persona y el dato no dice nada.
    por = defaultdict(list)
    for f in N:
        if f.get("poblacion"):
            por[f["poblacion"]].append(f)
    lugares = []
    for nom, g in por.items():
        if len(g) < 2:
            continue
        d = grupo(g)
        d["lugar"] = nom
        d["dispositivos"] = len({x.get("dispositivo", "") for x in g})
        lugares.append(d)
    lugares.sort(key=lambda d: d["indice"], reverse=True)

    # Las anomalías: donde el sitio se porta distinto de lo que dice su
    # estación. Es el hallazgo que ninguna red de 218 estaciones puede dar, y el
    # motivo por el que la muestra pequeña ya vale para algo.
    anomalias = []
    for f in N:
        des = num(f.get("desvio"))
        if des is None or des < 2.5 or not f.get("poblacion"):
            continue
        anomalias.append({
            "lugar": f["poblacion"],
            "tmin": round(num(f["ref_aemet"]), 1),
            "esperado": round(num(f["esperado"]), 1),
            "dijo": round(num(f["indice"]), 1),
            "deuda": int(num(f["deuda_sueno"])),
            "recurso": RECURSO.get(int(num(f["recurso"]) or 0), "otro"),
            "mejor": num(f["indice"]) > num(f["esperado"]),
        })
    anomalias.sort(key=lambda a: abs(a["dijo"] - a["esperado"]), reverse=True)

    disp = Counter(f.get("dispositivo", "") for f in N)
    cuantos = sorted(disp.values(), reverse=True)
    rec = Counter(RECURSO.get(int(num(f["recurso"]) or 0), "otro") for f in N)
    fechas = sorted(f["fecha"][:10] for f in N)

    datos = {
        "corte": date.today().isoformat(),
        "desde": fechas[0], "hasta": fechas[-1],
        "noches": len(N), "respuestas": len(todas), "repetidas": repetidas,
        "dispositivos": len(disp), "poblaciones": len(por),
        "apartadas": sum(1 for f in N if str(f.get("apartada", "")).strip() not in ("", "0")),
        "frescas": grupo(frescas) if frescas else None,
        "tropicales": grupo(tropicales) if tropicales else None,
        "r_tmin_deuda": (lambda r: round(r, 2) if r is not None else None)(
            pearson([num(f["ref_aemet"]) for f in N],
                    [num(f["deuda_sueno"]) for f in N])),
        "r_indice_deuda": (lambda r: round(r, 2) if r is not None else None)(
            pearson([num(f["indice"]) for f in N],
                    [num(f["deuda_sueno"]) for f in N])),
        "reparto": [sum(1 for f in N if int(num(f["deuda_sueno"])) == k)
                    for k in range(1, 6)],
        "recurso": {k: rec.get(k, 0) for k in
                    ("nada", "ventana", "ventilador", "aire", "fuera")},
        "lugares": lugares,
        "anomalias": anomalias[:6],
        # La honestidad de la muestra en un número: cuánto pesa quien más vota.
        "concentracion": round(100.0 * cuantos[0] / len(N)) if cuantos else 0,
        "top3": round(100.0 * sum(cuantos[:3]) / len(N)) if cuantos else 0,
    }

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")

    print(f"{len(todas)} respuestas · {repetidas} repetidas · {len(N)} noches")
    print(f"   {datos['desde']} a {datos['hasta']} · {len(disp)} dispositivos · "
          f"{len(por)} poblaciones · {datos['apartadas']} apartadas")
    if frescas and tropicales:
        print(f"   noche que refresca : n={datos['frescas']['n']:2d} · "
              f"{datos['frescas']['tmin']:.1f} °C · deuda {datos['frescas']['deuda']}/5")
        print(f"   noche tropical     : n={datos['tropicales']['n']:2d} · "
              f"{datos['tropicales']['tmin']:.1f} °C · deuda {datos['tropicales']['deuda']}/5")
    print(f"   r(mínima, deuda) = {datos['r_tmin_deuda']}")
    print(f"   quien más vota aporta el {datos['concentracion']} % de las noches")
    print(f"\n{SALIDA.relative_to(REPO_ROOT)} escrito.")
    print("Sube SOLO ese JSON y regenera: la página /deuda-de-sueno/ sale de ahí.")
    print(f"NO subas {ruta.name}: son las noches una a una y no se publican.")


if __name__ == "__main__":
    main()
