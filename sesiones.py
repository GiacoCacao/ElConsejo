"""Sesiones del Consejo: apertura, orden del debate, votaciones, acta de cierre y traslado a otros consejos.

Una sesión trata un asunto. Las consultas de la sala pertenecen a la sesión abierta del panel (si no
hay, se abre una al consultar). Para concluir: la Secretaría (IA neutral) redacta una propuesta de
acuerdo unificado o identifica alternativas, los expertos votan en el orden del debate y, al cerrar,
la Secretaría levanta el acta. Los datos objetivos del acta (asistentes, orden, votos, acuerdo) los
compone el código; la IA solo redacta la síntesis del debate y las conclusiones.
"""
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, abort, jsonify, request

import bd
import consumo
import ia

bp = Blueprint("sesiones", __name__)
TZ = ZoneInfo("America/Caracas")
ABIERTAS = ("abierta", "votacion")
MESES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
VOTOS = {"favor": "A favor", "contra": "En contra", "abstencion": "Abstención"}


def _app():   # import diferido: app importa este módulo
    import app
    return app


# ---- utilidades --------------------------------------------------------------
def _hora(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%H:%M")


def _fecha(ts):
    d = datetime.fromtimestamp(ts, TZ)
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _orden(sesion_orden, panel):
    """Orden del debate ajustado a los expertos actuales (los nuevos, al final)."""
    ids = [a["id"] for a in panel["agentes"]]
    orden = [i for i in sesion_orden if i in ids]
    return orden + [i for i in ids if i not in orden]


def sesion_dict(c, r, panel=None):
    panel = panel or _app()._panel(c, r["panel_id"])
    comp = json.loads(r["composicion"] or "null")
    return {"id": r["id"], "panel_id": r["panel_id"], "panel": panel["nombre"], "numero": r["numero"],
            "composicion": comp, "limite_palabras": r["limite_palabras"],
            "orden_dia": json.loads(r["orden_dia"] or "null") or [r["asunto"]], "punto": r["punto"] or 0,
            "receso": bool(r["receso"]), "oradores": json.loads(r["oradores"] or "[]"),
            "asunto": r["asunto"], "estado": r["estado"], "modo_debate": r["modo_debate"],
            "orden": orden_de(r, panel), "anexos": _anexos_info(c, r), "individual": r["individual"],
            "abierta": r["abierta"], "cerrada": r["cerrada"], "acuerdo": r["acuerdo"],
            "resultado": json.loads(r["resultado"] or "null"), "tiene_acta": bool(r["acta"]),
            "consultas": c.execute("SELECT COUNT(*) FROM mensajes WHERE sesion_id=? AND rol='user'", (r["id"],)).fetchone()[0]}


def _anexos_info(c, r):
    out = []
    for sid in json.loads(r["anexos"] or "[]"):
        a = c.execute("SELECT s.id, s.numero, s.asunto, s.cerrada, p.nombre FROM sesiones s "
                      "LEFT JOIN paneles p ON p.id=s.panel_id WHERE s.id=?", (sid,)).fetchone()
        if a:
            out.append({"id": a["id"], "numero": a["numero"], "asunto": a["asunto"], "panel": a["nombre"] or "Panel eliminado",
                        "cerrada": a["cerrada"]})
    return out


def activa(c, pid, individual=None):
    """La sesión abierta del panel; con `individual`, la del despacho de ese experto (van aparte)."""
    if individual:
        return c.execute("SELECT * FROM sesiones WHERE panel_id=? AND individual=? AND estado IN ('abierta','votacion') "
                         "ORDER BY id DESC LIMIT 1", (pid, individual)).fetchone()
    return c.execute("SELECT * FROM sesiones WHERE panel_id=? AND individual IS NULL AND estado IN ('abierta','votacion') "
                     "ORDER BY id DESC LIMIT 1", (pid,)).fetchone()


def orden_de(r, panel):
    """Orden del debate de una sesión (en una consulta individual, solo su experto)."""
    if r["individual"]:
        return [r["individual"]]
    return _orden(json.loads(r["orden"] or "[]"), panel)


def puntos_limpios(lista, asunto):
    puntos = [str(x).strip()[:200] for x in (lista or []) if str(x).strip()][:10]
    return puntos or [(asunto or "").strip()[:200] or "Consulta al Consejo"]


def abrir(c, pid, asunto, modo="orden", orden=None, anexos=None, orden_dia=None, individual=None):
    panel = _app()._panel(c, pid)
    numero = c.execute("SELECT COALESCE(MAX(numero),0)+1 FROM sesiones WHERE panel_id=?", (pid,)).fetchone()[0]
    validos = []
    for a in anexos or []:
        try:
            a = int(a)
        except (TypeError, ValueError):
            continue
        if c.execute("SELECT 1 FROM sesiones WHERE id=? AND acta IS NOT NULL", (a,)).fetchone() and a not in validos:
            validos.append(a)
    asunto = (asunto or "").strip()[:200] or "Consulta al Consejo"
    cur = c.execute("INSERT INTO sesiones(panel_id,numero,asunto,estado,modo_debate,orden,anexos,abierta,orden_dia,punto) "
                    "VALUES(?,?,?,?,?,?,?,?,?,0)",
                    (pid, numero, asunto, "abierta", modo if modo in ("orden", "simultaneo") else "orden",
                     json.dumps(_orden(orden or [], panel)), json.dumps(validos), time.time(),
                     json.dumps(puntos_limpios(orden_dia, asunto), ensure_ascii=False)))
    if individual:
        c.execute("UPDATE sesiones SET individual=?, orden=? WHERE id=?", (individual, json.dumps([individual]), cur.lastrowid))
    return cur.lastrowid


def _sesion(c, sid):
    r = c.execute("SELECT * FROM sesiones WHERE id=?", (sid,)).fetchone()
    if not r:
        abort(404)
    return r


def texto_anexos(c, sesion_row, tope=3500):
    """Actas anexas para el contexto de los expertos."""
    partes = []
    for a in json.loads(sesion_row["anexos"] or "[]"):
        r = c.execute("SELECT s.*, p.nombre AS panel FROM sesiones s LEFT JOIN paneles p ON p.id=s.panel_id "
                      "WHERE s.id=?", (a,)).fetchone()
        if r and r["acta"]:
            partes.append(f"### Acta anexa — {r['panel'] or 'otro consejo'}, sesión nº {r['numero']}: {r['asunto']}\n"
                          + r["acta"][:tope])
    return "\n\n".join(partes)


def transcripcion(c, sid, panel, tope=24000, punto=None):
    """Consultas e intervenciones de la sesión (o de un punto del orden del día), en orden, como texto."""
    nombres = {a["id"]: f"{a['nombre']} ({a['rol'] or 'experto'}{', ' + a['comite'] if a.get('comite') else ''})"
               for a in panel["agentes"]}
    solo = {a["id"]: a["nombre"] for a in panel["agentes"]}
    lineas = []
    filas = c.execute("SELECT * FROM mensajes WHERE sesion_id=? AND error=0 ORDER BY id", (sid,)).fetchall()
    for m in filas:
        if punto is not None and (m["punto"] or 0) != punto:
            continue
        if m["rol"] == "user":
            a_quien = f" (consulta individual a {solo.get(m['destinatario'], 'un experto')})" if m["destinatario"] else ""
            lineas.append(f"\n**Consulta de la presidencia{a_quien}:** {m['texto'] or '(documentos o imágenes adjuntos)'}")
        else:
            quien = nombres.get(m["agente_id"], "Experto retirado")
            tipo = {"palabra": " — en uso de la palabra", "alusion": " — por alusiones",
                    "orden": " — cuestión de orden"}.get(m["modo"]) or (
                f" — réplica {m['ronda']}" if m["ronda"] else "")
            lineas.append(f"**{quien}**{tipo}: {m['texto']}")
    t = "\n".join(lineas).strip()
    return t if len(t) <= tope else "[…]\n" + t[-tope:]


def _secretaria(panel, prompt, max_tokens=700, uso_ctx=None):
    sistema = (f"Eres la Secretaría del {panel['nombre']}. Eres neutral, rigurosa y formal; no opinas, "
               f"recoges con fidelidad lo debatido. Escribes en español. Hoy es {_app().fecha_actual()}.")
    uso = {}
    texto = ia.llamar([{"role": "system", "content": sistema}, {"role": "user", "content": prompt}],
                      temperatura=0.2, max_tokens=max_tokens, uso=uso)
    if uso_ctx:
        consumo.registrar(panel["id"], None, None, "secretaria", uso)
    return texto


def _votacion_dict(c, v):
    return {"id": v["id"], "sesion_id": v["sesion_id"], "tipo": v["tipo"], "propuesta": v["propuesta"], "punto": v["punto"] or 0,
            "alternativas": json.loads(v["alternativas"] or "[]"), "estado": v["estado"], "intento": v["intento"],
            "resultado": json.loads(v["resultado"] or "null"), "ts": v["ts"],
            "votos": [dict(x) for x in c.execute("SELECT agente_id, opcion, motivo, error FROM votos "
                                                  "WHERE votacion_id=? ORDER BY id", (v["id"],))]}


def votaciones_de(c, sid):
    return [_votacion_dict(c, v) for v in c.execute("SELECT * FROM votaciones WHERE sesion_id=? ORDER BY id", (sid,))]


# ---- registro y estado -----------------------------------------------------------
@bp.get("/api/sesiones")
def listar():
    filtros, args = [], []
    if request.args.get("panel"):
        filtros.append("s.panel_id=?")
        args.append(request.args["panel"])
    if request.args.get("estado") == "cerrada":
        filtros.append("s.estado='cerrada'")
    elif request.args.get("estado") == "abierta":
        filtros.append("s.estado IN ('abierta','votacion')")
    if request.args.get("con_acta"):
        filtros.append("s.acta IS NOT NULL")
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    with bd.db() as c:
        filas = c.execute(f"SELECT s.*, p.nombre AS pnombre FROM sesiones s LEFT JOIN paneles p ON p.id=s.panel_id "
                          f"{where} ORDER BY s.abierta DESC", args).fetchall()
        out = []
        for r in filas:
            experto = None
            if r["individual"]:
                p = c.execute("SELECT agentes FROM paneles WHERE id=?", (r["panel_id"],)).fetchone()
                experto = next((a["nombre"] for a in json.loads(p["agentes"] if p else "[]") if a["id"] == r["individual"]), "Experto")
            out.append({"id": r["id"], "panel_id": r["panel_id"], "panel": r["pnombre"] or "Panel eliminado", "individual": r["individual"],
                        "experto": experto,
                        "numero": r["numero"], "asunto": r["asunto"], "estado": r["estado"], "abierta": r["abierta"],
                        "cerrada": r["cerrada"], "acuerdo": r["acuerdo"], "tiene_acta": bool(r["acta"]),
                        "resultado": json.loads(r["resultado"] or "null"),
                        "consultas": c.execute("SELECT COUNT(*) FROM mensajes WHERE sesion_id=? AND rol='user'",
                                               (r["id"],)).fetchone()[0]})
        return jsonify(out)


@bp.get("/api/paneles/<pid>/sesion")
def sesion_activa(pid):
    """La sesión abierta del panel, con su transcripción y votaciones (o nada)."""
    with bd.db() as c:
        panel = _app()._panel(c, pid)
        r = activa(c, pid, request.args.get("individual") or None)
        if not r:
            return jsonify(sesion=None, mensajes=[], votaciones=[])
        msgs = [_app().msg_dict(m) for m in c.execute("SELECT * FROM mensajes WHERE sesion_id=? ORDER BY id", (r["id"],))]
        return jsonify(sesion=sesion_dict(c, r, panel), mensajes=msgs, votaciones=votaciones_de(c, r["id"]))


@bp.post("/api/paneles/<pid>/sesiones")
def iniciar(pid):
    d = request.get_json(force=True)
    with bd.db() as c:
        panel = _app()._panel(c, pid)
        ind = d.get("individual") if d.get("individual") in {a["id"] for a in panel["agentes"]} else None
        r = activa(c, pid, ind)
        if r:
            return jsonify(error=f"Ya hay una sesión abierta (nº {r['numero']}). Ciérrela antes de iniciar otra.",
                           sesion=sesion_dict(c, r)), 409
        sid = abrir(c, pid, d.get("asunto"), d.get("modo_debate", "orden"), d.get("orden"), d.get("anexos"), d.get("orden_dia"), ind)
        return jsonify(sesion_dict(c, _sesion(c, sid))), 201


@bp.get("/api/sesiones/<int:sid>")
def ver(sid):
    with bd.db() as c:
        r = _sesion(c, sid)
        try:
            panel = _app()._panel(c, r["panel_id"])
            s = sesion_dict(c, r, panel)
        except Exception:   # noqa: BLE001 — panel eliminado: solo queda el acta
            s = {"id": r["id"], "numero": r["numero"], "asunto": r["asunto"], "estado": r["estado"],
                 "panel": "Panel eliminado", "tiene_acta": bool(r["acta"])}
        msgs = [_app().msg_dict(m) for m in c.execute("SELECT * FROM mensajes WHERE sesion_id=? ORDER BY id", (sid,))]
        return jsonify(sesion=s, acta=r["acta"], mensajes=msgs, votaciones=votaciones_de(c, sid))


@bp.put("/api/sesiones/<int:sid>")
def editar(sid):
    d = request.get_json(force=True)
    with bd.db() as c:
        r = _sesion(c, sid)
        if r["estado"] == "cerrada":
            return jsonify(error="La sesión está cerrada"), 409
        panel = _app()._panel(c, r["panel_id"])
        anexos = json.loads(r["anexos"] or "[]")
        if "anexos" in d:
            anexos = [int(a) for a in d["anexos"] if c.execute(
                "SELECT 1 FROM sesiones WHERE id=? AND acta IS NOT NULL AND id<>?", (int(a), sid)).fetchone()]
        if "orden_dia" in d:
            puntos = puntos_limpios(d["orden_dia"], d.get("asunto") or r["asunto"])
            c.execute("UPDATE sesiones SET orden_dia=?, punto=? WHERE id=?",
                      (json.dumps(puntos, ensure_ascii=False), min(r["punto"] or 0, len(puntos) - 1), sid))
        c.execute("UPDATE sesiones SET asunto=?, modo_debate=?, orden=?, anexos=? WHERE id=?",
                  ((d.get("asunto") or r["asunto"]).strip()[:200],
                   d.get("modo_debate") if d.get("modo_debate") in ("orden", "simultaneo") else r["modo_debate"],
                   json.dumps(_orden(d.get("orden") or json.loads(r["orden"] or "[]"), panel)), json.dumps(anexos), sid))
        return jsonify(sesion_dict(c, _sesion(c, sid), panel))


@bp.delete("/api/sesiones/<int:sid>")
def borrar(sid):
    with bd.db() as c:
        _sesion(c, sid)
        borrar_sesion(c, sid)
    return "", 204


def borrar_sesion(c, sid):
    a = _app()
    for q in c.execute("SELECT id, imagenes FROM mensajes WHERE sesion_id=? AND rol='user'", (sid,)).fetchall():
        for d in c.execute("SELECT * FROM docs WHERE pregunta_id=? AND ambito='chat'", (q["id"],)).fetchall():
            a._quitar_doc(c, d)
    c.execute("DELETE FROM votos WHERE votacion_id IN (SELECT id FROM votaciones WHERE sesion_id=?)", (sid,))
    c.execute("DELETE FROM votaciones WHERE sesion_id=?", (sid,))
    c.execute("DELETE FROM mensajes WHERE sesion_id=?", (sid,))
    c.execute("DELETE FROM sesiones WHERE id=?", (sid,))


# ---- deliberación: propuesta y votación ---------------------------------------
def _alternativas(texto):
    alts = []
    for m in re.finditer(r"^\s*\**([A-F])[).:-]\**\s*(.+)$", texto, re.M):
        if m.group(1) not in [a["letra"] for a in alts]:
            alts.append({"letra": m.group(1), "texto": m.group(2).strip(" *")})
    return alts[:5]


@bp.post("/api/sesiones/<int:sid>/propuesta")
def propuesta(sid):
    """La Secretaría redacta la propuesta (consenso) o las alternativas (mayoría) a partir del debate."""
    d = request.get_json(force=True)
    tipo = "mayoria" if d.get("tipo") == "mayoria" else "consenso"
    with bd.db() as c:
        r = _sesion(c, sid)
        if r["estado"] == "cerrada":
            return jsonify(error="La sesión está cerrada"), 409
        panel = _app()._panel(c, r["panel_id"])
        debate = transcripcion(c, sid, panel, 16000, r["punto"] or 0)
        anexos = texto_anexos(c, r, 2000)
        puntos = json.loads(r["orden_dia"] or "null") or [r["asunto"]]
        punto_txt = puntos[min(r["punto"] or 0, len(puntos) - 1)]
        objeciones = ""
        if d.get("revisar"):
            v = c.execute("SELECT * FROM votaciones WHERE id=? AND sesion_id=?", (d["revisar"], sid)).fetchone()
            if v:
                objs = c.execute("SELECT agente_id, opcion, motivo FROM votos WHERE votacion_id=? AND opcion<>'favor'",
                                 (v["id"],)).fetchall()
                nombres = {a["id"]: a["nombre"] for a in panel["agentes"]}
                objeciones = (f"\n\nPropuesta anterior (no alcanzó el consenso):\n{v['propuesta']}\n\nObjeciones y reservas:\n"
                              + "\n".join(f"- {nombres.get(o['agente_id'], 'Experto')} ({VOTOS.get(o['opcion'], o['opcion'])}): "
                                          f"{o['motivo']}" for o in objs))
    if not debate:
        return jsonify(error="Aún no hay debate en esta sesión: plantee primero una consulta."), 400
    base = (f"Asunto de la sesión: {r['asunto']}\n" + (f"Punto del orden del día en debate: {punto_txt}\n" if len(puntos) > 1 else "")
            + f"\nDebate:\n{debate}" + (f"\n\nActas anexas:\n{anexos}" if anexos else ""))
    try:
        if tipo == "consenso":
            prompt = (base + objeciones + "\n\nRedacta una PROPUESTA DE ACUERDO UNIFICADO que recoja los puntos de "
                      "coincidencia y resuelva las discrepancias de forma equilibrada"
                      + (", atendiendo a las objeciones" if objeciones else "") +
                      ". Empieza por «El Consejo acuerda:» y usa como máximo 150 palabras. Devuelve solo el texto del acuerdo.")
            texto = _secretaria(panel, prompt, 500, True).strip()
            return jsonify(tipo=tipo, propuesta=texto, alternativas=[])
        prompt = (base + "\n\nIdentifica entre 2 y 4 ALTERNATIVAS claras y mutuamente excluyentes que hayan surgido en "
                  "el debate, para someterlas a votación por mayoría simple. Formato estricto, una por línea y nada más:\n"
                  "A) <alternativa en una frase, máximo 40 palabras>\nB) <…>")
        texto = _secretaria(panel, prompt, 500, True)
        alts = _alternativas(texto)
        if len(alts) < 2:
            return jsonify(tipo="consenso", propuesta=texto.strip(), alternativas=[],
                           aviso="La Secretaría no encontró alternativas distintas: se propone un único acuerdo.")
        return jsonify(tipo=tipo, propuesta="", alternativas=alts)
    except ia.IAError as e:
        return jsonify(error=str(e)), 502


@bp.post("/api/sesiones/<int:sid>/votaciones")
def abrir_votacion(sid):
    d = request.get_json(force=True)
    tipo = "mayoria" if d.get("tipo") == "mayoria" else "consenso"
    alts = [{"letra": chr(65 + i), "texto": (a.get("texto") if isinstance(a, dict) else str(a)).strip()[:400]}
            for i, a in enumerate(d.get("alternativas") or []) if (a.get("texto") if isinstance(a, dict) else str(a)).strip()][:5]
    texto = (d.get("propuesta") or "").strip()[:3000]
    if tipo == "mayoria" and len(alts) < 2 and not texto:
        return jsonify(error="Hacen falta al menos dos alternativas"), 400
    if tipo == "consenso" and not texto:
        return jsonify(error="Falta el texto de la propuesta"), 400
    with bd.db() as c:
        r = _sesion(c, sid)
        if r["estado"] == "cerrada":
            return jsonify(error="La sesión está cerrada"), 409
        intento = c.execute("SELECT COUNT(*)+1 FROM votaciones WHERE sesion_id=?", (sid,)).fetchone()[0]
        cur = c.execute("INSERT INTO votaciones(sesion_id,tipo,propuesta,alternativas,estado,intento,ts,punto) VALUES(?,?,?,?,?,?,?,?)",
                        (sid, tipo, texto, json.dumps(alts if len(alts) >= 2 else [], ensure_ascii=False), "abierta",
                         intento, time.time(), r["punto"] or 0))
        c.execute("UPDATE sesiones SET estado='votacion' WHERE id=?", (sid,))
        return jsonify(_votacion_dict(c, c.execute("SELECT * FROM votaciones WHERE id=?", (cur.lastrowid,)).fetchone())), 201


def _leer_voto(texto, alts):
    m = re.search(r"VOTO\s*:\s*\**\s*([^\n*]+)", texto, re.I)
    motivo = re.search(r"MOTIVO\s*:\s*(.+)", texto, re.I | re.S)
    motivo = (motivo.group(1).strip() if motivo else texto.strip())[:600]
    v = (m.group(1) if m else "").strip().upper()
    if alts:
        letra = re.match(r"([A-F])\b", v)
        if letra and letra.group(1) in [a["letra"] for a in alts]:
            return letra.group(1), motivo
        if "ABST" in v:
            return "abstencion", motivo
        return None, motivo
    if "ABST" in v:
        return "abstencion", motivo
    if "CONTRA" in v or v.startswith("NO"):
        return "contra", motivo
    if "FAVOR" in v or v.startswith("S"):
        return "favor", motivo
    return None, motivo


@bp.post("/api/votaciones/<int:vid>/votos/<aid>")
def votar(vid, aid):
    a_mod = _app()
    with bd.db() as c:
        v = c.execute("SELECT * FROM votaciones WHERE id=?", (vid,)).fetchone()
        if not v:
            abort(404)
        if v["estado"] != "abierta":
            return jsonify(error="La votación ya está cerrada"), 409
        s = _sesion(c, v["sesion_id"])
        panel = a_mod._panel(c, s["panel_id"])
        agente = next((a for a in panel["agentes"] if a["id"] == aid), None)
        if not agente:
            abort(404)
        debate = transcripcion(c, s["id"], panel, 12000)
        anexos = texto_anexos(c, s, 1500)
    alts = json.loads(v["alternativas"] or "[]")
    if alts:
        objeto = "las siguientes alternativas (vota UNA):\n" + "\n".join(f"{x['letra']}) {x['texto']}" for x in alts)
        formato = "VOTO: <letra de la alternativa, o ABSTENCIÓN>"
    else:
        objeto = f"la siguiente propuesta de acuerdo:\n\n{v['propuesta']}"
        formato = "VOTO: <A FAVOR | EN CONTRA | ABSTENCIÓN>"
    msgs = [{"role": "system", "content": a_mod.sistema_agente(panel, agente)},
            {"role": "user", "content": f"Asunto de la sesión: {s['asunto']}\n\nDebate del Consejo:\n{debate}"
             + (f"\n\nActas anexas:\n{anexos}" if anexos else "")
             + f"\n\nLa presidencia somete a votación {objeto}\n\nVota según tu criterio de experto. Responde "
               f"EXACTAMENTE con este formato y nada más:\n{formato}\nMOTIVO: <una o dos frases>"}]
    uso, opcion, motivo, error = {}, None, "", 0
    try:
        texto = ia.llamar(msgs, modelo=agente["modelo"], temperatura=agente["temperatura"], max_tokens=220, uso=uso,
                          agente=agente)
        consumo.registrar(panel["id"], aid, None, "voto", uso)
        opcion, motivo = _leer_voto(texto, alts)
        if not opcion:
            opcion, motivo = "abstencion", f"(Voto no válido, se computa como abstención) {motivo}"
    except ia.IAError as e:
        opcion, motivo, error = "abstencion", f"No pudo votar: {e}"[:400], 1
    with bd.db() as c:
        c.execute("DELETE FROM votos WHERE votacion_id=? AND agente_id=?", (vid, aid))
        c.execute("INSERT INTO votos(votacion_id,agente_id,opcion,motivo,error,ts) VALUES(?,?,?,?,?,?)",
                  (vid, aid, opcion, motivo, error, time.time()))
    return jsonify(agente_id=aid, opcion=opcion, motivo=motivo, error=bool(error))


def computar(v, votos, calidad=None):
    """Resultado de una votación. `calidad`: voto de calidad de la presidencia para deshacer un empate."""
    alts = json.loads(v["alternativas"] or "[]") if not isinstance(v, dict) else v["alternativas"]
    tipo = v["tipo"]
    if alts:
        cuenta = {a["letra"]: 0 for a in alts}
        abst = 0
        for x in votos:
            if x["opcion"] in cuenta:
                cuenta[x["opcion"]] += 1
            else:
                abst += 1
        orden = sorted(cuenta.items(), key=lambda kv: -kv[1])
        maximo = orden[0][1]
        empatadas = [k for k, n in orden if n == maximo]
        detalle = " · ".join(f"{k}: {n}" for k, n in cuenta.items()) + f" · abstenciones: {abst}"
        if maximo == 0:
            return {"estado": "sin_votos", "aprobado": False, "texto": "Sin votos válidos", "cuenta": cuenta, "abstenciones": abst}
        if len(empatadas) > 1 and calidad not in empatadas:
            return {"estado": "empate", "aprobado": False, "empatadas": empatadas, "cuenta": cuenta, "abstenciones": abst,
                    "texto": f"Empate entre las alternativas {' y '.join(empatadas)} ({detalle})"}
        ganadora = calidad if len(empatadas) > 1 else orden[0][0]
        alt = next(a for a in alts if a["letra"] == ganadora)
        return {"estado": "aprobado", "aprobado": True, "ganadora": ganadora, "acuerdo": alt["texto"], "cuenta": cuenta,
                "abstenciones": abst, "calidad": len(empatadas) > 1,
                "texto": f"Aprobada por mayoría simple la alternativa {ganadora} ({detalle})"
                         + (" con el voto de calidad de la presidencia" if len(empatadas) > 1 else "")}
    f = sum(1 for x in votos if x["opcion"] == "favor")
    k = sum(1 for x in votos if x["opcion"] == "contra")
    ab = len(votos) - f - k
    marcador = f"{f} a favor, {k} en contra, {ab} abstenciones"
    base = {"cuenta": {"favor": f, "contra": k, "abstencion": ab}}
    propuesta_txt = v["propuesta"]
    if tipo == "consenso":
        if k == 0 and f > 0:
            unanime = ab == 0
            return {**base, "estado": "aprobado", "aprobado": True, "acuerdo": propuesta_txt, "unanime": unanime,
                    "texto": ("Aprobado por unanimidad" if unanime else "Aprobado por consenso, con abstenciones") + f" ({marcador})"}
        return {**base, "estado": "sin_consenso", "aprobado": False, "texto": f"No se alcanzó el consenso ({marcador})"}
    if f > k or (f == k and calidad == "favor" and f > 0):
        return {**base, "estado": "aprobado", "aprobado": True, "acuerdo": propuesta_txt, "calidad": f == k,
                "texto": f"Aprobado por mayoría simple ({marcador})" + (" con el voto de calidad de la presidencia" if f == k else "")}
    if f == k and calidad != "contra":
        return {**base, "estado": "empate", "aprobado": False, "empatadas": ["favor", "contra"], "texto": f"Empate ({marcador})"}
    return {**base, "estado": "rechazado", "aprobado": False, "texto": f"Rechazado ({marcador})"}


@bp.post("/api/votaciones/<int:vid>/cerrar")
def cerrar_votacion(vid):
    d = request.get_json(silent=True) or {}
    with bd.db() as c:
        v = c.execute("SELECT * FROM votaciones WHERE id=?", (vid,)).fetchone()
        if not v:
            abort(404)
        votos = c.execute("SELECT * FROM votos WHERE votacion_id=?", (vid,)).fetchall()
        res = computar(v, votos, d.get("calidad"))
        definitivo = res["estado"] != "empate"
        c.execute("UPDATE votaciones SET estado=?, resultado=? WHERE id=?",
                  ("cerrada" if definitivo else "abierta", json.dumps(res, ensure_ascii=False), vid))
        if definitivo:
            c.execute("UPDATE sesiones SET estado='abierta' WHERE id=? AND estado='votacion'", (v["sesion_id"],))
            if res.get("aprobado"):
                c.execute("UPDATE sesiones SET acuerdo=?, resultado=? WHERE id=?",
                          (res["acuerdo"], json.dumps(res, ensure_ascii=False), v["sesion_id"]))
        return jsonify(_votacion_dict(c, c.execute("SELECT * FROM votaciones WHERE id=?", (vid,)).fetchone()))


@bp.post("/api/votaciones/<int:vid>/anular")
def anular_votacion(vid):
    with bd.db() as c:
        v = c.execute("SELECT * FROM votaciones WHERE id=?", (vid,)).fetchone()
        if not v:
            abort(404)
        c.execute("UPDATE votaciones SET estado='anulada' WHERE id=? AND estado='abierta'", (vid,))
        c.execute("UPDATE sesiones SET estado='abierta' WHERE id=? AND estado='votacion'", (v["sesion_id"],))
    return "", 204


# ---- acta de cierre --------------------------------------------------------------
def _seccion(texto, nombre, siguiente):
    # el modelo a veces pone las etiquetas en negrita o como título: «**SÍNTESIS:**», «## Conclusiones»
    texto = re.sub(r"^[#*_\s]*(SÍNTESIS|SINTESIS|CONCLUSIONES)[*_\s]*:?[*_\s]*$", lambda m: m.group(1).upper() + ":",
                   texto, flags=re.M | re.I)
    m = re.search(rf"{nombre}\s*:?\s*\n(.*?)(?=\n\s*{siguiente}\s*:?\s*\n|\Z)", texto, re.S | re.I)
    return m.group(1).strip() if m else ""


def _cita(t):
    """Una línea va como cita; un texto con varios puntos se deja tal cual para que se lea como lista."""
    t = (t or "").strip()
    return f"> {t}" if "\n" not in t else t


def componer_acta(c, s, panel, cierre_ts):
    nombres = {a["id"]: a for a in panel["agentes"]}
    orden = orden_de(s, panel)
    vots = votaciones_de(c, s["id"])
    debate = transcripcion(c, s["id"], panel)
    acuerdo = s["acuerdo"]
    # síntesis y conclusiones: lo único que redacta la IA
    sintesis, conclusiones = "", ""
    if debate:
        try:
            t = _secretaria(panel, f"Asunto: {s['asunto']}\n\nTranscripción de la sesión:\n{debate}\n\n"
                            + (f"Acuerdo adoptado: {acuerdo}\n\n" if acuerdo else "No se adoptó un acuerdo formal por votación.\n\n")
                            + "Redacta para el acta, con estilo formal y en tercera persona, basándote EXCLUSIVAMENTE en la "
                              "transcripción: no inventes intervenciones, posturas ni datos, y nombra a cada experto por su nombre.\n"
                              "SÍNTESIS:\n<síntesis del debate en el orden de intervención: qué sostuvo cada experto y "
                              "en qué coincidieron o discreparon; máximo 350 palabras, en párrafos o viñetas>\n"
                              "CONCLUSIONES:\n<conclusiones principales de la sesión; máximo 120 palabras>",
                            1400, True)
            sintesis = _seccion(t, "SÍNTESIS", "CONCLUSIONES") or t.strip()
            conclusiones = _seccion(t, "CONCLUSIONES", "ZZZ")
            if sintesis == t.strip():   # sin etiquetas reconocibles: al menos que no se cuelen
                sintesis = re.sub(r"(?im)^[#*_\s]*(SÍNTESIS|CONCLUSIONES)[*_\s:]*$", "", sintesis).strip()
        except ia.IAError:
            sintesis = "\n".join(f"- {linea[:300]}" for linea in debate.splitlines() if linea.strip())[:4000]
    L = [f"# Acta de la sesión nº {s['numero']}",
         f"**{panel['nombre']}**{' · consulta individual' if s['individual'] else ''} · {_fecha(s['abierta'])} · de {_hora(s['abierta'])} a {_hora(cierre_ts)} (hora de Caracas)",
         "", "## Asunto", s["asunto"], "", "## Asistentes",
         "- **La presidencia** (consultante), que convoca y dirige la sesión."]
    L += [f"- **{nombres[i]['nombre']}**, {nombres[i]['rol'] or 'experto'}"
          + (f" — delegado del {nombres[i]['comite']}." if nombres[i].get("comite") else ".") for i in orden]
    comp = json.loads(s["composicion"] or "null")
    if comp:
        L += ["", "Comités representados: " + ", ".join(x["nombre"] for x in comp["comites"]) + "."]
    if s["limite_palabras"]:
        L += [f"Tiempo de palabra: {s['limite_palabras']} palabras por intervención."]
    L += ["", "## Orden del debate",
          "Intervenciones " + ("por turnos, en este orden:" if s["modo_debate"] == "orden" else "simultáneas; orden de referencia:")]
    L += [f"{n}. {nombres[i]['nombre']}" for n, i in enumerate(orden, 1)]
    puntos = json.loads(s["orden_dia"] or "null") or [s["asunto"]]
    varios = len(puntos) > 1
    if varios:
        L += ["", "## Orden del día"] + [f"{n}. {p}" for n, p in enumerate(puntos, 1)]
    anexos = _anexos_info(c, s)
    if anexos:
        L += ["", "## Documentos anexos"]
        L += [f"- Acta de la sesión nº {a['numero']} del {a['panel']}: {a['asunto']}" for a in anexos]
    consultas = c.execute("SELECT texto FROM mensajes WHERE sesion_id=? AND rol='user' ORDER BY id", (s["id"],)).fetchall()
    if consultas:
        L += ["", "## Consultas planteadas"]
        L += [f"{n}. {q['texto'] or '(documentos o imágenes adjuntos)'}" for n, q in enumerate(consultas, 1)]
    L += ["", "## Síntesis del debate", sintesis or "No hubo intervenciones."]
    if vots:
        L += ["", "## Deliberación y votación"]
        for v in vots:
            if v["estado"] == "anulada":
                continue
            modo = "Mayoría simple" if v["tipo"] == "mayoria" else "Acuerdo unificado (consenso)"
            sobre = f" · punto {v['punto'] + 1}" if varios else ""
            L += ["", f"### Votación {v['intento']}{sobre} · {modo}"]
            if v["alternativas"]:
                L += ["Alternativas sometidas a votación:"] + [f"- **{a['letra']})** {a['texto']}" for a in v["alternativas"]]
            else:
                L += ["Propuesta sometida a votación:", "", _cita(v["propuesta"])]
            L += ["", "Votos emitidos:"]
            for x in v["votos"]:
                quien = nombres.get(x["agente_id"], {"nombre": "Experto retirado"})["nombre"]
                op = VOTOS.get(x["opcion"], f"Alternativa {x['opcion']}")
                L.append(f"- **{quien}** — {op}. {x['motivo']}")
            if v["resultado"]:
                L += ["", f"**Resultado:** {v['resultado']['texto']}."]
    mocs = c.execute("SELECT * FROM mociones WHERE sesion_id=? ORDER BY id", (s["id"],)).fetchall()
    if mocs:
        L += ["", "## Mociones de procedimiento"]
        L += [f"- {m['detalle']}: {json.loads(m['resultado'])['texto']}." for m in mocs]
    L += ["", "## Acuerdos"]
    aprobados = {}
    for v in vots:   # el último acuerdo aprobado de cada punto
        if v["resultado"] and v["resultado"].get("aprobado"):
            aprobados[v["punto"]] = v["resultado"]["acuerdo"]
    if varios:
        for n, p in enumerate(puntos):
            L += ["", f"**Punto {n + 1}. {p}**", ""]
            L += [_cita(aprobados[n])] if n in aprobados else ["No se adoptó acuerdo formal sobre este punto."]
    elif acuerdo or aprobados:
        L += ["Por votación, el Consejo adopta el siguiente acuerdo:", "", _cita(aprobados.get(0) or acuerdo)]
    else:
        L += ["No se adoptó un acuerdo formal por votación."]
    if conclusiones:
        L += ["", "## Conclusiones", conclusiones]
    L += ["", "## Cierre",
          f"Sin más asuntos que tratar, la presidencia levanta la sesión a las {_hora(cierre_ts)} del {_fecha(cierre_ts)}. "
          "De lo tratado se extiende la presente acta.", "", "*La Secretaría del Consejo*"]
    return "\n".join(L)


@bp.post("/api/sesiones/<int:sid>/cerrar")
def cerrar(sid):
    with bd.db() as c:
        s = _sesion(c, sid)
        if s["estado"] == "cerrada":
            return jsonify(error="La sesión ya está cerrada"), 409
        panel = _app()._panel(c, s["panel_id"])
        c.execute("UPDATE votaciones SET estado='anulada' WHERE sesion_id=? AND estado='abierta'", (sid,))
    ahora = time.time()
    with bd.db() as c:   # solo lecturas: la redacción de la IA no debe retener la base de datos
        acta = componer_acta(c, s, panel, ahora)
    with bd.db() as c:
        c.execute("UPDATE sesiones SET estado='cerrada', cerrada=?, acta=? WHERE id=?", (ahora, acta, sid))
        return jsonify(sesion=sesion_dict(c, _sesion(c, sid), panel), acta=acta)


@bp.get("/api/sesiones/<int:sid>/acta.md")
def descargar(sid):
    with bd.db() as c:
        s = _sesion(c, sid)
    if not s["acta"]:
        abort(404)
    nombre = f"acta-sesion-{s['numero']}.md"
    return Response(s["acta"], mimetype="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@bp.get("/api/sesiones/<int:sid>/acta.<fmt>")
def acta_con_membrete(sid, fmt):
    """El acta de cierre en PDF o Word, con el membrete de Ajustes."""
    import membrete
    if fmt not in ("pdf", "docx"):
        abort(404)
    with bd.db() as c:
        s = _sesion(c, sid)
        p = c.execute("SELECT nombre FROM paneles WHERE id=?", (s["panel_id"],)).fetchone()
    if not s["acta"]:
        abort(404)
    datos = (membrete.pdf if fmt == "pdf" else membrete.docx)(dict(s), p["nombre"] if p else "Consejo", s["acta"])
    tipo = "application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(datos, mimetype=tipo, headers={
        "Content-Disposition": f'{"inline" if fmt == "pdf" else "attachment"}; filename="acta-sesion-{s["numero"]}.{fmt}"'})


