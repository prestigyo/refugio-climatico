#!/usr/bin/env python3
"""
Genera docs/miniaturas/<provincia>.png: las MINIATURAS de las 52 landings.

Por qué existe: hasta ahora las 52 landings provinciales no tenían ni una sola
imagen ráster en el cuerpo (0 de 52), y las 369 páginas que declaraban og:image
declaraban todas el MISMO og.png. Google no elige miniatura de un banner
compartido por medio sitio, y no usa SVG en ningún caso — así que las páginas
con mejor CTR del sitio salían en el buscador sin imagen. Esto les da una
imagen propia, distinta y con el dato dentro.

Dos tamaños por provincia, desde la misma composición:
  <slug>.png     1200x1200  cuadrada  -> el <img> visible y Article.image.
                                         Google recorta CUADRADO la miniatura
                                         del resultado; un 1200x630 se queda a
                                         la mitad.
  <slug>-og.png  1200x630   apaisada  -> og:image y twitter:image, que es el
                                         formato que esperan WhatsApp, Twitter
                                         y Facebook.

A tamaño de miniatura real en Google (~92 px en escritorio) no se lee ni una
palabra: solo sobreviven la SILUETA de la provincia y UNA cifra grande. La
composición está hecha para eso — todo lo demás es para cuando se ve entera.

Color: reutiliza tal cual la escala color_nt() de generar_pagina_mapa.py. Una
miniatura que coloreara las estaciones distinto del mapa interactivo sería peor
aunque la escala fuese más ortodoxa.

Lee  : aemet-temperaturas/analisis/refugios_nocturnos_ranking.csv (vía generar_calculadora)
       aemet-temperaturas/datos/spain-provinces.geojson
Escribe: docs/miniaturas/*.png

Uso:
    python scripts/generar_miniaturas.py
    python scripts/generar_miniaturas.py --solo teruel,avila   # para mirarlas
"""
from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import generar_calculadora as g  # PROVINCIAS, slug, rutas, cargar_estaciones


GEOJSON = g.AEMET_DIR / "datos" / "spain-provinces.geojson"
OUT_DIR = g.DOCS_DIR / "miniaturas"

# Paleta del sitio (las mismas variables CSS de las páginas).
BG        = (22, 16, 9)       # --bg      #161009
PANEL     = (36, 27, 17)      # --panel   #241b11
LINEA     = (58, 44, 28)      # --line    #3a2c1c
PAPEL     = (239, 230, 214)   # --paper   #efe6d6
MUTED     = (179, 164, 140)   # --muted   #b3a48c
TEJA      = (217, 116, 78)    # --teja    #d9744e
VERDE     = (143, 176, 122)   # --verde   #8fb07a
TEAL      = (150, 182, 196)   # --teal    #96b6c4

# Las CINCO BANDAS de bandas_py() en generar_calculadora, con sus colores. Se
# reusan tal cual para no inventarse un criterio nuevo: la cifra grande se pinta
# con el color de SU banda, no de verde por defecto. Melilla (76,4 en su única
# estación) en verde habría dicho "refugio" de la peor noche de España.
BANDAS = [(1,  "REFUGIO",        (143, 176, 122), (30, 42, 23)),
          (10, "SE DUERME BIEN", (150, 182, 196), (22, 36, 43)),
          (30, "TEMPLADO",       (232, 154, 115), (44, 33, 20)),
          (60, "SE SUDA",        (217, 116, 78),  (44, 26, 18)),
          (1e9, "HORNO",         (207, 107, 84),  (44, 20, 17))]


def banda(nt: float) -> tuple[str, tuple, tuple]:
    for techo, etq, col, fondo in BANDAS:
        if nt < techo:
            return etq, col, fondo
    return BANDAS[-1][1:]

# La silueta necesita separarse del fondo: #241b11 sobre #161009 no se
# distingue al tamaño real de miniatura. Estos dos tonos son de la misma
# familia cálida pero con contraste suficiente para que la forma se reconozca.
TIERRA    = (52, 39, 25)
BORDE     = (94, 72, 47)

