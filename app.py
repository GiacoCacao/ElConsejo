"""El Consejo — paneles de expertos (agentes IA) que responden, dialogan y se nutren de sus pools."""
import base64
import hmac
import json
import mimetypes
import os
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import (Flask, Response, abort, jsonify, redirect, request, send_file, send_from_directory, session,
                   stream_with_context)

import bd
import config
import consumo
import copias
import fabrica
import ia
import paneles_base
import pools
import proveedores
import sesiones
import asamblea

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
app.register_blueprint(sesiones.bp)
app.register_blueprint(asamblea.bp)
app.secret_key = config.SECRETO or os.urandom(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=timedelta(days=30))

# ---- acceso --------------------------------------------------------------------
LIBRES = ("/salud", "/login", "/api/acceso")
_fallos = {}   # ip -> marcas de tiempo de intentos fallidos


def protegido():
    return bool(config.CLAVE_PRESIDENCIA)


def rol_actual():
    return session.get("rol") if protegido() else "presidencia"


@app.before_request
def proteger():
    if not protegido():
        return None
    p = request.path
    if p in LIBRES or p.startswith("/static/"):
        return None
    rol = session.get("rol")
    if not rol:
        if p.startswith(("/api/", "/img/")):
            return jsonify(error="Inicie sesión para continuar", acceso=True), 401
        return redirect("/login")
    if rol == "observador" and request.method not in ("GET", "HEAD"):
        return jsonify(error="Modo observador: solo lectura"), 403
    return None


@app.get("/login")
def pagina_login():
    if not protegido() or session.get("rol"):
        return redirect("/")
    return send_from_directory("static", "login.html")


@app.get("/api/acceso")
def ver_acceso():
    return jsonify(protegido=protegido(), rol=rol_actual(), observador=bool(config.CLAVE_OBSERVADOR))


@app.post("/api/acceso")
def entrar():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0]
    ahora = time.time()
    recientes = [t for t in _fallos.get(ip, []) if ahora - t < 600]
    if len(recientes) >= 5:
        return jsonify(error="Demasiados intentos. Espere unos minutos."), 429
    clave = (request.get_json(silent=True) or {}).get("clave", "")
    rol = None
    if config.CLAVE_PRESIDENCIA and hmac.compare_digest(clave.encode(), config.CLAVE_PRESIDENCIA.encode()):
        rol = "presidencia"
    elif config.CLAVE_OBSERVADOR and hmac.compare_digest(clave.encode(), config.CLAVE_OBSERVADOR.encode()):
        rol = "observador"
    if not rol:
        _fallos[ip] = recientes + [ahora]
        time.sleep(1)
        return jsonify(error="Clave incorrecta"), 401
    _fallos.pop(ip, None)
    session.clear()
    session.permanent = True
    session["rol"] = rol
    return jsonify(rol=rol)


@app.delete("/api/acceso")
def salir():
    session.clear()
    return "", 204


def solo_presidencia():
    if rol_actual() != "presidencia":
        abort(403)


# ---- fecha para los expertos -------------------------------------------------------
DIAS = "lunes martes miércoles jueves viernes sábado domingo".split()
MESES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()


def fecha_actual():
    d = datetime.now(ZoneInfo(config.TZ))
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}, {d:%H:%M} (hora de Caracas)"

PANEL_EJEMPLO = {
    "nombre": "Consejo de ejemplo",
    "descripcion": "Cuatro miradas distintas sobre la misma pregunta.",
    "contexto": "Sois un consejo de expertos. Respondéis en español, con criterio propio, "
                "de forma breve (máximo 120 palabras) y desde vuestra especialidad.",
    "agentes": [
        {"nombre": "Lex", "rol": "Jurista", "emoji": "", "color": "#c9a96e",
         "instrucciones": "Analizas riesgos legales, contratos y obligaciones."},
        {"nombre": "Fiona", "rol": "Finanzas", "emoji": "", "color": "#7f9cc9",
         "instrucciones": "Evalúas costes, rentabilidad y riesgo económico."},
        {"nombre": "Marco", "rol": "Estratega", "emoji": "", "color": "#8fb59a",
         "instrucciones": "Piensas en el largo plazo, alternativas y consecuencias."},
        {"nombre": "Ada", "rol": "Tecnología", "emoji": "", "color": "#c27c8e",
         "instrucciones": "Valoras la viabilidad técnica y las herramientas disponibles."},
    ],
}


# ---- paneles ---------------------------------------------------------------
def _agentes_limpios(lista, tope=12):
    out = []
    for a in lista or []:
        nombre = (a.get("nombre") or "").strip()
        if not nombre:
            continue
        out.append({
            "id": a.get("id") or uuid.uuid4().hex[:8],
            "nombre": nombre[:40],
            "rol": (a.get("rol") or "").strip()[:60],
            "emoji": (a.get("emoji") or "").strip()[:4],   # monograma; vacío = iniciales
            "color": a.get("color") or "#8b9cff",
            "instrucciones": (a.get("instrucciones") or "").strip()[:4000],
            "modelo": (a.get("modelo") or "").strip()[:120],
            "proveedor": (a.get("proveedor") or "").strip()[:12],   # vacío = la IA por defecto
            "temperatura": a.get("temperatura") if isinstance(a.get("temperatura"), (int, float)) else None,
            **({"comite": str(a["comite"])[:60], "comite_id": str(a.get("comite_id") or "")[:12]} if a.get("comite") else {}),
        })
    return out[:tope]


