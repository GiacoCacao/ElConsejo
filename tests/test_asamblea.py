from conftest import SOLICITAN

import ia
import proveedores


def _paneles(c):
    return {p["nombre"]: p for p in c.get("/api/paneles").get_json()}


def _lineas(r):
    import json
    return [json.loads(x) for x in r.data.decode().splitlines() if x.strip()]


def test_proveedores_claves_cifradas_y_por_experto(cliente):
    r = cliente.post("/api/proveedores", json={"nombre": "OpenAI", "url": "https://api.openai.com/v1/chat/completions",
                                               "clave": "sk-secretisima-1234", "modelo": "modelo-x"})
    pr = r.get_json()
    assert r.status_code == 201 and pr["url"] == "https://api.openai.com/v1" and pr["clave"] == "sk-…1234"
    assert "secretisima" not in cliente.get("/api/proveedores").data.decode()
    import bd
    with bd.db() as c:
        guardada = c.execute("SELECT clave FROM proveedores WHERE id=?", (pr["id"],)).fetchone()["clave"]
    assert "secretisima" not in guardada                          # cifrada en la base de datos
    url, clave, modelo, nombre = proveedores.destino({"proveedor": pr["id"], "modelo": ""})
    assert (url, clave, modelo, nombre) == ("https://api.openai.com/v1", "sk-secretisima-1234", "modelo-x", "OpenAI")
    assert proveedores.destino({"modelo": ""})[3] is None        # sin proveedor: la IA por defecto
    # un experto con ese proveedor no deja borrarlo
    p = _paneles(cliente)["Consejo de ejemplo"]
    p["agentes"][0]["proveedor"] = pr["id"]
    cliente.put(f"/api/paneles/{p['id']}", json=p)
    assert cliente.delete(f"/api/proveedores/{pr['id']}").status_code == 409
    p["agentes"][0]["proveedor"] = ""
    cliente.put(f"/api/paneles/{p['id']}", json=p)
    assert cliente.delete(f"/api/proveedores/{pr['id']}").status_code == 204


def test_parametros_que_otras_apis_rechazan():
    cuerpo = {"model": "m", "max_tokens": 10, "temperature": 0.2, "stream_options": {"include_usage": True}}
    assert ia._ajustar(cuerpo, "Unrecognized request argument: stream_options") and "stream_options" not in cuerpo
    assert ia._ajustar(cuerpo, "Use 'max_completion_tokens' instead of 'max_tokens'") and cuerpo["max_completion_tokens"] == 10
    assert ia._ajustar(cuerpo, "temperature is not supported") and "temperature" not in cuerpo
    assert not ia._ajustar(cuerpo, "invalid api key")


def test_pregunta_directa_en_sala_la_oye_el_resto(cliente, falsos):
    llamadas, _ = falsos
    p = _paneles(cliente)["Panel Financiero"]
    a, b = p["agentes"][0], p["agentes"][1]
    q = cliente.post(f"/api/paneles/{p['id']}/preguntas", data={"texto": "Pregunta para ti", "destinatario": a["id"]},
                     content_type="multipart/form-data").get_json()
    assert q["destinatario"] == a["id"]
    llamadas.clear()
    cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{a['id']}")
    assert "directamente a ti" in llamadas[0][0]["content"]
    q2 = cliente.post(f"/api/paneles/{p['id']}/preguntas", data={"texto": "¿Qué opinan?"},
                      content_type="multipart/form-data").get_json()
    assert q2["sesion_id"] == q["sesion_id"]                       # misma sesión: no se va al despacho
    llamadas.clear()
    cliente.post(f"/api/preguntas/{q2['pregunta_id']}/agentes/{b['id']}")
    vistos = " ".join(m["content"] for m in llamadas[0][1:] if isinstance(m["content"], str))
    assert "preguntó directamente a" in vistos and "Pregunta para ti" in vistos and f"Respuesta de {a['nombre'].split()[0]}" in vistos
    assert cliente.post(f"/api/paneles/{p['id']}/preguntas", data={"texto": "x", "destinatario": "nadie"},
                        content_type="multipart/form-data").status_code == 400


