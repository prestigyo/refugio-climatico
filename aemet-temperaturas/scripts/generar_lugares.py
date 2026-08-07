#!/usr/bin/env python3
"""Rehace datos/lugares.csv: la lista de poblaciones del Observatorio.

Es la lista con la que el navegador pone NOMBRE a la noche que se vota («tu
noche se guarda en Dénia») y con la que se busca cómo se duerme en otro sitio.
No es cosmética: el id de esta lista es la clave con la que el buzón agrupa los
votos, así que un id repetido mezcla las noches de dos pueblos distintos.

Qué arregla respecto a la lista que había (7.157 entradas de GeoNames «cities»):

  1. FALTABAN 881 municipios españoles: no estaban ni por su nombre ni por
     cercanía. Entre ellos Santa Lucía de Tirajana (67.000 hab.), San Vicente
     del Raspeig (55.000), Petrer (35.000), Caravaca de la Cruz, Ames, y los
     concejos asturianos de montaña —Aller, Lena—, que para lo que va esta web
     son de los sitios que más importan. Quien dormía allí no podía contarlo
     con el nombre de su pueblo.
  2. HABÍA 53 ids repetidos (107 filas), y ahora ninguno. Casi todos por lo mismo: el fichero de
     origen mete los BARRIOS de Madrid y Barcelona como si fueran poblaciones, y
     varios se llaman igual que un pueblo de verdad — el barrio de Salamanca y
     Salamanca, el de Ibiza e Ibiza, el de Amposta y Amposta. Sus votos caían en
     el mismo saco. Los barrios se conservan (el calor de una ciudad no es igual
     en Retiro que en Vallecas) pero pasan a llamarse «Salamanca (Madrid)».
  3. FALTABA la provincia en 845 filas; ahora sale del propio GeoNames.

Fuente: GeoNames (CC BY 4.0), fichero ES.txt del volcado oficial. Municipios =
código ADM3; núcleos de población = clase P. Se descarga solo, no hace falta
tener nada preparado.

    python generar_lugares.py            # solo municipios y lo que ya había
    python generar_lugares.py --aldeas   # añade además aldeas y pedanías

Con --aldeas la lista pasa de 8.038 a 20.824 entradas y el fichero que baja el
móvil crece de 132 KB a 362 KB comprimidos. Sirve para que quien duerme en una
aldea de montaña —Bulnes, Trevélez, San Martín de Castañeda— pueda contarlo con
su nombre y no con el del pueblo grande de al lado. Si pesa demasiado, la perilla
es RADIO_ALDEA_KM.
"""
import csv
import io
import math
import re
import sys
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

URL_GEONAMES = "https://download.geonames.org/export/dump/ES.zip"
DATOS = Path(__file__).resolve().parent.parent / "datos"
SALIDA = DATOS / "lugares.csv"

# Un municipio se considera ya cubierto si hay algo a menos de esto: no queremos
# dos entradas para el mismo pueblo con dos grafías, porque son dos sacos de
# votos distintos para un solo sitio.
RADIO_CUBIERTO_KM = 4.0

# Separación mínima entre aldeas para que una entre en la lista. A 1,5 km
# entran ~12.800 y el fichero que baja el móvil pesa 362 KB; subiéndolo a 3 km
# entran bastantes menos y pesa menos. Es la perilla para ajustar el peso.
RADIO_ALDEA_KM = 1.5

# Sitios donde se duerme aunque no sean una población y por eso no salen en
# ningún fichero de poblaciones. Se añaden a mano, uno a uno y con motivo: el
# criterio es que alguien pueda pasar allí la noche y quiera contarlo. Cabrera
# es el primero — parque nacional, con refugio y fondeadero, pero cero censados,
# así que GeoNames solo la conoce como isla. Aquí caben los refugios de montaña
# el día que se quieran meter.
EXTRAS = [
    ("Cabrera", 39.1480, 2.9316, "Illes Balears"),   # Port de Cabrera
]