def _quitar_doc(c, d):
    if d["fabrica_id"]:
        fabrica.borrar(d["fabrica_id"])
    pools.borrar_capitulos(c, d["id"])
    c.execute("DELETE FROM docs WHERE id=?", (d["id"],))


def guardar_panel(c, pid, d, tope=12):
    agentes = _agentes_limpios(d.get("agentes"), tope)
    nombre = (d.get("nombre") or "Panel sin nombre").strip()[:60]
    cuerpo = json.dumps(agentes, ensure_ascii=False)
    if pid:
        vivos = {a["id"] for a in agentes}
        for doc in c.execute("SELECT * FROM docs WHERE panel_id=? AND ambito='pool'", (pid,)).fetchall():
            if doc["agente_id"] not in vivos:   # el agente ya no existe: su pool tampoco
                _quitar_doc(c, doc)
        c.execute("UPDATE paneles SET nombre=?, descripcion=?, contexto=?, agentes=? WHERE id=?",
                  (nombre, d.get("descripcion", ""), d.get("contexto", ""), cuerpo, pid))
        return pid
    pid = uuid.uuid4().hex[:8]
    orden = c.execute("SELECT COALESCE(MAX(orden),0)+1 FROM paneles").fetchone()[0]
    c.execute("INSERT INTO paneles(id,nombre,descripcion,contexto,agentes,orden) VALUES(?,?,?,?,?,?)",
              (pid, nombre, d.get("descripcion", ""), d.get("contexto", ""), cuerpo, orden))
    return pid


def panel_dict(c, r):
    p = {"id": r["id"], "nombre": r["nombre"], "descripcion": r["descripcion"],
         "contexto": r["contexto"], "agentes": json.loads(r["agentes"]), "tipo": r["tipo"]}
    ids = [a["id"] for a in p["agentes"]]
    # las bibliotecas van por experto (un delegado de la Asamblea conserva la suya)
    cuenta = {x["agente_id"]: (x["d"], x["c"]) for x in c.execute(
        f"SELECT docs.agente_id, COUNT(DISTINCT docs.id) d, COUNT(capitulos.id) c FROM docs "
        f"LEFT JOIN capitulos ON capitulos.doc_id=docs.id WHERE ambito='pool' AND docs.agente_id IN ({','.join('?' * len(ids))}) "
        f"GROUP BY docs.agente_id", ids)} if ids else {}
    for a in p["agentes"]:
        a["docs"], a["capitulos"] = cuenta.get(a["id"], (0, 0))
    return p


def _panel(c, pid):
    r = c.execute("SELECT * FROM paneles WHERE id=?", (pid,)).fetchone()
    if not r:
        abort(404)
    return panel_dict(c, r)


def msg_dict(r):
    return {"id": r["id"], "pregunta_id": r["pregunta_id"], "rol": r["rol"], "agente_id": r["agente_id"],
            "texto": r["texto"], "imagenes": json.loads(r["imagenes"] or "[]"), "error": bool(r["error"]),
            "ronda": r["ronda"] or 0, "adjuntos": json.loads(r["adjuntos"] or "[]"),
            "fuentes": json.loads(r["fuentes"] or "[]"), "ts": r["ts"], "sesion_id": r["sesion_id"],
            "destinatario": r["destinatario"], "modo": r["modo"]}


@app.get("/salud")
def salud():
    return jsonify(estado="ok", ia_configurada=ia.configurada(), modelo=config.IA_MODELO,
                   fabrica_configurada=fabrica.configurada(), acceso_protegido=protegido())


@app.get("/")
def inicio():
    return send_from_directory("static", "index.html")


@app.get("/img/<nombre>")
def imagen(nombre):
    if "/" in nombre or ".." in nombre:
        abort(404)
    return send_from_directory(config.IMG, nombre)


@app.get("/api/paneles")
def listar():
    with bd.db() as c:
        return jsonify([panel_dict(c, r) for r in c.execute("SELECT * FROM paneles ORDER BY orden")])


@app.post("/api/paneles")
def crear():
    with bd.db() as c:
        pid = guardar_panel(c, None, request.get_json(force=True))
        return jsonify(_panel(c, pid)), 201


@app.put("/api/paneles/<pid>")
def editar(pid):
    with bd.db() as c:
        _panel(c, pid)
        guardar_panel(c, pid, request.get_json(force=True))
        return jsonify(_panel(c, pid))


def _borrar_conversacion(c, pid):
    for d in c.execute("SELECT * FROM docs WHERE panel_id=? AND ambito='chat'", (pid,)).fetchall():
        _quitar_doc(c, d)
    for m in c.execute("SELECT imagenes FROM mensajes WHERE panel_id=? AND rol='user'", (pid,)).fetchall():
        for n in json.loads(m["imagenes"] or "[]"):
            try:
                os.remove(os.path.join(config.IMG, n))
            except OSError:
                pass
    c.execute("DELETE FROM mensajes WHERE panel_id=?", (pid,))


@app.delete("/api/paneles/<pid>")
def borrar(pid):
    with bd.db() as c:
        if _panel(c, pid).get("tipo") == "asamblea":
            return jsonify(error="La Asamblea General no se puede eliminar"), 400
        _borrar_conversacion(c, pid)
        # las sesiones con acta se conservan (pueden estar anexadas en otros consejos); el resto se borra
        for s in c.execute("SELECT id FROM sesiones WHERE panel_id=? AND acta IS NULL", (pid,)).fetchall():
            sesiones.borrar_sesion(c, s["id"])
        for d in c.execute("SELECT * FROM docs WHERE panel_id=?", (pid,)).fetchall():
            _quitar_doc(c, d)
        c.execute("DELETE FROM paneles WHERE id=?", (pid,))
    return "", 204


