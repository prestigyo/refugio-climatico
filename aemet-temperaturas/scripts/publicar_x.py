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
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import generar_calculadora as g

PARTE_TXT = g.DOCS_DIR / "parte" / "parte.txt"
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
    texto = PARTE_TXT.read_text(encoding="utf-8").strip()
    if len(texto) > LIMITE:
        texto = texto[:LIMITE - 1].rstrip() + "…"

    import tweepy
    cliente = tweepy.Client(consumer_key=claves[0], consumer_secret=claves[1],
                            access_token=claves[2], access_token_secret=claves[3])
    r = cliente.create_tweet(text=texto)
    print(f"Publicado en X: https://x.com/nochetropicales/status/{r.data['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