def test_asamblea_con_derecho_de_palabra(cliente, falsos):
    llamadas, _ = falsos
    ps = _paneles(cliente)
    asam = ps["Asamblea General"]
    assert asam["tipo"] == "asamblea" and list(ps)[0] == "Asamblea General"
    assert cliente.delete(f"/api/paneles/{asam['id']}").status_code == 400
    jur, fin = ps["Panel Jurídico"], ps["Panel Financiero"]
    cuerpo = {"asunto": "¿Dolarizar los contratos laborales?", "limite_palabras": 120, "modo_debate": "orden",
              "comites": [{"panel_id": jur["id"], "delegados": [jur["agentes"][2]["id"]]},
                          {"panel_id": fin["id"], "delegados": [fin["agentes"][0]["id"], fin["agentes"][1]["id"]]}]}
    assert cliente.post("/api/asamblea/sesiones", json={**cuerpo, "comites": cuerpo["comites"][:1]}).status_code == 400
    s = cliente.post("/api/asamblea/sesiones", json=cuerpo).get_json()
    assert [c["nombre"] for c in s["composicion"]["comites"]] == ["Panel Jurídico", "Panel Financiero"]
    assert s["limite_palabras"] == 120 and len(s["orden"]) == 3
    assert cliente.post("/api/asamblea/sesiones", json=cuerpo).status_code == 409
    asam = _paneles(cliente)["Asamblea General"]
    carmen, gonzalo, raquel = asam["agentes"]
    assert carmen["comite"] == "Panel Jurídico" and carmen["id"] == jur["agentes"][2]["id"]   # conserva su id (y biblioteca)
    q = cliente.post(f"/api/paneles/{asam['id']}/preguntas", data={"texto": "¿Dolarizamos los contratos?"},
                     content_type="multipart/form-data").get_json()
    llamadas.clear()
    cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{carmen['id']}")
    sistema = llamadas[0][0]["content"]
    assert "delegado del Panel Jurídico" in sistema and "120 palabras" in sistema
    # palabra concedida por alusiones: recibe la transcripción y el motivo
    llamadas.clear()
    r = cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{gonzalo['id']}/flujo?modo=alusion&por={carmen['id']}")
    ev = _lineas(r)
    ultimo = llamadas[0][-1]["content"]
    assert "concede la palabra por alusiones" in ultimo and carmen["nombre"] in ultimo and "Transcripción" in ultimo
    assert ev[-1]["m"]["modo"] == "alusion" and ev[-1]["m"]["ronda"] == 1
    # detección de alusiones: por apellido o por comité
    import app
    assert app.alusiones(asam, gonzalo["id"], "Como dijo la Dra. Rondón, el comité jurídico duda") == [carmen["id"]]
    assert raquel["id"] in app.alusiones(asam, carmen["id"], "Discrepo de Domínguez")
    assert app.alusiones(asam, carmen["id"], "El riesgo financiero es alto") == []          # adjetivo suelto: no
    assert set(app.alusiones(asam, carmen["id"], "Como plantea la delegación financiera")) == {gonzalo["id"], raquel["id"]}
    assert app.alusiones(asam, gonzalo["id"], "Comparto lo que dicen los colegas del panel jurídico") == [carmen["id"]]
    # turno de solicitudes de palabra
    SOLICITAN.clear(); SOLICITAN.add("Raquel")
    piden = cliente.post(f"/api/preguntas/{q['pregunta_id']}/solicitudes").get_json()["piden"]
    assert [x["agente_id"] for x in piden] == [raquel["id"]] and "costes" in piden[0]["motivo"]
    SOLICITAN.clear()
    acta = cliente.post(f"/api/sesiones/{s['id']}/cerrar").get_json()["acta"]
    assert "delegado del Panel Jurídico" in acta and "Comités representados: Panel Jurídico, Panel Financiero" in acta
    assert "120 palabras" in acta
