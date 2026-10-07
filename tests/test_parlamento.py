import io
import json

from conftest import MANUAL, MOCION_NO, ORDEN

import app as aplicacion
import bd
import ia
import pools


def _paneles(c):
    return {p["nombre"]: p for p in c.get("/api/paneles").get_json()}


def _pregunta(c, pid, texto):
    return c.post(f"/api/paneles/{pid}/preguntas", data={"texto": texto}, content_type="multipart/form-data").get_json()


def _lineas(r):
    return [json.loads(x) for x in r.data.decode().splitlines() if x.strip()]


def _cerrar(c, pid):
    s = c.get(f"/api/paneles/{pid}/sesion").get_json()["sesion"]
    if s:
        c.post(f"/api/sesiones/{s['id']}/cerrar")


def test_bibliotecas_comun_y_general(cliente, falsos):
    llamadas, _ = falsos
    p = _paneles(cliente)["Panel Empresarial"]
    for destino in ("_consejo", "_general"):
        r = cliente.post(f"/api/paneles/{p['id']}/agentes/{destino}/docs",
                         data={"archivos": [(io.BytesIO(b"%PDF"), f"{destino}.pdf")]}, content_type="multipart/form-data")
        assert r.status_code == 202
    import time
    for _ in range(50):
        b = cliente.get(f"/api/paneles/{p['id']}/pools").get_json()
        if all(d["estado"] == "listo" for k in ("_consejo", "_general") for d in b[k]) and b["_consejo"] and b["_general"]:
            break
        time.sleep(0.1)
    assert b["_consejo"][0]["capitulos"] == 3 and b["_general"][0]["capitulos"] == 3
    # la general aparece también en cualquier otro consejo
    otro = _paneles(cliente)["Panel Financiero"]
    assert cliente.get(f"/api/paneles/{otro['id']}/pools").get_json()["_general"][0]["nombre"] == "_general.pdf"
    assert cliente.get(f"/api/paneles/{otro['id']}/pools").get_json()["_consejo"] == []
    # un experto del consejo consulta su biblioteca común y la general
    texto, fuentes = pools.conocimiento([p["agentes"][0]["id"], pools.clave_consejo(p["id"]), pools.GENERAL], "¿cómo ahorrar agua con riego?")
    assert {f["biblioteca"] for f in fuentes} <= {"Biblioteca común", "Biblioteca general"} and "goteo" in texto
    # retirar un experto no borra la biblioteca común
    p2 = dict(p, agentes=p["agentes"][1:])
    cliente.put(f"/api/paneles/{p['id']}", json=p2)
    assert cliente.get(f"/api/paneles/{p['id']}/pools").get_json()["_consejo"]


