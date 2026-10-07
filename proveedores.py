"""Proveedores de IA adicionales (APIs compatibles con OpenAI) que se pueden asignar a cada experto.

La clave de cada proveedor se guarda cifrada (Fernet) con una clave derivada de CONSEJO_SECRETO; si no
hay secreto, con una clave aleatoria guardada en datos/.clave_proveedores (600). Nunca se devuelve al
navegador: solo una máscara.
"""
import base64
import hashlib
import os
import time
import uuid

import requests
from cryptography.fernet import Fernet, InvalidToken

import bd
import config

# Direcciones base conocidas (todas exponen /chat/completions compatible con OpenAI)
PLANTILLAS = [
    {"nombre": "OpenAI", "url": "https://api.openai.com/v1"},
    {"nombre": "Anthropic (Claude)", "url": "https://api.anthropic.com/v1"},
    {"nombre": "Google Gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai"},
    {"nombre": "Mistral", "url": "https://api.mistral.ai/v1"},
    {"nombre": "Groq", "url": "https://api.groq.com/openai/v1"},
    {"nombre": "OpenRouter", "url": "https://openrouter.ai/api/v1"},
    {"nombre": "xAI (Grok)", "url": "https://api.x.ai/v1"},
    {"nombre": "DeepSeek", "url": "https://api.deepseek.com/v1"},
    {"nombre": "Ollama (local)", "url": "http://IP-DEL-SERVIDOR:11434/v1"},
]


def _fernet():
    if config.SECRETO:
        clave = hashlib.sha256(("proveedores:" + config.SECRETO).encode()).digest()
    else:
        ruta = os.path.join(config.DATOS, ".clave_proveedores")
        if not os.path.exists(ruta):
            with open(ruta, "wb") as f:
                f.write(os.urandom(32))
            os.chmod(ruta, 0o600)
        clave = open(ruta, "rb").read()
    return Fernet(base64.urlsafe_b64encode(clave))


def cifrar(texto):
    return _fernet().encrypt(texto.encode()).decode() if texto else ""


def descifrar(token):
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None   # el secreto cambió: hay que volver a escribir la clave


def mascara(clave):
    if not clave:
        return ""
    return clave[:3] + "…" + clave[-4:] if len(clave) > 10 else "…"


def _dict(r, con_clave=False):
    clave = descifrar(r["clave"])
    d = {"id": r["id"], "nombre": r["nombre"], "url": r["url"], "modelo": r["modelo"],
         "clave": mascara(clave) if clave else "", "clave_ilegible": clave is None}
    if con_clave:
        d["clave_real"] = clave or ""
    return d


def listar():
    with bd.db() as c:
        return [_dict(r) for r in c.execute("SELECT * FROM proveedores ORDER BY nombre")]


def obtener(pid, con_clave=False):
    if not pid:
        return None
    with bd.db() as c:
        r = c.execute("SELECT * FROM proveedores WHERE id=?", (pid,)).fetchone()
    return _dict(r, con_clave) if r else None


def guardar(d, pid=None):
    nombre = (d.get("nombre") or "").strip()[:60]
    url = (d.get("url") or "").strip().rstrip("/")[:300]
    if not nombre or not url.startswith(("http://", "https://")):
        raise ValueError("Hacen falta un nombre y una dirección http(s) válida")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    modelo = (d.get("modelo") or "").strip()[:120]
    with bd.db() as c:
        if pid:
            r = c.execute("SELECT * FROM proveedores WHERE id=?", (pid,)).fetchone()
            if not r:
                raise LookupError("No existe ese proveedor")
            clave = r["clave"] if d.get("clave") in (None, "") else cifrar(d["clave"].strip())
            c.execute("UPDATE proveedores SET nombre=?, url=?, modelo=?, clave=? WHERE id=?", (nombre, url, modelo, clave, pid))
        else:
            pid = uuid.uuid4().hex[:8]
            c.execute("INSERT INTO proveedores(id,nombre,url,modelo,clave,ts) VALUES(?,?,?,?,?,?)",
                      (pid, nombre, url, modelo, cifrar((d.get("clave") or "").strip()), time.time()))
    return obtener(pid)


def borrar(pid):
    with bd.db() as c:
        c.execute("DELETE FROM proveedores WHERE id=?", (pid,))


def probar(pid):
    """Pide la lista de modelos al proveedor: comprueba la dirección y la clave."""
    p = obtener(pid, con_clave=True)
    if not p:
        raise LookupError("No existe ese proveedor")
    h = {"Authorization": f"Bearer {p['clave_real']}"} if p["clave_real"] else {}
    if "anthropic.com" in p["url"] and p["clave_real"]:
        h.update({"x-api-key": p["clave_real"], "anthropic-version": "2023-06-01"})
    r = requests.get(f"{p['url']}/models", headers=h, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"{p['nombre']} respondió {r.status_code}: {r.text[:200]}")
    datos = r.json()
    lista = datos.get("data") if isinstance(datos, dict) else datos
    return sorted({(m.get("id") or m.get("name") or "").replace("models/", "") for m in lista or [] if isinstance(m, dict)} - {""})


def destino(agente=None):
    """(url, clave, modelo, nombre del proveedor) que usará un experto (o la IA por defecto)."""
    agente = agente or {}
    p = obtener(agente.get("proveedor"), con_clave=True) if agente.get("proveedor") else None
    if p:
        return p["url"], p["clave_real"], (agente.get("modelo") or p["modelo"]), p["nombre"]
    return config.IA_URL, config.IA_CLAVE, (agente.get("modelo") or config.IA_MODELO), None
