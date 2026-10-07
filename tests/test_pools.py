import bd
import pools
from conftest import MANUAL


def test_dividir_por_capitulos():
    caps = pools.dividir(MANUAL)
    assert [c["titulo"] for c in caps] == [
        "Capítulo 1. Suelo y sustrato", "Capítulo 2. Riego eficiente", "Capítulo 3. Plagas y control"]
    assert "goteo" in caps[1]["texto"] and "goteo" not in caps[0]["texto"]


def test_dividir_texto_de_pdf_sin_lineas_en_blanco():
    cuerpo = "Una frase de relleno con sentido. " * 20
    pdf = "".join(f"Capítulo {i}. Título {i}\n{cuerpo}\n" for i in (1, 2, 3))
    assert [c["titulo"] for c in pools.dividir(pdf)] == [f"Capítulo {i}. Título {i}" for i in (1, 2, 3)]


def test_titulo_pegado_al_texto_anterior_y_falsos_positivos():
    cuerpo = "Una frase de relleno con sentido. " * 20
    pdf = f"Manual sin separación\nCapítulo 1. Uno\n{cuerpo}\nCapítulo 2 Dos\n{cuerpo}\nTema III: Tres\n{cuerpo}\n"
    assert [c["titulo"] for c in pools.dividir(pdf)] == ["Capítulo 1. Uno", "Capítulo 2 Dos", "Tema III: Tres"]
    prosa = ("Esto es prosa corrida\nparte 2 del contrato establece que el pago\n" + cuerpo) * 4
    assert [c["titulo"] for c in pools.dividir(prosa)][0] == "Parte 1"


def test_dividir_numerado_y_sin_cabeceras():
    cuerpo = ("Texto de relleno bastante largo. " * 20 + "\n\n")
    num = "".join(f"{i}. Tema número {i}\n\n{cuerpo}" for i in (1, 2, 3))
    assert [c["titulo"] for c in pools.dividir(num)] == [f"{i}. Tema número {i}" for i in (1, 2, 3)]
    plano = pools.dividir(("Una frase normal sin títulos. " * 40 + "\n\n") * 12)
    assert len(plano) > 1 and plano[0]["titulo"] == "Parte 1"
    assert all(len(c["texto"]) <= pools.MAX_CAP for c in plano)


def test_un_capitulo_enorme_se_parte():
    caps = pools.dividir("CAPÍTULO 1\n\n" + ("Párrafo largo de prueba. " * 30 + "\n\n") * 40
                         + "CAPÍTULO 2\n\n" + "Corto pero suficiente. " * 30)
    assert [c["titulo"] for c in caps][0].startswith("CAPÍTULO 1 (parte 1)")
    assert all(len(c["texto"]) <= pools.MAX_CAP for c in caps)


def test_pool_completo_y_recuperacion(falsos):
    import app as aplicacion  # noqa: F401  (crea el esquema)
    with bd.db() as c:
        c.execute("INSERT INTO docs(id,panel_id,agente_id,ambito,nombre,estado,ts) VALUES('d1','p','ag1','pool','huertos.pdf','subiendo',0)")
    pools.procesar("d1", b"%PDF")
    with bd.db() as c:
        d = c.execute("SELECT * FROM docs WHERE id='d1'").fetchone()
        assert d["estado"] == "listo", d["error"]
        caps = c.execute("SELECT * FROM capitulos WHERE doc_id='d1' ORDER BY orden").fetchall()
        assert len(caps) == 3 and caps[0]["resumen"] == "Resumen simple." and caps[0]["simplificado"] == 1
    texto, fuentes = pools.conocimiento("ag1", "¿Cómo puedo ahorrar agua con el riego?")
    assert fuentes[0]["capitulo"] == 2 and "goteo" in texto
    assert pools.conocimiento("otro-agente", "riego") == ("", [])