ESCALA = 3  # se dibuja a 3x y se reduce con LANCZOS: Pillow no antialiasa polígonos

_SERIF = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
          "C:/Windows/Fonts/georgiab.ttf", "DejaVuSerif-Bold.ttf"]
_SANS  = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
          "C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf"]
_SANS_R = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
           "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"]


def fuente(rutas: list[str], size: int) -> ImageFont.FreeTypeFont:
    for r in rutas:
        try:
            return ImageFont.truetype(r, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


# --- Escala de color: PORTADA EXACTA de generar_pagina_mapa.color_nt() ---------
def color_nt(nt: float) -> tuple[int, int, int]:
    stops = [(0, (134, 176, 196)), (18, (217, 160, 94)),
             (36, (207, 75, 52)), (60, (150, 30, 20))]
    c = stops[0][1]
    for i in range(len(stops) - 1):
        a, ca = stops[i]
        b, cb = stops[i + 1]
        if nt <= b:
            t = max(0.0, (nt - a) / (b - a))
            c = tuple(round(ca[k] + (cb[k] - ca[k]) * t) for k in range(3))
            break
        c = cb
    return tuple(c)


# --- Casar nombres: el GeoJSON trae "Araba/Álava", el sitio "Araba/Álava" ------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def cargar_siluetas() -> dict[str, list[list[tuple[float, float]]]]:
    """{nombre normalizado -> lista de anillos exteriores en (lon, lat)}."""
    gj = json.loads(GEOJSON.read_text(encoding="utf-8"))
    out: dict[str, list] = {}
    for ft in gj["features"]:
        geom = ft["geometry"]
        polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                 else [geom["coordinates"]])
        # poly[0] es el anillo exterior; poly[1:] son huecos, que Pillow no sabe
        # recortar. Se ignoran: en este fichero no hay provincias con enclaves
        # interiores dibujables a este tamaño.
        anillos = [[(lon, lat) for lon, lat in poly[0]] for poly in polys
                   if len(poly[0]) >= 3]
        nombre = ft["properties"]["name"]
        for trozo in nombre.split("/"):
            out.setdefault(_norm(trozo), anillos)
        out[_norm(nombre)] = anillos
    return out


def anillos_utiles(anillos: list, lista: list, frac: float = 0.005) -> list:
    """Quita los islotes remotos SIN estación que estiran el encuadre.

    El encuadre sale de la caja envolvente de la provincia, así que un islote
    diminuto y lejano la dobla y deja la provincia dibujada a un tercio de su
    tamaño. Le pasaba a Almería con **Isla de Alborán** (0,7 km² a 90 km de la
    costa, sin estación): la caja pasaba de 1,21×0,8° a 1,21×1,98° y la
    silueta se quedaba en 308 px de ancho dentro de una caja de 1.060.

    Se descarta un anillo solo si es despreciable (menos del 0,5 % del área de
    la caja del mayor) Y no tiene ninguna estación dentro. Menorca, Ibiza,
    Lanzarote o Fuerteventura están muy por encima de ese umbral y se quedan;
    La Graciosa también, y además tiene estación.
    """
    def caja(a):
        xs = [q[0] for q in a]
        ys = [q[1] for q in a]
        return min(xs), min(ys), max(xs), max(ys)

    cajas = [caja(a) for a in anillos]
    areas = [(c[2] - c[0]) * (c[3] - c[1]) for c in cajas]
    mayor = max(areas) if areas else 0
    if not mayor:
        return anillos
    out = []
    for a, c, ar in zip(anillos, cajas, areas):
        if ar >= mayor * frac:
            out.append(a)
            continue
        mx = (c[2] - c[0]) * 0.3 + 0.03
        my = (c[3] - c[1]) * 0.3 + 0.03
        if any(c[0] - mx <= e["lon"] <= c[2] + mx and c[1] - my <= e["lat"] <= c[3] + my
               for e in lista):
            out.append(a)
    return out or anillos


