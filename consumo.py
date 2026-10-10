"""Consumo de la API: tokens por llamada, tarifas por modelo y coste aproximado.

Los precios están en USD por millón de tokens. Las tarifas de serie se siembran en la tabla
`tarifas` y desde ahí se pueden editar (panel «Consumo»); el coste se calcula al consultar, con
la tarifa vigente y la franja horaria en la que se hizo cada llamada.
"""
import re
import threading
import time
from datetime import datetime, timezone

import requests

import bd
import config

FUENTE = "api-docs.deepseek.com/quick_start/pricing · consultado el 2026-10-07"
TARIFAS_BASE = {
    "deepseek-flash": dict(proveedor="DeepSeek", contexto=1_000_000, entrada=0.15, cache=0.003, salida=0.6,
                           entrada_punta=0.3, cache_punta=0.006, salida_punta=1.2, franja="deepseek"),
    "deepseek-v4-pro": dict(proveedor="DeepSeek", contexto=1_000_000, entrada=0.66, cache=0.022, salida=1.98,
                            entrada_punta=1.32, cache_punta=0.044, salida_punta=3.96, franja="deepseek"),
}
CAMPOS = ("proveedor", "contexto", "entrada", "cache", "salida", "entrada_punta", "cache_punta", "salida_punta", "franja")


def es_punta(ts, franja):
    """DeepSeek cobra el doble de 01:00 a 04:00 y de 06:00 a 10:00 UTC, de lunes a viernes."""
    if franja != "deepseek":
        return False
    d = datetime.fromtimestamp(ts, timezone.utc)
    return d.weekday() < 5 and (1 <= d.hour < 4 or 6 <= d.hour < 10)


def sembrar(c):
    for modelo, t in TARIFAS_BASE.items():
        c.execute(f"INSERT OR IGNORE INTO tarifas(modelo,{','.join(CAMPOS)},origen,actualizado) "
                  f"VALUES(?,{','.join('?' * len(CAMPOS))},'serie',?)", (modelo, *[t.get(k) for k in CAMPOS], time.time()))
    c.execute("UPDATE tarifas SET origen='serie' WHERE origen IS NULL AND modelo IN (%s)" % ",".join("?" * len(TARIFAS_BASE)),
              list(TARIFAS_BASE))
    c.execute("UPDATE tarifas SET origen='manual' WHERE origen IS NULL")


def normalizar(modelo):
    """Nombre comparable entre proveedores: sin prefijo «proveedor/», puntos como guiones, sin fecha ni «-latest».
    claude-sonnet-5-5 = anthropic/claude-sonnet-5.5 = claude-sonnet-5-5-20260901."""
    m = (modelo or "").strip().lower().lstrip("~")
    m = m.split("/")[-1].split(":")[0]
    m = m.replace(".", "-").replace("_", "-")
    m = re.sub(r"-(latest|preview)$", "", m)
    m = re.sub(r"-(20\d{6}|\d{4})$", "", m)   # sufijo de fecha (20260901) o de versión (0813)
    return m


class Tarifas(dict):
    """Diccionario de tarifas que también encuentra el modelo por su nombre normalizado."""

    def __init__(self, filas):
        super().__init__(filas)
        prioridad = {"manual": 0, "serie": 1, "openrouter": 2}
        self._norm = {}
        for k, t in sorted(self.items(), key=lambda kv: prioridad.get(kv[1].get("origen"), 3)):
            self._norm.setdefault(normalizar(k), t)

    def get(self, modelo, defecto=None):
        if not modelo:
            return defecto
        return super().get(modelo) or self._norm.get(normalizar(modelo)) or defecto


def tarifas(c):
    return Tarifas({r["modelo"]: dict(r) for r in c.execute("SELECT * FROM tarifas ORDER BY proveedor, modelo")})


# ---- base de tarifas actualizada (OpenRouter publica los precios de cientos de modelos) ------------
URL_PRECIOS = "https://openrouter.ai/api/v1/models"
PROVEEDORES = {"openai": "OpenAI", "anthropic": "Anthropic", "google": "Google", "mistralai": "Mistral", "x-ai": "xAI",
               "deepseek": "DeepSeek", "meta-llama": "Meta", "qwen": "Qwen", "cohere": "Cohere", "moonshotai": "Moonshot",
               "z-ai": "Z.ai", "amazon": "Amazon", "microsoft": "Microsoft", "nvidia": "NVIDIA", "perplexity": "Perplexity"}


