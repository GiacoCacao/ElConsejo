"""Llamadas al modelo (endpoint compatible con OpenAI)."""
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


def llamar(mensajes, modelo=None, temperatura=None, max_tokens=800, uso=None):
    """Devuelve el texto. Si se pasa `uso` (dict), lo rellena con modelo y tokens consumidos."""
    if not configurada():
        raise IAError("Falta CONSEJO_IA_CLAVE en el .env: el consejo aún no puede responder.")
    cuerpo = {"model": modelo or config.IA_MODELO, "messages": mensajes, "max_tokens": max_tokens}
    if temperatura is not None:
        cuerpo["temperature"] = temperatura
    if "deepseek" in config.IA_URL:
        cuerpo["thinking"] = {"type": "enabled" if config.IA_PENSAR else "disabled"}
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
