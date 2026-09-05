#!/usr/bin/env python3
"""
La forma de la noche: qué curva dibuja la temperatura mientras se duerme.

Primer análisis del archivo horario (datos/horarias/AAAA/*.csv.gz). Los valores
climatológicos diarios solo dan la mínima: un instante. Esto mide la NOCHE
ENTERA, hora a hora, y responde a lo que la mínima esconde: cuántas horas se
pasa por debajo de cada umbral, a qué hora se cruza y con qué pendiente.

Dos estaciones con la misma mínima pueden dar noches opuestas: una que cruza
los 20° a las 23:00 y aguanta nueve horas debajo, y otra que solo baja de 20°
a las 06:00, cuando ya casi es hora de levantarse.

Ventana de sueño: 23:00-07:00 hora local (9 lecturas horarias). Canarias va en
su huso (UTC+1 frente a UTC+2 peninsular en horario de verano).

Umbrales:
  20 °C  noche tropical (el que usa todo el proyecto)
  18 °C  confort para dormir
  16 °C  óptimo

AVISO: esto NO mide sueño. Mide temperatura del aire en garita meteorológica.
La relación entre una y otro depende de la vivienda, la ventilación y la
persona. Aquí solo se afirma lo que el termómetro registró.

Fuente: AEMET (red de observación, valores provisionales sin validar).

Uso:
    python analisis_curva_nocturna.py                 # todas las noches completas
    python analisis_curva_nocturna.py --noche 2026-09-03
    python analisis_curva_nocturna.py --sin-grafico
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

AEMET_DIR = Path(__file__).resolve().parent.parent
DIR_HORARIAS = AEMET_DIR / "datos" / "horarias"
CSV_ESTACIONES = AEMET_DIR / "datos" / "estaciones.csv"
DIR_ANALISIS = AEMET_DIR / "analisis"

# Ventana de sueño en hora local: de las 23:00 a las 07:00, ambas incluidas.
HORA_INICIO_LOCAL = 23
HORAS_VENTANA = 9          # 23, 00, 01, 02, 03, 04, 05, 06, 07

UMBRALES = (20.0, 18.0, 16.0)

# Husos en horario de verano. Canarias va una hora por detrás de la península.
PROV_CANARIAS = {"LAS PALMAS", "SANTA CRUZ DE TENERIFE", "STA. CRUZ DE TENERIFE"}


def dms_a_decimal(txt: str) -> float | None:
    """'402425N' -> 40.4069. Devuelve None si no se puede interpretar."""
    txt = (txt or "").strip()
    if len(txt) < 7:
        return None
    hemi = txt[-1].upper()
    try:
        g, m, s = int(txt[0:-5]), int(txt[-5:-3]), int(txt[-3:-1])
    except ValueError:
        return None
    val = g + m / 60 + s / 3600
    return -val if hemi in ("S", "W", "O") else val


def cargar_estaciones() -> dict:
    """indicativo -> {nombre, provincia, altitud, lat, lon, utc_offset}."""
    est = {}
    with open(CSV_ESTACIONES, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            prov = (r.get("provincia") or "").strip().upper()
            try:
                alt = int(float(r.get("altitud") or 0))
            except ValueError:
                alt = 0
            est[r["indicativo"]] = {
                "nombre": (r.get("nombre") or "").strip(),
                "provincia": prov,
                "altitud": alt,
                "lat": dms_a_decimal(r.get("latitud", "")),
                "lon": dms_a_decimal(r.get("longitud", "")),
                # Verano: península UTC+2, Canarias UTC+1.
                "utc_offset": 1 if prov in PROV_CANARIAS else 2,
            }
    return est


def noches_disponibles() -> list:
    # .stem deja "2026-09-02.csv" (doble extensión): cortamos por el primer punto.
    return sorted(p.name.split(".")[0] for p in DIR_HORARIAS.rglob("*.csv.gz"))


def leer_noche(fecha: str) -> dict:
    """fecha 'AAAA-MM-DD' -> {idema: {datetime_utc: ta}}."""
    ruta = DIR_HORARIAS / fecha[:4] / f"{fecha}.csv.gz"
    if not ruta.exists():
        return {}
    lecturas = defaultdict(dict)
    with gzip.open(ruta, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ta = (r.get("ta") or "").strip()
            if not ta:
                continue
            try:
                valor = float(ta)
            except ValueError:
                continue
            try:
                t = datetime.strptime(r["fint"], "%Y-%m-%dT%H:%M:%S%z")
            except (ValueError, KeyError):
                continue
            lecturas[r["idema"]][t.astimezone(timezone.utc)] = valor
    return lecturas


def curva_de_sueno(serie: dict, fecha: str, utc_offset: int) -> list | None:
    """Devuelve las 9 temperaturas de 23:00 a 07:00 hora local, o None si falta alguna.

    La noche etiquetada 'fecha' es la que TERMINA esa mañana: empieza a las
    23:00 locales del día anterior.
    """
    dia = datetime.strptime(fecha, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    # 23:00 local del día anterior, expresado en UTC.
    inicio = dia - timedelta(days=1) + timedelta(hours=HORA_INICIO_LOCAL - utc_offset)
    curva = []
    for h in range(HORAS_VENTANA):
        t = inicio + timedelta(hours=h)
        if t not in serie:
            return None
        curva.append(serie[t])
    return curva


def metricas(curva: list) -> dict:
    """Describe la noche: cuánto baja, cuándo cruza y cuántas horas aguanta."""
    t_ini, t_fin = curva[0], curva[-1]
    t_min = min(curva)
    i_min = curva.index(t_min)
    m = {
        "t_23h": t_ini,
        "t_07h": t_fin,
        "t_min": t_min,
        "hora_min": (HORA_INICIO_LOCAL + i_min) % 24,
        "caida": round(t_ini - t_min, 1),
    }
    for u in UMBRALES:
        m[f"horas_bajo_{int(u)}"] = sum(1 for t in curva if t < u)
        # Primera hora local por debajo del umbral; None si nunca baja.
        cruce = next((i for i, t in enumerate(curva) if t < u), None)
        m[f"cruce_{int(u)}"] = None if cruce is None else (HORA_INICIO_LOCAL + cruce) % 24
    return m


def clasificar(m: dict) -> str:
    """Cinco tipos de noche, por horas de frescor real durante el sueño.

    El criterio es el TIEMPO por debajo de umbral, no la mínima puntual: es la
    diferencia que los valores diarios no pueden ver.
    """
    b20, b18 = m["horas_bajo_20"], m["horas_bajo_18"]
    if b20 == 0:
        return "tropical cerrada"      # ni una hora por debajo de 20°
    if b20 <= 3:
        return "tropical rota"         # baja de 20° de madrugada, tarde
    if b18 == 0:
        return "templada"              # se libra de los 20° pero nunca refresca
    if b18 <= 4:
        return "fresca a medias"
    return "fresca"                    # 5+ horas por debajo de 18°


ORDEN_TIPOS = ["tropical cerrada", "tropical rota", "templada",
               "fresca a medias", "fresca"]


# --- Forma de la curva -----------------------------------------------------
# Clasificación INDEPENDIENTE del nivel térmico: solo mira el dibujo, no si
# hace frío o calor. Una noche a 28° y otra a 12° pueden compartir forma.
# Por eso no es circular respecto a los umbrales de arriba: son dos ejes
# distintos (cuánto refresca / cómo refresca).
RANGO_PLANA = 1.5      # °C de recorrido total por debajo del cual no hay forma
REPUNTE_MIN = 0.8      # °C que debe subir tras el mínimo para llamarlo repunte

ORDEN_FORMAS = ["descendente", "plana", "en U", "invertida", "irregular"]


def forma(curva: list) -> str:
    """descendente | plana | en U | invertida | irregular.

    descendente: el mínimo llega al final (madrugada). Es la noche de manual.
    plana:       apenas se mueve en toda la noche (típico de costa y mar).
    en U:        baja, toca fondo a media noche y repunta antes del alba.
    invertida:   el mínimo está al principio; la noche se CALIENTA.
    irregular:   se mueve mucho pero sin patrón (a menudo, mala lectura).
    """
    t_min = min(curva)
    i_min = curva.index(t_min)
    rango = max(curva) - t_min
    if rango < RANGO_PLANA:
        return "plana"
    repunte = curva[-1] - t_min          # cuánto sube desde el mínimo al alba
    n = len(curva)
    if i_min >= n - 3:                   # mínimo en las tres últimas horas
        return "descendente"
    if i_min <= 2 and curva[-1] - curva[0] >= 1.0:
        return "invertida"               # empieza frío y se calienta
    if repunte >= REPUNTE_MIN:
        return "en U"
    return "irregular"


def analizar(fechas: list, est: dict) -> list:
    filas = []
    for fecha in fechas:
        lecturas = leer_noche(fecha)
        if not lecturas:
            continue
        completas = 0
        for idema, serie in lecturas.items():
            meta = est.get(idema)
            if not meta:
                continue
            curva = curva_de_sueno(serie, fecha, meta["utc_offset"])
            if curva is None:
                continue
            completas += 1
            m = metricas(curva)
            filas.append({
                "noche": fecha, "idema": idema, "nombre": meta["nombre"],
                "provincia": meta["provincia"], "altitud": meta["altitud"],
                "lat": meta["lat"], "lon": meta["lon"],
                "curva": curva, "tipo": clasificar(m), "forma": forma(curva), **m,
            })
        print(f"  {fecha}: {completas} estaciones con la ventana 23-07 completa "
              f"(de {len(lecturas)} con alguna lectura)")
    return filas


def resumen(filas: list) -> None:
    if not filas:
        print("Sin datos suficientes.")
        return
    n = len(filas)
    print(f"\n{'='*68}\nTIPOS DE NOCHE ({n} noches-estación)\n{'='*68}")
    porc = defaultdict(int)
    for f in filas:
        porc[f["tipo"]] += 1
    for t in ORDEN_TIPOS:
        c = porc[t]
        barra = "#" * int(round(48 * c / n))
        print(f"  {t:<18} {c:>4}  {c/n:5.1%} {barra}")

    print(f"\n{'='*68}\nLA MÍNIMA NO BASTA: misma mínima, noches distintas\n{'='*68}")
    print("  Estaciones agrupadas por mínima redondeada; horas bajo 20° observadas.")
    pormin = defaultdict(list)
    for f in filas:
        pormin[round(f["t_min"])].append(f["horas_bajo_20"])
    print(f"  {'mínima':>7}  {'n':>4}  {'horas<20 mín-máx':>18}  {'mediana':>7}")
    for tmin in sorted(pormin):
        v = pormin[tmin]
        if len(v) < 8 or not (14 <= tmin <= 24):
            continue
        print(f"  {tmin:>5}°C  {len(v):>4}  {min(v):>8} - {max(v):<7}  "
              f"{statistics.median(v):>7.1f}")

    print(f"\n{'='*68}\nCURVA MEDIA POR TIPO (°C hora a hora, 23:00 -> 07:00)\n{'='*68}")
    horas = [(HORA_INICIO_LOCAL + i) % 24 for i in range(HORAS_VENTANA)]
    print("  tipo                " + " ".join(f"{h:>5}h" for h in horas) + "   caída")
    for t in ORDEN_TIPOS:
        grupo = [f["curva"] for f in filas if f["tipo"] == t]
        if not grupo:
            continue
        media = [statistics.mean(c[i] for c in grupo) for i in range(HORAS_VENTANA)]
        print(f"  {t:<18} " + " ".join(f"{v:>5.1f} " for v in media)
              + f"  {media[0]-min(media):>5.1f}")

    print(f"\n{'='*68}\nLO QUE DECIDE LA NOCHE: hora del cruce de 20°\n{'='*68}")
    cruces = defaultdict(int)
    for f in filas:
        c = f["cruce_20"]
        cruces[HORAS_VENTANA if c is None else (c - HORA_INICIO_LOCAL) % 24] += 1
    for i in sorted(cruces):
        c = cruces[i]
        etq = "nunca" if i == HORAS_VENTANA else f"{(HORA_INICIO_LOCAL + i) % 24:02d}:00"
        print(f"  {etq:>6}  {c:>4}  {c/n:5.1%}  " + "#" * int(round(40 * c / n)))
    ya = cruces.get(0, 0)
    print(f"\n  Las {ya} noches que ya empiezan por debajo de 20° ({ya/n:.0%}) son el\n"
          f"  único grupo con la noche entera fresca. Cruzar tarde equivale a no cruzar:\n"
          f"  quien pasa de 20° a las 05:00 duerme casi lo mismo que quien no baja nunca.")


def temp_bulbo_humedo(t: float, hr: float) -> float | None:
    """Temperatura de bulbo húmedo por la aproximación de Stull (2011).

    Solo necesita temperatura y humedad relativa, que es justo lo que archiva
    el parte. Válida para presión próxima a la del nivel del mar y HR > 5%.
    """
    if not (5.0 < hr <= 100.0):
        return None
    return (t * math.atan(0.151977 * (hr + 8.313659) ** 0.5)
            + math.atan(t + hr) - math.atan(hr - 1.676331)
            + 0.00391838 * hr ** 1.5 * math.atan(0.023101 * hr) - 4.686035)


def margen_evaporativo(est: dict, fechas: list) -> dict:
    """Cuántos grados puede bajar, COMO MÁXIMO, el enfriamiento por evaporación.

    Es la depresión del bulbo húmedo: T - Tw. Marca el límite físico absoluto
    de cualquier truco basado en evaporar agua (sábana húmeda, botijo,
    climatizador evaporativo). Nadie lo alcanza —una sábana no es un
    saturador perfecto— pero por debajo de ese número no se puede bajar.

    Ventana: 21:00-05:00 UTC, la madrugada, que es cuando importa.
    """
    lect = defaultdict(list)
    for fecha in fechas:
        ruta = DIR_HORARIAS / fecha[:4] / f"{fecha}.csv.gz"
        if not ruta.exists():
            continue
        with gzip.open(ruta, "rt", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    hora = int(r["fint"][11:13])
                    t, hr = float(r["ta"]), float(r["hr"])
                except (ValueError, TypeError, KeyError, IndexError):
                    continue
                if not (hora >= 21 or hora <= 5):
                    continue
                tw = temp_bulbo_humedo(t, hr)
                if tw is not None:
                    lect[r["idema"]].append((t - tw, hr))

    filas = []
    for idema, v in lect.items():
        meta = est.get(idema)
        if not meta or len(v) < 12:      # al menos 12 lecturas nocturnas
            continue
        filas.append({
            "idema": idema, "nombre": meta["nombre"], "provincia": meta["provincia"],
            "altitud": meta["altitud"], "lat": meta["lat"], "lon": meta["lon"],
            "margen": round(statistics.mean(x[0] for x in v), 1),
            "hr": round(statistics.mean(x[1] for x in v)),
            "n": len(v),
        })
    filas.sort(key=lambda f: -f["margen"])
    return {"noches": fechas, "estaciones": filas}


def resumen_evaporativo(datos: dict) -> None:
    filas = datos["estaciones"]
    if not filas:
        return
    n = len(filas)
    m = [f["margen"] for f in filas]
    print(f"\n{'='*68}\nMARGEN EVAPORATIVO (depresión del bulbo húmedo, madrugada)"
          f"\n{'='*68}")
    print("  Techo físico de la sábana húmeda y de cualquier truco evaporativo.")
    for etq, lo, hi in (("no sirve", 0, 2), ("marginal", 2, 4),
                        ("funciona", 4, 7), ("muy eficaz", 7, 99)):
        c = sum(1 for x in m if lo <= x < hi)
        print(f"  {lo}-{hi if hi < 99 else '+'} °C  {etq:<11} {c:>4}  {c/n:5.1%}  "
              + "#" * int(round(38 * c / n)))
    print(f"\n  mediana nacional: {statistics.median(m):.1f} °C")
    print(f"  estaciones donde serían posibles 6 °C o más: "
          f"{sum(1 for x in m if x >= 6)} ({sum(1 for x in m if x >= 6)/n:.0%})")


def resumen_formas(filas: list) -> None:
    """¿La forma de la noche es un rasgo del SITIO o del DÍA?

    Prueba: si una estación repite forma las tres noches más de lo que
    predice el azar, la forma la impone el lugar. El contraste se hace forma
    a forma, nunca en global: "descendente" es el 80% de las noches, así que
    repetirla no significa nada y arrastraría la media hacia el azar.
    """
    n = len(filas)
    cuenta = defaultdict(int)
    for f in filas:
        cuenta[f["forma"]] += 1
    print(f"\n{'='*68}\nFORMA DE LA CURVA (independiente del nivel térmico)\n{'='*68}")
    for k in ORDEN_FORMAS:
        c = cuenta[k]
        print(f"  {k:<13} {c:>5}  {c/n:6.1%}  " + "#" * int(round(46 * c / n)))

    por_est = defaultdict(list)
    for f in filas:
        por_est[f["idema"]].append(f["forma"])
    noches = len({f["noche"] for f in filas})
    completas = {k: v for k, v in por_est.items() if len(v) == noches}
    if noches < 2 or not completas:
        return
    N = len(completas)
    print(f"\n{'='*68}\n¿RASGO DEL SITIO O DEL DÍA?  ({N} estaciones con las "
          f"{noches} noches)\n{'='*68}")
    print(f"  {'forma':<13} {'repite ' + str(noches) + '/' + str(noches):>12}"
          f" {'esperado azar':>14} {'ratio':>7}")
    for k in ORDEN_FORMAS:
        obs = sum(1 for v in completas.values() if set(v) == {k})
        esp = N * (cuenta[k] / n) ** noches
        ratio = f"{obs/esp:.0f}x" if esp > 0.05 else "-"
        print(f"  {k:<13} {obs:>12} {esp:>14.1f} {ratio:>7}")
    print("\n  Solo cuenta como rasgo del sitio la forma cuyo ratio se despega\n"
          "  de 1. Con pocas noches, las formas raras no son concluyentes.")


def estaciones_por_forma(filas: list, forma_buscada: str) -> list:
    """Estaciones que repiten esa forma TODAS las noches medidas."""
    por_est = defaultdict(list)
    for f in filas:
        por_est[f["idema"]].append(f)
    noches = len({f["noche"] for f in filas})
    return [v for v in por_est.values()
            if len(v) == noches and {x["forma"] for x in v} == {forma_buscada}]


def pares_reveladores(filas: list, tope: int = 6) -> list:
    """Parejas de la misma noche con mínima casi igual y noches opuestas.

    Es la prueba de que el dato diario engaña: si dos estaciones marcan la
    misma mínima pero una duerme nueve horas por debajo de 20° y la otra dos,
    la mínima no describe la noche.
    """
    pares = []
    pornoche = defaultdict(list)
    for f in filas:
        pornoche[f["noche"]].append(f)
    for noche, grupo in pornoche.items():
        grupo.sort(key=lambda f: f["t_min"])
        for i, a in enumerate(grupo):
            for b in grupo[i + 1:]:
                if b["t_min"] - a["t_min"] > 0.3:
                    break
                dif = abs(a["horas_bajo_20"] - b["horas_bajo_20"])
                if dif >= 5:
                    pares.append((dif, a, b))
    # Preferimos pares con curvas limpias. Un salto al alza de más de 1,5 °C en
    # una hora de madrugada no es meteorología: es una lectura sospechosa, y no
    # queremos ilustrar el hallazgo con una estación que probablemente falla.
    def salto_max(f):
        c = f["curva"]
        return max((c[i + 1] - c[i] for i in range(len(c) - 1)), default=0)

    pares = [(d, a, b) for d, a, b in pares
             if max(salto_max(a), salto_max(b)) <= 1.5]
    pares.sort(key=lambda p: -p[0])
    # Una aparición por estación, para no repetir el mismo caso seis veces.
    vistas, sel = set(), []
    for dif, a, b in pares:
        if a["idema"] in vistas or b["idema"] in vistas:
            continue
        vistas.add(a["idema"]); vistas.add(b["idema"])
        sel.append((dif, a, b))
        if len(sel) >= tope:
            break
    return sel


def imprimir_pares(pares: list) -> None:
    if not pares:
        print("\n(no hay pares con la misma mínima y noches muy distintas)")
        return
    print(f"\n{'='*68}\nMISMA MÍNIMA, NOCHE OPUESTA\n{'='*68}")
    for dif, a, b in pares:
        print(f"\n  {a['noche']}  ·  mínima {a['t_min']:.1f}° vs {b['t_min']:.1f}°"
              f"  ->  {dif} horas de diferencia por debajo de 20°")
        for f in (a, b):
            curva = " ".join(f"{t:4.1f}" for t in f["curva"])
            print(f"    {f['nombre'][:26]:<26} ({f['altitud']:>4} m) "
                  f"{f['horas_bajo_20']}/9 h<20  [{curva}]  {f['tipo']}")


def guardar_csv(filas: list, ruta: Path) -> None:
    campos = ["noche", "idema", "nombre", "provincia", "altitud", "lat", "lon",
              "tipo", "forma", "t_23h", "t_min", "t_07h", "hora_min", "caida",
              "horas_bajo_20", "horas_bajo_18", "horas_bajo_16",
              "cruce_20", "cruce_18", "cruce_16"]
    horas = [f"t_{(HORA_INICIO_LOCAL + i) % 24:02d}h" for i in range(HORAS_VENTANA)]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(campos + horas)
        for f in filas:
            w.writerow([f.get(c, "") for c in campos] + f["curva"])
    print(f"\n-> {ruta.relative_to(AEMET_DIR)}  ({len(filas)} filas)  Fuente: AEMET")


def grafico(filas: list, ruta: Path) -> None:
    """Tres paneles. Ninguno dibuja la media por tipo: eso sería circular.

    Los tipos se DEFINEN por horas bajo umbral, así que su curva media sale
    ordenada por construcción y no demuestra nada. Lo que sí informa:
      A. curvas reales de pares con la misma mínima y noches opuestas
      B. la dispersión mínima -> horas bajo 20 (la mínima no basta)
      C. a qué hora se cruzan los 20°, que es lo que de verdad decide
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("(matplotlib no disponible: no se dibuja el gráfico)")
        return

    PAPEL, TINTA = "#efe6d6", "#161009"
    CALIDO, FRESCO = "#b23a2e", "#4a7c59"
    horas = list(range(HORAS_VENTANA))
    etiquetas = [f"{(HORA_INICIO_LOCAL + i) % 24:02d}" for i in horas]

    fig = plt.figure(figsize=(13.5, 5.6))
    fig.patch.set_facecolor(PAPEL)
    ejes = fig.subplots(1, 3, gridspec_kw={"width_ratios": [1.15, 1, 1]})
    for ax in ejes:
        ax.set_facecolor(PAPEL)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)

    # --- A. dos noches con la misma mínima -------------------------------
    ax = ejes[0]
    pares = pares_reveladores(filas, tope=1)
    for u, est in zip(UMBRALES[:2], ("-", "--")):
        ax.axhline(u, color=TINTA, linewidth=0.9, linestyle=est, alpha=0.35)
        ax.text(HORAS_VENTANA - 1.05, u + 0.2, f"{u:.0f} °C", fontsize=8,
                color=TINTA, alpha=0.6, ha="right")
    if pares:
        dif, a, b = pares[0]
        frio = a if a["horas_bajo_20"] > b["horas_bajo_20"] else b
        calor = b if frio is a else a
        for f, col in ((frio, FRESCO), (calor, CALIDO)):
            ax.plot(horas, f["curva"], color=col, linewidth=2.6, marker="o",
                    markersize=3.5)
            ax.annotate(f"{f['nombre'][:20].title()}\n{f['horas_bajo_20']} de 9 h "
                        f"bajo 20°", (0, f["curva"][0]), xytext=(6, 0),
                        textcoords="offset points", fontsize=8.5, color=col,
                        va="center", ha="left", linespacing=1.35)
        ax.set_title(f"A. Misma mínima ({frio['t_min']:.1f}° y {calor['t_min']:.1f}°),"
                     f"\n    noches opuestas · {frio['noche']}",
                     fontsize=11, loc="left", color=TINTA)
    ax.set_ylabel("temperatura del aire (°C)")

    # --- B. la mínima no predice las horas de frescor --------------------
    ax = ejes[1]
    xs = [f["t_min"] for f in filas]
    ys = [f["horas_bajo_20"] + (hash(f["idema"]) % 7 - 3) * 0.035 for f in filas]
    ax.scatter(xs, ys, s=5, color=TINTA, alpha=0.12, linewidths=0)
    ax.axvline(20, color=CALIDO, linewidth=1.2, linestyle="--", alpha=0.7)
    ax.text(20.2, 8.6, "20 °C", fontsize=8.5, color=CALIDO)
    ax.set_title("B. La mínima no basta", fontsize=11, loc="left", color=TINTA)
    ax.set_xlabel("mínima de la noche (°C)")
    ax.set_ylabel("horas por debajo de 20 °C (de 9)")
    ax.set_yticks(range(0, HORAS_VENTANA + 1))

    # --- C. la hora del cruce ------------------------------------------
    ax = ejes[2]
    conteo = [0] * (HORAS_VENTANA + 1)
    for f in filas:
        c = f["cruce_20"]
        conteo[HORAS_VENTANA if c is None else (c - HORA_INICIO_LOCAL) % 24] += 1
    n = len(filas)
    etq_c = etiquetas + ["nunca"]
    colores = [FRESCO if i <= 2 else ("#c9a227" if i <= 5 else CALIDO)
               for i in range(HORAS_VENTANA)] + [CALIDO]
    ax.bar(range(len(conteo)), [c / n * 100 for c in conteo], color=colores,
           width=0.78)
    ax.set_xticks(range(len(conteo)))
    ax.set_xticklabels(etq_c, fontsize=8.5)
    ax.set_title("C. A qué hora se baja de 20 °C", fontsize=11, loc="left",
                 color=TINTA)
    ax.set_xlabel("hora local del cruce")
    ax.set_ylabel("% de noches-estación")

    for ax in ejes[:1]:
        ax.set_xticks(horas); ax.set_xticklabels(etiquetas)
        ax.set_xlabel("hora local")

    fig.suptitle(f"La forma de la noche · {n} noches-estación · Fuente: AEMET",
                 fontsize=13, x=0.008, ha="left", color=TINTA)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, dpi=140, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"-> {ruta.relative_to(AEMET_DIR)}")