def extension(anillos: list) -> float:
    """Lado mayor de la provincia en grados, corregido por latitud."""
    pts = [q for an in anillos for q in an]
    lons = [q[0] for q in pts]
    lats = [q[1] for q in pts]
    k = math.cos(math.radians((min(lats) + max(lats)) / 2))
    return max((max(lons) - min(lons)) * k, max(lats) - min(lats))


# Por debajo de esto no se dibuja mapa. Solo lo cruza Melilla (0,055°): su
# polígono son cuatro puntos, y ampliado a 505 px salía un rombo enorme que no
# se parece a nada. La siguiente provincia más pequeña (Gipuzkoa) mide 0,637°,
# once veces más, así que el umbral no está peleado con ningún caso real.
EXT_MINIMA = 0.2


def silueta_de(prov: str, siluetas: dict) -> list | None:
    for trozo in prov.split("/"):
        s = siluetas.get(_norm(trozo))
        if s:
            return s
    return siluetas.get(_norm(prov))


# --- Proyección local: la provincia sola, encajada en su caja -----------------
def encajador(anillos: list, caja: tuple[int, int, int, int]):
    """Devuelve proj(lat, lon) -> (x, y) que encaja la provincia en `caja`.

    Equirectangular con corrección por coseno de la latitud media: sin ella las
    provincias salen estiradas a lo ancho (a 40° de latitud, un grado de
    longitud mide un 77 % de uno de latitud).
    """
    pts = [p for anillo in anillos for p in anillo]
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    lon0, lon1 = min(lons), max(lons)
    lat0, lat1 = min(lats), max(lats)
    k = math.cos(math.radians((lat0 + lat1) / 2))
    ancho = max((lon1 - lon0) * k, 1e-9)
    alto = max(lat1 - lat0, 1e-9)
    x0, y0, x1, y1 = caja
    esc = min((x1 - x0) / ancho, (y1 - y0) / alto)
    # Centrada en horizontal, pero PEGADA ARRIBA en vertical: una provincia
    # ancha (Las Palmas, con tres islas en 2,4° de longitud) usa poca altura, y
    # centrarla la dejaba flotando en mitad de un hueco.
    dx = (x1 - x0 - ancho * esc) / 2

    def proj(lat: float, lon: float) -> tuple[float, float]:
        return (x0 + dx + (lon - lon0) * k * esc, y0 + (lat1 - lat) * esc)

    proj.abajo = y0 + alto * esc   # borde inferior REAL de la silueta
    return proj


# --- Primitivas de texto ------------------------------------------------------
def ancho(d: ImageDraw.ImageDraw, txt: str, fnt) -> int:
    b = d.textbbox((0, 0), txt, font=fnt)
    return b[2] - b[0]


def avance(d: ImageDraw.ImageDraw, txt: str, fnt) -> float:
    """Ancho de AVANCE, no de caja. textbbox() se come los espacios de los
    extremos, así que encadenar trozos con él los pegaba unos a otros."""
    return d.textlength(txt, font=fnt)


def segmentos(d: ImageDraw.ImageDraw, x: float, y: float, segs: list,
              size: int, maximo: float, minimo: int = 13) -> None:
    """Una línea de trozos con fuentes y colores distintos, que encoge hasta caber.

    segs = [(texto, rutas_de_fuente, color), ...]
    """
    while True:
        fs = [fuente(r, size) for _, r, _ in segs]
        if sum(avance(d, t, f) for (t, _, _), f in zip(segs, fs)) <= maximo or size <= minimo:
            break
        size -= 2
    for (t, _, c), f in zip(segs, fs):
        d.text((x, y), t, font=f, fill=c)
        x += avance(d, t, f)


def ajustar(d: ImageDraw.ImageDraw, txt: str, rutas: list[str],
            size: int, maximo: int, minimo: int = 10):
    """Baja el cuerpo hasta que el texto quepa en `maximo` píxeles."""
    f = fuente(rutas, size)
    while ancho(d, txt, f) > maximo and size > minimo:
        size -= 2
        f = fuente(rutas, size)
    return f