@bp.post("/api/sesiones/<int:sid>/trasladar")
def trasladar(sid):
    """Lleva un acta a otro consejo: se anexa a su sesión abierta o abre una sesión para deliberarla."""
    destino = (request.get_json(force=True) or {}).get("panel_id")
    with bd.db() as c:
        s = _sesion(c, sid)
        if not s["acta"]:
            return jsonify(error="Esta sesión aún no tiene acta de cierre"), 409
        _app()._panel(c, destino)
        origen = c.execute("SELECT nombre FROM paneles WHERE id=?", (s["panel_id"],)).fetchone()
        r = activa(c, destino)
        if r:
            anexos = json.loads(r["anexos"] or "[]")
            if sid not in anexos:
                anexos.append(sid)
            c.execute("UPDATE sesiones SET anexos=? WHERE id=?", (json.dumps(anexos), r["id"]))
            return jsonify(panel_id=destino, sesion=sesion_dict(c, _sesion(c, r["id"])), anexada=True)
        nueva = abrir(c, destino, f"Deliberación del acta nº {s['numero']} del {origen['nombre'] if origen else 'otro consejo'}: "
                                  f"{s['asunto']}", anexos=[sid])
        return jsonify(panel_id=destino, sesion=sesion_dict(c, _sesion(c, nueva)), anexada=False), 201


