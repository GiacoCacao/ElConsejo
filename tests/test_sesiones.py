import io

from conftest import VOTOS


def _panel(c, nombre="Consejo de ejemplo"):
    return next(p for p in c.get("/api/paneles").get_json() if p["nombre"] == nombre)


def _preguntar(c, pid, texto):
    return c.post(f"/api/paneles/{pid}/preguntas", data={"texto": texto}, content_type="multipart/form-data").get_json()


def _cerrar_si_abierta(c, pid):
    s = c.get(f"/api/paneles/{pid}/sesion").get_json()["sesion"]
    if s:
        c.post(f"/api/sesiones/{s['id']}/cerrar")


def test_consultar_abre_sesion_y_no_se_puede_abrir_otra(cliente):
    p = _panel(cliente)
    _cerrar_si_abierta(cliente, p["id"])
    q = _preguntar(cliente, p["id"], "¿Abrimos sucursal en Valencia?")
    s = cliente.get(f"/api/paneles/{p['id']}/sesion").get_json()
    assert s["sesion"]["asunto"] == "¿Abrimos sucursal en Valencia?" and q["sesion_id"] == s["sesion"]["id"]
    r = cliente.post(f"/api/paneles/{p['id']}/sesiones", json={"asunto": "Otra"})
    assert r.status_code == 409


def test_orden_del_debate_quien_habla_despues_oye_a_los_anteriores(cliente, falsos):
    llamadas, _ = falsos
    p = _panel(cliente, "Panel Financiero")
    _cerrar_si_abierta(cliente, p["id"])
    ids = [a["id"] for a in p["agentes"]]
    orden = [ids[2], ids[0]] + [i for i in ids if i not in (ids[2], ids[0])]
    s = cliente.post(f"/api/paneles/{p['id']}/sesiones", json={"asunto": "Presupuesto", "modo_debate": "orden",
                                                               "orden": orden}).get_json()
    assert s["orden"] == orden and s["numero"] >= 1
    q = _preguntar(cliente, p["id"], "¿Recortamos gastos?")["pregunta_id"]
    cliente.post(f"/api/preguntas/{q}/agentes/{orden[0]}")
    llamadas.clear()
    cliente.post(f"/api/preguntas/{q}/agentes/{orden[1]}")
    ultimo = llamadas[0][-1]["content"]
    primero = next(a for a in p["agentes"] if a["id"] == orden[0])
    assert "ya han intervenido" in ultimo and primero["nombre"] in ultimo
    assert "sesión nº" in llamadas[0][0]["content"] and "Presupuesto" in llamadas[0][0]["content"]


def test_consenso_votacion_acta_y_traslado(cliente, falsos):
    llamadas, _ = falsos
    p = _panel(cliente)
    _cerrar_si_abierta(cliente, p["id"])
    q = _preguntar(cliente, p["id"], "¿Abrimos la sucursal?")
    sid = q["sesion_id"]
    for a in p["agentes"]:
        cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{a['id']}")
    prop = cliente.post(f"/api/sesiones/{sid}/propuesta", json={"tipo": "consenso"}).get_json()
    assert prop["propuesta"].startswith("El Consejo acuerda")
    # Lex vota en contra: no hay consenso
    VOTOS.clear(); VOTOS["Lex"] = "EN CONTRA"
    v = cliente.post(f"/api/sesiones/{sid}/votaciones", json={"tipo": "consenso", "propuesta": prop["propuesta"]}).get_json()
    assert cliente.get(f"/api/paneles/{p['id']}/sesion").get_json()["sesion"]["estado"] == "votacion"
    for a in p["agentes"]:
        assert cliente.post(f"/api/votaciones/{v['id']}/votos/{a['id']}").get_json()["opcion"] in ("favor", "contra")
    r = cliente.post(f"/api/votaciones/{v['id']}/cerrar").get_json()["resultado"]
    assert r["estado"] == "sin_consenso" and r["cuenta"] == {"favor": 3, "contra": 1, "abstencion": 0}
    # la revisión recoge las objeciones de Lex
    llamadas.clear()
    cliente.post(f"/api/sesiones/{sid}/propuesta", json={"tipo": "consenso", "revisar": v["id"]})
    assert "Objeciones" in llamadas[0][-1]["content"] and "Lex" in llamadas[0][-1]["content"]
    VOTOS.clear()
    v2 = cliente.post(f"/api/sesiones/{sid}/votaciones", json={"tipo": "consenso", "propuesta": "El Consejo acuerda: por fases."}).get_json()
    for a in p["agentes"]:
        cliente.post(f"/api/votaciones/{v2['id']}/votos/{a['id']}")
    r2 = cliente.post(f"/api/votaciones/{v2['id']}/cerrar").get_json()["resultado"]
    assert r2["estado"] == "aprobado" and r2["unanime"]
    # acta: datos objetivos compuestos por código
    cierre = cliente.post(f"/api/sesiones/{sid}/cerrar").get_json()
    acta = cierre["acta"]
    assert cierre["sesion"]["estado"] == "cerrada"
    for trozo in ("# Acta de la sesión nº", "## Asistentes", "**Lex**", "## Orden del debate", "En contra",
                  "No se alcanzó el consenso", "Aprobado por unanimidad", "> El Consejo acuerda: por fases.",
                  "Los expertos debatieron con matices", "## Cierre"):
        assert trozo in acta, trozo
    assert cliente.get(f"/api/sesiones/{sid}/acta.md").data.decode().startswith("# Acta")
    assert cliente.get(f"/api/paneles/{p['id']}/sesion").get_json()["sesion"] is None
    # trasladar el acta a otro consejo: abre allí una sesión con el acta anexa
    otro = _panel(cliente, "Panel Empresarial")
    _cerrar_si_abierta(cliente, otro["id"])
    t = cliente.post(f"/api/sesiones/{sid}/trasladar", json={"panel_id": otro["id"]}).get_json()
    assert t["sesion"]["anexos"][0]["id"] == sid and "Deliberación del acta" in t["sesion"]["asunto"]
    q2 = _preguntar(cliente, otro["id"], "¿Qué opinan del acuerdo?")
    llamadas.clear()
    cliente.post(f"/api/preguntas/{q2['pregunta_id']}/agentes/{otro['agentes'][0]['id']}")
    assert "Acta anexa" in llamadas[0][0]["content"] and "por fases" in llamadas[0][0]["content"]
    reg = cliente.get("/api/sesiones").get_json()
    assert any(x["id"] == sid and x["tiene_acta"] for x in reg)


