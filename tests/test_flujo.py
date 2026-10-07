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
    assert "Consultor General" in sistema and "Hoy es" in sistema
    assert "due diligence" in usuario and "Consejo de ejemplo" in usuario and "Pasaje" in usuario
    assert cliente.post("/api/consultor", json={"pregunta": " "}).status_code == 400