def test_orden_del_dia_mociones_y_acta(cliente, falsos):
    llamadas, _ = falsos
    p = _paneles(cliente)["Panel Técnico Moderno"]
    _cerrar(cliente, p["id"])
    s = cliente.post(f"/api/paneles/{p['id']}/sesiones", json={"asunto": "Plan técnico", "orden_dia": ["Arquitectura", "Seguridad"]}).get_json()
    assert s["orden_dia"] == ["Arquitectura", "Seguridad"] and s["punto"] == 0
    q = _pregunta(cliente, p["id"], "¿Monolito o microservicios?")
    a = p["agentes"][0]
    cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{a['id']}")
    assert "Punto del orden del día en debate: Arquitectura" in llamadas[-1][0]["content"]
    # moción para limitar el tiempo de palabra: aprobada (todos SÍ)
    r = cliente.post(f"/api/sesiones/{s['id']}/mociones", json={"tipo": "limite", "palabras": 90}).get_json()
    assert r["resultado"]["aprobada"] and r["sesion"]["limite_palabras"] == 90
    # moción de pasar al siguiente punto: rechazada (mayoría NO)
    MOCION_NO.update(x["nombre"].split(" ")[0] for x in p["agentes"][:4])
    r = cliente.post(f"/api/sesiones/{s['id']}/mociones", json={"tipo": "siguiente"}).get_json()
    assert not r["resultado"]["aprobada"] and r["sesion"]["punto"] == 0
    MOCION_NO.clear()
    # votación del primer punto y paso al segundo
    v = cliente.post(f"/api/sesiones/{s['id']}/votaciones", json={"tipo": "consenso", "propuesta": "El Consejo acuerda: monolito modular."}).get_json()
    for x in p["agentes"]:
        cliente.post(f"/api/votaciones/{v['id']}/votos/{x['id']}")
    cliente.post(f"/api/votaciones/{v['id']}/cerrar")
    assert cliente.post(f"/api/sesiones/{s['id']}/punto", json={"punto": 1}).get_json()["punto"] == 1
    q2 = _pregunta(cliente, p["id"], "¿Y la seguridad?")
    assert q2["punto"] if "punto" in q2 else True
    with bd.db() as c:
        assert c.execute("SELECT punto FROM mensajes WHERE id=?", (q2["pregunta_id"],)).fetchone()["punto"] == 1
    # cuarto intermedio: no se puede consultar hasta reanudar
    cliente.post(f"/api/sesiones/{s['id']}/receso", json={"activo": True})
    assert cliente.post(f"/api/paneles/{p['id']}/preguntas", data={"texto": "x"}, content_type="multipart/form-data").status_code == 409
    cliente.post(f"/api/sesiones/{s['id']}/receso", json={"activo": False})
    acta = cliente.post(f"/api/sesiones/{s['id']}/cerrar").get_json()["acta"]
    for trozo in ("## Orden del día", "1. Arquitectura", "2. Seguridad", "## Mociones de procedimiento",
                  "limitar el tiempo de palabra a 90 palabras", "**Punto 1. Arquitectura**", "> El Consejo acuerda: monolito modular.",
                  "**Punto 2. Seguridad**", "No se adoptó acuerdo formal sobre este punto."):
        assert trozo in acta, trozo
    # el acta con membrete, en PDF y en Word
    pdf = cliente.get(f"/api/sesiones/{s['id']}/acta.pdf")
    assert pdf.status_code == 200 and pdf.data[:4] == b"%PDF"
    docx = cliente.get(f"/api/sesiones/{s['id']}/acta.docx")
    assert docx.status_code == 200 and docx.data[:2] == b"PK"
    from docx import Document
    texto = "\n".join(par.text for par in Document(io.BytesIO(docx.data)).paragraphs)
    assert "Acta de la sesión nº" in texto and "Arquitectura" in texto
    # membrete propio con logotipo
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (60, 60), "#123456").save(buf, "PNG")
    cliente.put("/api/ajustes/membrete", json={"nombre": "Fundación Prueba", "ciudad": "Valencia", "papel": "a4"})
    assert cliente.post("/api/ajustes/membrete/logo", data={"logo": (io.BytesIO(buf.getvalue()), "logo.png")},
                        content_type="multipart/form-data").get_json()["logo"]
    assert cliente.get(f"/api/sesiones/{s['id']}/acta.pdf").data[:4] == b"%PDF"
    cliente.delete("/api/ajustes/membrete/logo")
    cliente.put("/api/ajustes/membrete", json={"nombre": "", "ciudad": "", "papel": "carta"})