def actualizar_tarifas():
    """Descarga los precios vigentes y los guarda (origen «openrouter»). No toca las tarifas manuales ni las de serie
    (DeepSeek directo tiene franja punta/valle, que OpenRouter no refleja). → nº de modelos actualizados."""
    r = requests.get(URL_PRECIOS, timeout=30)
    r.raise_for_status()
    ahora, filas = time.time(), []
    for m in r.json().get("data", []):
        mid = m.get("id") or ""
        if mid.startswith("~") or ":" in mid or "/" not in mid:   # alias móviles y variantes (batch, free…)
            continue
        p = m.get("pricing") or {}
        try:
            entrada, salida = float(p.get("prompt") or 0) * 1e6, float(p.get("completion") or 0) * 1e6
            cache = float(p["input_cache_read"]) * 1e6 if p.get("input_cache_read") not in (None, "") else None
        except (TypeError, ValueError):
            continue
        if entrada <= 0 and salida <= 0:
            continue
        vendor, nombre = mid.split("/", 1)
        filas.append((nombre, PROVEEDORES.get(vendor, vendor.capitalize()), m.get("context_length"),
                      round(entrada, 6), None if cache is None else round(cache, 6), round(salida, 6), ahora))
    if not filas:
        raise RuntimeError("La fuente de precios no devolvió modelos")
    with bd.db() as c:
        propias = {r["modelo"] for r in c.execute("SELECT modelo FROM tarifas WHERE origen IN ('manual','serie')")}
        normal_propias = {normalizar(x) for x in propias}
        n = 0
        for f in filas:
            if f[0] in propias or normalizar(f[0]) in normal_propias:
                continue
            c.execute("INSERT INTO tarifas(modelo,proveedor,contexto,entrada,cache,salida,origen,actualizado) "
                      "VALUES(?,?,?,?,?,?,'openrouter',?) ON CONFLICT(modelo) DO UPDATE SET proveedor=excluded.proveedor, "
                      "contexto=excluded.contexto, entrada=excluded.entrada, cache=excluded.cache, salida=excluded.salida, "
                      "actualizado=excluded.actualizado WHERE tarifas.origen='openrouter'", f)
            n += 1
    bd.fijar_ajuste("tarifas_actualizadas", ahora)
    bd.fijar_ajuste("tarifas_modelos", n)
    return n


def estado_tarifas():
    t = bd.ajuste("tarifas_actualizadas")
    return {"actualizadas": float(t) if t else None, "modelos": int(bd.ajuste("tarifas_modelos", 0) or 0),
            "fuente": "openrouter.ai (precios públicos por modelo)"}


def _bucle_tarifas():
    while True:
        try:
            t = bd.ajuste("tarifas_actualizadas")
            if not t or time.time() - float(t) > 3 * 24 * 3600:   # cada 3 días
                actualizar_tarifas()
        except Exception as e:  # noqa: BLE001 — sin red no pasa nada: siguen valiendo las guardadas
            print(f"[tarifas] no se pudieron actualizar: {e}", flush=True)
        time.sleep(6 * 3600)


def arrancar_actualizacion():
    threading.Thread(target=_bucle_tarifas, daemon=True, name="tarifas").start()


def estimar(mensajes, texto):
    """Sin `usage` en la respuesta: ~3,5 caracteres por token y ~1000 por imagen."""
    n, imgs = 0, 0
    for m in mensajes:
        cont = m["content"]
        if isinstance(cont, list):
            for p in cont:
                if p.get("type") == "text":
                    n += len(p["text"])
                else:
                    imgs += 1
        else:
            n += len(cont or "")
    return {"entrada": int(n / 3.5) + 1000 * imgs, "salida": int(len(texto) / 3.5), "cache": 0, "estimado": True}


def registrar(panel_id, agente_id, pregunta_id, tipo, uso):
    if not uso:
        return
    with bd.db() as c:
        c.execute("INSERT INTO consumo(ts,panel_id,agente_id,pregunta_id,tipo,modelo,entrada,salida,cache,estimado)"
                  " VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (time.time(), panel_id, agente_id, pregunta_id, tipo, uso.get("modelo") or config.IA_MODELO,
                   uso.get("entrada", 0), uso.get("salida", 0), uso.get("cache", 0), int(bool(uso.get("estimado")))))


def coste(fila, t):
    if not t:
        return None
    p = "_punta" if es_punta(fila["ts"], t.get("franja")) and t.get("entrada_punta") is not None else ""
    fallo = max(0, fila["entrada"] - fila["cache"])
    return (fallo * (t["entrada" + p] or 0) + fila["cache"] * (t["cache" + p] or t["entrada" + p] or 0)
            + fila["salida"] * (t["salida" + p] or 0)) / 1e6


def _suma(filas, tars):
    s = {"llamadas": 0, "entrada": 0, "salida": 0, "cache": 0, "coste": 0.0, "sin_tarifa": 0, "estimado": False}
    for f in filas:
        s["llamadas"] += 1
        s["entrada"] += f["entrada"]
        s["salida"] += f["salida"]
        s["cache"] += f["cache"]
        s["estimado"] |= bool(f["estimado"])
        k = coste(f, tars.get(f["modelo"]))
        if k is None:
            s["sin_tarifa"] += 1
        else:
            s["coste"] += k
    return s


