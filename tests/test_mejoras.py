import io

import pytest

import bd
import config


def _panel(c):
    return next(p for p in c.get("/api/paneles").get_json() if p["nombre"] == "Consejo de ejemplo")


def test_los_expertos_conocen_la_fecha(cliente, falsos):
    llamadas, _ = falsos
    p = _panel(cliente)
    q = cliente.post(f"/api/paneles/{p['id']}/preguntas", data={"texto": "¿Qué día es?"},
                     content_type="multipart/form-data").get_json()
    cliente.post(f"/api/preguntas/{q['pregunta_id']}/agentes/{p['agentes'][0]['id']}")
    sistema = llamadas[-1][0]["content"]
    assert "Hoy es " in sistema and "hora de Caracas" in sistema and "fecha de corte" in sistema


def test_tope_de_gasto_avisa_o_bloquea(cliente, monkeypatch):
    import consumo
    import ia
    monkeypatch.setattr(consumo, "gastado", lambda desde: 5.0)
    r = cliente.put("/api/ajustes/gasto", json={"diario": "4", "mensual": "", "modo": "avisar"}).get_json()
    assert r["excedido"] == "diario" and r["modo"] == "avisar"
    consumo.comprobar()   # en modo «avisar» no se bloquea
    cliente.put("/api/ajustes/gasto", json={"diario": 4, "modo": "bloquear"})
    with pytest.raises(RuntimeError, match="Tope de gasto diario"):
        consumo.comprobar()
    # la IA real también se frena (antes de llamar a la API)
    monkeypatch.setattr(config, "IA_CLAVE", "x")
    from conftest import LLAMAR_REAL
    with pytest.raises(ia.IAError, match="Tope de gasto"):
        LLAMAR_REAL([{"role": "user", "content": "hola"}])
    cliente.put("/api/ajustes/gasto", json={"diario": "", "mensual": "", "modo": "avisar"})
    assert consumo.limites() == {"diario": None, "mensual": None, "modo": "avisar"}
    assert cliente.put("/api/ajustes/gasto", json={"diario": "-1"}).status_code == 400


def test_copias_de_seguridad_rotan(cliente, monkeypatch, tmp_path):
    import copias
    monkeypatch.setattr(config, "COPIAS", str(tmp_path))
    monkeypatch.setattr(config, "COPIAS_GUARDAR", 2)
    nombres = []
    for i in range(3):
        nombres.append(cliente.post("/api/copias").get_json()["nombre"])
        import time; time.sleep(1.05)
    lista = [c["nombre"] for c in cliente.get("/api/ajustes").get_json()["copias"]]
    assert lista == nombres[:0:-1]   # solo las dos más recientes
    r = cliente.get(f"/api/copias/{lista[0]}")
    assert r.status_code == 200 and r.data[:15] == b"SQLite format 3"
    assert cliente.get("/api/copias/..%2Fconsejo.db").status_code == 404


def test_acceso_con_clave_y_observador(cliente, monkeypatch):
    monkeypatch.setattr(config, "CLAVE_PRESIDENCIA", "clave-presi")
    monkeypatch.setattr(config, "CLAVE_OBSERVADOR", "clave-obs")
    assert cliente.get("/api/paneles").status_code == 401
    assert cliente.get("/").status_code == 302 and cliente.get("/salud").status_code == 200
    assert cliente.post("/api/acceso", json={"clave": "mala"}).status_code == 401
    assert cliente.post("/api/acceso", json={"clave": "clave-obs"}).get_json()["rol"] == "observador"
    assert cliente.get("/api/paneles").status_code == 200
    assert cliente.post("/api/paneles", json={"nombre": "X"}).status_code == 403   # solo lectura
    assert cliente.post("/api/copias").status_code == 403
    cliente.delete("/api/acceso")
    assert cliente.post("/api/acceso", json={"clave": "clave-presi"}).get_json()["rol"] == "presidencia"
    r = cliente.post("/api/paneles", json={"nombre": "Panel temporal"})
    assert r.status_code == 201
    cliente.delete(f"/api/paneles/{r.get_json()['id']}")
    cliente.delete("/api/acceso")


def test_bloqueo_tras_varios_intentos(cliente, monkeypatch):
    import app
    monkeypatch.setattr(config, "CLAVE_PRESIDENCIA", "otra")
    monkeypatch.setattr(app.time, "sleep", lambda s: None)
    for _ in range(5):
        cliente.post("/api/acceso", json={"clave": "x"}, environ_base={"REMOTE_ADDR": "10.9.9.9"})
    assert cliente.post("/api/acceso", json={"clave": "otra"}, environ_base={"REMOTE_ADDR": "10.9.9.9"}).status_code == 429
    app._fallos.clear()
