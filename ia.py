"""Llamadas al modelo (APIs compatibles con OpenAI): la IA por defecto o el proveedor de cada experto."""
import json
import time

import requests

import config


class IAError(RuntimeError):
    pass


def configurada():
    return bool(config.IA_CLAVE)


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


def _preparar(mensajes, modelo, temperatura, max_tokens, agente):
    """→ (url, clave, cuerpo). Comprueba la configuración y el tope de gasto antes de gastar nada."""
    import consumo
    import proveedores
    url, clave, modelo_d, nombre = proveedores.destino(agente)
    if not nombre and not clave:
        raise IAError("Falta CONSEJO_IA_CLAVE en el .env: el consejo aún no puede responder.")
    if nombre and not modelo_d:
        raise IAError(f"El proveedor «{nombre}» no tiene modelo: indíquelo en el experto o en Ajustes › Proveedores.")
    try:
        consumo.comprobar()
    except RuntimeError as e:
        raise IAError(str(e)) from None
    cuerpo = {"model": modelo or modelo_d, "messages": mensajes, "max_tokens": max_tokens}
    if temperatura is not None:
        cuerpo["temperature"] = temperatura
    if "deepseek" in url:
        cuerpo["thinking"] = {"type": "enabled" if config.IA_PENSAR else "disabled"}
    return url, clave, cuerpo


def _ajustar(cuerpo, texto):
    """Cada API acepta parámetros distintos: si uno se rechaza, se quita o se cambia por su equivalente."""
    t = texto.lower()
    if "stream_options" in t and "stream_options" in cuerpo:
        cuerpo.pop("stream_options")
    elif "max_completion_tokens" in t and "max_tokens" in cuerpo:
        cuerpo["max_completion_tokens"] = cuerpo.pop("max_tokens")
    elif "temperature" in t and "temperature" in cuerpo:
        cuerpo.pop("temperature")
    elif "thinking" in t and "thinking" in cuerpo:
        cuerpo.pop("thinking")
    else:
        return False
    return True


def _post(url, clave, cuerpo, stream=False):
    h = {"Authorization": f"Bearer {clave}"} if clave else {}
    error = None
    for _ in range(5):
        try:
            r = requests.post(f"{url}/chat/completions", json=cuerpo, headers=h, stream=stream,
                              timeout=(15, 150) if stream else 150)
        except requests.RequestException as e:
            error = IAError(f"No se pudo contactar con la IA: {e}")
            time.sleep(1.5)
            continue
        if r.status_code == 200:
            return r
        error = IAError(f"IA {r.status_code}: {r.text[:300]}")
        if r.status_code == 400 and _ajustar(cuerpo, r.text):
            continue
        if r.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(1.5)
    raise error


def llamar(mensajes, modelo=None, temperatura=None, max_tokens=800, uso=None, agente=None):
    """Devuelve el texto. Si se pasa `uso` (dict), lo rellena con modelo y tokens consumidos."""
    url, clave, cuerpo = _preparar(mensajes, modelo, temperatura, max_tokens, agente)
    j = _post(url, clave, cuerpo).json()
    texto = (j["choices"][0]["message"]["content"] or "").strip() or "(sin respuesta)"
    if uso is not None:
        _anotar(uso, j, cuerpo, texto)
    return texto


def llamar_flujo(mensajes, modelo=None, temperatura=None, max_tokens=800, uso=None, agente=None):
    """Generador: devuelve el texto por trozos según llega. Al terminar rellena `uso` (como `llamar`)."""
    url, clave, cuerpo = _preparar(mensajes, modelo, temperatura, max_tokens, agente)
    cuerpo.update(stream=True, stream_options={"include_usage": True})
    r = _post(url, clave, cuerpo, stream=True)
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
