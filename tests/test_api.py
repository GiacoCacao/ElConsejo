import io


def _panel(c):
    return next(p for p in c.get("/api/paneles").get_json() if p["nombre"] == "Consejo de ejemplo")


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
    assert [a["capitulos"] for a in _panel(cliente)["agentes"]] == [0, 3, 0, 0]
    # la pregunta llega a ese agente con su biblioteca; a los demás, no
    llamadas, _ = falsos
    q = _preguntar(cliente, p["id"], "¿Qué plagas hay y cómo las controlo?").get_json()["pregunta_id"]
    r = cliente.post(f"/api/preguntas/{q}/agentes/{ag['id']}").get_json()
    assert r["fuentes"] and "biblioteca propia" in llamadas[-1][0]["content"]
    assert cliente.post(f"/api/preguntas/{q}/agentes/{p['agentes'][0]['id']}").get_json()["fuentes"] == []
    # borrar el documento limpia capítulos e índice
    assert cliente.delete(f"/api/docs/{d['id']}").status_code == 204
    assert cliente.get(f"/api/paneles/{p['id']}/pools").get_json() == {"_consejo": [], "_general": []}


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


def test_base_de_tarifas_y_nombres_equivalentes(cliente, monkeypatch):
    import bd
    import consumo
    assert consumo.normalizar("claude-sonnet-5-5") == consumo.normalizar("anthropic/claude-sonnet-5.5") \
        == consumo.normalizar("claude-sonnet-5-5-20260901")
    assert consumo.normalizar("deepseek-v4-pro-0813") == "deepseek-v4-pro"

    class R:
        def raise_for_status(self): pass
        def json(self):
            return {"data": [
                {"id": "anthropic/claude-sonnet-5.5", "context_length": 1000000,
                 "pricing": {"prompt": "0.000002", "completion": "0.00001", "input_cache_read": "0.0000001"}},
                {"id": "anthropic/claude-sonnet-5.5:batch", "pricing": {"prompt": "0.000001", "completion": "0.000005"}},
                {"id": "~anthropic/claude-latest", "pricing": {"prompt": "1", "completion": "1"}},
                {"id": "deepseek/deepseek-flash", "pricing": {"prompt": "0.0000009", "completion": "0.0000009"}},
                {"id": "openai/gpt-5.6-sol", "context_length": 1050000, "pricing": {"prompt": "0.000002", "completion": "0.00001"}},
            ]}
    monkeypatch.setattr(consumo.requests, "get", lambda *a, **k: R())
    assert cliente.post("/api/tarifas/actualizar").get_json()["modelos"] == 2   # sin variantes ni la de serie
    with bd.db() as c:
        tars = consumo.tarifas(c)
        assert tars.get("deepseek-flash")["entrada"] == 0.15                  # la de serie no se pisa
        t = tars.get("claude-sonnet-5-5")                                     # nombre del proveedor directo
        assert t and t["entrada"] == 2 and t["salida"] == 10 and t["cache"] == 0.1 and t["origen"] == "openrouter"
        # el caso de la prueba: 18.392 tokens de entrada y 2.514 de salida con Claude Sonnet 5.5
        fila = {"ts": 0, "entrada": 18392, "salida": 2514, "cache": 0, "modelo": "claude-sonnet-5-5"}
        assert round(consumo.coste(fila, tars.get(fila["modelo"])), 6) == round((18392 * 2 + 2514 * 10) / 1e6, 6)
    # buscar en toda la base
    assert any(x["modelo"] == "gpt-5.6-sol" for x in cliente.get("/api/tarifas?q=gpt").get_json()["tarifas"])
    # una tarifa manual tiene prioridad y la actualización no la toca
    cliente.put("/api/tarifas/claude-sonnet-5-5", json={"entrada": 3, "salida": 15})
    cliente.post("/api/tarifas/actualizar")
    with bd.db() as c:
        assert consumo.tarifas(c).get("claude-sonnet-5-5")["entrada"] == 3