# ---- herramientas parlamentarias ----------------------------------------------------
TIPOS_ORADOR = ("alusion", "pide", "orden")


def agregar_oradores(c, sid, nuevos):
    """Añade a la lista de oradores sin repetir; las cuestiones de orden pasan delante."""
    r = c.execute("SELECT oradores FROM sesiones WHERE id=?", (sid,)).fetchone()
    lista = json.loads((r and r["oradores"]) or "[]")
    for n in nuevos:
        if n.get("tipo") not in TIPOS_ORADOR or any(o["id"] == n["id"] for o in lista):
            continue
        item = {k: n.get(k) for k in ("id", "tipo", "por", "motivo") if n.get(k)}
        if n["tipo"] == "orden":
            lista.insert(sum(1 for o in lista if o["tipo"] == "orden"), item)
        else:
            lista.append(item)
    c.execute("UPDATE sesiones SET oradores=? WHERE id=?", (json.dumps(lista, ensure_ascii=False), sid))
    return lista


def quitar_orador(c, sid, aid):
    r = c.execute("SELECT oradores FROM sesiones WHERE id=?", (sid,)).fetchone()
    lista = [o for o in json.loads((r and r["oradores"]) or "[]") if o["id"] != aid]
    c.execute("UPDATE sesiones SET oradores=? WHERE id=?", (json.dumps(lista, ensure_ascii=False), sid))
    return lista


