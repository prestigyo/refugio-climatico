#!/usr/bin/env python3
"""
El correo con el que se manda el dosier, con la cifra de CADA periodista.

Un pitch genérico no lo abre nadie: llegan quince esa semana y todos dicen lo
mismo. Lo que hace que un periodista conteste es que la primera línea hable de
SU territorio y traiga un dato que puede comprobar en treinta segundos.

Y el dato existe, provincia por provincia. El contraste dentro de una sola
provincia suele ser más fuerte que el nacional:

    Valencia   Utiel 1,0 noches tropicales al año  ·  Miramar 77,1
    Granada    Sierra Nevada 0,0                   ·  Castell de Ferro 69,2
    Murcia     Caravaca 3,5                        ·  Cartagena 79,6

Ese es el titular de un periódico provincial, y sale solo del ranking.

NO ESCRIBE NADA EN docs/. Esto es material interno: se imprime en pantalla
para copiar y pegar en el correo. No es una página del sitio.

Tres destinatarios, tres correos distintos:

  regional  el de un periódico o radio de provincia. El contraste local.
  nacional  el de una sección de clima o medio ambiente. El gancho es
            metodológico: medimos el verano con la ventana equivocada.
  datos     el de una unidad de datos. El gancho es lo que se pueden
            descargar y lo que nadie más tiene (el archivo horario).

Uso:
    python scripts/generar_pitch.py --provincia Valencia
    python scripts/generar_pitch.py --tipo nacional
    python scripts/generar_pitch.py --tipo datos
    python scripts/generar_pitch.py --listar        # provincias con contraste
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SITIO = "https://nochetropical.es"
KIT = SITIO + "/prensa/kit/"


# `.title()` de Python pone en mayúscula las preposiciones: «Santa Cruz De
# Tenerife», «Pola De Somiedo». En el asunto de un correo a un periodista eso
# canta. Estas van en minúscula salvo si abren el nombre.
_MINUS = {"de", "del", "la", "las", "los", "y", "el", "en", "a"}


def titulo(s: str) -> str:
    palabras = str(s).title().split()
    return " ".join(p if i == 0 or p.lower() not in _MINUS else p.lower()
                    for i, p in enumerate(palabras))


def num(x: float, dec: int = 1) -> str:
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")


# Provincias que el catálogo de AEMET escribe de dos formas. Medido sobre
# datos/estaciones.csv: Baleares aparece 33 veces en castellano y 11 en catalán,
# y Tenerife 19 y 19. Sin unificarlas, cualquier agrupación por provincia las
# parte en dos y calcula contrastes falsos — y además salen 54 «provincias»
# donde hay 52.
EQUIVALENTES = {
    "ILLES BALEARS": "BALEARES",
}


def sin_tildes(s: str) -> str:
    """Normaliza el nombre de provincia para comparar.

    Unifica «Sta.» con «Santa» porque el catálogo de AEMET trae la MISMA
    provincia escrita de dos formas: 19 estaciones como «SANTA CRUZ DE
    TENERIFE» y otras 19 como «STA. CRUZ DE TENERIFE». Sin esto, el correo
    de Tenerife saldría con la mitad de las estaciones y un contraste falso.
    """
    t = "".join(c for c in unicodedata.normalize("NFD", str(s))
                if unicodedata.category(c) != "Mn").upper().strip()
    t = t.replace("STA.", "SANTA").replace("  ", " ")
    return EQUIVALENTES.get(t, t)


def carga():
    r = ROOT / "analisis" / "refugios_nocturnos_ranking.csv"
    t = ROOT / "datos" / "tendencia_resumen.json"
    if not r.exists():
        sys.exit(f"Falta {r}: ejecuta antes analisis_refugios_nocturnos.py")
    rank = pd.read_csv(r)
    tend = json.loads(t.read_text("utf-8")) if t.exists() else {}
    return rank, tend


def datos_provincia(rank: pd.DataFrame, tend: dict, provincia: str) -> dict | None:
    clave = sin_tildes(provincia)
    s = rank[rank["provincia"].map(sin_tildes) == clave]
    if s.empty:
        return None
    mejor = s.nsmallest(1, "noches_trop_anio").iloc[0]
    peor = s.nlargest(1, "noches_trop_anio").iloc[0]
    # La tendencia provincial: solo se cita si está, y con su aviso.
    prov_t = (tend.get("por_provincia") or {}).get(clave, {})
    nombre = max((str(x) for x in s["provincia"].unique()), key=len)
    return {
        "provincia": titulo(nombre.replace("Sta.", "Santa")),
        "n": len(s),
        "mejor": titulo(mejor["nombre"]),
        "mejor_v": float(mejor["noches_trop_anio"]),
        "mejor_alt": int(mejor["altitud_m"]) if pd.notna(mejor["altitud_m"]) else None,
        "peor": titulo(peor["nombre"]),
        "peor_v": float(peor["noches_trop_anio"]),
        "bajo_una": int((s["noches_trop_anio"] < 1).sum()),
        "suben": prov_t.get("n_suben"), "de": prov_t.get("n_estaciones"),
    }


def correo_regional(d: dict, veranos: int) -> tuple[str, str]:
    asunto = (f"Datos de AEMET: en {d['provincia']} se duerme en dos veranos "
              f"distintos ({num(d['mejor_v'])} noches tropicales frente a "
              f"{num(d['peor_v'])})")
    veces = (f" — {num(d['peor_v']/d['mejor_v'], 0)} veces más"
             if d["mejor_v"] >= 1 else "")
    # Esa frase solo vale si hay alguna. Decir «0 de las 21 no llegan a una
    # noche» es una frase vacía, y en un correo frío cada línea cuenta.
    if d["bajo_una"] >= 1:
        una = d["bajo_una"] == 1
        resumen = (f"{d['bajo_una']} de las {d['n']} estaciones de la provincia "
                   f"{'no llega' if una else 'no llegan'} ni a una noche "
                   f"tropical al año.")
    else:
        resumen = (f"Son {d['n']} estaciones medidas en la provincia, y el "
                   f"salto entre la más fresca y la más cálida es ese.")
    sube = ""
    if d["suben"] and d["de"]:
        sube = (f"\n\nEn los últimos {veranos} veranos han subido las noches "
                f"tropicales en {d['suben']} de las {d['de']} estaciones de la "
                f"provincia con serie suficiente. Es una serie corta: describe "
                f"lo ocurrido, no es una tendencia climática ni permite "
                f"atribuir nada al cambio climático, y así está dicho en el "
                f"dosier.")
    cuerpo = f"""Hola [NOMBRE],

