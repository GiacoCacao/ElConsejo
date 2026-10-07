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
    assert {"Panel Político", "Panel Militar", "Panel de Internacionalistas y Diplomáticos",
            "Panel de Periodistas", "Panel Jurídico", "Panel Científico"} <= set(nombres)
    cliente.delete(f"/api/paneles/{filo['id']}")
    aplicacion.arrancar()   # un reinicio no lo resucita
    assert "Panel Filosófico" not in [p["nombre"] for p in cliente.get("/api/paneles").get_json()]


def test_consumo_y_coste_por_agente(cliente):
    import consumo
    p = _panel(cliente)
    q = _preguntar(cliente, p["id"], "¿Coste?").get_json()["pregunta_id"]
    for a in p["agentes"][:2]:
        cliente.post(f"/api/preguntas/{q}/agentes/{a['id']}")
    r = cliente.get(f"/api/paneles/{p['id']}/consumo").get_json()
    lex = r["agentes"][0]
    assert lex["ultima"]["entrada"] == 1000 and lex["contexto_usado"] == 1000 and lex["pct"] == 0.1
    assert r["ultima"]["llamadas"] == 2 and r["servicio"]["modelo"] == "deepseek-flash"
    # 600 sin caché + 400 en caché + 200 de salida, en franja valle o punta
    valle = (600 * .15 + 400 * .003 + 200 * .6) / 1e6
    assert round(r["ultima"]["coste"], 12) in (round(2 * valle, 12), round(4 * valle, 12))
    assert r["agentes"][2]["ultima"]["llamadas"] == 0   # no participó en esta consulta


def test_franja_punta_de_deepseek():
    import consumo
    from datetime import datetime, timezone
    ts = lambda *a: datetime(*a, tzinfo=timezone.utc).timestamp()
    assert consumo.es_punta(ts(2026, 10, 7, 8, 30), "deepseek")        # miércoles 08:30 UTC
    assert not consumo.es_punta(ts(2026, 10, 7, 12, 0), "deepseek")    # miércoles 12:00
    assert not consumo.es_punta(ts(2026, 10, 10, 8, 30), "deepseek")   # sábado
    assert not consumo.es_punta(ts(2026, 10, 7, 8, 30), None)


def test_tarifas_editables(cliente):
    r = cliente.put("/api/tarifas/mi-modelo", json={"proveedor": "Otro", "contexto": 200000, "entrada": 3, "salida": 15})
    assert r.status_code == 200
    t = {x["modelo"]: x for x in cliente.get("/api/tarifas").get_json()["tarifas"]}
    assert t["mi-modelo"]["salida"] == 15 and "deepseek-flash" in t
    assert cliente.put("/api/tarifas/x", json={"entrada": -1, "salida": 1}).status_code == 400
