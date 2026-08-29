#!/usr/bin/env python3
"""
¿Dónde están creciendo más deprisa las noches tropicales?

Hipótesis de partida: el crecimiento más rápido NO está en el litoral, donde el
fenómeno ya estaba extendido y queda poco margen (efecto techo), sino en el
interior a media altitud, en pueblos que hace una década apenas pasaban noches
tropicales y hoy acumulan varias semanas.

Análisis descriptivo de lo registrado en 2017-2026. Ejecución manual, no entra
en el workflow diario y no genera ninguna página.

Cuatro trampas metodológicas que este script resuelve explícitamente:

  1. VERANO INCOMPLETO. 2026 no tiene septiembre. Comparar un verano truncado
     con nueve completos hundiría el último punto, que es el que más pesa en la
     pendiente. Solución: ventana idéntica en todos los años (1 de junio hasta
     el último día con datos, recortado como máximo al 25 de agosto), más una
     serie de control junio-septiembre sin 2026 para verificar la dirección.

  2. TECHO Y SUELO. Una estación con 80 noches sobre 81 posibles no puede
     crecer. Se reporta siempre el nivel de partida y se marca cuando supera el
     80 % de las noches posibles.

  3. COMPARACIONES MÚLTIPLES. Con ~850 estaciones, unas 40 saldrán
     "significativas" al 5 % por puro azar. Por eso NO se ordena por p-valor ni
     se presenta un top de significativas: se ordena por tamaño del efecto y se
     acompaña cada pendiente de su intervalo de confianza del 95 %.

  4. SERIES NO HOMOGENEIZADAS. Un traslado de garita o un cambio de sensor
     produce saltos artificiales. Se marcan los saltos sospechosos como
     posible_inhomogeneidad para revisión manual; no se corrigen ni se eliminan.

Salidas:
  datos/tendencia_estaciones.csv
  datos/tendencia_resumen.json
  resumen por consola

Fuente: AEMET (valores climatológicos diarios).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Reutilizamos lo que ya existe: los cargadores y el umbral de noche tropical
# del análisis nocturno, y la maquinaria de costa del análisis del gradiente.
import analisis_refugios_nocturnos as arn  # noqa: E402
import analisis_gradiente as ag            # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATOS = ROOT / "datos"

FUENTE = "AEMET"
UMBRAL = arn.UMBRAL_NOCHE_TROPICAL      # 20,0 °C, criterio del proyecto

VENTANA_INI = (6, 1)                    # 1 de junio
VENTANA_FIN_TOPE = (8, 25)              # tope; se recorta al último día con datos
COBERTURA_MIN = 0.90                    # 90 % de días con dato en la ventana
VERANOS_MIN = 8                         # de los diez posibles
N_EXTREMOS = 3                          # veranos que promedian nivel inicial/final
UMBRAL_TECHO = 0.80                     # 80 % de las noches posibles
SIGMAS_SALTO = 3.0
DIST_COSTA_KM = 30.0

FRANJAS = (
    (None, 200.0, "<200"),
    (200.0, 500.0, "200-500"),
    (500.0, 800.0, "500-800"),
    (800.0, 1200.0, "800-1200"),
    (1200.0, None, ">1200"),
)

# t de Student al 95 % bilateral, df = 1..30; por encima, la normal
T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
       2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
       2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]

# El catálogo de AEMET arrastra dos grafías de la misma provincia
NORMALIZA_PROV = {
    "ILLES BALEARS": "BALEARES",
    "STA. CRUZ DE TENERIFE": "SANTA CRUZ DE TENERIFE",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("tendencia")


def t95(df: int) -> float:
    if df < 1:
        return float("nan")
    return T95[df - 1] if df <= 30 else 1.96


def franja(alt: float) -> str:
    for lo, hi, et in FRANJAS:
        if (lo is None or alt >= lo) and (hi is None or alt < hi):
            return et
    return ">1200"


def dias_ventana(anio: int, ini, fin) -> int:
    a = date(anio, *ini)
    b = date(anio, *fin)
    return (b - a).days + 1


def en_ventana(mes: int, dia: int, ini, fin) -> bool:
    return (mes, dia) >= ini and (mes, dia) <= fin


# ---------------------------------------------------------------- regresión

def regresion(xs, ys):
    """Mínimos cuadrados con ordenada. Aritmética pura: cuatro sumatorios."""
    n = len(xs)
    if n < 3:
        return None
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    den = n * sxx - sx * sx
    if den == 0:
        return None
    b = (n * sxy - sx * sy) / den
    a = (sy - b * sx) / n
    my = sy / n
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    sxx_c = sxx - sx * sx / n
    if n > 2 and sxx_c > 0 and ss_res >= 0:
        se = (ss_res / (n - 2) / sxx_c) ** 0.5
    else:
        se = float("nan")
    t = t95(n - 2)
    return {"pendiente": b, "ordenada": a, "r2": r2, "error_std": se,
            "ic_inf": b - t * se, "ic_sup": b + t * se, "n": n}


def salto_sospechoso(serie):
    """
    Marca inhomogeneidades: un salto entre veranos consecutivos que se sale de
    la variabilidad interanual de la propia estación.

    Se contrasta cada salto contra la media y la desviación típica de LOS DEMÁS
    saltos (leave-one-out). Con solo 9 diferencias, el z-score máximo posible
    frente a la desviación del conjunto completo es (n-1)/sqrt(n) = 2,67, así
    que un umbral de 3 sigma calculado sobre el conjunto entero no podría
    dispararse nunca. Excluyendo el propio punto, sí.

    Devuelve (marcado, salto_mayor_en_valor_absoluto).
    """
    ys = [v for _, v in serie]
    dif = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
    if len(dif) < 4:
        return False, (max(dif, key=abs) if dif else 0.0)
    marcado = False
    for i, d in enumerate(dif):
        resto = dif[:i] + dif[i + 1:]
        m = sum(resto) / len(resto)
        var = sum((r - m) ** 2 for r in resto) / (len(resto) - 1)
        sd = var ** 0.5
        if sd > 0 and abs(d - m) > SIGMAS_SALTO * sd:
            marcado = True
            break
    return marcado, max(dif, key=abs)


# ---------------------------------------------------------------- cálculo

def cuenta_por_verano(df, ini, fin, excluir_anios=()):
    """
    {indicativo: {anio: (noches_tropicales, dias_con_dato, dias_ventana)}}
    Noche tropical con el mismo criterio que el resto del proyecto: tmin > 20,0.
    """
    d = df[df["tmin"].notna()].copy()
    d = d[[en_ventana(m, dd, ini, fin) for m, dd in zip(d["mes"], d["fecha"].dt.day)]]
    if excluir_anios:
        d = d[~d["anio"].isin(excluir_anios)]
    d["trop"] = d["tmin"] > UMBRAL
    g = d.groupby(["indicativo", "anio"]).agg(trop=("trop", "sum"), dias=("tmin", "size"))
    out = {}
    for (ind, anio), fila in g.iterrows():
        out.setdefault(str(ind), {})[int(anio)] = (
            int(fila["trop"]), int(fila["dias"]), dias_ventana(int(anio), ini, fin))
    return out


def analiza(conteos, meta, idx_costa):
    """Una fila por estación válida, más el recuento de descartes por motivo."""
    filas, descartes = [], {}
    for ind, anios in conteos.items():
        validos = {a: v for a, v in anios.items() if v[1] >= COBERTURA_MIN * v[2]}
        if len(validos) < VERANOS_MIN:
            descartes[ind] = ("pocos_veranos_validos" if len(anios) >= VERANOS_MIN
                              else "serie_corta")
            continue
        if ind not in meta:
            descartes[ind] = "sin_metadatos"
            continue
        m = meta[ind]
        serie = sorted((a, float(v[0])) for a, v in validos.items())
        xs = [a for a, _ in serie]
        ys = [v for _, v in serie]
        reg = regresion(xs, ys)
        if reg is None:
            descartes[ind] = "regresion_imposible"
            continue
        k = min(N_EXTREMOS, len(ys) // 2) or 1
        nivel_ini = sum(ys[:k]) / k
        nivel_fin = sum(ys[-k:]) / k
        posibles = validos[xs[0]][2]
        marcado, salto = salto_sospechoso(serie)
        dc = ag.distancia_a_costa(m["lat"], m["lon"], idx_costa) if idx_costa else None
        filas.append({
            "indicativo": ind, "nombre": m["nombre"],
            "provincia": NORMALIZA_PROV.get(m["provincia"].strip().upper(),
                                            m["provincia"].strip().upper()),
            "altitud_m": m["altitud_m"], "lat": round(m["lat"], 4), "lon": round(m["lon"], 4),
            "dist_costa_km": round(dc, 1) if dc is not None else "",
            "grupo_costa": ("litoral" if (dc is not None and dc <= DIST_COSTA_KM)
                            else "interior"),
            "franja_altitud": franja(m["altitud_m"]),
            "n_veranos": len(ys), "anio_ini": xs[0], "anio_fin": xs[-1],
            "noches_posibles": posibles,
            "nivel_partida": round(nivel_ini, 2),
            "nivel_final": round(nivel_fin, 2),
            "cambio_absoluto": round(nivel_fin - nivel_ini, 2),
            "pendiente_noches_anio": round(reg["pendiente"], 4),
            "ic95_inf": round(reg["ic_inf"], 4),
            "ic95_sup": round(reg["ic_sup"], 4),
            "ic95_excluye_cero": "si" if reg["ic_inf"] * reg["ic_sup"] > 0 else "no",
            "r2": round(reg["r2"], 4),
            "error_std": round(reg["error_std"], 4),
            "cerca_del_techo": "si" if nivel_ini > UMBRAL_TECHO * posibles else "no",
            "posible_inhomogeneidad": "si" if marcado else "no",
            "salto_max_veranos": round(salto, 1),
            "serie": ";".join(f"{a}:{int(v)}" for a, v in serie),
            "fuente": FUENTE,
        })
    return filas, descartes


def agrega(filas, clave):
    out = {}
    for f in filas:
        out.setdefault(f[clave], []).append(f["pendiente_noches_anio"])
    res = {}
    for k, v in sorted(out.items()):
        res[k] = {"n_estaciones": len(v),
                  "pendiente_media": round(sum(v) / len(v), 4),
                  "pendiente_mediana": round(median(v), 4),
                  "n_suben": sum(1 for x in v if x > 0),
                  "n_bajan": sum(1 for x in v if x < 0)}
    return res


def agrega_cruce(filas):
    out = {}
    for f in filas:
        out.setdefault(f["franja_altitud"], {}).setdefault(f["grupo_costa"], []).append(
            f["pendiente_noches_anio"])
    res = {}
    for _, _, et in FRANJAS:
        if et not in out:
            continue
        res[et] = {g: {"n_estaciones": len(v),
                       "pendiente_media": round(sum(v) / len(v), 4),
                       "pendiente_mediana": round(median(v), 4)}
                   for g, v in sorted(out[et].items())}
    return res


COLUMNAS = ["indicativo", "nombre", "provincia", "altitud_m", "lat", "lon",
            "dist_costa_km", "grupo_costa", "franja_altitud",
            "n_veranos", "anio_ini", "anio_fin", "noches_posibles",
            "nivel_partida", "nivel_final", "cambio_absoluto",
            "pendiente_noches_anio", "ic95_inf", "ic95_sup", "ic95_excluye_cero",
            "r2", "error_std", "cerca_del_techo",
            "posible_inhomogeneidad", "salto_max_veranos", "serie", "fuente"]

NOTA_INHOMOGENEIDAD = (
    "AVISO SOBRE ESTA MARCA: con solo 9 diferencias interanuales el test no "
    "discrimina. Simulando 20.000 series gaussianas puras (sin ningún salto "
    "real) el criterio marca el 22,9 % de ellas; en los datos reales marca el "
    "20,9 %, es decir POR DEBAJO de lo que produciría el azar. La marca sirve "
    "como cribado para mirar a mano la serie de esa estación, no como evidencia "
    "de que haya un traslado o un cambio de sensor. Detectar inhomogeneidades "
    "de verdad exige metadatos de la estación y series de referencia vecinas."
)

NOTA_EDITORIAL = (
    "Diez veranos son una serie corta. Estos datos describen lo que ha ocurrido "
    "en las noches de verano españolas entre 2017 y 2026 en las estaciones de "
    "AEMET, y nada más: no constituyen una tendencia climática en sentido "
    "estricto, que exigiría series de treinta años o más, ni permiten atribuir "
    "lo observado al cambio climático, algo que requiere estudios específicos de "
    "detección y atribución. Las series diarias de AEMET no están homogeneizadas, "
    "de modo que un traslado de garita o un cambio de sensor pueden producir "
    "saltos que no son climáticos; las estaciones con saltos sospechosos van "
    "marcadas. Fuente: AEMET."
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Tendencia de noches tropicales por estación (Fuente: AEMET)")
    ap.add_argument("--top", type=int, default=20, help="cuántas estaciones listar")
    args = ap.parse_args()

    est = arn.cargar_estaciones()
    meta = {}
    for r in est.itertuples():
        if r.lat != r.lat or r.lon != r.lon or r.altitud_m != r.altitud_m:
            continue
        meta[str(r.indicativo)] = {"nombre": r.nombre, "provincia": r.provincia,
                                   "lat": float(r.lat), "lon": float(r.lon),
                                   "altitud_m": float(r.altitud_m)}

    df = arn.cargar_diarios()
    fmax = df["fecha"].max().date()

    # La ventana termina en el último día con datos, con tope el 25 de agosto.
    # AEMET publica con 3-5 días de retraso, así que el tope rara vez se alcanza.
    tope = date(fmax.year, *VENTANA_FIN_TOPE)
    fin = (VENTANA_FIN_TOPE if fmax >= tope else (fmax.month, fmax.day))
    ini = VENTANA_INI
    ndias = dias_ventana(fmax.year, ini, fin)
    log.info("Ventana estival: %d/%d - %d/%d (%d días), IDÉNTICA en todos los años",
             ini[1], ini[0], fin[1], fin[0], ndias)
    if fin != VENTANA_FIN_TOPE:
        log.info("  (el tope era el 25/8; los datos llegan al %s, así que la "
                 "ventana se recorta ahí para que siga siendo comparable)", fmax)

    pts, metodo_costa = ag.puntos_de_costa()
    idx_costa = ag.indexa_costa(pts) if pts else None

    conteos = cuenta_por_verano(df, ini, fin)
    filas, descartes = analiza(conteos, meta, idx_costa)
    filas.sort(key=lambda f: -f["cambio_absoluto"])

    # Serie de control: junio-septiembre completo, sin 2026
    ctrl_conteos = cuenta_por_verano(df, (6, 1), (9, 30), excluir_anios=(fmax.year,))
    ctrl_filas, _ = analiza(ctrl_conteos, meta, idx_costa)
    ctrl_por = {f["indicativo"]: f["pendiente_noches_anio"] for f in ctrl_filas}

    pend = [f["pendiente_noches_anio"] for f in filas]
    comunes = [(f["pendiente_noches_anio"], ctrl_por[f["indicativo"]])
               for f in filas if f["indicativo"] in ctrl_por]
    igual_signo = sum(1 for a, b in comunes if a * b > 0)
    ctrl_media = sum(b for _, b in comunes) / len(comunes) if comunes else float("nan")

    motivos = {}
    for m in descartes.values():
        motivos[m] = motivos.get(m, 0) + 1

    resumen = {
        "generado": date.today().isoformat(),
        "fuente": FUENTE,
        "metodo": (f"noches con tmin > {UMBRAL:g} °C contadas en una ventana estival "
                   f"idéntica en todos los años ({ini[1]}/{ini[0]}-{fin[1]}/{fin[0]}, "
                   f"{ndias} días); regresión lineal frente al año; ordenación por "
                   "tamaño del efecto, nunca por p-valor"),
        "ventana": {"inicio": f"{ini[1]:02d}-{ini[0]:02d}", "fin": f"{fin[1]:02d}-{fin[0]:02d}",
                    "dias": ndias, "identica_en_todos_los_anios": True},
        "criterios": {
            "umbral_noche_tropical_c": UMBRAL,
            "nota_umbral": ("criterio del proyecto: tmin ESTRICTAMENTE mayor que 20,0 "
                            "(mismo que analisis_refugios_nocturnos.py y que la web)"),
            "cobertura_minima_verano": COBERTURA_MIN,
            "veranos_minimos": VERANOS_MIN,
            "umbral_techo": UMBRAL_TECHO,
            "sigmas_salto_inhomogeneidad": SIGMAS_SALTO,
            "nota_inhomogeneidad": NOTA_INHOMOGENEIDAD,
            "umbral_costa_km": DIST_COSTA_KM,
            "metodo_costa": metodo_costa,
        },
        "periodo": {"anio_ini": min(f["anio_ini"] for f in filas),
                    "anio_fin": max(f["anio_fin"] for f in filas)} if filas else {},
        "estaciones": {"validas": len(filas), "descartadas": len(descartes),
                       "descartes_por_motivo": motivos,
                       "cerca_del_techo": sum(1 for f in filas if f["cerca_del_techo"] == "si"),
                       "posible_inhomogeneidad": sum(1 for f in filas
                                                     if f["posible_inhomogeneidad"] == "si")},
        "global": {
            "pendiente_media": round(sum(pend) / len(pend), 4) if pend else None,
            "pendiente_mediana": round(median(pend), 4) if pend else None,
            "n_suben": sum(1 for x in pend if x > 0),
            "n_bajan": sum(1 for x in pend if x < 0),
            "n_ic95_excluye_cero": sum(1 for f in filas if f["ic95_excluye_cero"] == "si"),
            "nota_comparaciones_multiples": (
                f"con {len(filas)} estaciones, unas {round(0.05 * len(filas))} darían un "
                "intervalo que excluye el cero por puro azar aunque no pasara nada. "
                "Por eso no se ordena ni se selecciona por significación."),
        },
        "control_junio_septiembre_sin_ultimo_anio": {
            "n_estaciones": len(comunes),
            "pendiente_media": round(ctrl_media, 4) if comunes else None,
            "coinciden_en_signo": igual_signo,
            "porcentaje_coincidencia": round(100 * igual_signo / len(comunes), 1) if comunes else None,
        },
        "por_altitud": agrega(filas, "franja_altitud"),
        "por_costa": agrega(filas, "grupo_costa"),
        "por_altitud_x_costa": agrega_cruce(filas),
        "por_provincia": agrega(filas, "provincia"),
        "limitaciones": NOTA_EDITORIAL,
    }

    DATOS.mkdir(exist_ok=True)
    with open(DATOS / "tendencia_estaciones.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        for f in filas:
            w.writerow(f)
    (DATOS / "tendencia_resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------- consola
    L = log.info
    L("=" * 92)
    L("NOCHES TROPICALES: DÓNDE CRECEN MÁS DEPRISA (%d-%d) — Fuente: AEMET",
      resumen["periodo"]["anio_ini"], resumen["periodo"]["anio_fin"])
    L("=" * 92)
    L("Ventana estival %02d/%02d-%02d/%02d (%d días), la MISMA en los %d veranos.",
      ini[1], ini[0], fin[1], fin[0], ndias,
      resumen["periodo"]["anio_fin"] - resumen["periodo"]["anio_ini"] + 1)
    L("Noche tropical: tmin > %.1f °C (criterio del proyecto).", UMBRAL)
    L("")
    L("Estaciones válidas ..... %d", len(filas))
    L("Estaciones descartadas . %d", len(descartes))
    for m, n in sorted(motivos.items(), key=lambda kv: -kv[1]):
        L("    %-24s %4d", m, n)
    L("    (válida = >=%d veranos con >=%.0f %% de días con dato)", VERANOS_MIN, 100 * COBERTURA_MIN)
    L("Marcadas cerca del techo ....... %d  (partían de >%.0f %% de las noches posibles)",
      resumen["estaciones"]["cerca_del_techo"], 100 * UMBRAL_TECHO)
    L("Marcadas posible inhomogeneidad  %d  (%.1f %%; salto entre veranos > %.0f sigma)",
      resumen["estaciones"]["posible_inhomogeneidad"],
      100 * resumen["estaciones"]["posible_inhomogeneidad"] / len(filas), SIGMAS_SALTO)
    for linea in _envuelve(NOTA_INHOMOGENEIDAD, 86):
        L("    %s", linea)
    L("-" * 92)
    L("CONTROL junio-septiembre sin %d: pendiente media %+.3f vs %+.3f de la serie",
      fmax.year, ctrl_media, resumen["global"]["pendiente_media"])
    L("principal; coinciden en signo %d de %d estaciones (%.0f %%). Misma dirección.",
      igual_signo, len(comunes), 100 * igual_signo / len(comunes))
    L("-" * 92)
    L("LAS %d QUE MÁS SUBEN, por aumento absoluto (media últimos 3 veranos menos", args.top)
    L("media de los 3 primeros). NO ordenado por p-valor — ver nota al final.")
    L("")
    L("     %-26s %-13s %6s %7s %7s %8s   %-18s", "estación", "provincia", "altitud",
      "inicio", "final", "cambio", "pendiente [IC95%]")
    for f in filas[:args.top]:
        marcas = ("  TECHO" if f["cerca_del_techo"] == "si" else "") + \
                 ("  ~SALTO?" if f["posible_inhomogeneidad"] == "si" else "")
        L("     %-26s %-13s %5.0fm %7.1f %7.1f %+8.1f   %+.2f [%+.2f,%+.2f]%s",
          f["nombre"][:26], f["provincia"][:13], f["altitud_m"],
          f["nivel_partida"], f["nivel_final"], f["cambio_absoluto"],
          f["pendiente_noches_anio"], f["ic95_inf"], f["ic95_sup"], marcas)
    bajan = [f for f in filas if f["cambio_absoluto"] < 0]
    L("-" * 92)
    if not bajan:
        L("LAS QUE BAJAN: ninguna. De las %d estaciones válidas, NO HAY UNA SOLA en la que", len(filas))
        L("las noches tropicales hayan disminuido. Eso también es un dato.")
    else:
        L("LAS %d QUE MÁS BAJAN (%d estaciones con cambio negativo de %d)",
          min(10, len(bajan)), len(bajan), len(filas))
        for f in sorted(bajan, key=lambda f: f["cambio_absoluto"])[:10]:
            L("     %-26s %-13s %5.0fm %7.1f %7.1f %+8.1f   %+.2f [%+.2f,%+.2f]",
              f["nombre"][:26], f["provincia"][:13], f["altitud_m"],
              f["nivel_partida"], f["nivel_final"], f["cambio_absoluto"],
              f["pendiente_noches_anio"], f["ic95_inf"], f["ic95_sup"])
    L("-" * 92)
    L("PENDIENTE MEDIA POR FRANJA DE ALTITUD (noches tropicales ganadas por año)")
    L("     %-12s %5s %9s %9s", "franja", "n", "media", "mediana")
    for _, _, et in FRANJAS:
        s = resumen["por_altitud"].get(et)
        if s:
            L("     %-12s %5d %+9.3f %+9.3f", et, s["n_estaciones"],
              s["pendiente_media"], s["pendiente_mediana"])
    L("")
    L("POR PROXIMIDAD AL MAR (umbral %g km)", DIST_COSTA_KM)
    for et in ("litoral", "interior"):
        s = resumen["por_costa"].get(et)
        if s:
            L("     %-12s %5d %+9.3f %+9.3f", et, s["n_estaciones"],
              s["pendiente_media"], s["pendiente_mediana"])
    L("")
    L("CRUCE ALTITUD x COSTA — la comparación que decide la hipótesis")
    L("     %-12s %-22s %-22s", "franja", "litoral", "interior")
    for _, _, et in FRANJAS:
        c = resumen["por_altitud_x_costa"].get(et, {})
        def celda(g):
            v = c.get(g)
            return f"{v['pendiente_media']:+.3f} (n={v['n_estaciones']})" if v else "—"
        L("     %-12s %-22s %-22s", et, celda("litoral"), celda("interior"))
    L("-" * 92)
    L("COMPARACIONES MÚLTIPLES: %s", resumen["global"]["nota_comparaciones_multiples"])
    L("  (%d estaciones tienen el IC95 fuera del cero, muy por encima de ese azar)",
      resumen["global"]["n_ic95_excluye_cero"])
    L("-" * 92)
    L("NOTA PARA LA PIEZA EDITORIAL (copiable tal cual):")
    for linea in _envuelve(NOTA_EDITORIAL, 88):
        L("  %s", linea)
    L("=" * 92)
    L("Escrito: %s", DATOS / "tendencia_estaciones.csv")
    L("Escrito: %s", DATOS / "tendencia_resumen.json")
    return 0


def _envuelve(texto, ancho):
    linea, out = "", []
    for p in texto.split():
        if len(linea) + len(p) + 1 > ancho:
            out.append(linea)
            linea = p
        else:
            linea = f"{linea} {p}".strip()
    if linea:
        out.append(linea)
    return out


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log.exception("Error en el análisis de tendencia")
        sys.exit(1)
