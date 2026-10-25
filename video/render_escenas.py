#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_escenas.py — motor de escenas animadas para los vídeos de nochetropical.es

Filosofía: el AUDIO manda. Primero se graba/genera la narración, se mide su
duración real, y la animación se estira para encajar. Nunca al revés.

Uso (desde la raíz del repo):
    python video/preparar_datos_video.py                     # escena 1: genera su JSON
    python video/preparar_noche_video.py --buscar            # escena 2: elige una noche medida
    python video/preparar_noche_video.py --estacion X --noche AAAA-MM-DD
    python video/render_escenas.py --datos --out video/salida
    python video/render_escenas.py --demo --out video/salida  # datos sintéticos, prueba de estilo

Salida: escena_01_mapa.mp4, escena_02_curva.mp4 (silenciosos, 1920x1080, 30 fps)
El audio se pega después con ffmpeg (ver montaje.sh).
"""

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import animation
from matplotlib.path import Path as MplPath
from matplotlib.patches import Polygon

AQUI = Path(__file__).resolve().parent
JSON_DATOS = AQUI / "datos" / "estaciones_video.json"
JSON_NOCHE = AQUI / "datos" / "noche_video.json"
GEOJSON = AQUI.parent / "aemet-temperaturas" / "datos" / "spain-provinces.geojson"

# ---------------------------------------------------------------------------
# 1. GUION: cada línea de narración con su duración REAL en segundos.
#    En producción esto se genera midiendo los ficheros .wav con ffprobe,
#    no se escribe a mano. Ver la función duraciones_desde_audio() abajo.
#
#    Cifras de la escena 1 sacadas de video/preparar_datos_video.py (panel fijo
#    de 654 estaciones, veranos 2017-2026, jun-sep, tmin >= 20 °C). Si cambia el
#    JSON, vuelve a mirar su resumen antes de grabar la voz.
# ---------------------------------------------------------------------------

GUION = {
    "escena_01_mapa": [
        ("En 2017, estas eran las estaciones de AEMET", 3.2),
        ("que registraban al menos una noche tropical en verano.", 3.4),
        ("Nueve veranos después, así está el mapa.", 3.0),
        ("Suben 556 de las 654 estaciones. Bajan 23.", 4.4),
    ],
    "escena_02_curva": [
        ("Una noche tropical es una noche en la que la temperatura", 3.4),
        ("no baja de veinte grados en ningún momento.", 3.2),
        ("No es una noche calurosa. Es una noche que no enfría.", 3.6),
    ],
}

FPS = 30
DPI = 100
FIGSIZE = (19.20, 10.80)  # 1920x1080 a 100 dpi

# Paleta. Una sola, coherente en todo el canal.
FONDO = "#0d1b2a"
TEXTO = "#e8eef5"
TENUE = "#7d92a8"
FRIO = "#4aa3df"
CALOR = "#e8703a"
EXTREMO = "#c1121f"
TIERRA = "#16293d"
COSTA = "#26405c"

# Encuadre del mapa principal y del recuadro de Canarias. Un grado de longitud
# mide cos(lat) de uno de latitud: sin corregirlo España sale ensanchada. El
# rango de longitudes se elige para que 1 px valga lo mismo en ambos ejes a 40°
# (y a 28° en Canarias). España queda a la derecha y deja libre la columna de la
# izquierda para los textos; Canarias va abajo a la izquierda con su marco.
LIM_PRINCIPAL = ((-20.2, 5.33), (33.4, 44.4))
LIM_CANARIAS = ((-18.35, -13.3), (27.55, 29.63))
CAJA_CANARIAS = [0.015, 0.035, 0.228, 0.189]   # en fracción de la figura
PROVINCIAS_CANARIAS = ("35", "38")
LAT_CORTE_CANARIAS = 31.0

# ---------------------------------------------------------------------------
# 2. DATOS
# ---------------------------------------------------------------------------

# Contorno MUY aproximado de la Península. Solo lo usa --demo si falta el
# geojson; el mapa real se dibuja con spain-provinces.geojson.
PENINSULA = [
    (-9.5, 43.8), (-7.7, 43.8), (-5.8, 43.6), (-4.0, 43.4), (-2.0, 43.4),
    (-1.8, 43.3), (0.7, 42.7), (3.3, 42.4), (3.2, 41.9), (1.0, 41.0),
    (0.9, 40.7), (0.2, 39.5), (-0.3, 39.3), (-0.7, 38.2), (-1.6, 37.4),
    (-2.9, 36.7), (-4.4, 36.7), (-5.4, 36.0), (-6.3, 36.8), (-7.4, 37.2),
    (-8.9, 37.0), (-8.8, 38.5), (-9.5, 39.4), (-8.9, 41.9), (-9.5, 43.8),
]
BALEARES = [(1.2, 38.9), (4.3, 39.6), (3.2, 40.1), (2.4, 39.5), (1.2, 38.9)]


def cargar_datos_reales(ruta: Path = JSON_DATOS):
    """Lee video/datos/estaciones_video.json (lo escribe preparar_datos_video.py)
    y devuelve la misma estructura que datos_demo()."""
    if ruta.is_dir():
        ruta = ruta / "estaciones_video.json"
    if not ruta.exists():
        raise SystemExit(f"No encuentro {ruta}. Ejecuta antes video/preparar_datos_video.py.")
    j = json.loads(ruta.read_text(encoding="utf-8"))
    est = j["estaciones"]
    anios = list(range(j["periodo"][0], j["periodo"][1] + 1))
    serie = np.array([[e["noches"][str(a)] for e in est] for a in anios], dtype=float)
    return dict(
        lon=np.array([e["lon"] for e in est], dtype=float),
        lat=np.array([e["lat"] for e in est], dtype=float),
        altitud=np.array([e["altitud"] for e in est], dtype=float),
        anios=anios,
        serie=serie,
        real=True,
    )


def datos_demo(n=320, semilla=7):
    """Estaciones sintéticas con una tendencia plausible. NO son datos reales:
    sirven para validar el pipeline, nunca para publicar."""
    rng = np.random.default_rng(semilla)
    lon = rng.uniform(-9.0, 3.2, n)
    lat = rng.uniform(36.2, 43.5, n)
    dentro = MplPath(PENINSULA).contains_points(np.column_stack([lon, lat]))
    lon, lat = lon[dentro], lat[dentro]
    n = len(lon)
    # La altitud manda: costa caliente, interior alto frío.
    dist_costa = np.minimum.reduce([lon + 9.3, 3.4 - lon, lat - 36.0, 43.9 - lat])
    altitud = np.clip(rng.normal(600, 420, n) + dist_costa * 90, 0, 2200)
    base = np.clip(55 - altitud / 22 + rng.normal(0, 6, n), 0, 95)
    anios = list(range(2016, 2026))
    serie = np.stack([
        np.clip(base + (a - 2016) * (1.05 - altitud / 2600) + rng.normal(0, 2.5, n), 0, 110)
        for a in anios
    ])
    return dict(lon=lon, lat=lat, altitud=altitud, anios=anios, serie=serie, real=False)


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")


def cargar_noche(ruta: Path = JSON_NOCHE):
    """Lee video/datos/noche_video.json (lo escribe preparar_noche_video.py, que
    comprueba antes que la noche es tropical de verdad). None si no existe."""
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


def noche_demo():
    """Curva inventada para probar estilo. NO es una medida: nunca publicar."""
    return dict(horas_locales=[f"{h % 24:02d}:00" for h in range(23, 32)],
                ta=[22.4, 22.1, 21.8, 21.6, 21.3, 21.1, 20.8, 20.6, 20.5], demo=True)


def grados(v):
    return f"{v:.1f} °C".replace(".", ",")


def cargar_contorno(ruta: Path = GEOJSON):
    """Anillos exteriores de las provincias: (resto de España, Canarias).
    None si no está el geojson (entonces se usa el contorno aproximado)."""
    if not ruta.exists():
        return None
    g = json.loads(ruta.read_text(encoding="utf-8"))
    resto, canarias = [], []
    for f in g["features"]:
        destino = canarias if f["properties"]["cod_prov"] in PROVINCIAS_CANARIAS else resto
        geom = f["geometry"]
        polis = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poli in polis:
            destino.append(np.asarray(poli[0], dtype=float))
    return resto, canarias


def pintar_tierra(ax, anillos, lim, paso=0.02):
    """Silueta sin rayas de provincia. El geojson no es topológicamente limpio
    (las vecinas no comparten vértices), así que se hace como generar_silueta.py:
    rasterizar, suavizar el borde y trazar el contorno."""
    (x0, x1), (y0, y1) = lim
    xs = np.arange(x0, x1, paso)
    ys = np.arange(y0, y1, paso)
    mask = np.zeros((len(ys), len(xs)), dtype=bool)
    for anillo in anillos:
        i0 = max(0, int((anillo[:, 0].min() - x0) / paso) - 1)
        i1 = min(len(xs), int((anillo[:, 0].max() - x0) / paso) + 2)
        j0 = max(0, int((anillo[:, 1].min() - y0) / paso) - 1)
        j1 = min(len(ys), int((anillo[:, 1].max() - y0) / paso) + 2)
        if i0 >= i1 or j0 >= j1:
            continue
        gx, gy = np.meshgrid(xs[i0:i1], ys[j0:j1])
        dentro = MplPath(anillo).contains_points(
            np.column_stack([gx.ravel(), gy.ravel()])).reshape(gx.shape)
        mask[j0:j1, i0:i1] |= dentro
    campo = mask.astype(np.float32)
    p = np.pad(campo, 1, mode="edge")
    campo = (p[:-2, :-2] + p[:-2, 1:-1] + p[:-2, 2:] + p[1:-1, :-2] + p[1:-1, 1:-1] +
             p[1:-1, 2:] + p[2:, :-2] + p[2:, 1:-1] + p[2:, 2:]) / 9.0
    ax.contourf(xs, ys, campo, levels=[0.5, 2.0], colors=[TIERRA], zorder=1)
    ax.contour(xs, ys, campo, levels=[0.5], colors=[COSTA], linewidths=1.6, zorder=2)


def duraciones_desde_audio(carpeta: Path):
    """En producción: mide cada .wav con ffprobe y devuelve la duración real.
    Así la animación se ajusta al locutor, no el locutor a la animación."""
    import subprocess
    dur = []
    for wav in sorted(carpeta.glob("*.wav")):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(wav)],
            capture_output=True, text=True, check=True)
        dur.append(float(out.stdout.strip()))
    return dur


# ---------------------------------------------------------------------------
# 3. UTILIDADES DE ESCENA
# ---------------------------------------------------------------------------

def lienzo():
    fig = plt.figure(figsize=FIGSIZE, dpi=DPI, facecolor=FONDO)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(FONDO)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    return fig, ax


def suave(t):
    """Easing. Sin esto, todo movimiento lineal delata que es un script."""
    return t * t * (3 - 2 * t)


def linea_narracion(guion, t):
    """Qué frase se está oyendo en el segundo t."""
    acc = 0.0
    for texto, dur in guion:
        if t < acc + dur:
            return texto, (t - acc) / dur
        acc += dur
    return guion[-1][0], 1.0


def firma(ax):
    ax.text(0.985, 0.03, "Fuente: AEMET  ·  nochetropical.es", transform=ax.transAxes,
            ha="right", va="bottom", color=TENUE, fontsize=15)


# ---------------------------------------------------------------------------
# 4. ESCENA 1 — mapa animado año a año
# ---------------------------------------------------------------------------

def escena_mapa(d, salida):
    guion = GUION["escena_01_mapa"]
    total = sum(x[1] for x in guion)
    n_frames = int(total * FPS)

    fig, ax = lienzo()
    ax.set_xlim(*LIM_PRINCIPAL[0]); ax.set_ylim(*LIM_PRINCIPAL[1])

    # Recuadro de Canarias con su propio marco (convención cartográfica).
    ax_can = fig.add_axes(CAJA_CANARIAS)
    ax_can.set_facecolor(FONDO)
    ax_can.set_xticks([]); ax_can.set_yticks([])
    for s in ax_can.spines.values():
        s.set_color(COSTA); s.set_linewidth(1.6)
    ax_can.set_xlim(*LIM_CANARIAS[0]); ax_can.set_ylim(*LIM_CANARIAS[1])
    ax_can.text(0.03, 0.95, "Canarias", transform=ax_can.transAxes, color=TENUE,
                fontsize=15, va="top")

    contorno = cargar_contorno()
    if contorno:
        pintar_tierra(ax, contorno[0], LIM_PRINCIPAL)
        pintar_tierra(ax_can, contorno[1], LIM_CANARIAS)
    else:
        for poly in (PENINSULA, BALEARES):
            ax.add_patch(Polygon(poly, closed=True, facecolor=TIERRA,
                                 edgecolor=COSTA, linewidth=1.6, zorder=1))

    en_can = d["lat"] < LAT_CORTE_CANARIAS
    grupos = [(ax, ~en_can), (ax_can, en_can)]
    puntos = [a.scatter(d["lon"][m], d["lat"][m], s=60, c=FRIO, alpha=0.9,
                        edgecolors="none", zorder=3) for a, m in grupos]

    n_est = len(d["lon"])
    txt_anio = ax.text(0.045, 0.945, "", transform=ax.transAxes, color=TEXTO,
                       fontsize=104, fontweight="bold", va="top")
    txt_dato = ax.text(0.048, 0.815, "", transform=ax.transAxes, color=TENUE,
                       fontsize=26, va="top")
    etiqueta_panel = (f"Panel fijo: las mismas {n_est} estaciones\n"
                      f"de AEMET todos los veranos\n"
                      f"(junio–septiembre), noche con mínima ≥ 20 °C"
                      if d.get("real") else "DATOS SINTÉTICOS\nsolo prueba de estilo")
    ax.text(0.048, 0.70, etiqueta_panel, transform=ax.transAxes, color=TENUE,
            fontsize=17, va="top", linespacing=1.4)
    txt_nar = ax.text(0.62, 0.07, "", transform=ax.transAxes, color=TEXTO,
                      fontsize=30, ha="center", va="bottom")
    firma(ax)

    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "nt", [FRIO, "#f2c14e", CALOR, EXTREMO])
    # Escala FIJA: el máximo de toda la serie, calculado una vez. Nunca por año.
    vmax = float(d["serie"].max())
    norm = matplotlib.colors.Normalize(0, vmax)

    n_anios = len(d["anios"])

    def frame(i):
        t = i / FPS
        # El barrido de años ocupa todo menos la última frase.
        t_barrido = min(t / max(total - guion[-1][1], 0.1), 1.0)
        pos = suave(t_barrido) * (n_anios - 1)
        j = int(np.floor(pos)); f = pos - j
        j2 = min(j + 1, n_anios - 1)
        vals = d["serie"][j] * (1 - f) + d["serie"][j2] * f

        for pts, (_, m) in zip(puntos, grupos):
            pts.set_color(cmap(norm(vals[m])))
            pts.set_sizes(40 + vals[m] / vmax * 208)

        anio = d["anios"][j] if f < 0.5 else d["anios"][j2]
        txt_anio.set_text(str(anio))
        # Recuento sobre el año que se enseña, no sobre la interpolación.
        n_con = int((d["serie"][j if f < 0.5 else j2] >= 1).sum())
        txt_dato.set_text(f"{n_con} de {n_est} estaciones\ncon al menos una noche tropical")
        txt_nar.set_text(linea_narracion(guion, t)[0])
        return (*puntos, txt_anio, txt_dato, txt_nar)

    escribir(fig, frame, n_frames, salida)
    plt.close(fig)
    return total


# ---------------------------------------------------------------------------
# 5. ESCENA 2 — la curva de una noche y el umbral de 20 °C
# ---------------------------------------------------------------------------

def escena_curva(salida, noche):
    guion = GUION["escena_02_curva"]
    total = sum(x[1] for x in guion)
    n_frames = int(total * FPS)

    # Una lectura por hora, tal cual. Los puntos son las medidas; la línea solo
    # las une. No se suaviza ni se rellena ningún hueco.
    ta = np.array(noche["ta"], dtype=float)
    horas = noche["horas_locales"]
    n = len(ta)
    xs = np.arange(n)
    i_min = int(ta.argmin())

    fig, ax = lienzo()
    ax.set_xlim(-0.6, n - 0.4)
    # Escala amplia: una noche que apenas se mueve tiene que VERSE plana. El margen
    # de arriba deja sitio al sello sin que tape la curva ni su primera lectura.
    ax.set_ylim(15.0, max(32.0, float(ta.max()) + 7))

    ax.axhline(20, color=TENUE, lw=2, ls="--", zorder=2)
    # A la izquierda y por debajo de la línea: a la derecha la curva acaba rozando
    # los 20 °C y el rótulo taparía la última lectura.
    ax.text(-0.5, 19.8, "20 °C", color=TENUE, fontsize=24, ha="left", va="top")
    for i in range(0, n, 2):
        ax.text(i, 17.4, horas[i], color=TENUE, fontsize=20, ha="center")

    if noche.get("demo"):
        titulo, detalle = "CURVA SINTÉTICA", "solo prueba de estilo, no es una medida"
    else:
        e = noche["estacion"]
        titulo = e["nombre"] if e["provincia"] in e["nombre"] else f"{e['nombre']} ({e['provincia']})"
        fin = date.fromisoformat(noche["noche"])
        ini = fin - timedelta(days=1)
        tramo = (f"Noche del {ini.day} al {fin.day} de {MESES[fin.month - 1]} de {fin.year}"
                 if ini.month == fin.month else
                 f"Noche del {ini.day} de {MESES[ini.month - 1]} al {fin.day} de "
                 f"{MESES[fin.month - 1]} de {fin.year}")
        detalle = (f"{tramo}\nTemperatura del aire, una lectura por hora "
                   f"({horas[0]}–{horas[-1]})"
                   + (" · datos provisionales" if noche.get("provisional") else ""))
    ax.text(0.045, 0.93, titulo, transform=ax.transAxes, color=TEXTO, fontsize=40,
            fontweight="bold", va="top")
    ax.text(0.047, 0.855, detalle, transform=ax.transAxes, color=TENUE, fontsize=20,
            va="top", linespacing=1.5)

    linea, = ax.plot([], [], color=CALOR, lw=5, zorder=4, solid_capstyle="round")
    marcas = ax.scatter([], [], s=110, color=CALOR, edgecolors=FONDO, linewidths=2, zorder=5)
    relleno = [None]
    etq_ini = ax.text(0, ta[0] + 0.5, grados(ta[0]), color=TEXTO, fontsize=22,
                      ha="center", va="bottom", alpha=0.0)
    etq_min = ax.text(i_min, ta[i_min] + 0.5, grados(ta[i_min]), color=TEXTO, fontsize=22,
                      ha="center", va="bottom", alpha=0.0)
    txt_nar = ax.text(0.5, 0.075, "", transform=ax.transAxes, color=TEXTO,
                      fontsize=30, ha="center", va="bottom")
    sello = ax.text(0.5, 0.69, "", transform=ax.transAxes, color=EXTREMO,
                    fontsize=76, fontweight="bold", ha="center", va="center", alpha=0.0)
    firma(ax)

    def frame(i):
        t = i / FPS
        avance = suave(min(t / (total * 0.72), 1.0))
        pos = avance * (n - 1)
        k = int(np.floor(pos)); f = pos - k
        x_vis, y_vis = list(xs[:k + 1]), list(ta[:k + 1])
        if k < n - 1 and f > 0:       # tramo que se está dibujando hacia la siguiente lectura
            x_vis.append(k + f); y_vis.append(ta[k] + (ta[k + 1] - ta[k]) * f)
        linea.set_data(x_vis, y_vis)
        marcas.set_offsets(np.column_stack([xs[:k + 1], ta[:k + 1]]))

        if relleno[0] is not None:
            relleno[0].remove()
        relleno[0] = ax.fill_between(x_vis, 20, y_vis, color=CALOR, alpha=0.20, zorder=3)

        etq_ini.set_alpha(min(t / 0.5, 1.0))
        if i_min > 0:
            etq_min.set_alpha(1.0 if k >= i_min else 0.0)

        if t > total * 0.75:
            sello.set_text("NOCHE TROPICAL")
            sello.set_alpha(min((t - total * 0.75) / 0.6, 1.0) * 0.95)
        txt_nar.set_text(linea_narracion(guion, t)[0])
        return linea, marcas, etq_ini, etq_min, txt_nar, sello

    escribir(fig, frame, n_frames, salida)
    plt.close(fig)
    return total


# ---------------------------------------------------------------------------
# 6. ESCRITURA
# ---------------------------------------------------------------------------

def escribir(fig, frame_fn, n_frames, salida):
    anim = animation.FuncAnimation(fig, frame_fn, frames=n_frames, blit=False)
    writer = animation.FFMpegWriter(
        fps=FPS, codec="libx264", bitrate=-1,
        extra_args=["-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "18"])
    anim.save(salida, writer=writer, dpi=DPI,
              savefig_kwargs={"facecolor": FONDO})
    print(f"  escrito {salida}  ({n_frames} frames, {n_frames/FPS:.1f} s)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--demo", action="store_true")
    p.add_argument("--datos", type=Path, nargs="?", const=JSON_DATOS,
                   help=f"JSON de preparar_datos_video.py (por defecto {JSON_DATOS.name})")
    p.add_argument("--out", type=Path, default=Path("."))
    a = p.parse_args()

    a.out.mkdir(parents=True, exist_ok=True)

    reales = bool(a.datos) and not a.demo
    d = cargar_datos_reales(a.datos) if reales else datos_demo()
    noche = cargar_noche() if reales else noche_demo()
    if noche is None:
        raise SystemExit(f"No encuentro {JSON_NOCHE}. Ejecuta antes video/preparar_noche_video.py.")

    print("Renderizando escenas…")
    t1 = escena_mapa(d, str(a.out / "escena_01_mapa.mp4"))
    t2 = escena_curva(str(a.out / "escena_02_curva.mp4"), noche)
    print(f"Total: {t1 + t2:.1f} s de vídeo.")


if __name__ == "__main__":
    main()