Te escribo por si os sirve para una pieza de verano. He analizado {veranos} veranos de datos abiertos de AEMET, estación por estación, para contar algo que el termómetro del telediario no cuenta: cuántas noches al año no se baja de 20 °C.

En {d['provincia']} el contraste es grande{veces}:

· {d['mejor']}{f" ({d['mejor_alt']} m)" if d['mejor_alt'] else ""}: {num(d['mejor_v'])} noches tropicales al año.
· {d['peor']}: {num(d['peor_v'])}.

{resumen}{sube}

Te dejo el dosier de dos páginas con la metodología y el resto de cifras: {KIT}
Los datos en bruto están en CSV descargable, y puedo prepararte el desglose de cualquier municipio de la provincia en el mismo día.

¿Te interesa que te pase el detalle?

Un saludo,
Ramón J. Lowesting
{SITIO}"""
    return asunto, cuerpo


def correo_nacional(c: dict) -> tuple[str, str]:
    asunto = (f"Medimos el verano con la ventana equivocada: el "
              f"{num(c['pct_fuera'])} % de las noches tropicales cae fuera de "
              f"junio-agosto")
    cuerpo = f"""Hola [NOMBRE],

Un apunte metodológico que quizá os sirva, con datos abiertos de AEMET y {c['veranos']} veranos en {c['estaciones']} estaciones.

Los balances de verano suelen contarse de junio a agosto. Esa ventana deja fuera el {num(c['pct_fuera'])} % de las noches tropicales del histórico, y septiembre acumula más que junio. No es una proyección: ya está pasando, y juega en contra del dato publicado — los sitios con peores noches son peores de lo que dicen las cifras al uso.

Dos cosas más del mismo análisis:

· La mínima publicada no dice cuánto se duerme. AEMET borra la observación horaria y no publica histórico, así que la archivamos desde agosto de 2026. De nueve horas de noche, la mediana nacional son {num(c['h20'])} h por debajo de 20 °C, pero solo {num(c['h18'])} h por debajo de 18. Dos pueblos con la misma mínima pueden haber tenido noches opuestas.
· La altitud no salva por sí sola: el gradiente nocturno real es de {num(c['gradiente'], 2)} °C por cada 100 m, y en {c['inversiones']} de {c['pares']} pares de estaciones cercanas el pueblo alto duerme peor que el bajo.

Dosier de dos páginas, con metodología y limitaciones: {KIT}
Todo es reproducible y los datos están en CSV. Si queréis comprobar una cifra concreta o necesitáis un corte distinto, os lo preparo.

Un saludo,
Ramón J. Lowesting
{SITIO}"""
    return asunto, cuerpo


def correo_datos(c: dict) -> tuple[str, str]:
    asunto = (f"{c['estaciones']} estaciones de AEMET, {c['veranos']} veranos, "
              f"en CSV: noches tropicales municipio a municipio")
    cuerpo = f"""Hola [NOMBRE],

