"""Llamadas al modelo (endpoint compatible con OpenAI)."""
import time

import requests

import config


class IAError(RuntimeError):
    pass


def configurada():
    return bool(config.IA_CLAVE)


def llamar(mensajes, modelo=None, temperatura=None, max_tokens=800):
    if not configurada():
        raise IAError("Falta CONSEJO_IA_CLAVE en el .env: el consejo aún no puede responder.")
    cuerpo = {"model": modelo or config.IA_MODELO, "messages": mensajes, "max_tokens": max_tokens}
    if temperatura is not None:
        cuerpo["temperature"] = temperatura
    ultimo = None
    for intento in range(2):
        try:
            r = requests.post(f"{config.IA_URL}/chat/completions", json=cuerpo, timeout=150,
                              headers={"Authorization": f"Bearer {config.IA_CLAVE}"})
        except requests.RequestException as e:
            ultimo = IAError(f"No se pudo contactar con la IA: {e}")
        else:
            if r.status_code == 200:
                return (r.json()["choices"][0]["message"]["content"] or "").strip() or "(sin respuesta)"
            ultimo = IAError(f"IA {r.status_code}: {r.text[:300]}")
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        time.sleep(1.5)
    raise ultimo
