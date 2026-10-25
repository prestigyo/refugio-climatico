#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preparar_datos_video.py — precalcula los datos de la escena del mapa del vídeo pilar.

Cuenta las noches tropicales EXACTAMENTE igual que la página pilar de la web
(generar_calculadora.cargar_tendencia_provincias + _balance_nacional):

  - mismas estaciones: las del ranking de la web (generar_calculadora.cargar_estaciones)
  - misma ventana: junio a septiembre (MESES_VERANO_PILAR)
  - mismo umbral: tmin >= UMBRAL_NOCHE_TROPICAL (20,0 °C)
  - misma completitud: un verano cuenta si tiene >= 90 días con mínima de 122

El acumulador de la web es una variable local de cargar_tendencia_provincias() y
no se puede importar sin tocar generar_calculadora.py, que está fuera de alcance.
Por eso aquí se repite la lectura, y al final se COMPRUEBA que el resultado es el
mismo: se pasan nuestros conteos por el _balance_nacional() de la web y se comparan
sus cifras con las que calcula la propia web. Si no cuadran, el script falla.

Además, para que la animación no enseñe crecimiento de la RED en vez de clima,
el vídeo usa un panel cerrado: solo estaciones con verano válido en TODOS los años
del periodo.

Uso:
    python video/preparar_datos_video.py                 # con comprobación (lee dos veces)
    python video/preparar_datos_video.py --sin-verificar  # rápido

Salida: video/datos/estaciones_video.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / "aemet-temperaturas" / "scripts"
DATOS = RAIZ / "aemet-temperaturas" / "datos"
SALIDA = Path(__file__).resolve().parent / "datos" / "estaciones_video.json"

sys.path.insert(0, str(SCRIPTS))
import generar_calculadora as g  # noqa: E402  (solo lectura: nombres y umbral de la web)

# El mismo mínimo que _balance_nacional() (allí es una constante local, MIN_DIAS).
MIN_DIAS_VERANO = 90
DIAS_VENTANA = 122      # 1 de junio a 30 de septiembre
N_EXTREMOS = 3          # veranos que se promedian al principio y al final
N_LISTA = 5             # estaciones que más suben y más bajan


