"""Copias de seguridad de la base de datos: una al día (y a petición), rotativas, en datos/copias.

Usa la API de copia en caliente de SQLite, que da una copia coherente aunque el servicio esté
escribiendo. Los documentos de las bibliotecas viven en la fábrica y tienen su propia custodia.
"""
import os
import sqlite3
import threading
import time
from datetime import datetime

import config

PREFIJO = "consejo-"


def hacer():
    os.makedirs(config.COPIAS, exist_ok=True)
    nombre = f"{PREFIJO}{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    destino = os.path.join(config.COPIAS, nombre)
    origen = sqlite3.connect(config.DB, timeout=30)
    copia = sqlite3.connect(destino)
    try:
        origen.backup(copia)
    finally:
        copia.close()
        origen.close()
    os.chmod(destino, 0o600)   # contiene todo el consejo: solo para el propietario
    rotar()
    return nombre


def listar():
    if not os.path.isdir(config.COPIAS):
        return []
    out = []
    for n in sorted(os.listdir(config.COPIAS), reverse=True):
        if n.startswith(PREFIJO) and n.endswith(".db"):
            p = os.path.join(config.COPIAS, n)
            out.append({"nombre": n, "tamano": os.path.getsize(p), "ts": os.path.getmtime(p)})
    return out


def rotar():
    for c in listar()[config.COPIAS_GUARDAR:]:
        os.remove(os.path.join(config.COPIAS, c["nombre"]))


def ruta(nombre):
    if not (nombre.startswith(PREFIJO) and nombre.endswith(".db")) or "/" in nombre or ".." in nombre:
        return None
    p = os.path.join(config.COPIAS, nombre)
    return p if os.path.exists(p) else None


def _bucle():
    while True:
        try:
            ultimas = listar()
            if not ultimas or time.time() - ultimas[0]["ts"] > 24 * 3600:
                hacer()
        except Exception as e:  # noqa: BLE001 — que un fallo puntual no mate el hilo
            print(f"[copias] no se pudo hacer la copia: {e}", flush=True)
        time.sleep(3600)


def arrancar():
    threading.Thread(target=_bucle, daemon=True, name="copias").start()