def test_asamblea_oradores_cuestion_de_orden_y_retirar_la_palabra(cliente, falsos, monkeypatch):
    llamadas, _ = falsos
    ps = _paneles(cliente)
    jur, fin = ps["Panel Jurídico"], ps["Panel Financiero"]
    asam = ps["Asamblea General"]
    _cerrar(cliente, asam["id"])
    s = cliente.post("/api/asamblea/sesiones", json={"asunto": "Salarios", "comites": [
        {"panel_id": jur["id"], "delegados": [jur["agentes"][2]["id"]]},
        {"panel_id": fin["id"], "delegados": [fin["agentes"][0]["id"], fin["agentes"][1]["id"]]}]}).get_json()
    asam = _paneles(cliente)["Asamblea General"]
    carmen, gonzalo, raquel = asam["agentes"]
    q = _pregunta(cliente, asam["id"], "¿Pagamos en dólares?")
    # una intervención que alude a Rondón deja a Carmen en la lista de oradores (persistente)
    flujo_falso = ia.llamar_flujo
    monkeypatch.setattr(ia, "llamar_flujo", lambda *a, **k: iter(["Discrepo de la Dra. Rondón ", "en ese punto."]))
    ev = _lineas(cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{gonzalo['id']}/flujo?modo=palabra"))
    assert ev[-1]["oradores"] == [{"id": carmen["id"], "tipo": "alusion", "por": gonzalo["id"]}]
    assert cliente.get(f"/api/paneles/{asam['id']}/sesion").get_json()["sesion"]["oradores"][0]["id"] == carmen["id"]
    # solicitudes: Raquel plantea una cuestión de orden, que pasa delante
    monkeypatch.setattr(ia, "llamar_flujo", flujo_falso)
    falsos_llamar = ia.llamar
    ORDEN.add("Raquel")
    r = cliente.post(f"/api/preguntas/{q['pregunta_id']}/solicitudes").get_json()
    ORDEN.clear()
    assert r["oradores"][0] == {"id": raquel["id"], "tipo": "orden", "motivo": "el debate se desvía del punto"}
    # concederle la palabra para la cuestión de orden: prompt específico y sale de la lista
    import conftest  # noqa: F401
    from conftest import LLAMAR_REAL  # noqa: F401
    def flujo_simulado(msgs, *a, **k):
        llamadas.append(msgs)
        yield "Cuestión de orden: volvamos al punto."
    monkeypatch.setattr(ia, "llamar_flujo", flujo_simulado)
    fin_ = _lineas(cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{raquel['id']}/flujo?modo=orden"))[-1]
    assert "CUESTIÓN DE ORDEN" in llamadas[-1][-1]["content"] and fin_["m"]["modo"] == "orden"
    assert [o["id"] for o in cliente.get(f"/api/paneles/{asam['id']}/sesion").get_json()["sesion"]["oradores"]] == [carmen["id"]]
    # la presidencia retira la palabra a mitad de intervención
    def larga(*a, **k):
        yield "Primera frase. "
        aplicacion.RETIRADAS.add((q["pregunta_id"], carmen["id"]))   # llega la orden de la presidencia
        for i in range(50):
            yield f"frase {i}. "
    monkeypatch.setattr(ia, "llamar_flujo", larga)
    ev = _lineas(cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{carmen['id']}/flujo?modo=alusion&por={gonzalo['id']}"))
    assert ev[-1]["retirada"] and "retiró la palabra" in ev[-1]["m"]["texto"] and "frase 5." not in ev[-1]["m"]["texto"]
    # lista editable por la presidencia
    assert cliente.put(f"/api/sesiones/{s['id']}/oradores", json={"oradores": [{"id": gonzalo["id"], "tipo": "pide"}, {"id": "x", "tipo": "pide"}]}).get_json() == [{"id": gonzalo["id"], "tipo": "pide"}]
    assert falsos_llamar


def test_estadisticas(cliente, falsos):
    r = cliente.get("/api/estadisticas?dias=30").get_json()
    t = r["tiles"]
    assert t["sesiones"] >= 1 and t["intervenciones"] >= 1 and t["votaciones"] >= 1
    assert len(r["gasto_serie"]) == 30 and r["periodo"]["por_dia"]
    assert r["gasto_por_modelo"] and r["sesiones_por_consejo"] and r["activos"]
    assert {x["nombre"] for x in r["resultados"]} & {"Unanimidad", "Mayoría simple", "Sin consenso", "Consenso con abstenciones"}
    anual = cliente.get("/api/estadisticas?dias=365").get_json()
    assert len(anual["gasto_serie"]) == 12 and not anual["periodo"]["por_dia"]
    p = _paneles(cliente)["Panel Técnico Moderno"]
    solo = cliente.get(f"/api/estadisticas?dias=0&panel={p['id']}").get_json()
    assert all(x["nombre"] == "Panel Técnico Moderno" for x in solo["sesiones_por_consejo"])