# ---- conversación ----------------------------------------------------------
@app.get("/api/paneles/<pid>/mensajes")
def mensajes(pid):
    with bd.db() as c:
        return jsonify([msg_dict(r) for r in c.execute(
            "SELECT * FROM mensajes WHERE panel_id=? ORDER BY id", (pid,))])


@app.delete("/api/paneles/<pid>/mensajes")
def vaciar(pid):
    with bd.db() as c:
        _borrar_conversacion(c, pid)
    return "", 204


@app.post("/api/paneles/<pid>/preguntas")
def preguntar(pid):
    """Una pregunta con imágenes (las ven los modelos) y documentos (la fábrica extrae su texto)."""
    texto = (request.form.get("texto") or "").strip()
    destinatario = (request.form.get("destinatario") or "").strip() or None
    with bd.db() as c:
        if destinatario and destinatario not in {a["id"] for a in _panel(c, pid)["agentes"]}:
            return jsonify(error="Ese experto no está en este consejo"), 400
    imagenes, documentos = [], []
    for f in request.files.getlist("imagenes"):
        ext = os.path.splitext(f.filename or "")[1].lower()
        datos = f.read()
        if ext in config.EXT_IMG:
            if len(datos) > config.MAX_IMG:
                return jsonify(error=f"{f.filename} supera 8 MB"), 400
            n = uuid.uuid4().hex + ext
            with open(os.path.join(config.IMG, n), "wb") as fh:
                fh.write(datos)
            imagenes.append(n)
        elif ext in config.EXT_DOC:
            if len(datos) > config.MAX_DOC:
                return jsonify(error=f"{f.filename} supera 50 MB"), 400
            documentos.append((f.filename, datos))
        else:
            return jsonify(error=f"Formato no admitido: {f.filename}"), 400
    if not texto and not imagenes and not documentos:
        return jsonify(error="Escribe una pregunta o adjunta algo"), 400

    adjuntos = []   # documentos del chat: la fábrica extrae el texto; se guarda para esta pregunta
    try:
        for nombre, datos in documentos:
            fid = fabrica.subir(nombre, datos, ["elconsejo", "chat"])
            did = uuid.uuid4().hex[:10]
            try:
                fabrica.esperar(fid, 150)
                t = fabrica.texto(fid)
            except Exception:
                fabrica.borrar(fid)
                raise
            if not t.strip():
                fabrica.borrar(fid)
                raise fabrica.FabricaError(f"No se encontró texto en {nombre}")
            with bd.db() as c:
                c.execute("INSERT INTO docs(id,panel_id,ambito,nombre,fabrica_id,estado,caracteres,texto,ts) "
                          "VALUES(?,?,?,?,?,?,?,?,?)", (did, pid, "chat", nombre, fid, "listo", len(t), t, time.time()))
            adjuntos.append({"id": did, "nombre": nombre, "caracteres": len(t)})
    except fabrica.FabricaError as e:
        with bd.db() as c:
            for a in adjuntos:
                _quitar_doc(c, c.execute("SELECT * FROM docs WHERE id=?", (a["id"],)).fetchone())
        for n in imagenes:
            os.remove(os.path.join(config.IMG, n))
        return jsonify(error=str(e)), 502
    with bd.db() as c:
        s = sesiones.activa(c, pid)   # sin sesión abierta, consultar abre una con la pregunta como asunto
        sid = s["id"] if s else sesiones.abrir(c, pid, texto[:120] or (adjuntos[0]["nombre"] if adjuntos else "Consulta al Consejo"))
        cur = c.execute("INSERT INTO mensajes(panel_id,rol,texto,imagenes,adjuntos,ronda,ts,sesion_id,destinatario) "
                        "VALUES(?,?,?,?,?,0,?,?,?)",
                        (pid, "user", texto, json.dumps(imagenes), json.dumps(adjuntos), time.time(), sid, destinatario))
        qid = cur.lastrowid
        c.execute("UPDATE mensajes SET pregunta_id=id WHERE id=?", (qid,))
        for a in adjuntos:
            c.execute("UPDATE docs SET pregunta_id=? WHERE id=?", (qid, a["id"]))
        return jsonify(msg_dict(c.execute("SELECT * FROM mensajes WHERE id=?", (qid,)).fetchone())), 201


def _contenido_usuario(c, q, pregunta_actual):
    """Texto (+ documentos adjuntos) y/o imágenes del mensaje de usuario `q`."""
    texto = q["texto"]
    docs = c.execute("SELECT * FROM docs WHERE pregunta_id=? AND ambito='chat' ORDER BY ts", (q["id"],)).fetchall()
    imagenes = json.loads(q["imagenes"] or "[]")
    if not pregunta_actual:   # del pasado solo queda constancia, no el contenido
        extra = [d["nombre"] for d in docs] + (["imagen adjunta"] if imagenes else [])
        return texto + (f" [adjuntos: {', '.join(extra)}]" if extra else "")
    for d in docs:
        texto += f"\n\n--- Documento adjunto: {d['nombre']} ---\n{pools.contexto_chat(d, q['texto'])}"
    if not imagenes:
        return texto
    partes = [{"type": "text", "text": texto or "Analiza la(s) imagen(es) adjunta(s)."}]
    for n in imagenes:
        ruta = os.path.join(config.IMG, n)
        if os.path.exists(ruta):
            mime = mimetypes.guess_type(ruta)[0] or "image/png"
            b64 = base64.b64encode(open(ruta, "rb").read()).decode()
            partes.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    return partes


