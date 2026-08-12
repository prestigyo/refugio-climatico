#!/usr/bin/env python3
"""Saca la marca de nochetropical.es como archivos sueltos y descargables.

El logo existe desde el principio —la luna menguante con el punto teja— pero
solo vivía en dos sitios: dentro del favicon y dibujado a mano en la cabecera de
cada página. Nunca ha habido un fichero que se pueda descargar, y eso hace falta
para tres cosas que empiezan ahora: la firma del correo, la sala de prensa (un
medio que te cite quiere el logo) y cualquiera que te enlace.

Escribe en aemet-temperaturas/img/, que el build copia a docs/img/:

    marca-luna.svg              solo el símbolo, vectorial
    marca-completa.svg          símbolo + nochetropical.es
    marca-luna-512.png          símbolo, fondo transparente
    marca-luna-1024.png         íd. en grande
    marca-luna-oscuro-1024.png  sobre el fondo de la web, para fondos claros

El SVG es lo que hay que mandar a un medio: no pierde calidad a ningún tamaño.
El PNG transparente sirve para todo lo demás.

    python generar_logos.py
"""
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("hace falta Pillow:  pip install --user pillow")

DESTINO = Path(__file__).resolve().parent.parent / "img"

# La paleta de la web. La luna es del color del papel; el punto, teja.
PAPEL = "#efe6d6"
TEJA = "#d9744e"
FONDO = "#1f1810"

# Geometría original del favicon, en un lienzo de 100x100.
LUNA_X, LUNA_Y, LUNA_R = 45.0, 52.0, 30.0     # el disco
CORTE_X, CORTE_Y, CORTE_R = 60.0, 44.0, 29.0  # lo que se le quita para el menguante
PUNTO_X, PUNTO_Y, PUNTO_R = 73.0, 34.0, 6.5   # el punto teja: la noche que no enfría


def _mascara(ident: str, esc: float = 1.0, dx: float = 0.0, dy: float = 0.0) -> str:
    """El mordisco de la luna, como máscara.

    Con fill-rule="evenodd" y dos circunferencias que se salen la una de la
    otra no sale un menguante: sale un anillo, porque solo se quita la parte
    común y el resto del segundo círculo también se pinta. Con máscara se
    borra justo donde tapa, y sale una luna a cualquier tamaño y sobre
    cualquier fondo."""
    return (f'  <mask id="{ident}">\n'
            f'    <rect width="100%" height="100%" fill="#fff"/>\n'
            f'    <circle cx="{CORTE_X * esc + dx:.2f}" cy="{CORTE_Y * esc + dy:.2f}" '
            f'r="{CORTE_R * esc:.2f}" fill="#000"/>\n'
            f'  </mask>\n')


def svg_luna(color=PAPEL, punto=TEJA) -> str:
    """El símbolo en vectorial, con fondo transparente."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
        'width="100" height="100" role="img" aria-label="nochetropical.es">\n'
        + _mascara("luna") +
        f'  <circle cx="{LUNA_X}" cy="{LUNA_Y}" r="{LUNA_R}" fill="{color}" '
        f'mask="url(#luna)"/>\n'
        f'  <circle cx="{PUNTO_X}" cy="{PUNTO_Y}" r="{PUNTO_R}" fill="{punto}"/>\n'
        '</svg>\n')


def svg_completa() -> str:
    """Símbolo y nombre, para cabeceras y firmas de correo."""
    e, dx, dy = 0.62, 6.0, 14.0
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 100" '
        'width="420" height="100" role="img" aria-label="nochetropical.es">\n'
        + _mascara("lunac", e, dx, dy) +
        f'  <circle cx="{LUNA_X * e + dx:.2f}" cy="{LUNA_Y * e + dy:.2f}" '
        f'r="{LUNA_R * e:.2f}" fill="{PAPEL}" mask="url(#lunac)"/>\n'
        f'  <circle cx="{PUNTO_X * e + dx:.2f}" cy="{PUNTO_Y * e + dy:.2f}" '
        f'r="{PUNTO_R * e:.2f}" fill="{TEJA}"/>\n'
        f'  <text x="86" y="63" font-family="Fraunces,Georgia,serif" '
        f'font-weight="600" font-size="38" fill="{PAPEL}">nochetropical.es</text>\n'
        '</svg>\n')

def png_luna(lado: int, fondo: str | None = None) -> Image.Image:
    """El símbolo en PNG. Se dibuja al cuádruple y se reduce, que es la manera
    de que los bordes salgan limpios sin antialias del propio dibujo."""
    esc = lado * 4 / 100.0
    lienzo = Image.new("RGBA", (lado * 4, lado * 4), (0, 0, 0, 0))
    luna = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(luna)
    d.ellipse([(LUNA_X - LUNA_R) * esc, (LUNA_Y - LUNA_R) * esc,
               (LUNA_X + LUNA_R) * esc, (LUNA_Y + LUNA_R) * esc], fill=PAPEL)
    # El mordisco: se borra de verdad, no se tapa con el color del fondo. Por eso
    # el logo se puede poner encima de cualquier cosa.
    d.ellipse([(CORTE_X - CORTE_R) * esc, (CORTE_Y - CORTE_R) * esc,
               (CORTE_X + CORTE_R) * esc, (CORTE_Y + CORTE_R) * esc],
              fill=(0, 0, 0, 0))
    d.ellipse([(PUNTO_X - PUNTO_R) * esc, (PUNTO_Y - PUNTO_R) * esc,
               (PUNTO_X + PUNTO_R) * esc, (PUNTO_Y + PUNTO_R) * esc], fill=TEJA)
    if fondo:
        base = Image.new("RGBA", lienzo.size, fondo)
        r = int(24 * esc)
        mascara = Image.new("L", lienzo.size, 0)
        ImageDraw.Draw(mascara).rounded_rectangle([0, 0, lienzo.size[0] - 1,
                                                   lienzo.size[1] - 1], r, fill=255)
        base.putalpha(mascara)
        base.alpha_composite(luna)
        luna = base
    return luna.resize((lado, lado), Image.LANCZOS)


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    salidas = []

    for nombre, texto in (("marca-luna.svg", svg_luna()),
                          ("marca-completa.svg", svg_completa())):
        (DESTINO / nombre).write_text(texto, encoding="utf-8")
        salidas.append(nombre)

    for lado in (512, 1024):
        f = DESTINO / f"marca-luna-{lado}.png"
        png_luna(lado).save(f, optimize=True)
        salidas.append(f.name)
    f = DESTINO / "marca-luna-oscuro-1024.png"
    png_luna(1024, FONDO).save(f, optimize=True)
    salidas.append(f.name)

    for n in salidas:
        print(f"   {n:<32} {(DESTINO / n).stat().st_size / 1024:6.1f} KB")
    print(f"\n{len(salidas)} archivos en {DESTINO}")
    print("Sube esa carpeta al repo: el build los copia a docs/img/.")


if __name__ == "__main__":
    main()
