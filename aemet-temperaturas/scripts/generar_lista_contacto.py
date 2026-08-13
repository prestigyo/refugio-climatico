#!/usr/bin/env python3
"""Lista de trabajo para la campaña de certificados: a quién escribir y con qué.

El problema que resuelve: los certificados llevan el nombre de la ESTACIÓN de
AEMET, no el del municipio. «Cerler, Cogulla» está a 2.374 m y es la estación de
esquí; el pueblo es Benasque, a 1.120 m, y tiene su propia estación y su propio
certificado. Mandarle al ayuntamiento el de la Cogulla es darle un motivo para
discutir el dato en la primera respuesta.

Aquí se cruza cada estación certificada con la población más cercana de
datos/lugares.csv y sale una fila por municipio, con:

  · el certificado que hay que enviarle (el de su estación más cercana),
  · a qué distancia y a cuánta altura está esa estación de su pueblo,
  · y una marca de «pueblo» o «montaña» para las 31 estaciones que están en
    cumbres, pistas de esquí, embalses o aeropuertos, donde no vive nadie y por
    tanto no hay ayuntamiento al que escribir.

Se certifica lo mismo que en generar_certificados.py: menos de una noche
tropical al año de media.

    python generar_lista_contacto.py

Escribe aemet-temperaturas/lista_contacto.csv, que se abre con Excel.
"""
import csv
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generar_calculadora as g   # noqa: E402  (para slug, PROVINCIAS, titular)

RAIZ = Path(__file__).resolve().parent.parent
LUGARES = RAIZ / "datos" / "lugares.csv"
SALIDA = RAIZ / "lista_contacto.csv"

# Nombres de estación que delatan un sitio donde no vive nadie. Miden bien, pero
# no representan a un pueblo y no tienen ayuntamiento al que escribir.
NO_HABITADO = re.compile(
    r"\b(?:esqu[ií]|radiotelesc\w*|observatorio|embalse|pantano|presa|"
    r"aeropuerto|aer[oó]dromo|faro|ca[nñ]adas|mirador|llac|refugio|"
    r"pico|pe[nñ]a|puig|coll|port)\b|puerto de[l]? ", re.I)

# Con límites de palabra: sin ellos, «Villacarriedo» se tomaba por montaña
# porque contiene «llac», y «Puerto del Pico» se colaba como pueblo porque el
# patrón exigía «puerto de» y allí pone «puerto del».
ALTITUD_MONTANA = 1600
# Si la estación está más lejos que esto del pueblo, conviene decirlo en el
# correo antes de que lo diga el secretario del ayuntamiento.
LEJOS_KM = 6.0


def km(a_la, a_lo, b_la, b_lo) -> float:
    return math.hypot((a_la - b_la) * 111.0, (a_lo - b_lo) * 85.0)


def main() -> None:
    estaciones, _ = g.cargar_estaciones()
    certificadas = [e for e in estaciones if e["nt"] < 1]
    print(f"{len(estaciones)} estaciones · {len(certificadas)} con certificado")

    if not LUGARES.exists():
        sys.exit(f"falta {LUGARES}")
    lugares = []
    with LUGARES.open(encoding="utf-8", newline="") as fh:
        for f in csv.DictReader(fh):
            # Las aldeas no tienen ayuntamiento: para escribir hace falta un
            # municipio, así que se buscan solo entre los que no son aldea.
            if f.get("tipo") == "aldea":
                continue
            try:
                lugares.append((f["nombre"], float(f["lat"]), float(f["lon"]),
                                f.get("provincia", "")))
            except (KeyError, ValueError):
                continue
    print(f"{len(lugares)} municipios y núcleos con los que cruzar")

    filas = []
    for e in certificadas:
        mejor, dist = None, 1e9
        for nom, la, lo, prov in lugares:
            d = km(e["lat"], e["lon"], la, lo)
            if d < dist:
                dist, mejor = d, (nom, prov)
        montana = bool(NO_HABITADO.search(e["loc"])) or e["alt"] > ALTITUD_MONTANA
        aviso = []
        if montana:
            aviso.append("estación de montaña: NO escribir como si fuera el pueblo")
        if dist > LEJOS_KM:
            aviso.append(f"la estación está a {dist:.0f} km del pueblo")
        filas.append({
            "municipio": mejor[0] if mejor else "",
            "provincia": e["prov"],   # la de AEMET: la del pueblo falla en las rayas
            "tipo": "montaña" if montana else "pueblo",
            "estacion": e["loc"],
            "altitud_estacion_m": e["alt"],
            "distancia_km": round(dist, 1),
            "noches_tropicales_ano": e["nt"],
            "tmin_media_verano": e["tmin"],
            "certificado": f"{g.SITE_URL}/certificados/{g.slug(e['loc'])}/",
            "pagina_provincia": f"{g.SITE_URL}/{g.slug(e['prov'])}/",
            "buscar_ayuntamiento": (
                "https://www.google.com/search?q=" +
                (f"ayuntamiento+de+{mejor[0]}+web+oficial" if mejor else "").replace(" ", "+")),
            "aviso": " · ".join(aviso),
        })

    # Una fila por municipio: si varias estaciones caen en el mismo pueblo, se
    # queda la MÁS CERCANA y de pueblo, que es la que hay que enviar. Benasque
    # se queda con Benasque, no con la Cogulla.
    porm = {}
    for f in filas:
        clave = (f["municipio"], f["provincia"])
        actual = porm.get(clave)
        if actual is None:
            porm[clave] = f
            continue
        mejor_ahora = (f["tipo"] == "pueblo", -f["distancia_km"])
        mejor_antes = (actual["tipo"] == "pueblo", -actual["distancia_km"])
        if mejor_ahora > mejor_antes:
            porm[clave] = f

    orden = sorted(porm.values(),
                   key=lambda f: (f["tipo"] != "pueblo", f["distancia_km"],
                                  f["noches_tropicales_ano"]))
    with SALIDA.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(orden[0].keys()))
        w.writeheader()
        w.writerows(orden)

    pueblos = sum(1 for f in orden if f["tipo"] == "pueblo")
    lejos = sum(1 for f in orden if f["distancia_km"] > LEJOS_KM)
    print(f"\n{SALIDA.name}: {len(orden)} municipios")
    print(f"   a los que se puede escribir (pueblo): {pueblos}")
    print(f"   estaciones de montaña, apartadas:     {len(orden) - pueblos}")
    print(f"   con la estación a más de {LEJOS_KM:.0f} km:        {lejos}")


if __name__ == "__main__":
    main()