AVISO_FECHA = ("Tus conocimientos tienen una fecha de corte anterior a hoy: si la respuesta depende de normas, "
               "precios, tipos de cambio, cargos o hechos recientes que puedan haber cambiado, adviértelo y recomienda "
               "verificarlo en fuentes oficiales actuales.")


def sistema_agente(panel, agente):
    return (f"{panel['contexto']}\n\nTe llamas {agente['nombre']}"
            + (f" y eres {agente['rol']}" if agente["rol"] else "") + ".\n" + agente["instrucciones"]
            + f"\n\nHoy es {fecha_actual()}. {AVISO_FECHA}").strip()


def _mensajes_ia(c, panel, agente, qid, ronda, modo=None, por=None):
    q = c.execute("SELECT * FROM mensajes WHERE id=?", (qid,)).fetchone()
    ses = c.execute("SELECT * FROM sesiones WHERE id=?", (q["sesion_id"],)).fetchone() if q["sesion_id"] else None
    cono, fuentes = pools.conocimiento(agente["id"], q["texto"] or " ".join(
        d["nombre"] for d in c.execute("SELECT nombre FROM docs WHERE pregunta_id=?", (qid,))))
    sistema = sistema_agente(panel, agente)
    if ses:
        sistema += f"\n\nEstás en la sesión nº {ses['numero']} del Consejo. Asunto: {ses['asunto']}."
        if ses["limite_palabras"]:
            sistema += (f" Tu tiempo de palabra es de {ses['limite_palabras']} palabras como máximo por intervención: "
                        "respétalo, como en un parlamento.")
        anexos = sesiones.texto_anexos(c, ses)
        if anexos:
            sistema += ("\n\nSe han anexado a esta sesión actas de otras sesiones o consejos. Tenlas en cuenta y "
                        "cítalas cuando sean pertinentes:\n\n" + anexos)
    if cono:
        sistema += ("\n\nTienes una biblioteca propia. Estos son los pasajes más pertinentes para la pregunta; "
                    "úsalos cuando aporten y di de qué documento y capítulo sacas cada dato. Si no vienen al caso, "
                    "ignóralos:\n\n" + cono)
    msgs = [{"role": "system", "content": sistema.strip()}]

    if ses:   # cada sesión es un asunto: el historial no sale de ella
        previos = c.execute("SELECT * FROM mensajes WHERE sesion_id=? AND pregunta_id<? ORDER BY id",
                            (ses["id"], qid)).fetchall()
    else:
        previos = c.execute("SELECT * FROM mensajes WHERE panel_id=? AND pregunta_id<? ORDER BY id",
                            (panel["id"], qid)).fetchall()
    ultimas = {}   # por pregunta, la última ronda de ESTE agente (su postura final)
    for m in previos:
        if m["rol"] == "agent" and m["agente_id"] == agente["id"] and not m["error"]:
            if m["pregunta_id"] not in ultimas or (m["ronda"] or 0) >= (ultimas[m["pregunta_id"]]["ronda"] or 0):
                ultimas[m["pregunta_id"]] = m
    # las consultas individuales a otro experto no forman parte de lo que este ha oído
    usuarios = [m for m in previos if m["rol"] == "user" and m["destinatario"] in (None, agente["id"])][-config.HISTORIAL:]
    for u in usuarios:
        msgs.append({"role": "user", "content": _contenido_usuario(c, u, False)})
        if u["id"] in ultimas:
            msgs.append({"role": "assistant", "content": ultimas[u["id"]]["texto"]})
    msgs.append({"role": "user", "content": _contenido_usuario(c, q, True)})

    # debate por turnos: quien habla después oye a quienes ya intervinieron en esta misma ronda
    previos_turno = []
    if ses and ses["modo_debate"] == "orden":
        orden = sesiones._orden(json.loads(ses["orden"] or "[]"), panel)
        nombres = {a["id"]: a for a in panel["agentes"]}
        for aid in orden[:orden.index(agente["id"])] if agente["id"] in orden else []:
            m = c.execute("SELECT texto FROM mensajes WHERE pregunta_id=? AND rol='agent' AND agente_id=? AND ronda=? "
                          "AND error=0", (qid, aid, ronda)).fetchone()
            if m:
                previos_turno.append(f"**{nombres[aid]['nombre']}** ({nombres[aid]['rol'] or 'experto'}): {m['texto']}")
    if ronda == 0 and previos_turno:
        msgs[-1] = {"role": "user", "content": msgs[-1]["content"] if isinstance(msgs[-1]["content"], list) else
                    msgs[-1]["content"] + "\n\n---\nEn el orden del debate ya han intervenido:\n\n" + "\n\n".join(previos_turno)
                    + "\n\nAporta tu visión sin repetir lo ya dicho; puedes apoyarte en ellos o rebatirlos."}
        if isinstance(msgs[-1]["content"], list):   # con imágenes, el texto va en la primera parte
            msgs[-1]["content"][0]["text"] += ("\n\n---\nEn el orden del debate ya han intervenido:\n\n"
                                               + "\n\n".join(previos_turno) + "\n\nAporta tu visión sin repetir lo ya dicho.")

    if modo and ses:   # turno de palabra concedido por la presidencia (Asamblea)
        aludido_por = next((x for x in panel["agentes"] if x["id"] == por), None)
        motivo = (f" por alusiones: {aludido_por['nombre']} se ha referido a ti o a tu comité"
                  if modo == "alusion" and aludido_por else "")
        msgs.append({"role": "user", "content":
                     f"Transcripción del debate hasta ahora:\n\n{sesiones.transcripcion(c, ses['id'], panel, 14000)}\n\n"
                     f"La presidencia te concede la palabra{motivo}. Dirígete a la presidencia y a la Asamblea; responde "
                     "a lo que te concierna, aporta argumentos nuevos y no repitas lo ya dicho por ti ni por otros."})
        return msgs, fuentes

    if ronda > 0:
        propia = c.execute("SELECT texto FROM mensajes WHERE pregunta_id=? AND rol='agent' AND agente_id=? "
                           "AND ronda=? AND error=0", (qid, agente["id"], ronda - 1)).fetchone()
        if propia:
            msgs.append({"role": "assistant", "content": propia["texto"]})
        otros = []
        for a in panel["agentes"]:
            if a["id"] == agente["id"]:
                continue
            m = c.execute("SELECT texto FROM mensajes WHERE pregunta_id=? AND rol='agent' AND agente_id=? "
                          "AND ronda=? AND error=0", (qid, a["id"], ronda - 1)).fetchone()
            if m:
                otros.append(f"**{a['nombre']}** ({a['rol'] or 'experto'}): {m['texto']}")
        if previos_turno:
            otros.append("En esta ronda de réplicas ya han hablado antes que tú:\n\n" + "\n\n".join(previos_turno))
        msgs.append({"role": "user", "content":
                     "Esto han respondido tus colegas del consejo:\n\n" + "\n\n".join(otros) +
                     "\n\nRéplica brevemente (máximo 90 palabras): en qué coincides, en qué discrepas y cuál es "
                     "tu posición final. Si no tienes nada que añadir, dilo en una frase."})
    return msgs, fuentes


