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

# Los dos techos que definen "invierno vendible" y "verano dormible". 40 noches
# de calefacción son menos de una de cada cuatro de la temporada; 5 noches
# tropicales al año es el criterio con el que el sitio certifica refugios.
TECHO_INVIERNO = 40
TECHO_VERANO = 5.0
CAJA_TROPICALES = 30  # techo de verano del cuadrante que dibuja la web
BANDAS = [(0, 1), (1, 5), (5, 15), (15, 40), (40, 70), (70, 999)]


def es_canaria(provincia: pd.Series) -> pd.Series:
    """Canarias juega en otra liga y tapa a la península en todas las listas."""
    return provincia.str.contains("PALMAS|CRUZ DE T|TENERIFE", case=False,
                                  na=False)


def mejor_de_banda(sub: pd.DataFrame, lo: float, hi: float):
    """De las estaciones con ese techo de verano, la de invierno más suave."""
    b = sub[(sub["tropicales"] > lo) & (sub["tropicales"] <= hi)]
    if b.empty:
        return None
    return b.loc[b["calefaccion_mediana"].idxmin()]


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


def serie_verano() -> "pd.DataFrame | None":
    """Noches tropicales por estación, del AÑO COMPLETO y con mediana.

    Se usa noches_por_anio.csv y no refugios_nocturnos_ranking.csv a propósito.
    El ranking publica `noches_trop_anio`, que es la MEDIA de jun-ago: dos
    defectos a la vez para lo que aquí se compara. Uno, la ventana jun-ago
    descarta el 21,4 % de las noches tropicales del histórico (en Canarias, más
    de la mitad), y este análisis mide el invierno de noviembre a marzo, así que
    mezclar una ventana recortada con otra completa falsearía el intercambio.
    Dos, es una media. Aquí va la mediana del año natural y el peor año.
    """
    ruta = SALIDA / "noches_por_anio.csv"
    if not ruta.exists():
        return None
    a = pd.read_csv(ruta)
    a = a[a["dias_con_dato"] >= 300]      # años incompletos fuera
    if a.empty:
        return None
    g = a.groupby("indicativo")["noches_trop"]
    return pd.DataFrame({
        "indicativo": g.median().index,
        "tropicales": g.median().values,
        "tropicales_peor": g.max().values,
        "anios_verano": g.size().values,
    })


def cruce_verano(r: pd.DataFrame) -> "pd.DataFrame | None":
    """El hallazgo editorial: el mejor invierno es el peor verano."""
    v = serie_verano()
    if v is None:
        print("\n  (sin noches_por_anio.csv: no se cruza con el verano)")
        return None
    j = r.merge(v, on="indicativo", how="inner")
    j = j[j["anios_verano"] >= MIN_TEMPORADAS]
    if len(j) < 30:
        print(f"\n  (solo {len(j)} estaciones cruzadas: muy pocas)")
        return None
    # Spearman a mano: rangos + Pearson. pandas lo hace con method="spearman",
    # pero eso importa scipy, que NO está en requirements.txt. Añadir una
    # dependencia entera para un coeficiente no compensa, y el workflow se
    # caería en la primera ejecución.
    rho = (j["calefaccion_mediana"].rank()).corr(j["tropicales"].rank())
    print("\n" + "=" * 72)
    print("  EL CRUCE: invierno suave <-> verano invivible")
    print("=" * 72)
    print(f"    {len(j)} estaciones con las dos series completas.")
    print(f"    Spearman entre noches de calefaccion y noches tropicales "
          f"(ano natural): {rho:+.2f}")

    print("\n  LAS DOS CARAS, EN PENINSULA Y BALEARES")
    pen = j[~es_canaria(j["provincia"])]
    for _, f in pen.nsmallest(14, "calefaccion_mediana").iterrows():
        print(f"    {f['nombre'][:30]:30} {f['provincia'][:14]:14} "
              f"calef. {f['calefaccion_mediana']:3.0f}  ·  terraza "
              f"{f['terraza_mediana']:3.0f} d  ·  lluvia "
              f"{f['lluvia_mediana']:3.0f} d  ·  verano "
              f"{f['tropicales']:5.1f} trop.")

    # LA PREGUNTA QUE VALE DINERO: ¿hay algún sitio con las dos cosas?
    ambos = j[(j["calefaccion_mediana"] <= TECHO_INVIERNO) &
              (j["tropicales"] <= TECHO_VERANO)]
    print(f"\n  ¿ALGUN SITIO CON LAS DOS COSAS?")
    print(f"    Criterio: <= {TECHO_INVIERNO} noches de calefaccion Y "
          f"<= {TECHO_VERANO:.0f} noches tropicales al ano.")
    if ambos.empty:
        print(f"    NINGUNA de las {len(j)} estaciones lo cumple.")
    else:
        for _, f in ambos.sort_values("calefaccion_mediana").iterrows():
            print(f"    {f['nombre'][:30]:30} {f['provincia'][:14]:14} "
                  f"{f['calefaccion_mediana']:3.0f} calef. · "
                  f"{f['tropicales']:.1f} trop. · terraza "
                  f"{f['terraza_mediana']:.0f} d · lluvia "
                  f"{f['lluvia_mediana']:.0f} d")

    print("\n  LA FRONTERA DEL COMPROMISO: lo mejor que se puede pedir")
    for etq, sub in (("Peninsula y Baleares", j[~es_canaria(j["provincia"])]),
                     ("Canarias", j[es_canaria(j["provincia"])])):
        print(f"\n    -- {etq}")
        for lo, hi in BANDAS:
            f = mejor_de_banda(sub, lo, hi)
            if f is None:
                continue
            print(f"       verano {lo:3.0f}-{min(hi, 99):3.0f} trop.  ->  "
                  f"{f['nombre'][:27]:27} {f['provincia'][:12]:12} "
                  f"{f['calefaccion_mediana']:3.0f} calef. · "
                  f"{f['terraza_mediana']:3.0f} d terraza · "
                  f"{f['lluvia_mediana']:3.0f} d lluvia")
    return j