def grafico_formas(filas: list, ruta: Path) -> None:
    """Small multiples: una línea por noche, un panel por estación.

    Es la vista que revela el patrón del sitio. Todos los paneles comparten
    el MISMO RECORRIDO del eje Y (RANGO_EJE grados), centrado en la mediana
    de cada estación: así las pendientes son comparables a ojo aunque una
    estación esté a 25° y otra a 12°.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("(matplotlib no disponible: no se dibuja el gráfico de formas)")
        return

    # Recorrido común generoso: las descendentes caen 12-15 °C y las planas
    # apenas 1. Con el mismo recorrido en los ocho, esa diferencia ES el
    # gráfico: arriba salen rectas, abajo toboganes.
    RANGO_EJE = 16.0
    PAPEL, TINTA = "#efe6d6", "#161009"
    planas = estaciones_por_forma(filas, "plana")
    desc = estaciones_por_forma(filas, "descendente")
    if not planas or not desc:
        print("(sin estaciones consistentes suficientes para el gráfico de formas)")
        return

    # De las descendentes elegimos las de mayor recorrido: son el contraste.
    desc.sort(key=lambda v: -statistics.mean(max(x["curva"]) - min(x["curva"])
                                             for x in v))
    planas.sort(key=lambda v: v[0]["nombre"])
    sel = [("plana", v) for v in planas[:4]] + [("descendente", v) for v in desc[:4]]

    horas = list(range(HORAS_VENTANA))
    etq = [f"{(HORA_INICIO_LOCAL + i) % 24:02d}" for i in horas]
    colores = ("#b23a2e", "#d9744e", "#4a7c59")

    fig, ejes = plt.subplots(2, 4, figsize=(14, 6.4), sharex=True)
    fig.patch.set_facecolor(PAPEL)
    for ax, (nombre_forma, noches) in zip(ejes.flat, sel):
        ax.set_facecolor(PAPEL)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        todos = [t for x in noches for t in x["curva"]]
        centro = (max(todos) + min(todos)) / 2   # punto medio real, no mediana
        for j, x in enumerate(sorted(noches, key=lambda v: v["noche"])):
            ax.plot(horas, x["curva"], color=colores[j % len(colores)],
                    linewidth=1.9, marker="o", markersize=2.6,
                    label=x["noche"][5:] if ax is ejes.flat[0] else None)
        ax.axhline(20, color=TINTA, linewidth=0.8, alpha=0.35)
        ax.set_ylim(centro - RANGO_EJE / 2, centro + RANGO_EJE / 2)
        est = noches[0]
        ax.set_title(f"{est['nombre'][:24].title()}\n{est['provincia'][:20].title()} · "
                     f"{est['altitud']} m · {nombre_forma}",
                     fontsize=8.8, loc="left", color=TINTA, linespacing=1.3)
        ax.tick_params(labelsize=7.5)
        ax.set_xticks(horas[::2]); ax.set_xticklabels(etq[::2])
        ax.grid(axis="y", alpha=0.18)

    ejes.flat[0].legend(frameon=False, fontsize=7, loc="lower left")
    for ax in ejes[1]:
        ax.set_xlabel("hora local", fontsize=8)
    for fila in ejes:
        fila[0].set_ylabel("°C", fontsize=8)

    fig.suptitle("Una línea por noche: el patrón de cada estación\n"
                 f"Arriba, noche PLANA · abajo, DESCENDENTE · mismo recorrido "
                 f"de eje ({RANGO_EJE:.0f} °C) en los ocho · Fuente: AEMET",
                 fontsize=12, x=0.006, ha="left", color=TINTA)
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, dpi=140, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"-> {ruta.relative_to(AEMET_DIR)}")


def main() -> int:
    args = sys.argv[1:]
    if "--noche" in args:
        fechas = [args[args.index("--noche") + 1]]
    else:
        fechas = noches_disponibles()
    if not fechas:
        print("No hay ficheros en datos/horarias/.", file=sys.stderr)
        return 1

    print(f"Noches en el archivo: {', '.join(fechas)}")
    est = cargar_estaciones()
    print(f"Catálogo: {len(est)} estaciones\n")

    filas = analizar(fechas, est)
    if not filas:
        print("Ninguna noche tiene la ventana 23:00-07:00 completa todavía.",
              file=sys.stderr)
        return 1

    resumen(filas)
    resumen_formas(filas)

    # El margen evaporativo usa TODAS las noches del archivo, no solo las de
    # ventana completa: para la humedad media de madrugada basta con tener
    # lecturas nocturnas, no hace falta la ventana 23-07 entera.
    evap = margen_evaporativo(est, fechas)
    resumen_evaporativo(evap)
    ruta_evap = AEMET_DIR / "datos" / "margen_evaporativo.json"
    ruta_evap.write_text(json.dumps(evap, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    print(f"-> {ruta_evap.relative_to(AEMET_DIR)} "
          f"({len(evap['estaciones'])} estaciones)  Fuente: AEMET")
    imprimir_pares(pares_reveladores(filas))
    guardar_csv(filas, DIR_ANALISIS / "curva_nocturna.csv")
    if "--sin-grafico" not in args:
        grafico(filas, DIR_ANALISIS / "curva_nocturna.png")
        grafico_formas(filas, DIR_ANALISIS / "curva_nocturna_formas.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