MODOS = ("palabra", "alusion")


def _preparar(qid, aid, ronda, modo=None, por=None):
    """Lo necesario para que un experto intervenga. `modo`: turno de palabra concedido en la Asamblea."""
    with bd.db() as c:
        q = c.execute("SELECT * FROM mensajes WHERE id=? AND rol='user'", (qid,)).fetchone()
        if not q:
            abort(404)
        panel = _panel(c, q["panel_id"])
        agente = next((a for a in panel["agentes"] if a["id"] == aid), None)
        if not agente:
            abort(404)
        ses = c.execute("SELECT * FROM sesiones WHERE id=?", (q["sesion_id"],)).fetchone() if q["sesion_id"] else None
        if modo:   # cada turno de palabra es una «ronda» nueva, para conservar el orden de intervención
            ronda = (c.execute("SELECT COALESCE(MAX(ronda),0) FROM mensajes WHERE pregunta_id=?", (qid,)).fetchone()[0] or 0) + 1
        limite = ses["limite_palabras"] if ses and ses["limite_palabras"] else None
        tokens = int(limite * 2.2) + 80 if limite else (400 if ronda and not modo else 800)
        p = {"panel": panel, "agente": agente, "q": q, "ronda": ronda, "modo": modo, "tokens": tokens,
             "msgs": None, "fuentes": [], "error": None}
        try:
            p["msgs"], p["fuentes"] = _mensajes_ia(c, panel, agente, qid, ronda, modo, por)
        except Exception as e:  # noqa: BLE001
            p["error"] = f"No se pudo preparar la consulta: {e}"[:400]
        return p


def _guardar(p, texto, error):
    with bd.db() as c:
        cur = c.execute("INSERT INTO mensajes(panel_id,pregunta_id,rol,agente_id,texto,error,ronda,fuentes,ts,sesion_id,modo)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (p["panel"]["id"], p["q"]["id"], "agent", p["agente"]["id"], texto, int(error), p["ronda"],
                         json.dumps(p["fuentes"], ensure_ascii=False), time.time(), p["q"]["sesion_id"], p["modo"]))
        return msg_dict(c.execute("SELECT * FROM mensajes WHERE id=?", (cur.lastrowid,)).fetchone())


def _ronda():
    return max(0, min(config.MAX_RONDAS, request.args.get("ronda", 0, type=int)))


def _modo():
    m = request.args.get("modo")
    return (m if m in MODOS else None), (request.args.get("por") or None)


REF_COMITE = r"(?:comit[ée]s?|panel(?:es)?|comisi[óo]n|delegaci[óo]n|delegad[oa]s?|bancada|representaci[óo]n|colegas?)\s+(?:de\s+la\s+|de\s+|del\s+)?"


