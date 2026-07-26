#!/usr/bin/env python3
"""Estudios de superposición de los mapas de AEMET: 'La España que nunca se
colorea'. Genera dos imágenes-estudio y un JSON con las cifras, que la
calculadora usa para montar la landing /la-espana-que-nunca-se-colorea/.

  1. Refugios NOCTURNOS (mínimas): tres zonas para no caer en el falso alivio
     de una Tmin puntual — bajó de 18° cada noche / nunca tropical pero rozó
     los 18-20° / alguna noche tropical (>=20°).
  2. Frescor de DÍA (máximas): en cuántos días la máxima se quedó bajo 24°.
     Revela las cumbres que resisten el calor también a mediodía.

Reproducible y parametrizable: apuntando a los PNG de otro verano se obtiene
su estudio. Lee   : aemet-temperaturas/images/peninsula/{minima,maxima}/*.png
              Escribe: docs/estudios/*.png y docs/estudios/estudio-datos.json
"""
from __future__ import annotations

import glob
import json
import re
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

SITE = "https://nochetropical.es"
KEYWORDS = ("noches tropicales, ola de calor, mapa de calor de España, mapa de "
            "temperaturas de España, AEMET, refugios climáticos, dónde se duerme "
            "fresco, verano, cambio climático, nochetropical.es")


def _guardar_png(cv, ruta, titulo, descripcion, url):
    """Guarda el PNG con metadatos: autor, copyright, keywords y URL de origen,
    para que la atribución y las señales SEO viajen DENTRO del archivo aunque
    lo copien o lo compartan."""
    m = PngImagePlugin.PngInfo()
    m.add_text("Title", titulo)
    m.add_text("Author", "Ramón J. Lowesting · nochetropical.es")
    m.add_text("Description", descripcion + " Fuente: AEMET · " + url)
    m.add_text("Copyright", "© nochetropical.es · datos de AEMET bajo CC BY 4.0")
    m.add_text("Keywords", KEYWORDS)
    m.add_text("Source", url)
    m.add_text("Software", "nochetropical.es")
    cv.save(ruta, pnginfo=m)

SCRIPT_DIR = Path(__file__).resolve().parent
AEMET_DIR = SCRIPT_DIR.parent
DOCS_DIR = AEMET_DIR.parent / "docs"
IMG = AEMET_DIR / "images" / "peninsula"
OUT = DOCS_DIR / "estudios"

BG = (22, 16, 9); PAPER = (239, 230, 214); TEJA = (217, 116, 78); MUTED = (160, 148, 124)
C_NUCLEO = (169, 198, 212); C_MARGEN = (201, 162, 74); C_RESTO = (201, 74, 46)

# Paleta AEMET (color -> borde inferior de banda). Para MÍNIMAS se capa a 32
# (las bandas >=34 no se dan de noche y así las fronteras rojo oscuro no
# ensucian); para MÁXIMAS se capa a 42.
_BANDAS = [((184,52,80),42),((208,52,113),40),((231,51,145),38),((255,51,178),36),
    ((255,0,0),32),((255,127,0),30),((255,159,0),28),((255,191,0),26),((255,223,0),24),
    ((255,255,0),22),((204,255,0),20),((102,255,102),18),((33,178,170),16),((21,197,192),14),
    ((10,217,214),12),((0,237,237),10),((30,142,255),8),((29,113,219),6),((28,84,183),4),
    ((26,54,147),2),((25,25,112),0)]
TOL2 = 32**2
MESES = ["","enero","febrero","marzo","abril","mayo","junio","julio","agosto",
         "septiembre","octubre","noviembre","diciembre"]
G = "°"; MAY = "≥"; P = "·"
FB = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"]
FR = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"]


def _fuente(paths, size):
    for f in paths:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _paleta(tope):
    b = [(c, t) for c, t in _BANDAS if t <= tope]
    return np.array([c for c, _ in b]), np.array([t for _, t in b])


def _bandas_dia(indir, tope):
    """Para cada PNG del directorio devuelve (tmin_banda, valido) apilado y las
    fechas. Clasifica cada píxel a la banda de temperatura más cercana."""
    pal, tmp = _paleta(tope)
    files = sorted(glob.glob(str(indir) + "/*.png"))
    if not files:
        raise SystemExit(f"Sin PNG en {indir}")
    fechas = sorted(date.fromisoformat(re.search(r"(\d{4}-\d{2}-\d{2})", f).group(1)) for f in files)
    H, W = np.asarray(Image.open(files[0]).convert("RGB")).shape[:2]
    roi = np.zeros((H, W), bool); roi[3:H - 26, 0:583] = True
    out = []
    for f in files:
        a = np.asarray(Image.open(f).convert("RGB"), dtype=np.int32)
        d = ((a[:, :, None, :] - pal[None, None, :, :]) ** 2).sum(3)
        idx = d.argmin(2)
        out.append((tmp[idx], (d.min(2) < TOL2) & roi))
    return out, fechas, (H, W)


def _mapa_png(mapa_arr, dims, esc=1.5, margen=14):
    """Imagen LIMPIA del mapa: solo las manchas de color, SIN texto de ningún
    idioma. El título, el pie y la leyenda de color van en el HTML de la página
    —donde Google sí los lee y sirven de contexto—, y así una misma imagen vale
    para el español y el inglés sin duplicar la biblioteca. Recorta la franja de
    la leyenda del PNG original de AEMET (queda en fondo) y reescala con NEAREST
    para que las manchas queden nítidas."""
    H, W = dims
    x1 = min(583, W)
    recorte = mapa_arr[3:max(4, H - 26), 0:x1]
    mp = Image.fromarray(recorte)
    mp = mp.resize((int(mp.width * esc), int(mp.height * esc)), Image.NEAREST)
    cv = Image.new("RGB", (mp.width + 2 * margen, mp.height + 2 * margen), BG)
    cv.paste(mp, (margen, margen))
    return cv


