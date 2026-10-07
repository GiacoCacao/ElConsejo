"""Estadísticas del Consejo: actividad, acuerdos, expertos y gasto, por periodo y por consejo."""
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request

import bd
import config
import consumo

bp = Blueprint("estadisticas", __name__)
MESES = "ene feb mar abr may jun jul ago sep oct nov dic".split()


def _resultado(r):
    if not r:
        return None
    e = r.get("estado")
    if e == "aprobado":
        if r.get("unanime"):
            return "Unanimidad"
        if "abstenciones" in r.get("texto", "") and "consenso" in r.get("texto", "").lower():
            return "Consenso con abstenciones"
        return "Mayoría simple"
    return {"sin_consenso": "Sin consenso", "rechazado": "Rechazado", "empate": "Empate", "sin_votos": "Sin votos"}.get(e, e)


@bp.get("/api/estadisticas")
def estadisticas():
    dias = request.args.get("dias", 90, type=int)
    pid = request.args.get("panel") or None
    tz = ZoneInfo(config.TZ)
    ahora = datetime.now(tz)
    desde = (ahora - timedelta(days=dias)).timestamp() if dias > 0 else 0
    with bd.db() as c:
        paneles = {r["id"]: r for r in c.execute("SELECT * FROM paneles")}
        nombre_agente = {}
        for r in sorted(paneles.values(), key=lambda r: r["tipo"] == "asamblea"):   # los consejos antes que la Asamblea
            for a in json.loads(r["agentes"] or "[]"):
                nombre_agente.setdefault(a["id"], (a["nombre"], r["nombre"] if r["tipo"] != "asamblea" else a.get("comite") or "Asamblea"))
        filtro, args = "abierta>=?", [desde]
        if pid:
            filtro += " AND panel_id=?"
            args.append(pid)
        ses = c.execute(f"SELECT * FROM sesiones WHERE {filtro}", args).fetchall()
        sids = [s["id"] for s in ses] or [-1]
        marcas = ",".join("?" * len(sids))
        msgs = c.execute(f"SELECT rol, agente_id, modo, error FROM mensajes WHERE sesion_id IN ({marcas})", sids).fetchall()
        vots = c.execute(f"SELECT * FROM votaciones WHERE sesion_id IN ({marcas}) AND estado='cerrada'", sids).fetchall()
        votos = c.execute(f"SELECT v.agente_id, v.opcion, x.resultado FROM votos v JOIN votaciones x ON x.id=v.votacion_id "
                          f"WHERE x.sesion_id IN ({marcas}) AND x.estado='cerrada'", sids).fetchall()
        mocs = c.execute(f"SELECT resultado FROM mociones WHERE sesion_id IN ({marcas})", sids).fetchall()
        cf, ca = "ts>=?", [desde]
        if pid:
            cf += " AND panel_id=?"
            ca.append(pid)
        filas = c.execute(f"SELECT * FROM consumo WHERE {cf}", ca).fetchall()
        tars = consumo.tarifas(c)

    # gasto: por día (≤ 31 días) o por mes
    coste = lambda f: consumo.coste(f, tars.get(f["modelo"])) or 0
    por_dia = dias and dias <= 31
    serie = defaultdict(float)
    for f in filas:
        d = datetime.fromtimestamp(f["ts"], tz)
        serie[d.strftime("%Y-%m-%d") if por_dia else d.strftime("%Y-%m")] += coste(f)
    claves = []
    if por_dia:
        claves = [(ahora - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(dias - 1, -1, -1)]
        etiqueta = lambda k: f"{int(k[8:])} {MESES[int(k[5:7]) - 1]}"
    else:
        meses = 12 if dias in (0, 365) or dias > 365 else max(1, round(dias / 30))
        y, m = ahora.year, ahora.month
        for _ in range(meses):
            claves.insert(0, f"{y}-{m:02d}")
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        etiqueta = lambda k: f"{MESES[int(k[5:7]) - 1]} {k[2:4]}"
    gasto_serie = [{"clave": k, "etiqueta": etiqueta(k), "valor": round(serie.get(k, 0), 6)} for k in claves]

    por_modelo, por_consejo = defaultdict(lambda: [0.0, 0]), defaultdict(float)
    for f in filas:
        por_modelo[f["modelo"] or "?"][0] += coste(f)
        por_modelo[f["modelo"] or "?"][1] += (f["entrada"] or 0) + (f["salida"] or 0)
        por_consejo[paneles[f["panel_id"]]["nombre"] if f["panel_id"] in paneles else "Sin consejo"] += coste(f)

    # resultados de las votaciones y disidencia (votar contra el resultado final)
    resultados = Counter(_resultado(json.loads(v["resultado"] or "null")) for v in vots)
    resultados.pop(None, None)
    diso = defaultdict(lambda: [0, 0])
    for v in votos:
        r = json.loads(v["resultado"] or "null")
        if not r or r.get("estado") == "empate" or v["opcion"] == "abstencion":
            continue
        ganadora = r.get("ganadora") or ("favor" if r.get("aprobado") else "contra")
        diso[v["agente_id"]][0] += 1
        if v["opcion"] != ganadora:
            diso[v["agente_id"]][1] += 1
    disidentes = sorted(({"nombre": nombre_agente.get(a, ("Experto retirado", ""))[0], "consejo": nombre_agente.get(a, ("", ""))[1],
                          "votos": t, "en_contra": d, "pct": round(100 * d / t, 1)} for a, (t, d) in diso.items() if t >= 3),
                        key=lambda x: (-x["pct"], -x["votos"]))[:8]
    activos = Counter(m["agente_id"] for m in msgs if m["rol"] == "agent" and not m["error"])
    aprobadas = sum(1 for v in vots if (json.loads(v["resultado"] or "{}") or {}).get("aprobado"))
    total_gasto = sum(coste(f) for f in filas)
    cerradas = sum(1 for s in ses if s["estado"] == "cerrada")
    return jsonify(
        periodo={"dias": dias, "desde": desde, "por_dia": bool(por_dia)},
        tiles={"sesiones": len(ses), "cerradas": cerradas, "abiertas": len(ses) - cerradas,
               "consultas": sum(1 for m in msgs if m["rol"] == "user"),
               "intervenciones": sum(1 for m in msgs if m["rol"] == "agent" and not m["error"]),
               "votaciones": len(vots), "aprobadas": aprobadas,
               "pct_acuerdo": round(100 * aprobadas / len(vots)) if vots else None,
               "gasto": round(total_gasto, 6), "gasto_por_sesion": round(total_gasto / len(ses), 6) if ses else None,
               "cuestiones_orden": sum(1 for m in msgs if m["modo"] == "orden"),
               "mociones": len(mocs), "mociones_aprobadas": sum(1 for m in mocs if json.loads(m["resultado"]).get("aprobada"))},
        gasto_serie=gasto_serie,
        sesiones_por_consejo=[{"nombre": n, "valor": v} for n, v in Counter(
            paneles[s["panel_id"]]["nombre"] if s["panel_id"] in paneles else "Consejo eliminado" for s in ses).most_common(12)],
        resultados=[{"nombre": n, "valor": v} for n, v in resultados.most_common()],
        activos=[{"nombre": nombre_agente.get(a, ("Experto retirado", ""))[0], "consejo": nombre_agente.get(a, ("", ""))[1], "valor": n}
                 for a, n in activos.most_common(8)],
        disidentes=disidentes,
        gasto_por_modelo=sorted(({"nombre": k, "valor": round(v[0], 6), "tokens": v[1]} for k, v in por_modelo.items()),
                                key=lambda x: -x["valor"]),
        gasto_por_consejo=sorted(({"nombre": k, "valor": round(v, 6)} for k, v in por_consejo.items() if v > 0),
                                 key=lambda x: -x["valor"])[:10],
        generado=time.time())