@bp.put("/api/sesiones/<int:sid>/oradores")
def fijar_oradores(sid):
    d = request.get_json(force=True)
    with bd.db() as c:
        r = _sesion(c, sid)
        ids = {a["id"] for a in _app()._panel(c, r["panel_id"])["agentes"]}
        lista = [{k: o.get(k) for k in ("id", "tipo", "por", "motivo") if o.get(k)}
                 for o in d.get("oradores") or [] if o.get("id") in ids and o.get("tipo") in TIPOS_ORADOR]
        c.execute("UPDATE sesiones SET oradores=? WHERE id=?", (json.dumps(lista, ensure_ascii=False), sid))
        return jsonify(lista)


@bp.post("/api/sesiones/<int:sid>/punto")
def cambiar_punto(sid):
    """La presidencia pasa a otro punto del orden del día."""
    d = request.get_json(force=True)
    with bd.db() as c:
        r = _sesion(c, sid)
        if r["estado"] == "cerrada":
            return jsonify(error="La sesión está cerrada"), 409
        puntos = json.loads(r["orden_dia"] or "null") or [r["asunto"]]
        n = max(0, min(len(puntos) - 1, int(d.get("punto", 0))))
        c.execute("UPDATE sesiones SET punto=?, oradores='[]' WHERE id=?", (n, sid))
        return jsonify(sesion_dict(c, _sesion(c, sid)))