def contar_pilar(ids: set) -> tuple[dict, int]:
    """{indicativo: {año: [noches_tropicales, dias_con_dato]}} en junio-septiembre.

    Réplica línea a línea de la lectura de cargar_tendencia_provincias(): con
    rutas_diarios(), el rolling diarios_estaciones.csv va primero y manda; una
    fila de un anual cuya (estación, fecha) ya vino del rolling se salta. Devuelve
    también cuántas filas se saltaron así, solo para informar.
    """
    pilar: dict = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    vistos: set = set()
    repetidas = 0
    for path in g.rutas_diarios():
        es_rolling = path.name == "diarios_estaciones.csv"
        with path.open(encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            cab = next(rd, None)
            if not cab:
                continue
            try:
                i_f, i_ind, i_tmin = cab.index("fecha"), cab.index("indicativo"), cab.index("tmin")
            except ValueError:
                continue
            for row in rd:
                if len(row) <= i_tmin:
                    continue
                if row[i_ind] not in ids:
                    continue
                fecha = row[i_f]
                if fecha[5:7] not in g.MESES_VERANO_PILAR:
                    continue
                clave = (row[i_ind], fecha)
                if es_rolling:
                    vistos.add(clave)
                elif clave in vistos:
                    repetidas += 1
                    continue
                try:
                    tmin = float(row[i_tmin])
                except ValueError:
                    continue
                cp = pilar[row[i_ind]][int(fecha[:4])]
                cp[1] += 1
                if tmin >= g.UMBRAL_NOCHE_TROPICAL:
                    cp[0] += 1
    return pilar, repetidas


def verificar_con_la_web(pilar: dict, estaciones: list, anio_bal: int) -> None:
    """Las cifras de la página pilar, calculadas con nuestros conteos y con los de la
    web, tienen que ser idénticas. Si no, el vídeo diría una cosa y la web otra."""
    print("Comprobando contra la web (relee los diarios con generar_calculadora)…")
    _, web = g.cargar_tendencia_provincias(estaciones, anio_bal)
    nuestro = g._balance_nacional(pilar, {}, anio_bal, estaciones)
    claves = ["anio", "anios", "n_veranos", "n_estaciones_bal", "total_nt",
              "media_bal", "media_serie", "n_cero_serie", "ids_cero", "max_nt_medio"]
    distintas = [k for k in claves if web.get(k) != nuestro.get(k)]
    if web["peor"]["id"] != nuestro["peor"]["id"]:
        distintas.append("peor")
    if distintas:
        for k in distintas:
            print(f"  DISTINTO {k}: web={web.get(k)!r}  video={nuestro.get(k)!r}")
        raise SystemExit("El conteo del vídeo no coincide con el de la web.")
    print(f"  OK: mismas cifras que la web ({web['n_estaciones_bal']} estaciones en "
          f"{web['anio']}, {web['total_nt']} noches, media {web['media_bal']:.1f}).")


def cargar_inhomogeneas() -> set:
    ruta = DATOS / "tendencia_estaciones.csv"
    if not ruta.exists():
        return set()
    with ruta.open(encoding="utf-8", newline="") as fh:
        return {f["indicativo"] for f in csv.DictReader(fh)
                if f.get("posible_inhomogeneidad") == "si"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sin-verificar", action="store_true",
                   help="no relee los diarios para comparar con la web")
    a = p.parse_args()

    estaciones, _ = g.cargar_estaciones()
    por_id = {e["id"]: e for e in estaciones}
    print(f"Estaciones de la web: {len(estaciones)}")

    pilar, repetidas = contar_pilar(set(por_id))

    # Periodo: del primer año con datos al último verano CERRADO (el mismo que usa la web).
    anio_fin = g.anio_balance()
    anio_ini = min(a_ for anios in pilar.values() for a_ in anios)
    periodo = list(range(anio_ini, anio_fin + 1))

    # Regla 3: un verano con < 90 días es NULO, no cero.
    anios_estacion = len(por_id) * len(periodo)
    incompletos = sum(1 for ind in por_id for an in periodo
                      if 0 < pilar.get(ind, {}).get(an, [0, 0])[1] < MIN_DIAS_VERANO)
    sin_dato = sum(1 for ind in por_id for an in periodo
                   if pilar.get(ind, {}).get(an, [0, 0])[1] == 0)

    # Regla 1: panel cerrado.
    panel, descartadas_serie, descartadas_coord = [], 0, 0
    for ind, e in por_id.items():
        anios = pilar.get(ind, {})
        if any(anios.get(an, [0, 0])[1] < MIN_DIAS_VERANO for an in periodo):
            descartadas_serie += 1
            continue
        if e.get("lat") is None or e.get("lon") is None or e["lat"] != e["lat"] or e["lon"] != e["lon"]:
            descartadas_coord += 1
            continue
        panel.append((ind, e, {str(an): anios[an][0] for an in periodo}))

    # Regla 4, decidida con el usuario: la marca de tendencia_estaciones.csv NO excluye.
    # El propio análisis avisa de que marca menos series que el azar puro (20,9 % frente
    # a 22,9 % en simulación). Se guarda la marca por estación y se informa del recuento.
    inhomog = cargar_inhomogeneas()
    marcadas = sum(1 for ind, _, _ in panel if ind in inhomog)

    panel.sort(key=lambda x: x[0])
    salida = {
        "generado": date.today().isoformat(),
        "fuente": "AEMET",
        "periodo": [anio_ini, anio_fin],
        "criterio": f"tmin >= {g.UMBRAL_NOCHE_TROPICAL:.1f} °C, junio-septiembre "
                    "(mismo criterio que la página pilar de nochetropical.es)",
        "umbral_completitud_dias": MIN_DIAS_VERANO,
        "panel": {
            "estaciones": len(panel),
            "descartadas_sin_coordenada": descartadas_coord,
            "descartadas_serie_incompleta": descartadas_serie,
            "descartadas_inhomogeneas": 0,
        },
        "nota_inhomogeneidad": (
            f"{marcadas} estaciones del panel llevan posible_inhomogeneidad=si en "
            "tendencia_estaciones.csv. No se excluyen: esa marca, según su propio análisis, "
            "no discrimina mejor que el azar con nueve saltos interanuales."),
        "estaciones": [
            {"indicativo": ind, "nombre": e["loc"], "provincia": e["prov"],
             "lat": e["lat"], "lon": e["lon"], "altitud": e["alt"],
             "posible_inhomogeneidad": ind in inhomog, "noches": noches}
            for ind, e, noches in panel
        ],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    if not a.sin_verificar:
        verificar_con_la_web(pilar, estaciones, anio_fin)

    # ------------------------------------------------------------ resumen
    ini, fin = str(anio_ini), str(anio_fin)
    maximo = max(max(n.values()) for _, _, n in panel)
    quien_max = [(e["loc"], an) for _, e, n in panel for an, v in n.items() if v == maximo]

    def media(n, anios):
        return sum(n[str(x)] for x in anios) / len(anios)

    cambios = []
    for ind, e, n in panel:
        c = media(n, periodo[-N_EXTREMOS:]) - media(n, periodo[:N_EXTREMOS])
        cambios.append((c, ind, e, n))
    cambios.sort(key=lambda x: x[0])
    suben = sum(1 for c, *_ in cambios if c > 0)
    bajan = sum(1 for c, *_ in cambios if c < 0)

    print()
    print("=" * 72)
    print(f"Periodo: {anio_ini}-{anio_fin} ({len(periodo)} veranos)   ·   {salida['criterio']}")
    print(f"Completitud: >= {MIN_DIAS_VERANO} de {DIAS_VENTANA} días con mínima por verano")
    print(f"  años-estación posibles: {anios_estacion}; nulos por verano incompleto: "
          f"{incompletos}; sin ningún dato: {sin_dato}")
    print(f"  filas (estación, fecha) repetidas en los diarios: {repetidas}")
    print(f"PANEL FINAL: {len(panel)} estaciones (de {len(por_id)} de la web)")
    for k, v in salida["panel"].items():
        print(f"  {k}: {v}")
    print(f"  marcadas posible_inhomogeneidad dentro del panel (no excluidas): {marcadas} "
          f"(de {len(inhomog)} marcadas en total)")
    print(f"Máximo de noches tropicales en un verano (escala de color): {maximo}  "
          f"— {', '.join(f'{nm} {an}' for nm, an in quien_max)}")
    con_1_ini = sum(1 for *_, n in panel if n[ini] >= 1)
    con_1_fin = sum(1 for *_, n in panel if n[fin] >= 1)
    print(f"Con >= 1 noche tropical: {con_1_ini} en {ini}, {con_1_fin} en {fin} "
          f"(de {len(panel)})")
    tot_ini = sum(n[ini] for *_, n in panel)
    tot_fin = sum(n[fin] for *_, n in panel)
    print(f"Noches tropicales sumadas del panel: {tot_ini} en {ini}, {tot_fin} en {fin}")
    etq = (f"media {periodo[0]}-{periodo[N_EXTREMOS-1]} frente a "
           f"{periodo[-N_EXTREMOS]}-{periodo[-1]}")
    print(f"Suben {suben}, bajan {bajan}, igual {len(panel) - suben - bajan} ({etq}); "
          f"suben el {100 * suben / len(panel):.1f} %".replace(".", ",", 1))

    def fila(c, ind, e, n):
        return (f"  {e['loc']} ({e['prov']}, {e['alt']} m, {ind}): {c:+.1f} noches/verano"
                f"   ·   {ini}: {n[ini]}  {fin}: {n[fin]}   serie: "
                + " ".join(str(n[str(x)]) for x in periodo))

    print(f"Las {N_LISTA} que MÁS SUBEN ({etq}):")
    for x in reversed(cambios[-N_LISTA:]):
        print(fila(*x))
    print(f"Las {N_LISTA} que MÁS BAJAN:")
    for x in cambios[:N_LISTA]:
        print(fila(*x))
    print(f"Escrito {SALIDA.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