# Las estaciones que un lector extranjero reconoce, agrupadas por el papel que
# juegan en el relato. Nombre EXACTO del catálogo de AEMET: el sitio no
# interpola ni promedia estaciones vecinas, así que cada fila publicada dice de
# qué termómetro sale. Ojo con las ciudades que tienen varias: MÁLAGA (centro)
# y MÁLAGA AEROPUERTO difieren en 46 noches de calefacción, que es el efecto de
# isla de calor, no un error.
CIUDADES_WEB = [
    ("winter", "MÁLAGA", "Malaga"),
    ("winter", "MARBELLA", "Marbella"),
    ("winter", "ESTEPONA", "Estepona"),
    ("winter", "NERJA", "Nerja"),
    ("winter", "CÁDIZ", "Cadiz"),
    ("winter", "ALMERÍA AEROPUERTO", "Almeria"),
    ("winter", "ALACANT/ALICANTE", "Alicante"),
    ("winter", "BENIDORM", "Benidorm"),
    ("winter", "MURCIA", "Murcia"),
    ("winter", "VALENCIA AEROPUERTO", "Valencia"),
    ("winter", "PALMA, PUERTO", "Palma de Mallorca"),
    ("winter", "BARCELONA, DRASSANES", "Barcelona"),
    ("canary", "TENERIFE SUR AEROPUERTO", "Tenerife South"),
    ("canary", "LANZAROTE AEROPUERTO", "Lanzarote"),
    ("canary", "LAS PALMAS DE GRAN CANARIA, SAN CRISTOBAL", "Las Palmas"),
    ("canary", "SAN ANDRÉS Y SAUCES", "San Andres y Sauces (La Palma)"),
    ("summer", "A CORUÑA", "A Coruna"),
    ("summer", "ESTACA DE BARES", "Estaca de Bares"),
    ("summer", "SANTANDER", "Santander"),
    ("summer", "DONOSTIA / SAN SEBASTIÁN, IGELDO", "San Sebastian"),
    ("summer", "BILBAO AEROPUERTO", "Bilbao"),
    ("summer", "VIGO", "Vigo"),
    ("inland", "MADRID, RETIRO", "Madrid"),
    ("inland", "SEVILLA AEROPUERTO", "Seville"),
    ("inland", "GRANADA-CARTUJA", "Granada"),
]


def frontera_pareto(j: pd.DataFrame) -> pd.DataFrame:
    """Las estaciones que nadie mejora en las DOS cosas a la vez.

    Una estación está en la frontera si ninguna otra tiene a la vez menos
    noches de calefacción y menos noches tropicales. Es la forma honesta de
    responder «¿dónde está el mejor clima de España?»: no hay un ganador, hay
    un conjunto de opciones no dominadas, y su tamaño es la noticia.
    """
    j = j.sort_values(["calefaccion_mediana", "tropicales"])
    fila, mejor = [], float("inf")
    for _, f in j.iterrows():
        if f["tropicales"] < mejor:
            fila.append(f)
            mejor = f["tropicales"]
    return pd.DataFrame(fila)


def _fila_web(f) -> dict:
    return {
        "estacion": f["nombre"],
        "provincia": f["provincia"],
        "altitud": int(f["altitud"]) if pd.notna(f["altitud"]) else None,
        "calefaccion": int(f["calefaccion_mediana"]),
        "calefaccion_peor": int(f["calefaccion_peor"]),
        "tropicales": float(f["tropicales"]),
        "terraza": int(f["terraza_mediana"]),
        "lluvia": int(f["lluvia_mediana"]),
        "heladas": int(f["heladas_mediana"]),
        "temporadas": int(f["temporadas"]),
    }