def resumen(panel):
    """Totales del panel, de su última consulta, de sus pools y global, y el detalle por agente."""
    with bd.db() as c:
        tars = tarifas(c)
        todas = c.execute("SELECT * FROM consumo ORDER BY id").fetchall()
        ult = c.execute("SELECT MAX(id) FROM mensajes WHERE panel_id=? AND rol='user'", (panel["id"],)).fetchone()[0]
    del_panel = [f for f in todas if f["panel_id"] == panel["id"]]
    agentes = []
    for a in panel["agentes"]:
        suyas = [f for f in del_panel if f["agente_id"] == a["id"]]
        import proveedores
        modelo = proveedores.destino(a)[2]
        t = tars.get(modelo)
        consultas = [f for f in suyas if f["tipo"] != "resumen"]
        ultima = consultas[-1] if consultas else None
        ctx = (t or {}).get("contexto")
        agentes.append({
            "id": a["id"], "nombre": a["nombre"], "modelo": modelo, "tarifa": bool(t),
            "precio": {"entrada": t["entrada"], "salida": t["salida"], "modelo": t["modelo"], "origen": t.get("origen")} if t else None,
            "proveedor": proveedores.destino(a)[3] or (t or {}).get("proveedor"),
            **{k: v for k, v in _suma(suyas, tars).items()},
            "ultima": _suma([f for f in consultas if f["pregunta_id"] == ult], tars) if ult else None,
            "contexto_usado": ultima["entrada"] if ultima else 0, "contexto_max": ctx,
            "pct": round(100 * ultima["entrada"] / ctx, 2) if ultima and ctx else None,
        })
    t = tars.get(config.IA_MODELO)
    return {
        "servicio": {"proveedor": (t or {}).get("proveedor") or config.IA_URL.split("//")[-1].split("/")[0],
                     "modelo": config.IA_MODELO, "tarifa": t, "punta": es_punta(time.time(), (t or {}).get("franja")),
                     "fuente": FUENTE},
        "panel": _suma([f for f in del_panel if f["tipo"] != "resumen"], tars),
        "pools": _suma([f for f in del_panel if f["tipo"] == "resumen"], tars),
        "ultima": _suma([f for f in del_panel if f["pregunta_id"] == ult and f["tipo"] != "resumen"], tars) if ult else None,
        "global": _suma(todas, tars),
        "agentes": agentes,
        "sin_tarifa": sorted({f["modelo"] for f in todas if not tars.get(f["modelo"])}),
        "tarifas": estado_tarifas(),
        "gasto": estado_gasto(),
    }


# ---- tope de gasto --------------------------------------------------------------
def _inicios():
    from zoneinfo import ZoneInfo
    ahora = datetime.now(ZoneInfo(config.TZ))
    dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    return dia.timestamp(), dia.replace(day=1).timestamp()


def gastado(desde):
    with bd.db() as c:
        tars = tarifas(c)
        filas = c.execute("SELECT * FROM consumo WHERE ts>=?", (desde,)).fetchall()
    return sum(coste(f, tars.get(f["modelo"])) or 0 for f in filas)


def limites():
    def num(k):
        v = bd.ajuste(k)
        return float(v) if v not in (None, "") else None
    return {"diario": num("limite_diario"), "mensual": num("limite_mensual"), "modo": bd.ajuste("limite_modo", "avisar")}


def estado_gasto():
    dia, mes = _inicios()
    lim = limites()
    hoy, este_mes = gastado(dia), gastado(mes)
    excedido = ("mensual" if lim["mensual"] is not None and este_mes >= lim["mensual"]
                else "diario" if lim["diario"] is not None and hoy >= lim["diario"] else None)
    cerca = any(lim[k] and v >= 0.8 * lim[k] for k, v in (("diario", hoy), ("mensual", este_mes)))
    return {"hoy": hoy, "mes": este_mes, **lim, "excedido": excedido, "cerca": cerca and not excedido}


def comprobar():
    """Antes de cada llamada: con el modo «bloquear», no se gasta más allá del tope."""
    lim = limites()
    if lim["modo"] != "bloquear" or (lim["diario"] is None and lim["mensual"] is None):
        return
    e = estado_gasto()
    if e["excedido"]:
        tope = e["mensual"] if e["excedido"] == "mensual" else e["diario"]
        cifra = f"{tope:.6f}".rstrip("0").rstrip(".") if tope < 1 else f"{tope:.2f}"
        raise RuntimeError(f"Tope de gasto {e['excedido']} alcanzado (US$ {cifra}). Súbalo en Ajustes para seguir consultando.")


def tarifa_valida(d):
    out = {}
    for k in CAMPOS:
        v = d.get(k)
        if k in ("proveedor", "franja"):
            out[k] = (str(v).strip()[:40] or None) if v else None
        elif v in (None, ""):
            out[k] = None
        else:
            out[k] = float(v) if k != "contexto" else int(float(v))
            if out[k] < 0:
                raise ValueError(f"{k} no puede ser negativo")
    for k in ("entrada", "salida"):
        if out[k] is None:
            raise ValueError(f"Falta el precio de {k}")
    return out

