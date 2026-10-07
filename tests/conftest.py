import os
import sys
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["CONSEJO_DATOS"] = _tmp
os.environ["CONSEJO_IA_CLAVE"] = "x"
os.environ["CONSEJO_FABRICA_URL"] = "http://fabrica.invalida"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest  # noqa: E402

import fabrica  # noqa: E402
import ia  # noqa: E402

MANUAL = "# Manual de huertos urbanos\n\n" + "".join(
    f"## Capítulo {i}. {t}\n\n" + (f"{x} " * 30) + "\n\n" for i, (t, x) in enumerate([
        ("Suelo y sustrato", "El suelo ideal combina compost, tierra negra y fibra de coco."),
        ("Riego eficiente", "El riego por goteo ahorra hasta un sesenta por ciento de agua."),
        ("Plagas y control", "Contra los pulgones funciona el jabón potásico, un control ecológico."),
    ], 1))


@pytest.fixture()
def falsos(monkeypatch):
    """Fábrica e IA simuladas. `llamadas` guarda lo que recibió la IA."""
    llamadas, subidas = [], []
    monkeypatch.setattr(fabrica, "subir", lambda n, d, e: (subidas.append((n, e)), f"fab-{len(subidas)}")[1])
    monkeypatch.setattr(fabrica, "esperar", lambda fid, limite=0: {"estado": "listo"})
    monkeypatch.setattr(fabrica, "texto", lambda fid: MANUAL)
    monkeypatch.setattr(fabrica, "buscar", lambda q, ids, limite=6: [])
    monkeypatch.setattr(fabrica, "borrar", lambda fid: None)

    def llamar(msgs, modelo=None, temperatura=None, max_tokens=800):
        llamadas.append(msgs)
        sis = msgs[0]["content"]
        if sis.startswith("Simplificas"):
            return "TITULO: Título IA\nRESUMEN: Resumen simple.\nCLAVES: a, b, c"
        return "Respuesta de " + sis.split("Te llamas ")[1].split(" ")[0]
    monkeypatch.setattr(ia, "llamar", llamar)
    return llamadas, subidas


@pytest.fixture()
def cliente(falsos):
    import app as aplicacion
    return aplicacion.app.test_client()