def alusiones(panel, aid, texto):
    """Delegados aludidos: por su nombre o apellido, o cuando se nombra a su comité como tal
    («el comité jurídico», «la delegación financiera»). El nombre del comité suelto no cuenta: «financiero» o
    «técnico» son adjetivos corrientes y darían falsas alusiones."""
    import re
    t = texto.lower()
    out = []
    for a in panel["agentes"]:
        if a["id"] == aid:
            continue
        palabras = [w for w in re.split(r"\s+", a["nombre"]) if not w.endswith(".")]
        claves = {a["nombre"].lower()} | {w.lower() for w in palabras[-1:] if len(w) >= 4}
        if len(palabras) == 1 and len(palabras[0]) >= 3:
            claves.add(palabras[0].lower())
        hit = any(k and re.search(rf"(?<!\w){re.escape(k)}(?!\w)", t) for k in claves)
        corto = re.sub(r"^(panel|consejo|comité)\s+(de\s+|del\s+)?", "", (a.get("comite") or "").lower()).strip()
        if not hit and corto:
            raiz = re.sub(r"(os|as|o|a|es|e)$", "", corto.split()[0]) if len(corto.split()[0]) > 5 else corto.split()[0]
            hit = bool(re.search(rf"(?<!\w){REF_COMITE}{re.escape(raiz)}\w{{0,4}}(?!\w)", t))
        if hit:
            out.append(a["id"])
    return out


@app.post("/api/preguntas/<int:qid>/agentes/<aid>")
def responder(qid, aid):
    p = _preparar(qid, aid, _ronda(), *_modo())
    texto, error = p["error"] or "", bool(p["error"])
    if not error:
        uso = {}
        a = p["agente"]
        try:
            texto = ia.llamar(p["msgs"], modelo=a["modelo"], temperatura=a["temperatura"], max_tokens=p["tokens"],
                              uso=uso, agente=a)
            consumo.registrar(p["panel"]["id"], aid, qid, "replica" if p["ronda"] else "respuesta", uso)
        except Exception as e:  # noqa: BLE001 — se muestra al usuario en la burbuja
            error, texto = True, str(e)[:400]
    m = _guardar(p, texto, error)
    m["alusiones"] = [] if error else alusiones(p["panel"], aid, texto)
    return jsonify(m)


def _linea(**d):
    return json.dumps(d, ensure_ascii=False) + "\n"


