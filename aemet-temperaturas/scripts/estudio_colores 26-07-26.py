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


def _fecha_larga(d):
    return f"{d.day} de {MESES[d.month]} de {d.year}"


def _lienzo(mapa_arr, cfg, pie_lineas, leyenda=None, escala=None):
    mp = Image.fromarray(mapa_arr)
    esc = 1.5; mw, mh = int(mp.width * esc), int(mp.height * esc)
    mp = mp.resize((mw, mh), Image.NEAREST)
    HEAD = 176; MARG = 44
    FOOT = 150 + (66 if escala else 26 * len(leyenda or []))
    CW, CH = mw + 2 * MARG, HEAD + mh + FOOT
    cv = Image.new("RGB", (CW, CH), BG); d = ImageDraw.Draw(cv)
    cv.paste(mp, (MARG, HEAD))
    d.text((MARG, 30), cfg["kicker"], font=_fuente(FB, 19), fill=TEJA)
    d.text((MARG, 58), cfg["titulo"], font=_fuente(FB, 48), fill=PAPER)
    d.text((MARG, 120), cfg["sub"][0], font=_fuente(FR, 22), fill=MUTED)
    d.text((MARG, 146), cfg["sub"][1], font=_fuente(FR, 22), fill=MUTED)
    y0 = HEAD + mh + 16
    d.text((MARG, y0), pie_lineas[0], font=_fuente(FB, 24), fill=cfg["acento"])
    d.text((MARG, y0 + 38), pie_lineas[1], font=_fuente(FR, 19), fill=MUTED)
    if escala:  # barra horizontal de temperatura (color -> grados)
        d.text((MARG, y0 + 70), escala["titulo"], font=_fuente(FR, 19), fill=MUTED)
        sy, sw, sh = y0 + 96, 62, 20
        for j, (rgb, lab) in enumerate(escala["pasos"]):
            x = MARG + j * sw
            d.rectangle([x, sy, x + sw - 3, sy + sh], fill=rgb)
            d.text((x + (sw - 3) / 2, sy + sh + 3), lab, font=_fuente(FR, 18),
                   fill=MUTED, anchor="ma")
    else:
        ly = y0 + 74
        for i, (col, txt) in enumerate(leyenda or []):
            yy = ly + i * 26
            d.rectangle([MARG, yy, MARG + 15, yy + 15], fill=col)
            d.text((MARG + 22, yy - 2), txt, font=_fuente(FR, 19), fill=MUTED)
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
    cfg = dict(kicker=f"ESTUDIO {P} REFUGIOS NOCTURNOS {P} DATOS AEMET",
               titulo="La España que nunca se colorea", acento=C_NUCLEO,
               sub=[f"No basta con no ser noche tropical: una mínima puntual de 19,5{G} es un falso",
                    f"alivio. Bajar de 18{G} significa horas de frescor real para dormir."])
    pie = [f"El {pn:.0f} % de España baja de 18{G} cada noche {P} sueño garantizado",
           f"Del {_fecha_larga(fechas[0])} al {_fecha_larga(fechas[-1])} {P} {n} noches {P} nochetropical.es"]
    leyenda = [(C_NUCLEO, f"baja de 18{G} cada noche {P} refugio profundo ({pn:.0f} %)"),
               (C_MARGEN, f"nunca tropical, pero roza los 20{G} {P} alivio justo ({pm:.0f} %)"),
               (C_RESTO, f"alguna noche tropical ({MAY}20{G}) ({pr:.0f} %)")]
    _guardar_png(_lienzo(mapa, cfg, pie, leyenda), OUT / "refugios-nocturnos.png",
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
    cfg = dict(kicker=f"ESTUDIO {P} REFUGIOS DE DÍA {P} DATOS AEMET",
               titulo="¿Dónde no aprieta el día?", acento=(120, 200, 214),
               sub=[f"Cuántos de los {n} días la máxima se quedó por debajo de {umbral}{G}. Cuanto más claro,",
                    "más a menudo hace fresco a mediodía. Casi todo está oscuro: de día, España arde."])
    pie = [f"Solo el {p50:.0f} % de España tiene medio verano con la máxima < {umbral}{G}",
           f"Del {_fecha_larga(fechas[0])} al {_fecha_larga(fechas[-1])} {P} {n} días {P} nochetropical.es"]
    leyenda = [((120, 200, 214), "las cumbres que resisten: Sierra Nevada, Pirineo, Cantábrica, Gúdar"),
               ((70, 62, 48), "de día también aprieta")]
    _guardar_png(_lienzo(mapa, cfg, pie, leyenda), OUT / "frescor-dia.png",
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
    cfg = dict(kicker=f"ESTUDIO {P} EL TECHO DEL CALOR {P} DATOS AEMET",
               titulo="La España que no se colorea de rojo", acento=(255, 223, 0),
               sub=[f"Cada zona, pintada con la temperatura más alta que alcanzó en {n} días. Casi",
                    "toda España enrojece; solo las cumbres se quedan en amarillo o naranja."])
    pie = [f"El {enrojece:.0f} % de España llega al rojo ({MAY}32{G}) algún día {P} solo el {nunca_rojo:.0f} % no",
           f"Del {_fecha_larga(fechas[0])} al {_fecha_larga(fechas[-1])} {P} {n} días {P} máximas de AEMET {P} nochetropical.es"]
    escala = {"titulo": f"Escala de la máxima alcanzada ({G}C) {P} el amarillo son las cumbres, el magenta el horno:",
              "pasos": [((255, 255, 0), "22"), ((255, 191, 0), "26"), ((255, 127, 0), "30"),
                        ((255, 0, 0), "32"), ((255, 51, 178), "36"), ((208, 52, 113), "40")]}
    _guardar_png(_lienzo(mapa, cfg, pie, escala=escala), OUT / "techo-del-calor.png",
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