def vacio_temporada_a_temporada(t: pd.DataFrame) -> dict:
    """¿El hueco peninsular está vacío CADA temporada, o solo en la mediana?

    Es una comprobación distinta y más exigente: que ninguna estación tenga las
    dos cosas en la mediana de nueve años no implica que no las tuviera en
    algún año suelto. Se cruza cada temporada de invierno con el verano que la
    sigue y se cuenta. Sin esto, la frase "y ha estado vacío todos los años"
    sería una suposición.
    """
    a = pd.read_csv(SALIDA / "noches_por_anio.csv")
    a = a[a["dias_con_dato"] >= 300]
    pen = t[~es_canaria(t["provincia"])].copy()
    # La temporada 2024-25 termina en marzo de 2025: le toca el verano de 2025.
    pen["anio_verano"] = pen["temporada"].str[:4].astype(int) + 1
    j = pen.merge(a[["indicativo", "anio", "noches_trop"]],
                  left_on=["indicativo", "anio_verano"],
                  right_on=["indicativo", "anio"])
    if j.empty:
        return {"temporadas": 0, "pares": 0, "dobles": 0}
    dobles = j[(j["noches_calefaccion"] <= TECHO_INVIERNO) &
               (j["noches_trop"] <= CAJA_TROPICALES)]
    return {"temporadas": int(j["temporada"].nunique()),
            "pares": len(j), "dobles": len(dobles)}


def guardar_json_web(t: pd.DataFrame, j: pd.DataFrame, ruta: Path) -> None:
    """Las cifras que consume la landing inglesa. Sin JSON no hay página."""
    import json
    temps = sorted(t["temporada"].unique())
    fr = frontera_pareto(j)
    ciudades = []
    for papel, estacion, etiqueta in CIUDADES_WEB:
        # .strip(): el catálogo de AEMET trae nombres con espacio final ("VIGO ").
        m = j[j["nombre"].str.strip() == estacion]
        if m.empty:
            print(f"   (aviso: '{estacion}' no está en el cruce; se omite)")
            continue
        d = _fila_web(m.iloc[0])
        d["papel"], d["etiqueta"] = papel, etiqueta
        ciudades.append(d)
    ambos = j[(j["calefaccion_mediana"] <= TECHO_INVIERNO) &
              (j["tropicales"] <= TECHO_VERANO)]
    tot = int(t["noches_calefaccion"].sum())
    nuc = int(t["calefaccion_nucleo"].sum())
    hel_t, hel_n = int(t["heladas"].sum()), int(t["heladas_nucleo"].sum())
    datos = {
        "periodo": {
            "temporadas": len(temps), "ini": temps[0], "fin": temps[-1],
            "estaciones": int(j["indicativo"].nunique()),
            "dias_temporada": DIAS_TEMPORADA,
        },
        "umbrales": {
            "calefaccion": CALEFACCION, "terraza": TERRAZA, "helada": HELADA,
            "lluvia": LLUVIA, "techo_invierno": TECHO_INVIERNO,
            "techo_verano": TECHO_VERANO,
        },
        "correlacion": {"rho": round(float(
            j["calefaccion_mediana"].rank().corr(j["tropicales"].rank())), 2),
            "n": len(j)},
        "frontera": [_fila_web(f) for _, f in fr.iterrows()],
        "ambos": [_fila_web(f) for _, f in
                  ambos.sort_values("calefaccion_mediana").iterrows()],
        "ciudades": ciudades,
        # La nube entera, redondeada: es lo que hace ver de un vistazo que el
        # cuadrante bueno está vacío. 828 puntos pesan ~12 KB.
        "nube": [[int(f["calefaccion_mediana"]), round(float(f["tropicales"]), 1),
                  1 if es_canaria(pd.Series([f["provincia"]])).iloc[0] else 0]
                 for _, f in j.iterrows()],
        "sin_helada": int((j["heladas_peor"] == 0).sum()),
        "vacio": vacio_temporada_a_temporada(t),
        "hombro": {
            "cuota_dias": round(100 * 61 / DIAS_TEMPORADA, 1),
            "calefaccion": round(100 * (tot - nuc) / tot, 1),
            "heladas": round(100 * (hel_t - hel_n) / hel_t, 1),
        },
        "fuente": "AEMET OpenData · valores climatológicos diarios",
    }
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    print(f"-> {ruta}  ({ruta.stat().st_size // 1024} KB, datos para la landing)")


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
    j = cruce_verano(r)
    if j is not None:
        guardar_json_web(t, j, ROOT.parent / "docs" / "estudios" /
                         "invierno-datos.json")
    print(f"\n-> analisis/invierno_por_temporada.csv  ({len(t)} filas)")
    print(f"-> analisis/invierno_por_estacion.csv   ({len(r)} filas)")


if __name__ == "__main__":
    main()
