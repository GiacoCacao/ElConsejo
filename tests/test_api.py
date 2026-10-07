import io


def _panel(c):
    return c.get("/api/paneles").get_json()[0]


def _preguntar(c, pid, texto, archivos=()):
    data = {"texto": texto, "imagenes": [(io.BytesIO(d), n) for n, d in archivos]}
    return c.post(f"/api/paneles/{pid}/preguntas", data=data, content_type="multipart/form-data")


def test_dialogo_entre_agentes(cliente, falsos):
    llamadas, _ = falsos
    p = _panel(cliente)
    q = _preguntar(cliente, p["id"], "¿Abrimos una sucursal?").get_json()["pregunta_id"]
    for a in p["agentes"]:
        r = cliente.post(f"/api/preguntas/{q}/agentes/{a['id']}?ronda=0").get_json()
        assert r["ronda"] == 0 and r["texto"].startswith("Respuesta de")
    llamadas.clear()
    lex = p["agentes"][0]
    r = cliente.post(f"/api/preguntas/{q}/agentes/{lex['id']}?ronda=1").get_json()
    assert r["ronda"] == 1
    ultimo = llamadas[0][-1]["content"]
    assert "tus colegas" in ultimo and "**Fiona**" in ultimo and "**Lex**" not in ultimo
    assert llamadas[0][-2] == {"role": "assistant", "content": "Respuesta de Lex"}


def test_pdf_del_chat_pasa_por_la_fabrica(cliente, falsos):
    llamadas, subidas = falsos
    p = _panel(cliente)
    r = _preguntar(cliente, p["id"], "Resume el documento", [("informe.pdf", b"%PDF-1.4")])
    assert r.status_code == 201 and r.get_json()["adjuntos"][0]["nombre"] == "informe.pdf"
    assert subidas[0][1] == ["elconsejo", "chat"]
    q = r.get_json()["pregunta_id"]
    cliente.post(f"/api/preguntas/{q}/agentes/{p['agentes'][0]['id']}")
    contenido = llamadas[-1][-1]["content"]
    assert "Documento adjunto: informe.pdf" in contenido and "goteo" in contenido
    assert _preguntar(cliente, p["id"], "x", [("virus.exe", b"MZ")]).status_code == 400


def test_pool_por_agente_via_api(cliente, falsos):
    import time
    p = _panel(cliente)
    ag = p["agentes"][1]
    r = cliente.post(f"/api/paneles/{p['id']}/agentes/{ag['id']}/docs",
                     data={"archivos": [(io.BytesIO(b"%PDF"), "huertos.pdf")]}, content_type="multipart/form-data")
    assert r.status_code == 202
    for _ in range(50):
        d = cliente.get(f"/api/paneles/{p['id']}/pools").get_json()[ag["id"]][0]
        if d["estado"] in ("listo", "error"):
            break
        time.sleep(0.1)
    assert d["estado"] == "listo" and d["capitulos"] == 3
    assert [a["capitulos"] for a in cliente.get("/api/paneles").get_json()[0]["agentes"]] == [0, 3, 0, 0]
    # la pregunta llega a ese agente con su biblioteca; a los demás, no
    llamadas, _ = falsos
    q = _preguntar(cliente, p["id"], "¿Qué plagas hay y cómo las controlo?").get_json()["pregunta_id"]
    r = cliente.post(f"/api/preguntas/{q}/agentes/{ag['id']}").get_json()
    assert r["fuentes"] and "biblioteca propia" in llamadas[-1][0]["content"]
    assert cliente.post(f"/api/preguntas/{q}/agentes/{p['agentes'][0]['id']}").get_json()["fuentes"] == []
    # borrar el documento limpia capítulos e índice
    assert cliente.delete(f"/api/docs/{d['id']}").status_code == 204
    assert cliente.get(f"/api/paneles/{p['id']}/pools").get_json() == {}


def test_paneles_de_serie_se_siembran_una_vez(cliente):
    import app as aplicacion
    import paneles_base
    nombres = [p["nombre"] for p in cliente.get("/api/paneles").get_json()]
    assert all(p["nombre"] in nombres for p in paneles_base.PANELES)
    filo = next(p for p in cliente.get("/api/paneles").get_json() if p["nombre"] == "Panel Filosófico")
    assert {"Materialismo filosófico", "Teología"} <= {a["rol"] for a in filo["agentes"]}
    cliente.delete(f"/api/paneles/{filo['id']}")
    aplicacion.arrancar()   # un reinicio no lo resucita
    assert "Panel Filosófico" not in [p["nombre"] for p in cliente.get("/api/paneles").get_json()]
