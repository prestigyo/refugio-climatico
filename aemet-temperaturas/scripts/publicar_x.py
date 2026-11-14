#!/usr/bin/env python3
"""
Publica el parte de la noche en X (@nochetropicales).

Lee docs/parte/parte.txt (lo genera parte_nocturno.py justo antes) y lo
publica vía la API v2 de X. Si faltan las credenciales, NO falla: avisa y
sale limpio (así el workflow funciona aunque aún no estén los secretos).

Requiere 4 secretos del repositorio (Settings → Secrets → Actions):
  X_API_KEY, X_API_SECRET          (de la app en developer.x.com)
  X_ACCESS_TOKEN, X_ACCESS_SECRET  (generados con permiso Read and Write)

Cuota: el plan gratuito de la API de X permite de sobra 1 publicación/día.

Si X rechaza la publicación, SALE CON ERROR. El workflow sigue —para no perder
el commit del parte— pero acaba en rojo: del 9 de noviembre de 2026 hacia atrás
este paso devolvía «401 Unauthorized» cada día y nadie lo veía, porque el
`continue-on-error` lo dejaba en verde.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import generar_calculadora as g

PARTE_TXT = g.DOCS_DIR / "parte" / "parte.txt"
PARTE_JSON = g.DOCS_DIR / "parte" / "parte.json"
MARCA_X = g.DOCS_DIR / "parte" / "ultimo-tuit.txt"   # candado anti-duplicados
LIMITE = 275  # margen bajo los 280 de X


def main() -> int:
    claves = [os.environ.get(k) for k in
              ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")]
    if not all(claves):
        print("Sin credenciales de X: no se publica (configura los 4 secretos).")
        return 0
    if not PARTE_TXT.exists():
        print("No hay parte.txt que publicar.", file=sys.stderr)
        return 1
    # Candado: si el parte de HOY ya se tuiteó (p. ej. por el cron de respaldo
    # o un run manual), no publicar dos veces.
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # parte.txt es SIEMPRE el último parte que salió, no necesariamente el de hoy.
    # Si hoy no hay parte (era pronto, o falló), publicar ese fichero sería
    # tuitear el de ayer con fecha de ayer. La fecha buena está en parte.json.
    try:
        fecha_parte = json.loads(PARTE_JSON.read_text(encoding="utf-8")).get("fecha", "")
    except (OSError, ValueError):
        fecha_parte = ""
    if fecha_parte != hoy:
        print(f"El último parte es del {fecha_parte or '¿?'} y hoy es {hoy}: "
              "no hay parte de hoy que publicar en X.")
        return 0
    if MARCA_X.exists() and MARCA_X.read_text(encoding="utf-8").strip() == hoy:
        print(f"El parte de {hoy} ya se publicó en X: no se duplica.")
        return 0
    texto = PARTE_TXT.read_text(encoding="utf-8").strip()
    if len(texto) > LIMITE:
        texto = texto[:LIMITE - 1].rstrip() + "…"

    import tweepy
    cliente = tweepy.Client(consumer_key=claves[0], consumer_secret=claves[1],
                            access_token=claves[2], access_token_secret=claves[3])
    try:
        r = cliente.create_tweet(text=texto)
    except tweepy.TweepyException as e:
        print(f"ERROR: X ha rechazado la publicación ({type(e).__name__}: {e}).", file=sys.stderr)
        if isinstance(e, tweepy.Unauthorized):
            print("  401 = las credenciales no valen. Regenera en developer.x.com las claves "
                  "de la app y el Access Token (con permiso Read and Write) y actualiza los "
                  "4 secretos X_* del repositorio.", file=sys.stderr)
        elif isinstance(e, tweepy.Forbidden):
            print("  403 = la app no tiene permiso de escritura, o X considera el texto "
                  "duplicado.", file=sys.stderr)
        return 1
    MARCA_X.write_text(hoy + "\n", encoding="utf-8")   # el commit del workflow lo persiste
    print(f"Publicado en X: https://x.com/nochetropicales/status/{r.data['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