def test_mayoria_simple_con_empate_y_voto_de_calidad(cliente, falsos):
    p = _panel(cliente, "Panel Técnico Moderno")
    _cerrar_si_abierta(cliente, p["id"])
    q = _preguntar(cliente, p["id"], "¿Monolito o microservicios?")
    cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{p['agentes'][0]['id']}")
    prop = cliente.post(f"/api/sesiones/{q['sesion_id']}/propuesta", json={"tipo": "mayoria"}).get_json()
    assert [a["letra"] for a in prop["alternativas"]] == ["A", "B"]
    VOTOS.clear()
    for i, a in enumerate(p["agentes"]):   # 3 a A y 3 a B: empate
        VOTOS[a["nombre"].split(" ")[0]] = "A" if i % 2 else "B"
    v = cliente.post(f"/api/sesiones/{q['sesion_id']}/votaciones", json={"tipo": "mayoria", "alternativas": prop["alternativas"]}).get_json()
    for a in p["agentes"]:
        cliente.post(f"/api/votaciones/{v['id']}/votos/{a['id']}")
    r = cliente.post(f"/api/votaciones/{v['id']}/cerrar").get_json()
    assert r["resultado"]["estado"] == "empate" and r["estado"] == "abierta"
    r = cliente.post(f"/api/votaciones/{v['id']}/cerrar", json={"calidad": "B"}).get_json()
    assert r["resultado"]["ganadora"] == "B" and r["resultado"]["calidad"] and r["estado"] == "cerrada"
    VOTOS.clear()


def test_las_respuestas_quedan_en_la_sesion_y_llegan_a_la_secretaria(cliente, falsos):
    llamadas, _ = falsos
    p = _panel(cliente, "Panel Psicológico")
    _cerrar_si_abierta(cliente, p["id"])
    q = _preguntar(cliente, p["id"], "¿Cómo gestiono la ansiedad antes de hablar en público?")
    a = p["agentes"][0]
    r = cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{a['id']}").get_json()
    assert r["sesion_id"] == q["sesion_id"]
    est = cliente.get(f"/api/paneles/{p['id']}/sesion").get_json()
    assert [m["rol"] for m in est["mensajes"]] == ["user", "agent"]   # al recargar, la respuesta sigue ahí
    llamadas.clear()
    cliente.post(f"/api/sesiones/{q['sesion_id']}/propuesta", json={"tipo": "consenso"})
    assert f"**{a['nombre']}" in llamadas[0][-1]["content"]          # la Secretaría ve el debate
    llamadas.clear()
    acta = cliente.post(f"/api/sesiones/{q['sesion_id']}/cerrar").get_json()["acta"]
    assert f"**{a['nombre']}" in llamadas[0][-1]["content"] and "EXCLUSIVAMENTE" in llamadas[0][-1]["content"]


def test_etiquetas_del_acta_en_negrita():
    import sesiones
    t = "**SÍNTESIS:**\n\nLex defendió el híbrido.\n\n**CONCLUSIONES:**\n\nHíbrido."
    assert sesiones._seccion(t, "SÍNTESIS", "CONCLUSIONES") == "Lex defendió el híbrido."
    assert sesiones._seccion(t, "CONCLUSIONES", "ZZZ") == "Híbrido."
