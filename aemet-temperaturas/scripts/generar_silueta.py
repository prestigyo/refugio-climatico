# Saca la SILUETA de España (solo el contorno: costa y frontera, sin las rayas
# de provincia) de datos/spain-provinces.geojson, proyectada exactamente igual
# que los puntos del mapa del Observatorio.
#
# El fichero no es topológicamente limpio —dos provincias vecinas no comparten
# los mismos vértices—, así que unir los polígonos por sus tramos no funciona:
# salían las 52 provincias. Se hace por lo bruto y seguro: se pinta el país en
# una rejilla fina, se suaviza el borde de sierra y se traza el contorno.
# Se ejecuta a mano; su resultado se pega en el generador.
import json, math, sys
import numpy as np
from matplotlib.path import Path
import matplotlib.pyplot as plt

SP = sys.argv[1]
S = 190 / 7.9                      # px por grado de latitud
K = math.cos(math.radians(40))     # los grados de longitud son más cortos
DX = (300 - 12.8 * K * S) / 2      # centrado en el lienzo de 300x190
PASO = 0.008                       # grados por celda (~1/5 de píxel)


def proy(lo, la):
    return (DX + (lo + 9.4) * K * S, (43.9 - la) * S)


d = json.load(open(SP, encoding="utf-8"))
LO0, LO1, LA0, LA1 = -9.8, 4.6, 35.8, 44.0
xs = np.arange(LO0, LO1, PASO)
ys = np.arange(LA0, LA1, PASO)
mask = np.zeros((len(ys), len(xs)), dtype=bool)

for f in d["features"]:
    if f["properties"]["cod_prov"] in ("35", "38"):   # Canarias: fuera del lienzo
        continue
    for poli in f["geometry"]["coordinates"]:
        anillo = np.asarray(poli[0])
        i0 = max(0, int((anillo[:, 0].min() - LO0) / PASO) - 1)
        i1 = min(len(xs), int((anillo[:, 0].max() - LO0) / PASO) + 2)
        j0 = max(0, int((anillo[:, 1].min() - LA0) / PASO) - 1)
        j1 = min(len(ys), int((anillo[:, 1].max() - LA0) / PASO) + 2)
        if i0 >= i1 or j0 >= j1:
            continue
        gx, gy = np.meshgrid(xs[i0:i1], ys[j0:j1])
        dentro = Path(anillo).contains_points(
            np.column_stack([gx.ravel(), gy.ravel()])).reshape(gx.shape)
        mask[j0:j1, i0:i1] |= dentro

print("celdas de tierra:", int(mask.sum()))

# Suavizar el borde de sierra de la rejilla: dos pasadas de media 3x3.
campo = mask.astype(np.float32)
for _ in range(2):
    p = np.pad(campo, 1, mode="edge")
    campo = (p[:-2, :-2] + p[:-2, 1:-1] + p[:-2, 2:] +
             p[1:-1, :-2] + p[1:-1, 1:-1] + p[1:-1, 2:] +
             p[2:, :-2] + p[2:, 1:-1] + p[2:, 2:]) / 9.0

segs = plt.contour(xs, ys, campo, levels=[0.5]).allsegs[0]
print("contornos:", len(segs))


def dp(pts, tol):
    """Douglas-Peucker iterativo: quita los puntos que no cambian la forma."""
    if len(pts) < 3:
        return pts
    guarda = [False] * len(pts)
    guarda[0] = guarda[-1] = True
    pila = [(0, len(pts) - 1)]
    while pila:
        a, b = pila.pop()
        if b <= a + 1:
            continue
        x1, y1 = pts[a]; x2, y2 = pts[b]
        dx, dy = x2 - x1, y2 - y1
        norma = math.hypot(dx, dy)
        dmax, idx = 0.0, a
        for i in range(a + 1, b):
            x, y = pts[i]
            dist = (abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norma) if norma else math.hypot(x - x1, y - y1)
            if dist > dmax:
                dmax, idx = dist, i
        if dmax > tol:
            guarda[idx] = True
            pila.append((a, idx)); pila.append((idx, b))
    return [p for p, g in zip(pts, guarda) if g]


TOL = 0.3           # px: por debajo de esto el ojo no lo distingue
MIN_LARGO = 7.0     # px de recorrido: por debajo es un islote y solo hace ruido

partes, total = [], 0
for seg in sorted(segs, key=len, reverse=True):
    p = [proy(lo, la) for lo, la in seg]
    largo = sum(math.hypot(p[i + 1][0] - p[i][0], p[i + 1][1] - p[i][1])
                for i in range(len(p) - 1))
    if largo < MIN_LARGO:
        continue
    cerrada = math.hypot(p[0][0] - p[-1][0], p[0][1] - p[-1][1]) < 0.5
    p = dp(p, TOL)
    if cerrada:
        p = p[:-1]
    if len(p) < 3:
        continue
    total += len(p)
    partes.append("M" + "L".join("%.1f %.1f" % (x, y) for x, y in p) + ("Z" if cerrada else ""))

path = "".join(partes)
print("trozos:", len(partes), "| puntos:", total, "| bytes del path:", len(path))
xmin = min(float(t) for parte in partes for t in parte.replace("M", "").replace("Z", "").replace("L", " ").split()[::2])
print("comprobacion de encaje: x de %.1f a %.1f (lienzo 0-300)" % (
    min(x for parte in partes for x in [float(v) for v in parte.replace("M", "").replace("Z", "").replace("L", " ").split()[0::2]]),
    max(x for parte in partes for x in [float(v) for v in parte.replace("M", "").replace("Z", "").replace("L", " ").split()[0::2]])))
open(SP.rsplit("/", 1)[0] + "/silueta.txt", "w", encoding="utf-8").write(path)
