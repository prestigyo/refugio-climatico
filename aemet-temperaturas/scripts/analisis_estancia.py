#!/usr/bin/env python3
"""
Cuánto dura tu estancia decide QUÉ NÚMERO es verdad.

Todo el mercado del viaje a España se describe con cifras mensuales: «Huelva,
18 °C de máxima en noviembre». Esa cifra responde igual de bien —o sea, igual
de mal— a quien viene dos semanas y a quien viene tres meses. Y medido, no son
el mismo sitio:

    Huelva, llegando el 1 de noviembre
      · 2 semanas → 14 días de terraza de 14. Perfecto.
      · 3 meses   → 53 de 90, con un tramo de 25 DÍAS SEGUIDOS sin uno solo,
                    y 60 noches de calefacción.

Con quince días no se distingue de ningún otro sitio del sur: todos dan 14 de
14. Con noventa, el orden se da la vuelta. Por eso este análisis no resume el
año ni la temporada: recorta exactamente la ventana que va a vivir el visitante
y la mide dentro.

QUÉ SE MIDE, y por qué cada métrica es la que es:

  terraza       días que llegaron a 18 °C de máxima — el día utilizable
  sin_terraza   el tramo MÁS LARGO sin ni uno. Para una estancia larga esto
                manda sobre la mediana: lo que no puedes esperar a que pase
  calef         noches por debajo de 10 °C — lo que se paga en calefacción
  helada        noches bajo 0 °C
  tropi         noches de 20 °C o más — lo que no deja dormir
  lluvia        días con 1 mm o más

NADA DE MEDIAS, como en el resto del proyecto. Se guarda el valor de CADA AÑO
por separado, no su promedio, y es la web quien calcula con ellos la mediana,
el peor caso y —lo que de verdad le sirve a quien viene una semana— en cuántos
de los nueve años esa ventana habría cumplido lo que pide. «7 de los últimos 9
noviembres» es una frase que se puede comprobar; «18 °C de media» no.

LA VENTANA empieza el DÍA 1 del mes elegido. Es una simplificación, y la página
la declara: una quincena del 20 de junio al 4 de julio no es la misma que la
del 1 al 14. Se ancla al día 1 para que los nueve años sean nueve muestras
independientes — deslizar la ventana por todo el mes daría 270 ventanas que se
solapan entre sí, y «el 73 % de las quincenas» sonaría a mucho más de lo que
mide.

UN AÑO CUENTA solo si AEMET midió al menos el 90 % de los días de esa ventana,
y una estación se publica solo si le quedan 5 años válidos o más. Un hueco no
es un cero.

Salidas:
  analisis/estancia_por_ventana.csv   — una fila por estación, mes y duración
  docs/en/stays/stations.json         — catálogo (id, nombre, provincia, altitud)
  docs/en/stays/<mes>-<días>.json     — una ventana, con el valor de cada año

Uso:
    python scripts/analisis_estancia.py
    python scripts/analisis_estancia.py --sin-json   # solo el CSV
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATOS = ROOT / "datos"
SALIDA = ROOT / "analisis"
DOCS = ROOT.parent / "docs"
SALIDA.mkdir(exist_ok=True)

# Años COMPLETOS. El año en curso va a medias y una ventana a medias no es una
# ventana: contaría menos días y parecería mejor de lo que fue.
ANIO_INI, ANIO_FIN = 2017, 2025

# Las cinco duraciones del formulario. La clave es la que viaja en la URL.
DURACIONES = {7: "1 week", 14: "2 weeks", 30: "1 month", 90: "3 months",
              182: "6 months"}

COBERTURA_MIN = 0.90   # días medidos sobre días de la ventana
ANIOS_MIN = 5          # años válidos para publicar una estación

CAMPOS = ["terraza", "sin_terraza", "calef", "helada", "tropi", "lluvia"]


def carga() -> pd.DataFrame:
    """Los diarios de los años completos, solo con las columnas que se usan."""
    quiero = {"fecha", "indicativo", "nombre", "provincia", "altitud",
              "tmin", "tmax", "prec"}
    trozos = []
    for anio in range(ANIO_INI, ANIO_FIN + 1):
        f = DATOS / f"diarios_{anio}.csv"
        if not f.exists():
            print(f"   AVISO: falta {f.name}, ese año no entra")
            continue
        trozos.append(pd.read_csv(f, usecols=lambda c: c in quiero,
                                  low_memory=False))
    if not trozos:
        sys.exit("No hay ningún diarios_AAAA.csv: nada que analizar.")
    d = pd.concat(trozos, ignore_index=True)
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce")
    for c in ("tmin", "tmax", "prec"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna(subset=["fecha"])


def matriz(d: pd.DataFrame, idx, est, col: str, op, umbral):
    """Rejilla día × estación: 1 si se cumple, 0 si no, NaN si no hubo medida.

    El NaN es lo importante: sin él, un día que AEMET no midió contaría como
    un día sin helada, y las estaciones con huecos saldrían premiadas.
    """
    p = (d.pivot_table(index="fecha", columns="indicativo", values=col,
                       aggfunc="first")
         .reindex(index=idx, columns=est))
    hay = p.notna().to_numpy()
    return np.where(hay, op(p.to_numpy(), umbral), np.nan).astype(float), hay


def racha_max(bloque: np.ndarray) -> np.ndarray:
    """Tramo más largo de días consecutivos que cumplen, por estación."""
    b = np.nan_to_num(bloque, nan=0.0) > 0.5
    actual = np.zeros(b.shape[1], dtype=np.int16)
    maximo = np.zeros(b.shape[1], dtype=np.int16)
    for fila in b:
        actual = np.where(fila, actual + 1, 0)
        maximo = np.maximum(maximo, actual)
    return maximo


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sin-json", action="store_true",
                    help="no escribir los ficheros de docs/, solo el CSV")
    args = ap.parse_args()

    print("Estancias: qué número es verdad según cuánto te quedes")
    d = carga()
    est = sorted(d["indicativo"].unique())
    idx = pd.date_range(f"{ANIO_INI}-01-01", f"{ANIO_FIN}-12-31", freq="D")
    print(f"   {len(d):,} registros · {len(est)} estaciones · "
          f"{ANIO_INI}-{ANIO_FIN}")

    terraza, hay_tx = matriz(d, idx, est, "tmax", np.greater_equal, 18.0)
    calef, hay_tn = matriz(d, idx, est, "tmin", np.less, 10.0)
    helada, _ = matriz(d, idx, est, "tmin", np.less, 0.0)
    tropi, _ = matriz(d, idx, est, "tmin", np.greater_equal, 20.0)
    lluvia, _ = matriz(d, idx, est, "prec", np.greater_equal, 1.0)
    # La cobertura se mide sobre temperatura: es lo que sostiene cinco de las
    # seis métricas. La lluvia tiene su propio hueco y va dicho en la página.
    hay = hay_tx & hay_tn

    filas, ventanas = [], {}
    for mes in range(1, 13):
        for dias in DURACIONES:
            crudo = {c: [] for c in CAMPOS}
            cob, anios = [], []
            for anio in range(ANIO_INI, ANIO_FIN + 1):
                ini = pd.Timestamp(year=anio, month=mes, day=1)
                fin = ini + pd.Timedelta(days=dias - 1)
                if fin > idx[-1]:
                    continue          # la ventana se saldría de la serie
                a, b = idx.get_loc(ini), idx.get_loc(fin) + 1
                anios.append(anio)
                cob.append(hay[a:b].mean(axis=0))
                crudo["terraza"].append(np.nansum(terraza[a:b], axis=0))
                crudo["sin_terraza"].append(racha_max(1 - terraza[a:b]))
                crudo["calef"].append(np.nansum(calef[a:b], axis=0))
                crudo["helada"].append(np.nansum(helada[a:b], axis=0))
                crudo["tropi"].append(np.nansum(tropi[a:b], axis=0))
                crudo["lluvia"].append(np.nansum(lluvia[a:b], axis=0))
            if not anios:
                continue
            valido = np.array(cob) >= COBERTURA_MIN
            n_val = valido.sum(axis=0)
            vals = {c: np.where(valido, np.array(crudo[c], dtype=float), np.nan)
                    for c in CAMPOS}

            publica = []
            for i, e in enumerate(est):
                if n_val[i] < ANIOS_MIN:
                    continue
                # -1 marca el año sin medida suficiente. No es un cero.
                serie = [[int(v) if np.isfinite(v) else -1 for v in vals[c][:, i]]
                         for c in CAMPOS]
                publica.append([e] + serie)
                with np.errstate(all="ignore"):
                    med = {c: np.nanmedian(vals[c][:, i]) for c in CAMPOS}
                    peor = {c: np.nanmax(vals[c][:, i]) for c in CAMPOS}
                filas.append([e, mes, dias, int(n_val[i])]
                             + [med[c] for c in CAMPOS]
                             + [peor["sin_terraza"], peor["tropi"],
                                np.nanmin(vals["terraza"][:, i])])
            ventanas[(mes, dias)] = {"mes": mes, "dias": dias, "anios": anios,
                                     "campos": CAMPOS, "filas": publica}

    cols = (["indicativo", "mes", "dias", "anios_validos"]
            + [f"{c}_mediana" for c in CAMPOS]
            + ["sin_terraza_peor", "tropi_peor", "terraza_peor"])
    r = pd.DataFrame(filas, columns=cols)
    csv = SALIDA / "estancia_por_ventana.csv"
    r.to_csv(csv, index=False, float_format="%.1f")
    print(f"   {csv.relative_to(ROOT)}: {len(r):,} filas "
          f"({r['indicativo'].nunique()} estaciones × {len(ventanas)} ventanas)")

    if args.sin_json:
        print("   --sin-json: no se escribe docs/")
        return

    destino = DOCS / "en" / "stays"
    destino.mkdir(parents=True, exist_ok=True)
    cat = (d.groupby("indicativo")
           .agg(nombre=("nombre", "first"), prov=("provincia", "first"),
                alt=("altitud", "first")))
    # El cuarto campo marca Canarias. No es decorativo: en invierno las islas
    # copan las listas enteras —pedí terrazas en noviembre y los ocho primeros
    # puestos eran canarios— y sin poder apartarlas la herramienta contesta lo
    # mismo doce meses de doce.
    def canaria(provincia: str) -> int:
        p = provincia.upper()
        return 1 if (p.startswith("LAS PALMAS") or "CRUZ DE TENERIFE" in p) else 0

    catalogo = {e: [" ".join(str(cat.loc[e, "nombre"]).split()).title(),
                    " ".join(str(cat.loc[e, "prov"]).split()).title(),
                    int(cat.loc[e, "alt"]) if pd.notna(cat.loc[e, "alt"]) else 0,
                    canaria(str(cat.loc[e, "prov"]))]
                for e in est if e in cat.index}
    (destino / "stations.json").write_text(
        json.dumps(catalogo, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8")

    peso = 0
    for (mes, dias), v in ventanas.items():
        f = destino / f"{mes:02d}-{dias:03d}.json"
        txt = json.dumps(v, separators=(",", ":"), ensure_ascii=False)
        f.write_text(txt, encoding="utf-8")
        peso += len(txt.encode("utf-8"))
    print(f"   docs/en/stays/: {len(ventanas)} ventanas + catálogo · "
          f"{peso/1024/1024:.1f} MB "
          f"({peso/len(ventanas)/1024:.0f} KB por ventana, que es lo que "
          f"descarga el visitante)")

    # El contraste que sostiene la página: el mismo sitio, dos duraciones.
    def mira(nombre_parcial, mes, dias):
        s = r[(r["mes"] == mes) & (r["dias"] == dias)]
        s = s[s["indicativo"].isin(
            [e for e in catalogo if nombre_parcial.lower() in catalogo[e][0].lower()])]
        return None if s.empty else s.iloc[0]
    for sitio in ("Huelva, Ronda", "Sevilla Aeropuerto"):
        corta, larga = mira(sitio, 11, 14), mira(sitio, 11, 90)
        if corta is None or larga is None:
            continue
        print(f"   {sitio}: 2 semanas → {corta['terraza_mediana']:.0f}/14 de "
              f"terraza · 3 meses → {larga['terraza_mediana']:.0f}/90 y "
              f"{larga['sin_terraza_peor']:.0f} días seguidos sin ninguna")


if __name__ == "__main__":
    main()