def espaciado(d: ImageDraw.ImageDraw, xy, txt: str, fnt, fill, sep: int = 0):
    """Texto con letter-spacing (Pillow no lo trae)."""
    x, y = xy
    for ch in txt:
        d.text((x, y), ch, font=fnt, fill=fill)
        x += ancho(d, ch, fnt) + sep if ch != " " else fnt.size * 0.32 + sep
    return x


# El formato de la cifra vive en generar_calculadora (nt_cifra): lo usan la
# imagen y el alt/caption que la describen, y con dos reglas distintas el texto
# alternativo acabaría diciendo un número que la imagen no enseña.
cifra = g.nt_cifra


# --- Composición --------------------------------------------------------------
def dibujar_mapa(d: ImageDraw.ImageDraw, anillos: list, lista: list,
                 caja: tuple[int, int, int, int], s: int) -> float:
    """Dibuja la silueta y sus estaciones. Devuelve el borde inferior real."""
    proj = encajador(anillos, caja)
    for anillo in anillos:
        pts = [proj(lat, lon) for lon, lat in anillo]
        if len(pts) >= 3:
            d.polygon(pts, fill=TIERRA, outline=BORDE, width=max(1, int(1.5 * s)))
    # El radio se adapta al número de estaciones: con 44 (Barcelona) o 37 (Las
    # Palmas) un radio fijo las funde en un racimo ilegible; con 1 (Melilla) un
    # punto pequeño se pierde.
    lado = min(caja[2] - caja[0], caja[3] - caja[1])
    frac = min(0.030, max(0.009, 0.021 * (16 / max(len(lista), 4)) ** 0.30))
    r = lado * frac
    # de más caluroso a más fresco: los refugios quedan dibujados ENCIMA
    for e in sorted(lista, key=lambda x: -x["nt"]):
        x, y = proj(e["lat"], e["lon"])
        # anillo del color del fondo: dos estaciones pegadas siguen siendo dos
        h = r + 2.2 * s
        d.ellipse([x - h, y - h, x + h, y + h], fill=BG)
        d.ellipse([x - r, y - r, x + r, y + r], fill=color_nt(e["nt"]))
    return proj.abajo


def fondo(W: int, H: int, s: int) -> Image.Image:
    """Degradado vertical cálido, como la cabecera de las páginas."""
    im = Image.new("RGB", (W * s, H * s), BG)
    d = ImageDraw.Draw(im)
    alto = int(H * s * 0.55)
    for i in range(alto):
        t = 1 - i / alto
        c = tuple(round(BG[k] + (PANEL[k] - BG[k]) * t * 0.85) for k in range(3))
        d.line([(0, i), (W * s, i)], fill=c)
    return im


def chip(d: ImageDraw.ImageDraw, xy, etq: str, col, fondo_chip, s: int) -> None:
    """La etiqueta de banda, con la misma forma que en la tabla de la landing."""
    x, y = xy
    f = fuente(_SANS, int(23 * s))
    pad_x, pad_y = int(18 * s), int(11 * s)
    w = ancho(d, etq, f) + int(2.6 * s) * (len(etq) - 1)
    d.rounded_rectangle([x, y, x + w + 2 * pad_x, y + f.size + 2 * pad_y],
                        radius=int(7 * s), fill=fondo_chip, outline=col,
                        width=max(1, int(1.5 * s)))
    espaciado(d, (x + pad_x, y + pad_y), etq, f, col, sep=int(2.6 * s))


