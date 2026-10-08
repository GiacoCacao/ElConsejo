import json

import ia


def _panel(c, nombre="Consejo de ejemplo"):
    return next(p for p in c.get("/api/paneles").get_json() if p["nombre"] == nombre)


def _lineas(r):
    return [json.loads(x) for x in r.data.decode().splitlines() if x.strip()]


def test_respuesta_en_tiempo_real(cliente, falsos):
    p = _panel(cliente)
    q = cliente.post(f"/api/paneles/{p['id']}/preguntas", data={"texto": "¿Flujo?"},
                     content_type="multipart/form-data").get_json()
    a = p["agentes"][1]
    r = cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{a['id']}/flujo")
    assert r.mimetype == "application/x-ndjson"
    ev = _lineas(r)
    trozos = [e["x"] for e in ev if e["t"] == "d"]
    fin = ev[-1]
    assert len(trozos) > 1 and fin["t"] == "fin"
    assert fin["m"]["texto"] == "".join(trozos) == f"Respuesta de {a['nombre']}"
    assert fin["m"]["sesion_id"] == q["sesion_id"] and not fin["m"]["error"]
    est = cliente.get(f"/api/paneles/{p['id']}/sesion").get_json()
    assert any(m["rol"] == "agent" and m["agente_id"] == a["id"] for m in est["mensajes"])


def test_corte_a_mitad_conserva_lo_dicho(cliente, falsos, monkeypatch):
    def cortada(*a, **k):
        yield "Empiezo a responder"
        raise ia.IAError("conexión perdida")
    monkeypatch.setattr(ia, "llamar_flujo", cortada)
    p = _panel(cliente)
    q = cliente.post(f"/api/paneles/{p['id']}/preguntas", data={"texto": "¿Corte?"},
                     content_type="multipart/form-data").get_json()
    fin = _lineas(cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{p['agentes'][0]['id']}/flujo"))[-1]
    assert fin["m"]["texto"].startswith("Empiezo a responder") and "interrumpida" in fin["m"]["texto"]


def test_consultor_general(cliente, falsos):
    llamadas, _ = falsos
    p = _panel(cliente)
    r = cliente.post("/api/consultor", json={"pregunta": "¿Qué significa «due diligence»?",
                                            "contexto": "condicionado a la due diligence", "panel_id": p["id"]})
    ev = _lineas(r)
    assert ev[-1]["t"] == "fin" and ev[-1]["error"] is None
    sistema, usuario = llamadas[-1][0]["content"], llamadas[-1][1]["content"]
    assert "Asistente de El Consejo" in sistema and "Hoy es" in sistema
    assert "GUÍA DE EL CONSEJO" in sistema and "Panel Jurídico" in sistema   # sabe cómo funciona y qué paneles hay
    assert "due diligence" in usuario and "Consejo de ejemplo" in usuario and "Pasaje" in usuario
    assert cliente.post("/api/consultor", json={"pregunta": " "}).status_code == 400


def test_asistente_ordena_el_planteamiento(cliente, falsos):
    llamadas, _ = falsos
    r = cliente.post("/api/asistente", json={"pregunta": "quiero ver lo de la sucursal en valencia", "modo": "ordenar",
                                             "ambiente": "menú principal"})
    ev = _lineas(r)
    assert '"paneles": ["Panel Empresarial"]' in ev[-1]["texto"]
    assert "Ordena este planteamiento" in llamadas[-1][1]["content"] and "Planteamiento: quiero ver" in llamadas[-1][1]["content"]


def test_consulta_individual_con_su_propia_sesion(cliente, falsos):
    p = _panel(cliente, "Panel Financiero")
    s = cliente.get(f"/api/paneles/{p['id']}/sesion").get_json()["sesion"]
    if s:
        cliente.post(f"/api/sesiones/{s['id']}/cerrar")
    # sesión de grupo abierta en el panel
    g = cliente.post(f"/api/paneles/{p['id']}/preguntas", data={"texto": "Pregunta al pleno"}, content_type="multipart/form-data").get_json()
    a = p["agentes"][0]
    # consulta individual en el despacho: abre su propia sesión, aparte
    i = cliente.post(f"/api/paneles/{p['id']}/preguntas", data={"texto": "Solo para ti", "individual": a["id"]},
                     content_type="multipart/form-data").get_json()
    assert i["sesion_id"] != g["sesion_id"] and i["destinatario"] == a["id"]
    ind = cliente.get(f"/api/paneles/{p['id']}/sesion?individual={a['id']}").get_json()["sesion"]
    assert ind["individual"] == a["id"] and ind["orden"] == [a["id"]]
    assert cliente.get(f"/api/paneles/{p['id']}/sesion").get_json()["sesion"]["id"] == g["sesion_id"]
    cliente.post(f"/api/preguntas/{i['pregunta_id']}/agentes/{a['id']}")
    acta = cliente.post(f"/api/sesiones/{ind['id']}/cerrar").get_json()["acta"]
    assert "consulta individual" in acta and acta.count("— ") >= 0
    asistentes = acta.split("## Asistentes")[1].split("##")[0]
    assert a["nombre"] in asistentes and p["agentes"][1]["nombre"] not in asistentes
    reg = cliente.get("/api/sesiones").get_json()
    assert any(x["id"] == ind["id"] and x["experto"] == a["nombre"] for x in reg)
