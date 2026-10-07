"""Cliente de la fábrica de documentos (extracción con OCR, texto y búsqueda por significado)."""
import time

import requests

import config


class FabricaError(RuntimeError):
    pass


def configurada():
    return bool(config.FABRICA_URL)


def _h():
    return {"X-API-Key": config.FABRICA_CLAVE} if config.FABRICA_CLAVE else {}


def _pedir(metodo, ruta, **kw):
    if not configurada():
        raise FabricaError("Falta CONSEJO_FABRICA_URL en el .env: no se pueden procesar documentos.")
    try:
        r = requests.request(metodo, config.FABRICA_URL + ruta, headers=_h(), timeout=kw.pop("timeout", 60), **kw)
    except requests.RequestException as e:
        raise FabricaError(f"No se pudo contactar con la fábrica: {e}") from e
    if r.status_code >= 400:
        raise FabricaError(f"Fábrica {r.status_code}: {r.text[:200]}")
    return r


def subir(nombre, datos, etiquetas):
    r = _pedir("POST", "/documentos", files={"archivo": (nombre, datos)}, timeout=180,
               data={"etiquetas": ",".join(etiquetas), "indexar": "true"})
    j = r.json()
    return j.get("documento_id") or j["id"]


def esperar(fid, limite=600):
    """Espera a que la fábrica termine de extraer el texto; devuelve la ficha."""
    fin = time.time() + limite
    while time.time() < fin:
        ficha = _pedir("GET", f"/documentos/{fid}").json()
        if ficha.get("estado") == "listo":
            return ficha
        if ficha.get("estado") == "error":
            raise FabricaError(f"La fábrica no pudo procesarlo: {ficha.get('error') or 'error'}")
        time.sleep(1.5)
    raise FabricaError("La fábrica tarda demasiado en procesar el documento")


def texto(fid):
    return _pedir("GET", f"/documentos/{fid}/texto", timeout=120).json().get("texto") or ""


def buscar(consulta, ids, limite=6):
    r = _pedir("GET", "/buscar", params=[("q", consulta), ("limite", limite)] + [("documento", i) for i in ids])
    return r.json().get("resultados", [])


def borrar(fid):
    try:
        _pedir("DELETE", f"/documentos/{fid}")
    except FabricaError:
        pass  # ya no estaba o la fábrica no responde: no bloquea el borrado local
