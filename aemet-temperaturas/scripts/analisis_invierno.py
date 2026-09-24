#!/usr/bin/env python3
"""
La otra mitad del año: cómo es de verdad el invierno español, medido.

El mercado del "winter sun" se vende con medias mensuales —«Málaga, 17 °C de
media en enero»— y esa cifra no responde a ninguna de las preguntas que se hace
quien va a pasar tres meses aquí: cuántas noches voy a encender la calefacción,
cuántos días voy a poder comer en la calle, cuánto dura el peor tramo. Una media
de 17° sale igual con veinte días templados que con diez de 24° y diez de 10°.

Así que aquí NO hay medias. Hay conteos por umbral, rachas consecutivas y
extremos, exactamente el mismo criterio con el que el sitio mide el verano.

LA TEMPORADA. Se usa el 1 de noviembre → 31 de marzo, y se etiqueta por el año
en que empieza: «2024-25». No es una ventana astronómica (el proyecto ya
demostró que el día más frío llega +24 días después del solsticio, así que
diciembre-febrero no es «el invierno», es una convención). Es la ventana de
mercado: la estancia larga de quien huye de su invierno. Y se mide además
diciembre-febrero por separado, para poder decir cuánto se pierde mirando solo
al núcleo — la misma pregunta que en verano destapó que jun-ago descarta el
21,4 % de las noches tropicales.

Salidas en analisis/:
- invierno_por_temporada.csv — una fila por estación y temporada
- invierno_por_estacion.csv  — resumen por estación, con extremos y medianas

Uso:
    python scripts/analisis_invierno.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATOS = ROOT / "datos"
SALIDA = ROOT / "analisis"
SALIDA.mkdir(exist_ok=True)

# --- Umbrales -------------------------------------------------------------
# Cada uno responde a una pregunta concreta, no a una convención meteorológica.
CALEFACCION = 10.0   # tmin por debajo: la noche pide calefacción
NOCHE_FRIA = 5.0     # tmin por debajo: frío de verdad dentro de casa
HELADA = 0.0         # tmin por debajo: hiela
HELADA_FUERTE = -3.0
TERRAZA = 18.0       # tmax por encima: se puede comer fuera
TERRAZA_HOLGADA = 20.0
LLUVIA = 1.0         # mm: día de lluvia de verdad, no llovizna

INICIO = (11, 1)     # 1 de noviembre
FIN = (3, 31)        # 31 de marzo
DIAS_TEMPORADA = 151
MIN_DIAS = 120       # ~80 % de cobertura para que la temporada cuente
MIN_TEMPORADAS = 5   # para entrar en el resumen por estación


def rutas_diarios() -> list[Path]:
    """Los CSV diarios, EMPEZANDO por el rolling.

    El rolling (diarios_estaciones.csv) trae los días que aún no han cerrado su
    fichero anual. Olvidarlo fue el bug que hizo que el sitio publicara nueve
    veranos teniendo diez: diarios_2026.csv terminaba en mayo y el verano en
    curso era invisible. Va primero para que, al deduplicar, gane su versión.
    """
    rutas = []
    rolling = DATOS / "diarios_estaciones.csv"
    if rolling.exists():
        rutas.append(rolling)
    rutas += sorted(DATOS.glob("diarios_2*.csv"))
    return rutas


def cargar() -> pd.DataFrame:
    """Todos los días de invierno de la serie, en un DataFrame."""
    trozos = []
    for ruta in rutas_diarios():
        d = pd.read_csv(
            ruta,
            usecols=["fecha", "indicativo", "nombre", "provincia", "altitud",
                     "tmin", "tmax", "prec"],
            dtype={"indicativo": "string", "nombre": "string",
                   "provincia": "string"},
        )
        d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce")
        d = d[d["fecha"].notna()]
        # Solo los meses de la temporada: recorta la memoria a la mitad larga.
        d = d[d["fecha"].dt.month.isin([11, 12, 1, 2, 3])]
        if not d.empty:
            trozos.append(d)
    if not trozos:
        sys.exit("No hay ficheros diarios en datos/. Nada que analizar.")
    d = pd.concat(trozos, ignore_index=True)
    # El rolling va primero, así que keep='first' se queda con su versión.
    d = d.drop_duplicates(subset=["indicativo", "fecha"], keep="first")
    for col in ("tmin", "tmax", "prec", "altitud"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    # Etiqueta de temporada: noviembre y diciembre pertenecen a la que empieza
    # ese año; enero, febrero y marzo, a la que empezó el anterior.
    anio = d["fecha"].dt.year
    d["temporada"] = (anio.where(d["fecha"].dt.month >= 11, anio - 1)
                      .astype(int))
    d["nucleo"] = d["fecha"].dt.month.isin([12, 1, 2])
    return d.sort_values(["indicativo", "fecha"])


def racha_maxima(fechas: pd.Series, marca: pd.Series) -> int:
    """Racha de días consecutivos con la marca puesta.

    Exige que los días sean contiguos de verdad: si falta un día en medio, la
    racha se corta en vez de saltar el hueco. Un hueco no es una noche templada.
    """
    mejor = act = 0
    prev = None
    for f, m in zip(fechas, marca):
        if not m:
            act = 0
        else:
            act = act + 1 if prev is not None and (f - prev).days == 1 else 1
            mejor = max(mejor, act)
        prev = f
    return mejor


def fecha_de(g: pd.DataFrame, col: str, buscar_max: bool) -> str:
    """La fecha del valor extremo de una columna, o '' si no hay dato."""
    s = g[col]
    if s.notna().sum() == 0:
        return ""
    i = s.idxmax() if buscar_max else s.idxmin()
    return g.loc[i, "fecha"].date().isoformat()


def por_temporada(d: pd.DataFrame) -> pd.DataFrame:
    """Una fila por estación y temporada. Conteos y rachas, ningún promedio."""
    filas = []
    for (ind, temp), g in d.groupby(["indicativo", "temporada"], sort=False):
        con_tmin = g["tmin"].notna()
        if int(con_tmin.sum()) < MIN_DIAS:
            continue
        gt = g[con_tmin]
        con_tmax = g["tmax"].notna()
        gx = g[con_tmax]
        nuc = gt[gt["nucleo"]]
        filas.append({
            "indicativo": ind,
            "temporada": f"{temp}-{str(temp + 1)[2:]}",
            "nombre": g["nombre"].iloc[0],
            "provincia": g["provincia"].iloc[0],
            "altitud": g["altitud"].iloc[0],
            "dias_tmin": int(con_tmin.sum()),
            "dias_tmax": int(con_tmax.sum()),
            # Noches: lo que se paga en calefacción.
            "noches_calefaccion": int((gt["tmin"] < CALEFACCION).sum()),
            "noches_frias": int((gt["tmin"] < NOCHE_FRIA).sum()),
            "heladas": int((gt["tmin"] < HELADA).sum()),
            "heladas_fuertes": int((gt["tmin"] < HELADA_FUERTE).sum()),
            # Lo mismo, pero solo en dic-feb: cuánto se pierde con el núcleo.
            "calefaccion_nucleo": int((nuc["tmin"] < CALEFACCION).sum()),
            "heladas_nucleo": int((nuc["tmin"] < HELADA).sum()),
            # Días: lo que se viene a buscar.
            "dias_terraza": int((gx["tmax"] >= TERRAZA).sum()) if len(gx) else 0,
            "dias_terraza_20": (int((gx["tmax"] >= TERRAZA_HOLGADA).sum())
                                if len(gx) else 0),
            "dias_lluvia": int((g["prec"] >= LLUVIA).sum()),
            # Rachas: el tramo que de verdad se recuerda.
            "racha_terraza": racha_maxima(gx["fecha"], gx["tmax"] >= TERRAZA),
            "racha_sin_terraza": racha_maxima(gx["fecha"], gx["tmax"] < TERRAZA),
            "racha_heladas": racha_maxima(gt["fecha"], gt["tmin"] < HELADA),
            # Extremos con su fecha, nunca una media.
            "tmin_p05": round(float(gt["tmin"].quantile(0.05)), 1),
            "tmin_min": round(float(gt["tmin"].min()), 1),
            "tmin_min_fecha": fecha_de(gt, "tmin", False),
            "tmax_max": round(float(gx["tmax"].max()), 1) if len(gx) else None,
            "tmax_max_fecha": fecha_de(gx, "tmax", True) if len(gx) else "",
        })
    return pd.DataFrame(filas)


def por_estacion(t: pd.DataFrame) -> pd.DataFrame:
    """Resumen por estación: peor temporada, mejor, última y medianas.

    Mediana y extremos, nunca media: promediar un invierno duro con uno suave
    inventa uno templado que no ocurrió, que es el error que este proyecto
    lleva denunciando desde el principio.
    """
    filas = []
    for ind, g in t.groupby("indicativo", sort=False):
        if len(g) < MIN_TEMPORADAS:
            continue
        g = g.sort_values("temporada")
        peor = g.loc[g["noches_calefaccion"].idxmax()]
        mejor = g.loc[g["noches_calefaccion"].idxmin()]
        ult = g.iloc[-1]
        filas.append({
            "indicativo": ind,
            "nombre": g["nombre"].iloc[0],
            "provincia": g["provincia"].iloc[0],
            "altitud": g["altitud"].iloc[0],
            "temporadas": len(g),
            # Lo que se paga
            "calefaccion_mediana": float(g["noches_calefaccion"].median()),
            "calefaccion_peor": int(peor["noches_calefaccion"]),
            "calefaccion_peor_temporada": peor["temporada"],
            "calefaccion_mejor": int(mejor["noches_calefaccion"]),
            "calefaccion_ultima": int(ult["noches_calefaccion"]),
            # Lo que se busca
            "terraza_mediana": float(g["dias_terraza"].median()),
            "terraza_peor": int(g["dias_terraza"].min()),
            "terraza_mejor": int(g["dias_terraza"].max()),
            "racha_sin_terraza_max": int(g["racha_sin_terraza"].max()),
            "racha_terraza_max": int(g["racha_terraza"].max()),
            # Heladas: el criterio binario que decide muchas compras
            "heladas_mediana": float(g["heladas"].median()),
            "heladas_peor": int(g["heladas"].max()),
            "temporadas_sin_helada": int((g["heladas"] == 0).sum()),
            "racha_heladas_max": int(g["racha_heladas"].max()),
            # Lluvia y frío extremo
            "lluvia_mediana": float(g["dias_lluvia"].median()),
            "tmin_p05_peor": float(g["tmin_p05"].min()),
            "tmin_min": float(g["tmin_min"].min()),
            "tmin_min_fecha": g.loc[g["tmin_min"].idxmin(), "tmin_min_fecha"],
            # Cuánto se pierde mirando solo a dic-feb
            "calefaccion_fuera_nucleo": int(
                (g["noches_calefaccion"] - g["calefaccion_nucleo"]).sum()),
            "calefaccion_total": int(g["noches_calefaccion"].sum()),
        })
    return pd.DataFrame(filas)


def informe(t: pd.DataFrame, r: pd.DataFrame) -> None:
    """Las cifras de titular, por pantalla."""
    print()
    print("=" * 72)
    print(f"  {len(t)} temporadas-estación · {r['indicativo'].nunique()} "
          f"estaciones con {MIN_TEMPORADAS}+ temporadas")
    print(f"  Temporadas: {sorted(t['temporada'].unique())[0]} → "
          f"{sorted(t['temporada'].unique())[-1]}  (1 nov – 31 mar)")
    print("=" * 72)

    # 1. Cuánto se pierde mirando solo a diciembre-febrero.
    tot = int(t["noches_calefaccion"].sum())
    nuc = int(t["calefaccion_nucleo"].sum())
    hel_t, hel_n = int(t["heladas"].sum()), int(t["heladas_nucleo"].sum())
    # OJO: aquí la comparación honesta no es el porcentaje a secas, sino el
    # porcentaje CONTRA la cuota de días. Noviembre y marzo son 61 de los 151
    # días de la temporada (40,4 %). Si se llevan el 40 % del frío, no es que
    # "se pierdan": es que pesan lo que les toca. En verano la ventana jun-ago
    # sí concentraba de forma desproporcionada, y por eso allí era noticia.
    cuota = 100 * 61 / DIAS_TEMPORADA
    p_cal = 100 * (tot - nuc) / tot
    p_hel = 100 * (hel_t - hel_n) / hel_t
    print("\n  NOVIEMBRE Y MARZO: ¿temporada baja o invierno igual?")
    print(f"    Son el {cuota:.1f} % de los días de la temporada.")
    print(f"    Se llevan el {p_cal:.1f} % de las noches de calefacción "
          f"(x{p_cal / cuota:.2f} su cuota): el frío general NO se concentra "
          f"en dic-feb.")
    print(f"    Pero solo el {p_hel:.1f} % de las heladas "
          f"(x{p_hel / cuota:.2f}): la helada SÍ se concentra.")
    print("    Traducción: en invierno no hay meses hombro para la "
          "calefacción, sí para el hielo.")

    # 2. Dónde se está mejor: menos calefacción, más terraza.
    print("\n  MENOS NOCHES DE CALEFACCIÓN (mediana de la serie, de 151)")
    for _, f in r.nsmallest(12, "calefaccion_mediana").iterrows():
        print(f"    {f['nombre'][:30]:30} {f['provincia'][:14]:14} "
              f"{f['calefaccion_mediana']:5.0f}  ·  terraza "
              f"{f['terraza_mediana']:3.0f} d  ·  peor invierno "
              f"{f['calefaccion_peor']:3d} ({f['calefaccion_peor_temporada']})")

    print("\n  MÁS DÍAS DE TERRAZA (tmax ≥ 18 °C, mediana de 151)")
    for _, f in r.nlargest(12, "terraza_mediana").iterrows():
        print(f"    {f['nombre'][:30]:30} {f['provincia'][:14]:14} "
              f"{f['terraza_mediana']:5.0f}  ·  racha sin terraza "
              f"{f['racha_sin_terraza_max']:3d} d  ·  heladas "
              f"{f['heladas_mediana']:.0f}")

    print("\n  SOLO PENÍNSULA Y BALEARES (Canarias juega en otra liga)")
    pen = r[~r["provincia"].str.contains("PALMAS|CRUZ DE T|TENERIFE",
                                         case=False, na=False)]
    for _, f in pen.nsmallest(12, "calefaccion_mediana").iterrows():
        print(f"    {f['nombre'][:30]:30} {f['provincia'][:14]:14} "
              f"{f['calefaccion_mediana']:5.0f} noches  ·  terraza "
              f"{f['terraza_mediana']:3.0f} d  ·  heladas "
              f"{f['heladas_mediana']:.0f}  ·  peor invierno "
              f"{f['calefaccion_peor']:3d}")

    # 3. Sin heladas en NINGUNA temporada: el criterio binario.
    cero = r[r["heladas_peor"] == 0]
    print(f"\n  SIN UNA SOLA HELADA en ninguna de sus temporadas: "
          f"{len(cero)} estaciones")
    for _, f in cero.nlargest(10, "terraza_mediana").iterrows():
        print(f"    {f['nombre'][:30]:30} {f['provincia'][:14]:14} "
              f"terraza {f['terraza_mediana']:3.0f} d  ·  mínima absoluta "
              f"{f['tmin_min']:5.1f}° ({f['tmin_min_fecha']})")

    # 4. La media miente: misma mediana de calefacción, inviernos distintos.
    print("\n  LA MEDIANA TAMPOCO BASTA (peor invierno vs mejor, misma estación)")
    print("  Solo entre las de invierno vendible (mediana < 40 noches de "
          "calefacción):")
    r2 = r[r["calefaccion_mediana"] < 40].assign(
        salto=lambda x: x["calefaccion_peor"] - x["calefaccion_mejor"])
    for _, f in r2.nlargest(8, "salto").iterrows():
        print(f"    {f['nombre'][:30]:30} {f['provincia'][:14]:14} "
              f"de {f['calefaccion_mejor']:3d} a {f['calefaccion_peor']:3d} "
              f"noches ({f['salto']:+d}) · mediana {f['calefaccion_mediana']:.0f}")


def cruce_verano(r: pd.DataFrame) -> None:
    """El hallazgo editorial: el mejor invierno es el peor verano.

    Cruza con el ranking nocturno de verano, que es la fuente de verdad de la
    web. Si el cruce no está disponible, se dice y se sigue.
    """
    ruta = SALIDA / "refugios_nocturnos_ranking.csv"
    if not ruta.exists():
        print("\n  (sin refugios_nocturnos_ranking.csv: no se cruza con verano)")
        return
    v = pd.read_csv(ruta)
    col_ind = next((c for c in v.columns if c.lower() in
                    ("indicativo", "idema", "estacion")), None)
    col_nt = next((c for c in v.columns
                   if c.lower() in ("noches_trop_anio", "noches_tropicales")
                   or "tropical" in c.lower()), None)
    if not col_ind or not col_nt:
        print(f"\n  (ranking de verano sin columnas esperadas: {list(v.columns)[:8]})")
        return
    j = r.merge(v[[col_ind, col_nt]].rename(
        columns={col_ind: "indicativo", col_nt: "noches_tropicales"}),
        on="indicativo", how="inner")
    if len(j) < 30:
        print(f"\n  (solo {len(j)} estaciones cruzadas: muy pocas)")
        return
    rho = j["calefaccion_mediana"].corr(j["noches_tropicales"], method="spearman")
    print("\n" + "=" * 72)
    print("  EL CRUCE: invierno suave ↔ verano invivible")
    print("=" * 72)
    print(f"    {len(j)} estaciones con las dos series.")
    print(f"    Correlación de Spearman entre noches de calefacción y noches "
          f"tropicales: {rho:+.2f}")
    print("    (negativa = cuanto menos calefacción en invierno, más noches "
          "tropicales en verano)")
    print("\n  LAS DOS CARAS, EN PENÍNSULA Y BALEARES")
    pen = j[~j["provincia"].str.contains("PALMAS|CRUZ DE T|TENERIFE",
                                         case=False, na=False)]
    for _, f in pen.nsmallest(14, "calefaccion_mediana").iterrows():
        print(f"    {f['nombre'][:30]:30} {f['provincia'][:14]:14} "
              f"calef. {f['calefaccion_mediana']:3.0f}  ·  terraza "
              f"{f['terraza_mediana']:3.0f} d  ·  lluvia "
              f"{f['lluvia_mediana']:3.0f} d  ·  verano "
              f"{f['noches_tropicales']:5.1f} trop.")

    # LA PREGUNTA QUE VALE DINERO: ¿hay algún sitio con las dos cosas?
    # Si la respuesta es "ninguno", esa frase es el titular y además es un
    # dato verificable, no una opinión.
    INV, VER = 40, 5.0
    ambos = j[(j["calefaccion_mediana"] <= INV) &
              (j["noches_tropicales"] <= VER)]
    print(f"\n  ¿ALGÚN SITIO CON LAS DOS COSAS?")
    print(f"    Criterio: <= {INV} noches de calefacción en invierno "
          f"Y <= {VER:.0f} noches tropicales en verano.")
    if ambos.empty:
        print(f"    NINGUNA de las {len(j)} estaciones lo cumple.")
    else:
        for _, f in ambos.sort_values("calefaccion_mediana").iterrows():
            print(f"    {f['nombre'][:30]:30} {f['provincia'][:14]:14} "
                  f"{f['calefaccion_mediana']:3.0f} noches calef. · "
                  f"{f['noches_tropicales']:.1f} trop. · terraza "
                  f"{f['terraza_mediana']:.0f} d · lluvia "
                  f"{f['lluvia_mediana']:.0f} d · {f['temporadas']} temporadas")

    # La frontera del compromiso: por cada BANDA de verano, el invierno más
    # suave que se puede conseguir. En bandas y no acumulado, porque acumulando
    # gana siempre la misma estación y no se ve la forma del intercambio.
    # Separado península/Canarias: son dos mercados y dos climas.
    print("\n  LA FRONTERA DEL COMPROMISO: lo mejor que se puede pedir")
    bandas = [(0, 1), (1, 5), (5, 15), (15, 40), (40, 70), (70, 999)]
    for etq, sub in (("Península y Baleares",
                      j[~j["provincia"].str.contains("PALMAS|CRUZ DE T|TENERIFE",
                                                     case=False, na=False)]),
                     ("Canarias",
                      j[j["provincia"].str.contains("PALMAS|CRUZ DE T|TENERIFE",
                                                    case=False, na=False)])):
        print(f"\n    -- {etq}")
        for lo, hi in bandas:
            b = sub[(sub["noches_tropicales"] > lo) &
                    (sub["noches_tropicales"] <= hi)]
            if b.empty:
                continue
            f = b.loc[b["calefaccion_mediana"].idxmin()]
            print(f"       verano {lo:3.0f}-{min(hi, 99):3.0f} trop.  ->  "
                  f"{f['nombre'][:27]:27} {f['provincia'][:12]:12} "
                  f"{f['calefaccion_mediana']:3.0f} noches calef. · "
                  f"{f['terraza_mediana']:3.0f} d terraza · "
                  f"{f['lluvia_mediana']:3.0f} d lluvia")


def main() -> None:
    d = cargar()
    print(f"-> {len(d):,} días de invierno leídos".replace(",", "."))
    t = por_temporada(d)
    if t.empty:
        sys.exit("Ninguna temporada alcanza la cobertura mínima.")
    r = por_estacion(t)
    t.to_csv(SALIDA / "invierno_por_temporada.csv", index=False)
    r.to_csv(SALIDA / "invierno_por_estacion.csv", index=False)
    informe(t, r)
    cruce_verano(r)
    print(f"\n-> analisis/invierno_por_temporada.csv  ({len(t)} filas)")
    print(f"-> analisis/invierno_por_estacion.csv   ({len(r)} filas)")


if __name__ == "__main__":
    main()