def _cabecera(d: ImageDraw.ImageDraw, prov: str, W: int, M: int,
              s: int, cuadrada: bool) -> int:
    """Antetítulo + nombre de provincia + regla. Devuelve la y de la regla."""
    f_kick = fuente(_SANS, int((21 if cuadrada else 18) * s))
    espaciado(d, (M, int((56 if cuadrada else 40) * s)),
              "NOCHES TROPICALES · AEMET", f_kick, TEJA, sep=int(3.2 * s))
    y_nom = int((100 if cuadrada else 74) * s)
    f_nom = ajustar(d, prov.upper(), _SERIF, int((86 if cuadrada else 64) * s),
                    W * s - 2 * M, int(26 * s))
    d.text((M, y_nom), prov.upper(), font=f_nom, fill=PAPEL)
    y_regla = y_nom + f_nom.size + int(20 * s)
    d.line([(M, y_regla), (M + int(120 * s), y_regla)], fill=TEJA, width=int(4 * s))
    return y_regla


def _pie(d: ImageDraw.ImageDraw, n: int, W: int, H: int, M: int,
         s: int, cuadrada: bool) -> int:
    """Recuento de estaciones + dominio. Devuelve la y de la regla del pie."""
    y_pie = H * s - int((72 if cuadrada else 54) * s)
    y_regla = y_pie - int(26 * s)
    d.line([(M, y_regla), (W * s - M, y_regla)], fill=LINEA, width=max(1, int(2 * s)))
    f_pie = fuente(_SANS_R, int((24 if cuadrada else 21) * s))
    est = f'{n} {"estaciones" if n != 1 else "estación"} de AEMET · veranos 2017–2026'
    d.text((M, y_pie), est, font=f_pie, fill=MUTED)
    f_dom = fuente(_SANS, int((24 if cuadrada else 21) * s))
    d.text((W * s - M - ancho(d, "nochetropical.es", f_dom), y_pie),
           "nochetropical.es", font=f_dom, fill=TEJA)
    return y_regla