Por si os encaja en la unidad de datos: tengo procesados {c['veranos']} veranos de AEMET OpenData ({c['anio_ini']}-{c['anio_fin']}) para {c['estaciones']} estaciones, con las noches tropicales (mínima que no baja de 20 °C) estación por estación, y está todo descargable en CSV.

Lo que creo que no tiene nadie más: **el archivo horario**. AEMET borra la observación horaria a las pocas horas y no publica histórico, así que la venimos guardando desde agosto de 2026 — hoy son {c['h_estaciones']} estaciones. Eso permite responder «cuántas HORAS estuvo la noche por debajo de 20°», no solo «cuánto bajó en el punto más frío». Mediana nacional: {num(c['h20'])} h de nueve.

· Datos y metodología: {SITIO}/metodologia/
· Mapa interactivo de las estaciones: {SITIO}/mapa-estaciones/
· Dosier de dos páginas: {KIT}

El proceso es reproducible y las limitaciones están escritas: {c['veranos']} veranos son una serie corta, no constituyen una tendencia climática en sentido estricto y no permiten atribuir nada al cambio climático.

Si os sirve, puedo prepararos el corte que necesitéis —por provincia, por municipio o por umbral— en el día.

Un saludo,
Ramón J. Lowesting
{SITIO}"""
    return asunto, cuerpo


def cifras_globales(rank: pd.DataFrame, tend: dict) -> dict:
    n = pd.read_csv(ROOT / "analisis" / "noches_por_estacion.csv")
    h = pd.read_csv(ROOT / "analisis" / "horas_dormibles.csv")
    g = json.loads((ROOT / "datos" / "gradiente_nocturno.json").read_text("utf-8"))
    per = tend.get("periodo", {"anio_ini": 2017, "anio_fin": 2026})
    return {
        "estaciones": len(rank),
        "anio_ini": per["anio_ini"], "anio_fin": per["anio_fin"],
        "veranos": per["anio_fin"] - per["anio_ini"] + 1,
        "pct_fuera": n["noches_fuera_jja_anio"].sum()
                     / n["noches_trop_anio_medio"].sum() * 100,
        "h_estaciones": len(h),
        "h20": float(h["h20_mediana"].median()),
        "h18": float(h["h18_mediana"].median()),
        "gradiente": g["global"]["descenso_c_por_100m"],
        "pares": g["global"]["n_pares"], "inversiones": g["n_inversiones_puras"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--provincia", help="para el correo regional")
    ap.add_argument("--tipo", choices=("regional", "nacional", "datos"),
                    default=None)
    ap.add_argument("--listar", action="store_true",
                    help="las 52 provincias ordenadas por contraste interno")
    args = ap.parse_args()

    rank, tend = carga()

    if args.listar:
        filas = []
        # Se recorre la provincia NORMALIZADA, no el texto tal cual: «Santa Cruz
        # de Tenerife» y «Sta. Cruz de Tenerife» son la misma y salían dos veces,
        # cada una con la mitad de sus estaciones y un contraste falso.
        vistas = set()
        for prov in sorted(rank["provincia"].unique()):
            clave = sin_tildes(prov)
            if clave in vistas:
                continue
            vistas.add(clave)
            d = datos_provincia(rank, tend, prov)
            if d and d["peor_v"] > 0:
                filas.append((d["peor_v"] - d["mejor_v"], d))
        filas.sort(reverse=True, key=lambda x: x[0])
        print(f"{len(filas)} provincias, ordenadas por el contraste de dentro "
              f"(es el titular local):\n")
        for salto, d in filas:
            print(f"  {d['provincia'][:22]:22} {d['mejor'][:26]:26} "
                  f"{num(d['mejor_v']):>5}  vs  {d['peor'][:26]:26} "
                  f"{num(d['peor_v']):>5}")
        return 0

    tipo = args.tipo or ("regional" if args.provincia else "nacional")
    c = cifras_globales(rank, tend)

    if tipo == "regional":
        if not args.provincia:
            sys.exit("El correo regional necesita --provincia")
        d = datos_provincia(rank, tend, args.provincia)
        if not d:
            sys.exit(f"No encuentro la provincia «{args.provincia}». "
                     f"Prueba con --listar.")
        asunto, cuerpo = correo_regional(d, c["veranos"])
    elif tipo == "nacional":
        asunto, cuerpo = correo_nacional(c)
    else:
        asunto, cuerpo = correo_datos(c)

    print("=" * 74)
    print("ASUNTO: " + asunto)
    print("=" * 74)
    print(cuerpo)
    print("=" * 74)
    print("Sustituye [NOMBRE]. Adjunta el PDF del dosier o deja el enlace, no")
    print("las dos cosas: un adjunto de un desconocido baja la entregabilidad.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
