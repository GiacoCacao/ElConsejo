"""Asamblea General: debate de un asunto entre varios comités (paneles) con derecho de palabra parlamentario.

La Asamblea es un consejo especial (paneles.tipo = 'asamblea'). Al convocar una sesión se eligen los
comités y sus delegados: cada delegado es una copia del experto de su comité (mismo id, así conserva su
biblioteca; mismo proveedor y modelo) con el mandato de su comité añadido a sus instrucciones. La
composición queda guardada en la sesión, y todo lo demás (turnos, votación, acta) es el mecanismo de
sesiones de siempre.
"""
import json

from flask import Blueprint, jsonify, request

import bd
import sesiones

bp = Blueprint("asamblea", __name__)
NOMBRE = "Asamblea General"
MAX_DELEGADOS = 16
COLORES = ["#c9a96e", "#7f9cc9", "#8fb59a", "#c27c8e", "#a593c9", "#d1a173", "#7fb5b5", "#b5a77f",
           "#c98f6e", "#8fa3c9", "#a9c27c", "#c97fb0"]
CONTEXTO = ("Ustedes son la Asamblea General del Consejo: delegados de distintos comités reunidos para tratar un "
            "asunto común. Cada delegado defiende la posición de su comité con cortesía parlamentaria: se dirige a "
            "la presidencia, usa la palabra con brevedad, responde a las alusiones, reconoce los buenos argumentos "
            "de otros comités y busca acuerdos. Respondan en español.")


def _app():
    import app
    return app


def panel_id(c):
    """El consejo de la Asamblea; se crea la primera vez."""
    r = c.execute("SELECT id FROM paneles WHERE tipo='asamblea'").fetchone()
    if r:
        return r["id"]
    pid = _app().guardar_panel(c, None, {"nombre": NOMBRE, "contexto": CONTEXTO, "agentes": [],
                                         "descripcion": "Debate entre comités con derecho de palabra parlamentario."})
    c.execute("UPDATE paneles SET tipo='asamblea', orden=0 WHERE id=?", (pid,))
    return pid


@bp.post("/api/asamblea/sesiones")
def convocar():
    d = request.get_json(force=True)
    a = _app()
    with bd.db() as c:
        aid = panel_id(c)
        r = sesiones.activa(c, aid)
        if r:
            return jsonify(error=f"La Asamblea ya está reunida (sesión nº {r['numero']}). Ciérrela antes de convocar otra."), 409
        delegados, comites = [], []
        for i, com in enumerate(d.get("comites") or []):
            fila = c.execute("SELECT * FROM paneles WHERE id=? AND COALESCE(tipo,'')<>'asamblea'", (com.get("panel_id"),)).fetchone()
            if not fila:
                continue
            p = a.panel_dict(c, fila)
            elegidos = [x for x in p["agentes"] if x["id"] in set(com.get("delegados") or [])]
            if not elegidos:
                continue
            color = COLORES[len(comites) % len(COLORES)]
            comites.append({"id": p["id"], "nombre": p["nombre"], "color": color})
            for x in elegidos:
                delegados.append({**{k: x.get(k) for k in ("id", "nombre", "rol", "emoji", "modelo", "proveedor", "temperatura")},
                                  "color": color, "comite": p["nombre"], "comite_id": p["id"],
                                  "instrucciones": (x.get("instrucciones") or "") +
                                  f"\n\nEn esta Asamblea General eres delegado del {p['nombre']}"
                                  + (f" ({p['descripcion']})" if p.get("descripcion") else "") + ". Mandato de tu comité: "
                                  + (p.get("contexto") or "").split("\n\n")[0]})
        if len(comites) < 2:
            return jsonify(error="Elija al menos dos comités con algún delegado"), 400
        if len(delegados) > MAX_DELEGADOS:
            return jsonify(error=f"Como máximo {MAX_DELEGADOS} delegados en la Asamblea (hay {len(delegados)})"), 400
        fila = c.execute("SELECT * FROM paneles WHERE id=?", (aid,)).fetchone()
        a.guardar_panel(c, aid, {"nombre": fila["nombre"], "descripcion": fila["descripcion"], "contexto": fila["contexto"],
                                 "agentes": delegados}, tope=MAX_DELEGADOS)
        sid = sesiones.abrir(c, aid, d.get("asunto"), d.get("modo_debate", "orden"), [x["id"] for x in delegados],
                             d.get("anexos"), d.get("orden_dia"))
        try:
            limite = max(40, min(400, int(d.get("limite_palabras") or 0))) if d.get("limite_palabras") else None
        except (TypeError, ValueError):
            limite = None
        c.execute("UPDATE sesiones SET composicion=?, limite_palabras=? WHERE id=?",
                  (json.dumps({"comites": comites, "delegados": [{k: x[k] for k in ("id", "nombre", "rol", "comite", "color")}
                                                                  for x in delegados]}, ensure_ascii=False), limite, sid))
        return jsonify(sesiones.sesion_dict(c, sesiones._sesion(c, sid))), 201