def _cuadrada(d: ImageDraw.ImageDraw, prov: str, lista: list, anillos: list,
              con_mapa: bool, mejor: dict, peor: dict, hay_contraste: bool,
              etq: str, col_banda, fondo_banda, s: int) -> None:
    """1200×1200: mapa a TODO el ancho arriba, bloque de texto abajo.

    El reparto va anclado DE ABAJO ARRIBA: primero el pie, luego la línea de
    altitud, el nombre de la estación y la fila de la cifra; el mapa se queda
    con lo que sobre. Así el nombre de la estación dispone del ancho entero
    —hay muchos largos o compuestos ("San Bartolomé Tirajana, Lomo Pedro
    Alfonso")— en vez de encogerse dentro de media columna.
    """
    W = H = 1200
    M = int(70 * s)
    n = len(lista)
    y_regla = _cabecera(d, prov, W, M, s, True)
    y_regla_pie = _pie(d, n, W, H, M, s, True)
    util = W * s - 2 * M

    # --- Fila de abajo: altitud y, si la hay, la estación más calurosa ---
    cuerpo_bajo = int(27 * s)
    y_bajo = y_regla_pie - int(24 * s) - cuerpo_bajo

    # --- Nombre de la estación: a TODO el ancho ---
    f_est = ajustar(d, mejor["loc"], _SANS, int(58 * s), util, int(22 * s))
    y_est = y_bajo - int(20 * s) - f_est.size

    # --- Fila de la cifra: chip a la izquierda, cifra + etiqueta a la derecha ---
    txt_cifra = cifra(mejor["nt"])
    f_cifra = ajustar(d, txt_cifra, _SERIF, int((150 if con_mapa else 250) * s),
                      int(560 * s), int(70 * s))
    f_lbl = fuente(_SANS, int(28 * s))
    lineas = ("noches tropicales", "al año en")
    w_lbl = max(avance(d, t, f_lbl) for t in lineas)
    alto_fila = max(f_cifra.size, int(2.6 * f_lbl.size))
    y_fila = y_est - int(36 * s) - alto_fila

    top = y_regla + int(46 * s)
    if con_mapa:
        mapa_abajo = dibujar_mapa(d, anillos, lista, (M, top, W * s - M,
                                                      y_fila - int(30 * s)), s)
    else:
        # Sin mapa (Melilla) el bloque de texto se centra en el hueco libre.
        subir = (y_fila - top) // 2
        y_fila -= subir
        y_est -= subir
        y_bajo -= subir

    # cifra + etiqueta, alineadas al margen DERECHO
    w_cifra = avance(d, txt_cifra, f_cifra)
    x_grupo = W * s - M - (w_cifra + int(30 * s) + w_lbl)
    d.text((x_grupo, y_fila), txt_cifra, font=f_cifra, fill=col_banda)
    x_lbl = x_grupo + w_cifra + int(30 * s)
    y_lbl = y_fila + (alto_fila - int(2.2 * f_lbl.size)) // 2
    for t in lineas:
        d.text((x_lbl, y_lbl), t, font=f_lbl, fill=MUTED)
        y_lbl += int(1.25 * f_lbl.size)
    # el chip, a la izquierda y centrado contra la cifra
    chip(d, (M, y_fila + (alto_fila - int(45 * s)) // 2), etq, col_banda,
         fondo_banda, s)

    d.text((M, y_est), mejor["loc"], font=f_est, fill=PAPEL)

    segs = [(f'{g.miles(mejor["alt"])} m de altitud', _SANS_R, MUTED)]
    if hay_contraste:
        segs += [("   ·   frente a ", _SANS_R, MUTED),
                 (cifra(peor["nt"]), _SANS, color_nt(peor["nt"])),
                 (f' en {peor["loc"]}', _SANS_R, PAPEL)]
    segmentos(d, M, y_bajo, segs, cuerpo_bajo, util)


def _apaisada(d: ImageDraw.ImageDraw, prov: str, lista: list, anillos: list,
              con_mapa: bool, mejor: dict, peor: dict, hay_contraste: bool,
              etq: str, col_banda, fondo_banda, s: int) -> None:
    """1200×630 para og:image: mapa a la izquierda, texto a la derecha.

    Aquí no cabe el reparto de la cuadrada (630 px de alto), así que mantiene
    las dos columnas, que en este formato sí leen bien.
    """
    W, H = 1200, 630
    M = int(56 * s)
    n = len(lista)
    y_regla = _cabecera(d, prov, W, M, s, False)
    y_regla_pie = _pie(d, n, W, H, M, s, False)

    top = y_regla + int(30 * s)
    if con_mapa:
        caja = (M, top, M + int(300 * s), top + int(300 * s))
        x_txt = M + int(350 * s)
        dibujar_mapa(d, anillos, lista, caja, s)
    else:
        x_txt = M
    ancho_txt = W * s - x_txt - M

    txt_cifra = cifra(mejor["nt"])
    f_cifra = ajustar(d, txt_cifra, _SERIF, int((150 if con_mapa else 200) * s),
                      ancho_txt, int(56 * s))
    y = top
    d.text((x_txt, y), txt_cifra, font=f_cifra, fill=col_banda)
    # el chip va EN LÍNEA con la cifra: apilado chocaba con el contrapunto
    chip(d, (x_txt + ancho(d, txt_cifra, f_cifra) + int(30 * s),
             y + int(f_cifra.size * 0.40)), etq, col_banda, fondo_banda, s)

    y += f_cifra.size + int(18 * s)
    f_lbl = fuente(_SANS, int(22 * s))
    for t in ("noches tropicales", "al año en"):
        d.text((x_txt, y), t, font=f_lbl, fill=MUTED)
        y += int(29 * s)
    y += int(6 * s)
    f_est = ajustar(d, mejor["loc"], _SANS, int(30 * s), ancho_txt, int(15 * s))
    d.text((x_txt, y), mejor["loc"], font=f_est, fill=PAPEL)
    y += f_est.size + int(12 * s)

    segs = [(f'{g.miles(mejor["alt"])} m de altitud', _SANS_R, MUTED)]
    if hay_contraste:
        segs += [("   ·   frente a ", _SANS_R, MUTED),
                 (cifra(peor["nt"]), _SANS, color_nt(peor["nt"])),
                 (f' en {peor["loc"]}', _SANS_R, PAPEL)]
    if y + int(30 * s) < y_regla_pie:
        segmentos(d, x_txt, y, segs, int(20 * s), ancho_txt)


def componer(prov: str, lista: list, anillos: list, cuadrada: bool) -> Image.Image:
    W, H = (1200, 1200) if cuadrada else (1200, 630)
    s = ESCALA
    im = fondo(W, H, s)
    d = ImageDraw.Draw(im)

    ordenadas = sorted(lista, key=lambda x: (x["nt"], -x["alt"]))
    mejor = ordenadas[0]
    peor = max(lista, key=lambda x: x["nt"])
    hay_contraste = len(lista) > 1 and peor["id"] != mejor["id"]
    etq, col_banda, fondo_banda = banda(mejor["nt"])
    anillos = anillos_utiles(anillos, lista)
    # Una ciudad autónoma no tiene silueta que enseñar: la cifra ocupa el ancho.
    con_mapa = extension(anillos) >= EXT_MINIMA

    dibujar = _cuadrada if cuadrada else _apaisada
    dibujar(d, prov, lista, anillos, con_mapa, mejor, peor, hay_contraste,
            etq, col_banda, fondo_banda, s)

    # Paleta adaptativa de 256: son imágenes de colores planos, así que baja al
    # 37 % del peso sin artefactos. Ojo, tiene que ser convert("P", ADAPTIVE) y
    # NO quantize(): quantize() rompe el degradado del fondo en un escalón duro
    # (medido: un salto de 9 niveles a media altura) y el dither no lo arregla.
    return (im.resize((W, H), Image.LANCZOS)
              .convert("P", palette=Image.ADAPTIVE, colors=256))


def main() -> None:
    ap = argparse.ArgumentParser(description="Miniaturas de las landings provinciales")
    ap.add_argument("--solo", help="slugs separados por coma, para revisar unas pocas")
    args = ap.parse_args()

    if not GEOJSON.exists():
        raise SystemExit(f"No encuentro el GeoJSON de provincias: {GEOJSON}")

    estaciones, _ = g.cargar_estaciones()
    por_prov: dict[str, list] = defaultdict(list)
    for e in estaciones:
        por_prov[e["prov"]].append(e)

    siluetas = cargar_siluetas()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    filtro = {x.strip() for x in args.solo.split(",")} if args.solo else None

    hechas, sin_silueta, peso = 0, [], 0
    indice: dict[str, bool] = {}
    for prov, lista in sorted(por_prov.items()):
        sl = g.slug(prov)
        if filtro and sl not in filtro:
            continue
        anillos = silueta_de(prov, siluetas)
        if not anillos:
            # Sin silueta no hay miniatura: mejor ninguna que una caja vacía.
            sin_silueta.append(prov)
            continue
        indice[sl] = extension(anillos_utiles(anillos, lista)) >= EXT_MINIMA
        for cuadrada, nombre in ((True, f"{sl}.png"), (False, f"{sl}-og.png")):
            ruta = OUT_DIR / nombre
            componer(prov, lista, anillos, cuadrada).save(ruta, optimize=True)
            peso += ruta.stat().st_size
        hechas += 1

    # Quién lleva mapa y quién no, para que generar_calculadora escriba un alt
    # que describa la imagen de verdad. Solo se reescribe si se generaron TODAS
    # (con --solo se quedaría a medias y dejaría el índice mintiendo).
    if not filtro:
        (OUT_DIR / "indice.json").write_text(
            json.dumps({"con_mapa": sorted(k for k, v in indice.items() if v),
                        "sin_mapa": sorted(k for k, v in indice.items() if not v)},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"   miniaturas: {hechas} provincias × 2 tamaños = {hechas * 2} PNG "
          f"({peso / 1048576:.1f} MB) en {OUT_DIR.relative_to(g.REPO_ROOT)}/")
    if sin_silueta:
        print(f"   SIN silueta en el GeoJSON (no se genera): {', '.join(sin_silueta)}")


if __name__ == "__main__":
    main()
