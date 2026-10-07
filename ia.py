"""Llamadas al modelo (endpoint compatible con OpenAI)."""
import json
import time

import requests

import config


class IAError(RuntimeError):
    pass


def _anotar(uso, j, cuerpo, texto):
    import consumo
    u = j.get("usage") or {}
    uso["modelo"] = j.get("model") if j.get("model") in consumo.TARIFAS_BASE else cuerpo["model"]
    if u.get("prompt_tokens") is not None:
        cache = u.get("prompt_cache_hit_tokens")
        if cache is None:
            cache = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        uso.update(entrada=u["prompt_tokens"], salida=u.get("completion_tokens", 0), cache=cache, estimado=False)
    else:
        uso.update(consumo.estimar(cuerpo["messages"], texto))


def configurada():
    return bool(config.IA_CLAVE)


def _cuerpo(mensajes, modelo, temperatura, max_tokens):
    if not configurada():
        raise IAError("Falta CONSEJO_IA_CLAVE en el .env: el consejo aún no puede responder.")
    import consumo
    try:
        consumo.comprobar()
    except RuntimeError as e:
        raise IAError(str(e)) from None
    cuerpo = {"model": modelo or config.IA_MODELO, "messages": mensajes, "max_tokens": max_tokens}
    if temperatura is not None:
        cuerpo["temperature"] = temperatura
    if "deepseek" in config.IA_URL:
        cuerpo["thinking"] = {"type": "enabled" if config.IA_PENSAR else "disabled"}
    return cuerpo


def llamar_flujo(mensajes, modelo=None, temperatura=None, max_tokens=800, uso=None):
    """Generador: devuelve el texto por trozos según llega. Al terminar rellena `uso` (como `llamar`)."""
    cuerpo = _cuerpo(mensajes, modelo, temperatura, max_tokens)
    cuerpo.update(stream=True, stream_options={"include_usage": True})
    r = None
    for intento in range(2):   # se reintenta solo si falla antes de empezar a hablar
        try:
            r = requests.post(f"{config.IA_URL}/chat/completions", json=cuerpo, stream=True, timeout=(15, 150),
                              headers={"Authorization": f"Bearer {config.IA_CLAVE}"})
        except requests.RequestException as e:
            r, error = None, IAError(f"No se pudo contactar con la IA: {e}")
        else:
            if r.status_code == 200:
                break
            error = IAError(f"IA {r.status_code}: {r.text[:300]}")
            if r.status_code not in (429, 500, 502, 503, 504):
                raise error
        time.sleep(1.5)
    else:
        raise error
    r.encoding = "utf-8"
    partes, final = [], {"usage": None, "model": None}
    try:
        for linea in r.iter_lines(decode_unicode=True):
            if not linea or not linea.startswith("data:"):
                continue
            dato = linea[5:].strip()
            if dato == "[DONE]":
                break
            j = json.loads(dato)
            final["usage"] = j.get("usage") or final["usage"]
            final["model"] = j.get("model") or final["model"]
            for ch in j.get("choices") or []:
                x = (ch.get("delta") or {}).get("content")
                if x:
                    partes.append(x)
                    yield x
    except requests.RequestException as e:
        raise IAError(f"Se cortó la conexión con la IA: {e}") from None
    finally:
        r.close()
    if uso is not None:
        _anotar(uso, final, cuerpo, "".join(partes))


def llamar(mensajes, modelo=None, temperatura=None, max_tokens=800, uso=None):
    """Devuelve el texto. Si se pasa `uso` (dict), lo rellena con modelo y tokens consumidos."""
    cuerpo = _cuerpo(mensajes, modelo, temperatura, max_tokens)
    ultimo = None
    for intento in range(2):
        try:
            r = requests.post(f"{config.IA_URL}/chat/completions", json=cuerpo, timeout=150,
                              headers={"Authorization": f"Bearer {config.IA_CLAVE}"})
        except requests.RequestException as e:
            ultimo = IAError(f"No se pudo contactar con la IA: {e}")
        else:
            if r.status_code == 200:
                j = r.json()
                texto = (j["choices"][0]["message"]["content"] or "").strip() or "(sin respuesta)"
                if uso is not None:
                    _anotar(uso, j, cuerpo, texto)
                return texto
            ultimo = IAError(f"IA {r.status_code}: {r.text[:300]}")
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        time.sleep(1.5)
    raise ultimo