def flujo_ndjson(gen):
    """Respuesta que se va enviando por líneas JSON: {"t":"d","x":trozo} … {"t":"fin",…}."""
    return Response(stream_with_context(gen), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/preguntas/<int:qid>/agentes/<aid>/flujo")
def responder_flujo(qid, aid):
    """Como `responder`, pero el texto llega mientras el experto lo escribe."""
    p = _preparar(qid, aid, _ronda(), *_modo())
    a = p["agente"]

    def gen():
        if p["error"]:
            yield _linea(t="fin", m=_guardar(p, p["error"], True), alusiones=[])
            return
        partes, uso, fallo = [], {}, None
        try:
            for x in ia.llamar_flujo(p["msgs"], modelo=a["modelo"], temperatura=a["temperatura"],
                                     max_tokens=p["tokens"], uso=uso, agente=a):
                partes.append(x)
                yield _linea(t="d", x=x)
            consumo.registrar(p["panel"]["id"], aid, qid, "replica" if p["ronda"] else "respuesta", uso)
        except Exception as e:  # noqa: BLE001
            fallo = str(e)[:400]
        texto = "".join(partes).strip()
        if fallo and texto:   # se cortó a mitad: se guarda lo dicho y se avisa
            texto += f"\n\n*(Intervención interrumpida: {fallo})*"
        m = _guardar(p, texto or fallo or "(sin respuesta)", bool(fallo) and not partes)
        yield _linea(t="fin", m=m, alusiones=alusiones(p["panel"], aid, texto) if texto else [])
    return flujo_ndjson(gen())


@app.post("/api/preguntas/<int:qid>/solicitudes")
def solicitudes(qid):
    """Turno de solicitudes: cada delegado decide (en una línea) si pide la palabra y para qué."""
    from concurrent.futures import ThreadPoolExecutor
    excluir = set(request.args.getlist("excluir"))
    with bd.db() as c:
        q = c.execute("SELECT * FROM mensajes WHERE id=? AND rol='user'", (qid,)).fetchone()
        if not q:
            abort(404)
        panel = _panel(c, q["panel_id"])
        debate = sesiones.transcripcion(c, q["sesion_id"], panel, 9000) if q["sesion_id"] else ""
    if not debate:
        return jsonify(error="Aún no hay debate"), 400

    def uno(a):
        uso = {}
        try:
            t = ia.llamar([{"role": "system", "content": sistema_agente(panel, a)},
                           {"role": "user", "content": f"Debate hasta ahora:\n{debate}\n\nLa presidencia abre el turno de "
                            "solicitudes de palabra. Pide la palabra SOLO si tienes algo nuevo y relevante que aportar, "
                            "rebatir o aclarar. Responde EXACTAMENTE con una línea: «SÍ: <motivo en menos de 10 palabras>» "
                            "o «NO»."}], temperatura=0.3, max_tokens=40, uso=uso, agente=a)
            consumo.registrar(panel["id"], a["id"], qid, "solicitud", uso)
        except Exception:  # noqa: BLE001 — quien no responde, no pide la palabra
            return None
        import re
        m = re.match(r"\W*S[ÍI]\b\W*(.*)", t.strip(), re.I)
        return {"agente_id": a["id"], "motivo": m.group(1).strip()[:120]} if m else None

    candidatos = [a for a in panel["agentes"] if a["id"] not in excluir]
    with ThreadPoolExecutor(6) as ex:
        piden = [x for x in ex.map(uno, candidatos) if x]
    return jsonify(piden)


# ---- consultor general (fuera del hemiciclo) ----------------------------------------
SISTEMA_CONSULTOR = (
    "Eres el Consultor General del Consejo: un asesor interno, neutral y erudito, que no forma parte del "
    "debate. Aclaras el significado de palabras, conceptos, siglas, términos técnicos o jurídicos, nombres y "
    "referencias que aparecen en las deliberaciones. No opinas sobre el asunto que se debate ni recomiendas "
    "decisiones. Respondes en español, en un máximo de 160 palabras, con este orden:\n"
    "**Definición:** … (si es ambiguo, las acepciones principales)\n"
    "**En este contexto:** … (solo si se te da un pasaje o un asunto)\n"
    "**Ejemplo:** …\n**Relacionados:** 2 a 4 términos.\n"
    "Si no conoces el término con certeza o puede haber cambiado (normas, cifras, cargos), dilo con claridad.")


@app.post("/api/consultor")
def consultor():
    d = request.get_json(force=True)
    pregunta = (d.get("pregunta") or "").strip()[:500]
    if not pregunta:
        return jsonify(error="Escriba la palabra o el concepto que quiere aclarar"), 400
    contexto = (d.get("contexto") or "").strip()[:1200]
    panel = sesion_r = None
    if d.get("panel_id"):
        with bd.db() as c:
            r = c.execute("SELECT * FROM paneles WHERE id=?", (d["panel_id"],)).fetchone()
            panel = panel_dict(c, r) if r else None
            sesion_r = sesiones.activa(c, panel["id"]) if panel else None
    datos = []
    if panel:
        datos.append(f"Consejo: {panel['nombre']}")
    if sesion_r:
        datos.append(f"Asunto de la sesión: {sesion_r['asunto']}")
    if contexto:
        datos.append(f"Pasaje donde aparece: «{contexto}»")
    msgs = [{"role": "system", "content": f"{SISTEMA_CONSULTOR}\n\nHoy es {fecha_actual()}."},
            {"role": "user", "content": ("\n".join(datos) + "\n\n" if datos else "") + f"Consulta: {pregunta}"}]

    def gen():
        partes, uso, fallo = [], {}, None
        try:
            for x in ia.llamar_flujo(msgs, temperatura=0.3, max_tokens=450, uso=uso):
                partes.append(x)
                yield _linea(t="d", x=x)
            consumo.registrar(panel["id"] if panel else None, None, None, "consultor", uso)
        except Exception as e:  # noqa: BLE001
            fallo = str(e)[:400]
        yield _linea(t="fin", texto="".join(partes).strip(), error=fallo if not partes else None)
    return flujo_ndjson(gen())


# ---- proveedores de IA ------------------------------------------------------------
@app.get("/api/proveedores")
def ver_proveedores():
    return jsonify(proveedores=proveedores.listar(), plantillas=proveedores.PLANTILLAS,
                   defecto={"url": config.IA_URL, "modelo": config.IA_MODELO})


@app.post("/api/proveedores")
@app.put("/api/proveedores/<prid>")
def guardar_proveedor(prid=None):
    solo_presidencia()
    try:
        return jsonify(proveedores.guardar(request.get_json(force=True), prid)), 200 if prid else 201
    except (ValueError, LookupError) as e:
        return jsonify(error=str(e)), 400


@app.delete("/api/proveedores/<prid>")
def borrar_proveedor(prid):
    solo_presidencia()
    with bd.db() as c:
        usan = [f"{a['nombre']} ({p['nombre']})" for p in (panel_dict(c, r) for r in c.execute("SELECT * FROM paneles"))
                for a in p["agentes"] if a.get("proveedor") == prid]
    if usan:
        return jsonify(error="Lo usan estos expertos; cámbielos antes: " + ", ".join(usan[:8])), 409
    proveedores.borrar(prid)
    return "", 204


@app.post("/api/proveedores/<prid>/probar")
def probar_proveedor(prid):
    solo_presidencia()
    try:
        return jsonify(modelos=proveedores.probar(prid))
    except Exception as e:  # noqa: BLE001
        return jsonify(error=str(e)[:300]), 502


# ---- ajustes: tope de gasto y copias de seguridad --------------------------------
@app.get("/api/ajustes")
def ver_ajustes():
    return jsonify(gasto=consumo.estado_gasto(), copias=copias.listar(), copias_guardar=config.COPIAS_GUARDAR,
                   rol=rol_actual(), protegido=protegido(), observador=bool(config.CLAVE_OBSERVADOR))


@app.put("/api/ajustes/gasto")
def fijar_gasto():
    solo_presidencia()
    d = request.get_json(force=True)
    for k in ("diario", "mensual"):
        v = d.get(k)
        if v in (None, ""):
            bd.fijar_ajuste(f"limite_{k}", None)
            continue
        try:
            v = float(str(v).replace(",", "."))
        except ValueError:
            return jsonify(error=f"Tope {k} no válido"), 400
        if v < 0:
            return jsonify(error="El tope no puede ser negativo"), 400
        bd.fijar_ajuste(f"limite_{k}", v)
    bd.fijar_ajuste("limite_modo", "bloquear" if d.get("modo") == "bloquear" else "avisar")
    return jsonify(consumo.estado_gasto())


@app.post("/api/copias")
def copia_ahora():
    solo_presidencia()
    return jsonify(nombre=copias.hacer(), copias=copias.listar()), 201


@app.get("/api/copias/<nombre>")
def bajar_copia(nombre):
    solo_presidencia()
    p = copias.ruta(nombre)
    if not p:
        abort(404)
    return send_file(p, as_attachment=True, download_name=nombre)


# ---- consumo y tarifas -----------------------------------------------------
@app.get("/api/paneles/<pid>/consumo")
def ver_consumo(pid):
    with bd.db() as c:
        panel = _panel(c, pid)
    return jsonify(consumo.resumen(panel))


@app.get("/api/tarifas")
def ver_tarifas():
    with bd.db() as c:
        return jsonify(tarifas=list(consumo.tarifas(c).values()), fuente=consumo.FUENTE, modelo=config.IA_MODELO)


@app.put("/api/tarifas/<path:modelo>")
def guardar_tarifa(modelo):
    modelo = modelo.strip()[:80]
    try:
        t = consumo.tarifa_valida(request.get_json(force=True))
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400
    with bd.db() as c:
        c.execute(f"INSERT OR REPLACE INTO tarifas(modelo,{','.join(consumo.CAMPOS)}) VALUES(?,{','.join('?' * len(consumo.CAMPOS))})",
                  (modelo, *[t[k] for k in consumo.CAMPOS]))
    return jsonify(ok=True)


@app.delete("/api/tarifas/<path:modelo>")
def borrar_tarifa(modelo):
    with bd.db() as c:
        c.execute("DELETE FROM tarifas WHERE modelo=?", (modelo,))
    return "", 204


# ---- pools por agente ------------------------------------------------------
def _doc_dict(r):
    return {"id": r["id"], "nombre": r["nombre"], "estado": r["estado"], "paso": r["paso"],
            "error": r["error"], "caracteres": r["caracteres"], "capitulos": r["n"]}


@app.get("/api/paneles/<pid>/pools")
def ver_pools(pid):
    with bd.db() as c:
        _panel(c, pid)
        out = {}
        for r in c.execute("SELECT d.*, (SELECT COUNT(*) FROM capitulos WHERE doc_id=d.id) n FROM docs d "
                           "WHERE panel_id=? AND ambito='pool' ORDER BY ts", (pid,)):
            out.setdefault(r["agente_id"], []).append(_doc_dict(r))
        return jsonify(out)


@app.post("/api/paneles/<pid>/agentes/<aid>/docs")
def subir_al_pool(pid, aid):
    with bd.db() as c:
        if aid not in {a["id"] for a in _panel(c, pid)["agentes"]}:
            abort(404)
    if not fabrica.configurada():
        return jsonify(error="Falta CONSEJO_FABRICA_URL en el .env: sin la fábrica no se pueden procesar documentos."), 503
    nuevos = []
    for f in request.files.getlist("archivos"):
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in config.EXT_DOC:
            return jsonify(error=f"Formato no admitido: {f.filename} (PDF, DOCX, TXT, MD, ODT o RTF)"), 400
        datos = f.read()
        if len(datos) > config.MAX_DOC:
            return jsonify(error=f"{f.filename} supera 50 MB"), 400
        did = uuid.uuid4().hex[:10]
        with bd.db() as c:
            c.execute("INSERT INTO docs(id,panel_id,agente_id,ambito,nombre,estado,paso,ts) VALUES(?,?,?,?,?,?,?,?)",
                      (did, pid, aid, "pool", f.filename, "subiendo", "En cola", time.time()))
        pools.lanzar(did, datos)
        nuevos.append(did)
    return jsonify(nuevos), 202


def _doc(c, did):
    d = c.execute("SELECT * FROM docs WHERE id=? AND ambito='pool'", (did,)).fetchone()
    if not d:
        abort(404)
    return d


@app.get("/api/docs/<did>/capitulos")
def capitulos(did):
    with bd.db() as c:
        d = _doc(c, did)
        rows = c.execute("SELECT id, orden, titulo, resumen, claves, simplificado, LENGTH(texto) n "
                         "FROM capitulos WHERE doc_id=? ORDER BY orden", (did,)).fetchall()
        return jsonify(doc=d["nombre"], capitulos=[dict(r) for r in rows])


@app.get("/api/capitulos/<int:cid>")
def capitulo(cid):
    with bd.db() as c:
        r = c.execute("SELECT * FROM capitulos WHERE id=?", (cid,)).fetchone()
        if not r:
            abort(404)
        return jsonify(dict(r))


@app.delete("/api/docs/<did>")
def borrar_doc(did):
    with bd.db() as c:
        _quitar_doc(c, _doc(c, did))
    return "", 204


@app.post("/api/docs/<did>/reprocesar")
def reprocesar(did):
    with bd.db() as c:
        d = _doc(c, did)
        if d["estado"] not in ("listo", "error"):
            return jsonify(error="Ya se está procesando"), 409
        c.execute("UPDATE docs SET estado='subiendo', paso='En cola', error=NULL WHERE id=?", (did,))
    pools.lanzar(did)
    return "", 202


def arrancar():
    bd.init()
    with bd.db() as c:
        if not c.execute("SELECT 1 FROM paneles").fetchone():
            guardar_panel(c, None, PANEL_EJEMPLO)
        for p in paneles_base.PANELES:   # una sola vez: si el usuario lo borra, no vuelve
            if not c.execute("SELECT 1 FROM semillas WHERE nombre=?", (p["nombre"],)).fetchone():
                if not c.execute("SELECT 1 FROM paneles WHERE nombre=?", (p["nombre"],)).fetchone():
                    guardar_panel(c, None, p)
                c.execute("INSERT INTO semillas VALUES(?)", (p["nombre"],))
    with bd.db() as c:
        asamblea.panel_id(c)
    if not os.environ.get("CONSEJO_SIN_COPIAS"):
        copias.arrancar()


arrancar()
