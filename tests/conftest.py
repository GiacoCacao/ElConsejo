import os
import sys
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["CONSEJO_DATOS"] = _tmp
os.environ["CONSEJO_IA_CLAVE"] = "x"
os.environ["CONSEJO_FABRICA_URL"] = "http://fabrica.invalida"
os.environ["CONSEJO_SIN_COPIAS"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest  # noqa: E402

import fabrica  # noqa: E402
import ia  # noqa: E402

LLAMAR_REAL = ia.llamar   # la de verdad, antes de que las pruebas la sustituyan

VOTOS = {}   # nombre del experto -> lo que «vota» la IA simulada (por defecto, A FAVOR)

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

    def llamar(msgs, modelo=None, temperatura=None, max_tokens=800, uso=None):
        llamadas.append(msgs)
        if uso is not None:
            uso.update(modelo=modelo or "deepseek-flash", entrada=1000, salida=200, cache=400, estimado=False)
        sis = msgs[0]["content"]
        ult = msgs[-1]["content"] if isinstance(msgs[-1]["content"], str) else msgs[-1]["content"][0]["text"]
        if "Consultor General" in sis:
            return "**Definición:** revisión previa a una operación.\n**Relacionados:** auditoría."
        if sis.startswith("Eres la Secretaría"):
            if "ALTERNATIVAS" in ult:
                return "A) Abrir ya la sucursal.\nB) Esperar seis meses."
            if "SÍNTESIS" in ult:
                return "SÍNTESIS:\nLos expertos debatieron con matices.\nCONCLUSIONES:\nConviene actuar por fases."
            return "El Consejo acuerda: abrir la sucursal por fases."
        if "somete a votación" in ult:
            nombre = sis.split("Te llamas ")[1].split(" ")[0].rstrip(".")
            return f"VOTO: {VOTOS.get(nombre, 'A FAVOR')}\nMOTIVO: Es lo prudente."
        if sis.startswith("Simplificas"):
            return "TITULO: Título IA\nRESUMEN: Resumen simple.\nCLAVES: a, b, c"
        return "Respuesta de " + sis.split("Te llamas ")[1].split(" ")[0]
    monkeypatch.setattr(ia, "llamar", llamar)

    def llamar_flujo(msgs, modelo=None, temperatura=None, max_tokens=800, uso=None):
        texto = llamar(msgs, modelo, temperatura, max_tokens, uso)
        for i in range(0, len(texto), 7):   # en trozos, como la API real
            yield texto[i:i + 7]
    monkeypatch.setattr(ia, "llamar_flujo", llamar_flujo)
    return llamadas, subidas


@pytest.fixture()
def cliente(falsos):
    import app as aplicacion
    return aplicacion.app.test_client()
