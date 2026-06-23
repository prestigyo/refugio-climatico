#!/usr/bin/env python3
"""
Genera GIFs animados de la ola de calor a partir de los mapas diarios de AEMET
que recoge descarga_aemet.py (images/peninsula/{minima,maxima}/YYYY-MM-DD.png).

Produce:
  docs/ola-minimas.gif    -> mínimas nocturnas, día a día (la tesis: los
                             refugios del interior aguantan azules mientras
                             la costa se pone roja de noche).
  docs/ola-dia-noche.gif  -> doble panel máximas | mínimas: de día casi todo
                             arde; de noche, los refugios resisten.

Reproducible: vuelve a ejecutarlo cuando haya más días y el GIF crecerá solo.

Uso:
    python scripts/generar_gif.py
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
AEMET_DIR = SCRIPT_DIR.parent
REPO_ROOT = AEMET_DIR.parent
IMG_DIR = AEMET_DIR / "images" / "peninsula"
DOCS_DIR = REPO_ROOT / "docs"

BG = (22, 16, 9)        # #161009
PAPER = (239, 230, 214)
TEJA = (217, 116, 78)
TEAL = (150, 182, 196)
MUTED = (160, 148, 124)

MESES = ["", "ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]

FUENTES = [
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/Arial.ttf",
    "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def fuente(size: int) -> ImageFont.FreeTypeFont:
    for f in FUENTES:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def fecha_bonita(nombre: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", nombre)
    if not m:
        return nombre
    a, mes, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{d} {MESES[mes]} {a}"


def archivos(tipo: str, zona: str = "peninsula") -> list[Path]:
    base = AEMET_DIR / "images" / zona
    return sorted(Path(p) for p in glob.glob(str(base / tipo / "*.png")))


def texto_centrado(draw, cx, y, txt, fnt, fill):
    b = draw.textbbox((0, 0), txt, font=fnt)
    draw.text((cx - (b[2] - b[0]) / 2, y), txt, font=fnt, fill=fill)


def texto_derecha(draw, x, y, txt, fnt, fill):
    b = draw.textbbox((0, 0), txt, font=fnt)
    draw.text((x - (b[2] - b[0]), y), txt, font=fnt, fill=fill)


def duraciones(n: int, normal=380, ultimo=1700, primero=900) -> list[int]:
    d = [normal] * n
    if n:
        d[0] = primero
        d[-1] = ultimo
    return d


def gif_simple(tipo: str, etiqueta: str, salida: Path, color_etq, zona: str = "peninsula") -> None:
    fs = archivos(tipo, zona)
    if not fs:
        print(f"  (sin imágenes en {tipo})")
        return
    base = Image.open(fs[0]).convert("RGB")
    w, h = base.size
    band = 46
    f_fecha, f_etq = fuente(24), fuente(15)
    frames = []
    for p in fs:
        mapa = Image.open(p).convert("RGB").resize((w, h))
        lienzo = Image.new("RGB", (w, h + band), BG)
        lienzo.paste(mapa, (0, band))
        d = ImageDraw.Draw(lienzo)
        d.text((16, 14), etiqueta, font=f_etq, fill=color_etq)
        texto_derecha(d, w - 16, 9, fecha_bonita(p.name), f_fecha, PAPER)
        d.line([(0, band - 1), (w, band - 1)], fill=TEJA, width=2)
        frames.append(lienzo)
    salida.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(salida, save_all=True, append_images=frames[1:],
                   duration=duraciones(len(frames)), loop=0, optimize=True)
    print(f"  OK {salida.name}: {len(frames)} frames, {salida.stat().st_size/1024:.0f} KB")


def gif_dual(salida: Path) -> None:
    fmax = {p.name: p for p in archivos("maxima")}
    fmin = {p.name: p for p in archivos("minima")}
    comunes = sorted(set(fmax) & set(fmin))
    if not comunes:
        print("  (sin fechas comunes máx/mín)")
        return
    base = Image.open(fmin[comunes[0]]).convert("RGB")
    w, h = base.size
    band = 52
    gap = 6
    W = w * 2 + gap
    f_fecha, f_pan = fuente(26), fuente(16)
    frames = []
    for nombre in comunes:
        izq = Image.open(fmax[nombre]).convert("RGB").resize((w, h))
        der = Image.open(fmin[nombre]).convert("RGB").resize((w, h))
        lienzo = Image.new("RGB", (W, h + band), BG)
        lienzo.paste(izq, (0, band))
        lienzo.paste(der, (w + gap, band))
        d = ImageDraw.Draw(lienzo)
        d.text((16, 16), "DÍA · máximas", font=f_pan, fill=TEJA)
        texto_derecha(d, W - 16, 16, "NOCHE · mínimas", f_pan, TEAL)
        texto_centrado(d, W / 2, 12, fecha_bonita(nombre), f_fecha, PAPER)
        d.line([(0, band - 1), (W, band - 1)], fill=TEJA, width=2)
        frames.append(lienzo)
    salida.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(salida, save_all=True, append_images=frames[1:],
                   duration=duraciones(len(frames)), loop=0, optimize=True)
    print(f"  OK {salida.name}: {len(frames)} frames, {salida.stat().st_size/1024:.0f} KB")


def gif_vertical(salida: Path) -> None:
    """Doble panel apilado (máximas arriba, mínimas abajo): formato vertical
    para que se vea bien en móvil (WhatsApp, stories)."""
    fmax = {p.name: p for p in archivos("maxima")}
    fmin = {p.name: p for p in archivos("minima")}
    comunes = sorted(set(fmax) & set(fmin))
    if not comunes:
        print("  (sin fechas comunes máx/mín)")
        return
    base = Image.open(fmin[comunes[0]]).convert("RGB")
    w, h = base.size
    band, strip = 46, 28
    H = band + strip + h + strip + h
    f_fecha, f_lbl = fuente(24), fuente(15)
    frames = []
    for nombre in comunes:
        arriba = Image.open(fmax[nombre]).convert("RGB").resize((w, h))
        abajo = Image.open(fmin[nombre]).convert("RGB").resize((w, h))
        lienzo = Image.new("RGB", (w, H), BG)
        lienzo.paste(arriba, (0, band + strip))
        lienzo.paste(abajo, (0, band + strip + h + strip))
        d = ImageDraw.Draw(lienzo)
        d.text((16, 14), "Refugio Climático", font=f_lbl, fill=TEJA)
        texto_derecha(d, w - 16, 9, fecha_bonita(nombre), f_fecha, PAPER)
        d.line([(0, band - 1), (w, band - 1)], fill=TEJA, width=2)
        d.text((16, band + 6), "DÍA · máximas", font=f_lbl, fill=TEJA)
        d.text((16, band + strip + h + 6), "NOCHE · mínimas", font=f_lbl, fill=TEAL)
        frames.append(lienzo)
    salida.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(salida, save_all=True, append_images=frames[1:],
                   duration=duraciones(len(frames)), loop=0, optimize=True)
    print(f"  OK {salida.name}: {len(frames)} frames, {salida.stat().st_size/1024:.0f} KB")


def og_image(salida: Path) -> None:
    """Imagen 1200x630 para og:image (preview al compartir en redes/buscadores)."""
    W, H = 1200, 630
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    fmin = archivos("minima")
    if fmin:
        m = Image.open(fmin[-1]).convert("RGB")
        mw = 600
        mh = int(m.height * mw / m.width)
        canvas.paste(m.resize((mw, mh)), (W - mw, (H - mh) // 2))
    f_k, f_h, f_s, f_m = fuente(22), fuente(54), fuente(26), fuente(22)
    x = 60
    d.text((x, 70), "REFUGIO CLIMÁTICO · DATOS AEMET", font=f_k, fill=TEJA)
    d.line([(x, 106), (x + 320, 106)], fill=TEJA, width=2)
    d.text((x, 136), "El mapa del calor", font=f_h, fill=PAPER)
    d.text((x, 198), "que no te deja dormir", font=f_h, fill=(232, 154, 115))
    d.text((x, 300), "¿Cuántas noches tropicales", font=f_s, fill=PAPER)
    d.text((x, 334), "aguanta tu pueblo?", font=f_s, fill=PAPER)
    d.text((x, 432), "848 estaciones · 10 veranos de AEMET", font=f_m, fill=MUTED)
    salida.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(salida)
    print(f"  OK {salida.name}: {salida.stat().st_size/1024:.0f} KB")


def main() -> int:
    print("Generando GIFs de la ola de calor...")
    # GIFs independientes (para embeber responsive: lado a lado en escritorio,
    # apilados en móvil).
    gif_simple("maxima", "Máximas · de día", DOCS_DIR / "ola-maximas.gif", TEJA)
    gif_simple("minima", "Mínimas · de noche", DOCS_DIR / "ola-minimas.gif", TEAL)
    # Canarias (también España): solo mínimas, que es el dato que importa de noche.
    gif_simple("minima", "Mínimas · de noche · Canarias",
               DOCS_DIR / "ola-canarias-minimas.gif", TEAL, zona="canarias")
    # Doble panel en un solo archivo para compartir (horizontal y vertical).
    gif_dual(DOCS_DIR / "ola-dia-noche.gif")               # horizontal: X, escritorio
    gif_vertical(DOCS_DIR / "ola-dia-noche-vertical.gif")  # vertical: WhatsApp, móvil
    og_image(DOCS_DIR / "og.png")                          # imagen social / og:image
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
