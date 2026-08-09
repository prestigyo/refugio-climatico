#!/usr/bin/env python3
"""Deja las imágenes de los artículos listas para publicar.

Coge lo que haya en aemet-temperaturas/fotos/ (los originales, del tamaño que
sean) y escribe en aemet-temperaturas/img/ las versiones que sirve la web:

    img/<nombre>-800.webp     móvil
    img/<nombre>-1200.webp    tamaño normal de lectura
    img/<nombre>-1600.webp    pantallas grandes y retina
    img/<nombre>.jpg          respaldo para lo que no entienda WebP

Por qué así y no subir el original tal cual:

  · PESO. Un original de cámara o de un generador de imágenes ronda los 2-4 MB.
    Eso en un móvil con datos es medio segundo de espera y puntos perdidos en
    Core Web Vitals, que Google sí mide. Estas salen en 60-200 KB.
  · METADATOS. Los originales llevan EXIF dentro: cámara, software, a veces
    coordenadas GPS de dónde se hizo la foto. Al reescribir la imagen no se
    copia nada de eso; solo se pone el copyright que le digamos.
  · FORMATO. WebP pesa entre un 25 % y un 35 % menos que un JPEG de la misma
    calidad y lo entiende el 97 % de los navegadores. El .jpg queda de respaldo
    para el 3 % restante.

    python preparar_imagenes.py                    # todas las que haya
    python preparar_imagenes.py bosque-sombra      # solo esa
    python preparar_imagenes.py bosque-sombra --3x2  # y recórtala a apaisada

El recorte 3:2 es para los originales verticales: en un artículo una imagen
vertical ocupa una pantalla entera y obliga a hacer scroll para seguir leyendo,
además de pesar el doble. Se recorta por el centro.

Y después: subir aemet-temperaturas/img/ al repo. De ahí a docs/img/ —que es lo
único que publica GitHub Pages— las lleva solo el build, en copiar_imagenes()
de generar_calculadora.py. Se suben una vez y a la carpeta de material fuente,
como los CSV: no hay que acordarse de nada más.
"""
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("hace falta Pillow:  pip install --user pillow")

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "fotos"
DESTINO = RAIZ / "img"

ANCHOS = (800, 1200, 1600)
CALIDAD_WEBP = 82      # por encima de 85 el archivo crece y no se nota
CALIDAD_JPG = 84
AUTOR = "nochetropical.es"


def recorta_3x2(im):
    """Recorte centrado a 3:2 apaisado. Solo para originales verticales."""
    objetivo = 3 / 2
    actual = im.width / im.height
    if abs(actual - objetivo) < 0.02:
        return im
    if actual > objetivo:                       # demasiado ancha: sobra a los lados
        ancho = round(im.height * objetivo)
        izq = (im.width - ancho) // 2
        return im.crop((izq, 0, izq + ancho, im.height))
    alto = round(im.width / objetivo)           # demasiado alta: sobra arriba y abajo
    arriba = (im.height - alto) // 2
    return im.crop((0, arriba, im.width, arriba + alto))


def prepara(origen: Path, apaisar: bool = False) -> None:
    im = Image.open(origen)
    # Respeta la orientación que venga en el EXIF y luego olvida el EXIF: al
    # copiar los píxeles a una imagen nueva no viaja ningún metadato original.
    try:
        from PIL import ImageOps
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    if apaisar:
        im = recorta_3x2(im)
    limpia = Image.new(im.mode, im.size)
    limpia.putdata(list(im.getdata()))

    nombre = origen.stem
    DESTINO.mkdir(parents=True, exist_ok=True)
    print(f"{origen.name}  ({im.width}x{im.height}, {origen.stat().st_size/1024:.0f} KB)")

    for ancho in ANCHOS:
        if ancho > limpia.width:
            continue          # nunca agrandar: solo se vería peor y pesaría más
        alto = round(limpia.height * ancho / limpia.width)
        chica = limpia.resize((ancho, alto), Image.LANCZOS)
        salida = DESTINO / f"{nombre}-{ancho}.webp"
        chica.save(salida, "WEBP", quality=CALIDAD_WEBP, method=6)
        print(f"   {salida.name:<34} {ancho}x{alto}  {salida.stat().st_size/1024:5.0f} KB")

    ancho_jpg = min(1200, limpia.width)
    alto_jpg = round(limpia.height * ancho_jpg / limpia.width)
    respaldo = DESTINO / f"{nombre}.jpg"
    limpia.resize((ancho_jpg, alto_jpg), Image.LANCZOS).save(
        respaldo, "JPEG", quality=CALIDAD_JPG, optimize=True, progressive=True)
    print(f"   {respaldo.name:<34} {ancho_jpg}x{alto_jpg}  {respaldo.stat().st_size/1024:5.0f} KB")

    # Comprobación de que no se ha colado nada del original.
    resto = Image.open(DESTINO / f"{nombre}-{min(a for a in ANCHOS if a <= limpia.width)}.webp")
    sobra = getattr(resto, "info", {}).get("exif") or getattr(resto, "_getexif", lambda: None)()
    print(f"   metadatos heredados: {'SÍ — revisar' if sobra else 'ninguno'}\n")


def main() -> None:
    if not ORIGEN.exists():
        sys.exit(f"no existe {ORIGEN}: crea la carpeta y mete ahí los originales")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apaisar = "--3x2" in sys.argv
    filtro = args[0] if args else ""
    fotos = [f for f in sorted(ORIGEN.iterdir())
             if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
             and (not filtro or filtro in f.stem)]
    if not fotos:
        sys.exit("no hay imágenes que preparar")
    for f in fotos:
        prepara(f, apaisar)
    print(f"listo en {DESTINO}")


if __name__ == "__main__":
    main()