def estudio_nocturno():
    bandas, fechas, (H, W) = _bandas_dia(IMG / "minima", tope=32)
    ge18 = np.zeros((H, W), int); ge20 = np.zeros((H, W), int); valid = np.zeros((H, W), int)
    for t, ok in bandas:
        ge18 += ok & (t >= 18); ge20 += ok & (t >= 20); valid += ok
    n = len(bandas); land = valid >= 0.6 * n
    nucleo = land & (ge18 == 0); margen = land & (ge18 > 0) & (ge20 == 0); resto = land & (ge20 > 0)
    pn = 100 * nucleo.sum() / land.sum(); pm = 100 * margen.sum() / land.sum(); pr = 100 * resto.sum() / land.sum()
    frac = np.where(valid > 0, ge20 / np.maximum(valid, 1), 0.0)
    mapa = np.zeros((H, W, 3), np.uint8); mapa[:] = BG
    c0 = np.array([74, 42, 26]); c1 = np.array([214, 74, 46])
    f3 = frac[resto][:, None]; mapa[resto] = (c0 * (1 - f3) + c1 * f3).astype(np.uint8)
    mapa[margen] = C_MARGEN; mapa[nucleo] = C_NUCLEO
    _guardar_png(_mapa_png(mapa, (H, W)), OUT / "refugios-nocturnos.png",
                 "La España que nunca se colorea — refugios climáticos nocturnos",
                 "Mapa de los refugios climáticos nocturnos de España: dónde la mínima "
                 "no cruza los 20 grados ni una noche, superponiendo los mapas de "
                 "mínimas de AEMET del verano.",
                 SITE + "/la-espana-que-nunca-se-colorea/")
    return dict(profundo=round(pn, 1), margen=round(pm, 1), tropical=round(pr, 1),
                ini=fechas[0].isoformat(), fin=fechas[-1].isoformat(), n=n)


def estudio_frescor(umbral=24):
    bandas, fechas, (H, W) = _bandas_dia(IMG / "maxima", tope=42)
    fresco = np.zeros((H, W), int); valid = np.zeros((H, W), int)
    for t, ok in bandas:
        fresco += ok & (t < umbral); valid += ok
    n = len(bandas); land = valid >= 0.6 * n
    frac = np.where(valid > 0, fresco / np.maximum(valid, 1), 0.0)
    p50 = 100 * (land & (frac >= 0.5)).sum() / land.sum()
    mapa = np.zeros((H, W, 3), np.uint8); mapa[:] = BG
    base = np.array([40, 34, 26]); teal = np.array([120, 200, 214])
    ys, xs = np.where(land); fr = frac[ys, xs][:, None]
    mapa[ys, xs] = (base * (1 - fr) + teal * fr).astype(np.uint8)
    _guardar_png(_mapa_png(mapa, (H, W)), OUT / "frescor-dia.png",
                 "Dónde no aprieta el día — el frescor diurno en España",
                 "Mapa del frescor de día en España: las cumbres donde la máxima no "
                 "pasa de 24 grados ni a mediodía en verano, según AEMET.",
                 SITE + "/la-espana-que-nunca-se-colorea/")
    return dict(medio_verano_fresco=round(p50, 1), umbral=umbral,
                ini=fechas[0].isoformat(), fin=fechas[-1].isoformat(), n=n)


def estudio_techo_calor():
    """Mapa ENVOLVENTE de máximas: cada píxel pintado con la temperatura más
    alta que alcanzó en todo el periodo, con la propia paleta de AEMET. Revela
    'la España que no se colorea de rojo': casi todo enrojece; solo las cumbres
    se quedan en amarillo."""
    pal, tmp = _paleta(42)
    col = pal.astype(np.uint8)
    bandas, fechas, (H, W) = _bandas_dia(IMG / "maxima", tope=42)
    maxT = np.full((H, W), -99); valid = np.zeros((H, W), int)
    for t, ok in bandas:
        maxT = np.where(ok, np.maximum(maxT, t), maxT); valid += ok
    n = len(bandas); land = valid >= 0.6 * n
    nunca_rojo = 100 * (land & (maxT < 32)).sum() / land.sum()
    enrojece = 100 - nunca_rojo
    mapa = np.zeros((H, W, 3), np.uint8); mapa[:] = BG
    ys, xs = np.where(land)
    t2i = {int(t): i for i, t in enumerate(tmp)}
    idx = np.array([t2i.get(int(v), 0) for v in maxT[ys, xs]])
    mapa[ys, xs] = col[idx]
    _guardar_png(_mapa_png(mapa, (H, W)), OUT / "techo-del-calor.png",
                 "La España que no se colorea de rojo — el techo del calor",
                 "Mapa de máximas de España: cada zona pintada con su día más caliente "
                 "del verano; el 98 % del país enrojece (supera 32 grados) y solo el "
                 "2 %, las cumbres, no, según AEMET.",
                 SITE + "/la-espana-que-nunca-se-colorea/")
    return dict(nunca_rojo=round(nunca_rojo, 1), enrojece=round(enrojece, 1))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    noc = estudio_nocturno()
    dia = estudio_frescor()
    techo = estudio_techo_calor()
    datos = {"periodo": {"ini": noc["ini"], "fin": noc["fin"], "noches": noc["n"], "dias": dia["n"]},
             "nocturno": {k: noc[k] for k in ("profundo", "margen", "tropical")},
             "dia": {**{k: dia[k] for k in ("medio_verano_fresco", "umbral")}, **techo}}
    (OUT / "estudio-datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK estudios:", json.dumps(datos, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