def sin_tildes(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", sin_tildes(s)).strip("-")
    return s[:40]


def variantes(nombre: str) -> set:
    """«Gijón/Xixón» → {gijon, xixon}. «Puerto de Santa María, El» → añade
    «el puerto de santa maria», que es como lo escribe y lo busca la gente."""
    out = set()
    for parte in nombre.split("/"):
        p = parte.strip()
        if not p:
            continue
        out.add(sin_tildes(p))
        if "," in p:
            base, art = p.rsplit(",", 1)
            out.add(sin_tildes(f"{art.strip()} {base.strip()}"))
    return out


def limpia_provincia(s: str) -> str:
    """GeoNames las escribe en cuatro idiomas y con adornos: «Provincia de
    Teruel», «Province of Asturias», «Província de Barcelona». Aquí se quiere
    «Teruel», que es lo que se enseña al lado del nombre del pueblo."""
    s = re.sub(r"^(?:prov[ií]n[cç]ia|province)\s+(?:de|del|dels|da|d'|of)?\s*",
               "", s, flags=re.I).strip()
    # GeoNames se come el artículo de las que lo llevan pegado al nombre.
    # …y en dos usa la forma valenciana, mientras el resto de la web usa la
    # castellana. Se unifica para que /castellon/ y su gente casen.
    return {"Coruña": "A Coruña", "Rioja": "La Rioja",
            "Castelló": "Castellón", "València": "Valencia"}.get(s, s)


def nombre_legible(nombre: str) -> str:
    """GeoNames escribe «Puerto de Santa María, El». Se le da la vuelta."""
    n = nombre.split("/")[0].strip()
    if "," in n:
        base, art = n.rsplit(",", 1)
        if sin_tildes(art.strip()) in ("el", "la", "los", "las", "l'", "els", "es", "sa"):
            n = f"{art.strip()} {base.strip()}"
    return n


def descargar() -> list:
    print("descargando GeoNames ES…")
    with urllib.request.urlopen(URL_GEONAMES, timeout=180) as r:
        crudo = r.read()
    z = zipfile.ZipFile(io.BytesIO(crudo))
    filas = []
    for linea in z.open("ES.txt"):
        c = linea.decode("utf-8").rstrip("\n").split("\t")
        try:
            filas.append({"nombre": c[1], "lat": float(c[4]), "lon": float(c[5]),
                          "clase": c[6], "codigo": c[7], "adm2": c[11],
                          "pob": int(c[14] or 0)})
        except (IndexError, ValueError):
            continue
    print(f"   {len(filas)} registros")
    return filas


def km(a_la, a_lo, b_la, b_lo) -> float:
    """Suficiente a esta escala: un grado de longitud mide ~85 km a 40°."""
    return math.hypot((a_la - b_la) * 111.0, (a_lo - b_lo) * 85.0)


class Rejilla:
    """Vecino más cercano por casillas de 0,05° (~5 km). Con 30.000 puntos,
    comparar todos contra todos son 900 millones de cuentas; así son unas pocas."""

    def __init__(self, paso=0.05):
        self.paso, self.celdas = paso, {}

    def add(self, la, lo):
        self.celdas.setdefault((int(la / self.paso), int(lo / self.paso)), []).append((la, lo))

    def cerca(self, la, lo, radio_km):
        r = int(radio_km / (self.paso * 85)) + 1
        ci, cj = int(la / self.paso), int(lo / self.paso)
        for i in range(ci - r, ci + r + 1):
            for j in range(cj - r, cj + r + 1):
                for a, o in self.celdas.get((i, j), ()):
                    if km(la, lo, a, o) <= radio_km:
                        return True
        return False


def main(con_aldeas: bool) -> None:
    geo = descargar()
    provincias = {f["adm2"]: limpia_provincia(nombre_legible(f["nombre"]))
                  for f in geo if f["codigo"] == "ADM2"}
    municipios = [f for f in geo if f["codigo"] == "ADM3"]
    nucleos = [f for f in geo if f["clase"] == "P"]
    print(f"   {len(municipios)} municipios · {len(nucleos)} núcleos de población")

    if not SALIDA.exists():
        sys.exit(f"no encuentro {SALIDA}")
    previas = list(csv.DictReader(SALIDA.open(encoding="utf-8", newline="")))
    print(f"lista actual: {len(previas)} entradas")

    salida, ids, nombres, rejilla = [], {}, set(), Rejilla()

    def mete(nombre, la, lo, prov, tipo):
        """Añade una entrada garantizando que el id es único. Si el nombre ya
        está cogido por OTRO sitio, este se desempata con su provincia — en el
        id y también en el nombre visible, porque dos «Salamanca» seguidas en el
        buscador no le sirven a nadie."""
        base = slug(nombre)
        ident = base
        if ident in ids:
            nombre = f"{nombre} ({prov})" if prov else nombre
            ident = slug(nombre)
            n = 1
            while ident in ids:
                n += 1
                ident = f"{slug(nombre)}-{n}"
        ids[ident] = (la, lo)
        nombres.add(sin_tildes(nombre))
        rejilla.add(la, lo)
        salida.append({"id": ident, "nombre": nombre, "lat": round(la, 4),
                       "lon": round(lo, 4), "provincia": prov, "tipo": tipo})

    # 1) Todo lo que ya había. Cuando dos entradas comparten nombre, el id
    #    limpio tiene que quedárselo el pueblo de verdad y no el barrio de
    #    Madrid que se llama igual: gana la que esté más cerca del municipio con
    #    ese nombre. Salamanca se queda «salamanca»; el barrio pasa a ser
    #    «Salamanca (Madrid)».
    muni_por_nombre = {}
    for m in municipios:
        for v in variantes(m["nombre"]):
            muni_por_nombre.setdefault(v, m)

    def distancia_a_su_municipio(r):
        m = muni_por_nombre.get(sin_tildes(r["nombre"]))
        if not m:
            return 0.0
        try:
            return km(float(r["lat"]), float(r["lon"]), m["lat"], m["lon"])
        except (KeyError, ValueError):
            return 1e9

    previas.sort(key=distancia_a_su_municipio)
    for r in previas:
        try:
            la, lo = float(r["lat"]), float(r["lon"])
        except (KeyError, ValueError):
            continue
        # La provincia se recalcula SIEMPRE desde las coordenadas. La que traía
        # el fichero faltaba en 845 filas y en otras era falsa: el barrio de
        # Arapiles de Madrid venía como provincia de Salamanca, y al desempatar
        # nombres eso producía «Arapiles (Salamanca)» para un sitio de Madrid.
        cerca = min(municipios, key=lambda m: km(la, lo, m["lat"], m["lon"]))
        mete(r["nombre"], la, lo, provincias.get(cerca["adm2"], ""), "base")

    n_previas = len(salida)

    # 2) Los municipios que no estaban: ni por nombre ni por cercanía.
    nuevos = 0
    for m in sorted(municipios, key=lambda m: -m["pob"]):
        if variantes(m["nombre"]) & nombres:
            continue
        if rejilla.cerca(m["lat"], m["lon"], RADIO_CUBIERTO_KM):
            continue
        # Mismo id y a tiro de piedra = el mismo pueblo escrito de otra forma
        # («Medina Sidonia» y «Medina-Sidonia»). Entrarlo dos veces partiría sus
        # votos en dos sacos, así que no se entra.
        ya = ids.get(slug(nombre_legible(m["nombre"])))
        if ya and km(m["lat"], m["lon"], ya[0], ya[1]) < 25:
            continue
        mete(nombre_legible(m["nombre"]), m["lat"], m["lon"],
             provincias.get(m["adm2"], ""), "municipio")
        nuevos += 1
    print(f"municipios añadidos: {nuevos}")

    # 3) Aldeas y pedanías, si se piden.
    aldeas = 0
    if con_aldeas:
        for p in sorted(nucleos, key=lambda p: -p["pob"]):
            if sin_tildes(p["nombre"]) in nombres:
                continue
            if rejilla.cerca(p["lat"], p["lon"], RADIO_ALDEA_KM):
                continue
            prov = provincias.get(p["adm2"], "")
            if not prov:   # unas pocas aldeas no traen provincia: se saca del mapa
                cerca = min(municipios, key=lambda m: km(p["lat"], p["lon"], m["lat"], m["lon"]))
                prov = provincias.get(cerca["adm2"], "")
            mete(nombre_legible(p["nombre"]), p["lat"], p["lon"], prov, "aldea")
            aldeas += 1
        print(f"aldeas y pedanías añadidas: {aldeas}")

    # 4) Los sitios de la lista de a mano, si no han entrado ya solos.
    extras = 0
    for nombre, la, lo, prov in EXTRAS:
        if sin_tildes(nombre) in nombres and rejilla.cerca(la, lo, RADIO_CUBIERTO_KM):
            continue
        mete(nombre, la, lo, prov, "extra")
        extras += 1
    if extras:
        print(f"sitios añadidos a mano: {extras}")

    salida.sort(key=lambda r: sin_tildes(r["nombre"]))
    with SALIDA.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "nombre", "lat", "lon", "provincia", "tipo"])
        w.writeheader()
        w.writerows(salida)

    # La columna tipo separa lo que se baja siempre (municipios) de lo que solo
    # se baja si hace falta (aldeas). Ver publicar_lugares() en el generador.
    sin_prov = sum(1 for r in salida if not r["provincia"])
    print(f"\n{SALIDA}: {len(salida)} entradas "
          f"({n_previas} de antes + {nuevos} municipios"
          f"{f' + {aldeas} aldeas' if con_aldeas else ''})")
    print(f"ids únicos: {len(ids)} · sin provincia: {sin_prov}")


if __name__ == "__main__":
    main("--aldeas" in sys.argv)
