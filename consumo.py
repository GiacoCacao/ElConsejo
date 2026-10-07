"""Consumo de la API: tokens por llamada, tarifas por modelo y coste aproximado.

Los precios están en USD por millón de tokens. Las tarifas de serie se siembran en la tabla
`tarifas` y desde ahí se pueden editar (panel «Consumo»); el coste se calcula al consultar, con
la tarifa vigente y la franja horaria en la que se hizo cada llamada.
"""
import time
from datetime import datetime, timezone

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
        c.execute(f"INSERT OR IGNORE INTO tarifas(modelo,{','.join(CAMPOS)}) VALUES(?,{','.join('?' * len(CAMPOS))})",
                  (modelo, *[t.get(k) for k in CAMPOS]))


def tarifas(c):
    return {r["modelo"]: dict(r) for r in c.execute("SELECT * FROM tarifas ORDER BY proveedor, modelo")}


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
        modelo = a.get("modelo") or config.IA_MODELO
        t = tars.get(modelo)
        consultas = [f for f in suyas if f["tipo"] != "resumen"]
        ultima = consultas[-1] if consultas else None
        ctx = (t or {}).get("contexto")
        agentes.append({
            "id": a["id"], "nombre": a["nombre"], "modelo": modelo, "tarifa": bool(t),
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
    }


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