@bp.post("/api/sesiones/<int:sid>/receso")
def receso(sid):
    """Cuarto intermedio: se suspenden las intervenciones hasta que la presidencia reanude."""
    activo = bool((request.get_json(force=True) or {}).get("activo"))
    with bd.db() as c:
        _sesion(c, sid)
        c.execute("UPDATE sesiones SET receso=? WHERE id=?", (int(activo), sid))
        return jsonify(sesion_dict(c, _sesion(c, sid)))


MOCIONES = {
    "cierre": "Moción de cierre del debate: dar por suficientemente debatido el punto y pasar a la votación del acuerdo",
    "siguiente": "Moción de orden: pasar al siguiente punto del orden del día",
    "limite": "Moción para limitar el tiempo de palabra a {n} palabras por intervención",
    "cuarto": "Moción de cuarto intermedio: suspender brevemente la sesión",
}


@bp.post("/api/sesiones/<int:sid>/mociones")
def mocion(sid):
    """La presidencia somete una moción de procedimiento; los delegados la votan (mayoría simple)."""
    from concurrent.futures import ThreadPoolExecutor
    d = request.get_json(force=True)
    tipo = d.get("tipo")
    if tipo not in MOCIONES:
        return jsonify(error="Moción no reconocida"), 400
    n = None
    if tipo == "limite":
        try:
            n = max(40, min(400, int(d.get("palabras") or 0)))
        except (TypeError, ValueError):
            return jsonify(error="Indique el nuevo tiempo de palabra"), 400
    texto = MOCIONES[tipo].format(n=n)
    a_mod = _app()
    with bd.db() as c:
        s = _sesion(c, sid)
        if s["estado"] == "cerrada":
            return jsonify(error="La sesión está cerrada"), 409
        panel = a_mod._panel(c, s["panel_id"])
        debate = transcripcion(c, sid, panel, 5000, s["punto"] or 0)

    def voto(a):
        uso = {}
        try:
            t = ia.llamar([{"role": "system", "content": a_mod.sistema_agente(panel, a)},
                           {"role": "user", "content": f"Debate del punto en curso (extracto):\n{debate or '(aún sin intervenciones)'}\n\n"
                            f"La presidencia somete a votación de procedimiento: «{texto}». Vota pensando en el buen "
                            "orden del debate. Responde EXACTAMENTE con una línea: «SÍ» o «NO», y un motivo de menos de 10 palabras."}],
                          temperatura=0.2, max_tokens=40, uso=uso, agente=a)
            consumo.registrar(panel["id"], a["id"], None, "mocion", uso)
        except ia.IAError:
            return {"agente_id": a["id"], "voto": "abstencion", "motivo": "No pudo votar"}
        v = t.strip().upper()
        opcion = "favor" if re.match(r"\W*S[ÍI]\b", v) else "contra" if re.match(r"\W*NO\b", v) else "abstencion"
        return {"agente_id": a["id"], "voto": opcion, "motivo": re.sub(r"^\W*(S[ÍI]|NO)\W*", "", t.strip(), flags=re.I)[:120]}

    with ThreadPoolExecutor(6) as ex:
        votos = list(ex.map(voto, panel["agentes"]))
    f = sum(1 for v in votos if v["voto"] == "favor")
    k = sum(1 for v in votos if v["voto"] == "contra")
    aprobada = f > k
    res = {"aprobada": aprobada, "favor": f, "contra": k, "abstencion": len(votos) - f - k,
           "texto": f"{'Aprobada' if aprobada else 'Rechazada'} ({f} a favor, {k} en contra, {len(votos) - f - k} abstenciones)"}
    with bd.db() as c:
        if aprobada and tipo == "limite":
            c.execute("UPDATE sesiones SET limite_palabras=? WHERE id=?", (n, sid))
        if aprobada and tipo == "siguiente":
            puntos = json.loads(s["orden_dia"] or "null") or [s["asunto"]]
            c.execute("UPDATE sesiones SET punto=?, oradores='[]' WHERE id=?", (min(len(puntos) - 1, (s["punto"] or 0) + 1), sid))
        if aprobada and tipo == "cuarto":
            c.execute("UPDATE sesiones SET receso=1 WHERE id=?", (sid,))
        c.execute("INSERT INTO mociones(sesion_id,punto,tipo,detalle,votos,resultado,ts) VALUES(?,?,?,?,?,?,?)",
                  (sid, s["punto"] or 0, tipo, texto, json.dumps(votos, ensure_ascii=False), json.dumps(res, ensure_ascii=False), time.time()))
        return jsonify(mocion=texto, resultado=res, votos=votos, sesion=sesion_dict(c, _sesion(c, sid)))
