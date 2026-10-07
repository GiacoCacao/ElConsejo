"""Pools por agente: cada documento se divide en capítulos, se simplifica, se ordena y se indexa.

Flujo (en segundo plano): subir a la fábrica → extraer texto (OCR si hace falta) → dividir en
capítulos → resumir cada uno con IA → índice de texto (FTS5). Al responder, el agente recibe los
capítulos más pertinentes (FTS5 + búsqueda semántica de la fábrica).
"""
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import bd
import fabrica
import ia

MIN_CAP, MAX_CAP, TROZO = 350, 9000, 5000
MAX_RESUMIR = 60       # capítulos por documento que se resumen con IA; el resto, extracto
TOPE_CHAT = 14000      # caracteres de un PDF del chat que se pasan enteros

RE_CAP = re.compile(r"^\s{0,6}(?:#{1,6}\s*)?((?i:cap[ií]tulo|cap\.|tema|secci[oó]n|parte|unidad|lecci[oó]n"
                    r"|m[oó]dulo|anexo|ap[eé]ndice|chapter|section|part)\s+(?:\d+|[IVXLCDM]+)\b.*)$")
# «Capítulo 2. Riego», «Tema 3: Plagas», «Parte IV Suelos»… pero no «parte 2 del contrato establece»
RE_TITULO = re.compile(r"^\W*[\w.]+\s+(?:\d+|[IVXLCDM]+)\s*(?:[.:\-–—)]|$|\s+[A-ZÁÉÍÓÚÑ¿¡])")
RE_MD = re.compile(r"^\s{0,3}(#{1,3})\s+(.+?)\s*#*$")
RE_NUM = re.compile(r"^\s{0,6}(\d{1,2})[.)]\s+([A-ZÁÉÍÓÚÑ¿¡][^\n]{2,90})$")
PARADAS = set("de la el los las un una unos unas y o u e a en que qué por para con sin sobre del al se es son "
              "como cómo cuál cual cuáles cuales cuando cuándo donde dónde mi tu su lo le les me te nos más "
              "muy ya no sí si pero también este esta estos estas ese esa eso hay ser está están".split())


# ---- dividir ---------------------------------------------------------------
def _limpiar(t):
    t = t.replace("\r", "").replace("\f", "\n\n")
    t = re.sub(r"[ \t]+\n", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _titulo(s):
    return re.sub(r"\s+", " ", s.strip(" #*_\t")).strip()[:110]


def _detectar(lineas):
    """Líneas que parecen cabeceras de capítulo, por orden de fiabilidad."""
    def tras_vacia(i):   # los PDF no suelen dejar línea en blanco: vale también tras el final de una frase
        return i == 0 or not lineas[i - 1].strip() or lineas[i - 1].rstrip().endswith((".", "!", "?"))
    cap, md, num, may = [], [], [], []
    for i, l in enumerate(lineas):
        s = l.strip()
        if not s or len(s) > 110:
            continue
        if (m := RE_CAP.match(l)) and (tras_vacia(i) or (len(s) <= 70 and RE_TITULO.match(s))):
            cap.append((i, _titulo(m.group(1))))
        if m := RE_MD.match(l):
            md.append((i, _titulo(m.group(2)), len(m.group(1))))
        if (m := RE_NUM.match(l)) and tras_vacia(i) and not s.endswith((".", ",", ";", ":")) and len(s.split()) <= 12:
            num.append((i, _titulo(s)))
        if (s.isupper() and 4 <= len(s) <= 80 and sum(ch.isalpha() for ch in s) >= 4 and tras_vacia(i)):
            may.append((i, _titulo(s)))
    candidatos = [(cap, 2)]
    for nivel in (1, 2, 3):
        candidatos.append(([(i, t) for i, t, n in md if n == nivel], 2))
    candidatos += [(num, 3), (may, 3)]
    for lista, minimo in candidatos:
        if minimo <= len(lista) <= 300:
            return lista
    return []


def _trocear(texto, tam):
    """Trozos de ~tam caracteres cortando por párrafos."""
    trozos, actual = [], ""
    for p in re.split(r"\n\s*\n", texto):
        while len(p) > tam:   # párrafo gigante: se corta en una frase o a pelo
            corte = max(p.rfind(". ", 0, tam), p.rfind("\n", 0, tam))
            corte = corte + 1 if corte > tam // 2 else tam
            if actual:
                trozos.append(actual)
                actual = ""
            trozos.append(p[:corte].strip())
            p = p[corte:].strip()
        if actual and len(actual) + len(p) > tam:
            trozos.append(actual)
            actual = ""
        actual = f"{actual}\n\n{p}".strip()
    if actual:
        trozos.append(actual)
    return [t for t in trozos if t.strip()]


def dividir(texto):
    """Texto → [{titulo, texto}] en orden. Cabeceras si las hay; si no, partes de tamaño parejo."""
    texto = _limpiar(texto)
    if not texto:
        return []
    lineas = texto.split("\n")
    cab = _detectar(lineas)
    if cab:
        caps = []
        previo = "\n".join(lineas[:cab[0][0]]).strip()
        if len(previo) >= MIN_CAP:
            caps.append(("Introducción", previo))
        for k, (i, t) in enumerate(cab):
            fin = cab[k + 1][0] if k + 1 < len(cab) else len(lineas)
            caps.append((t, "\n".join(lineas[i + 1:fin]).strip()))
    else:
        caps = [(f"Parte {n}", t) for n, t in enumerate(_trocear(texto, TROZO), 1)]
    fusion = []
    for t, c in caps:   # un capítulo casi vacío se pega al anterior en vez de quedar suelto
        if fusion and len(c) < MIN_CAP:
            fusion[-1] = (fusion[-1][0], f"{fusion[-1][1]}\n\n{t}\n{c}".strip())
        else:
            fusion.append((t, c))
    final = []
    for t, c in fusion:
        trozos = _trocear(c, MAX_CAP) if len(c) > MAX_CAP else [c]
        for n, x in enumerate(trozos, 1):
            if x.strip():
                final.append({"titulo": t if len(trozos) == 1 else f"{t} (parte {n})", "texto": x})
    return final or [{"titulo": "Documento", "texto": texto}]


# ---- simplificar -----------------------------------------------------------
SISTEMA_RESUMEN = ("Simplificas capítulos de documentos. Resume el capítulo en español sencillo, máximo 80 "
                   "palabras, sin florituras y sin inventar nada.\nResponde exactamente así:\n"
                   "TITULO: <título breve y descriptivo>\nRESUMEN: <resumen>\nCLAVES: <5 palabras clave, separadas por comas>")


def _extracto(texto, n=300):
    plano = re.sub(r"\s+", " ", texto).strip()
    frases = re.split(r"(?<=[.!?])\s+", plano)
    return (" ".join(frases[:2]) if frases else plano)[:n].strip()


def simplificar(titulo, texto):
    """→ (titulo, resumen, claves, hecho_con_ia). Sin IA o si falla, cae a un extracto."""
    if ia.configurada():
        try:
            r = ia.llamar([{"role": "system", "content": SISTEMA_RESUMEN},
                           {"role": "user", "content": f"Capítulo: {titulo}\n\n{texto[:6000]}"}],
                          temperatura=0.2, max_tokens=300)
            campo = lambda k: (re.search(rf"^{k}:\s*(.+?)(?=^\w+:|\Z)", r, re.M | re.S) or [None, ""])[1].strip()
            resumen = campo("RESUMEN")
            if resumen:
                return campo("TITULO") or titulo, resumen, campo("CLAVES"), True
        except ia.IAError:
            pass
    return titulo, _extracto(texto), "", False


# ---- procesar un documento -------------------------------------------------
def _estado(doc_id, estado, paso=None, error=None):
    with bd.db() as c:
        c.execute("UPDATE docs SET estado=?, paso=?, error=? WHERE id=?", (estado, paso, error, doc_id))


def borrar_capitulos(c, doc_id):
    c.execute("DELETE FROM capfts WHERE cap_id IN (SELECT id FROM capitulos WHERE doc_id=?)", (doc_id,))
    c.execute("DELETE FROM capitulos WHERE doc_id=?", (doc_id,))


def _indexar(c, doc_id):
    c.execute("DELETE FROM capfts WHERE cap_id IN (SELECT id FROM capitulos WHERE doc_id=?)", (doc_id,))
    c.execute("INSERT INTO capfts(titulo,resumen,texto,cap_id,agente_id) "
              "SELECT titulo, resumen||' '||COALESCE(claves,''), texto, id, agente_id FROM capitulos WHERE doc_id=?",
              (doc_id,))


def procesar(doc_id, datos=None):
    """Hilo de fondo. Con `datos` sube el fichero a la fábrica; sin ellos reprocesa el ya subido."""
    try:
        with bd.db() as c:
            doc = c.execute("SELECT * FROM docs WHERE id=?", (doc_id,)).fetchone()
        if datos is not None:
            _estado(doc_id, "subiendo", "Enviando a la fábrica")
            fid = fabrica.subir(doc["nombre"], datos, ["elconsejo", f"agente:{doc['agente_id']}"])
            with bd.db() as c:
                c.execute("UPDATE docs SET fabrica_id=? WHERE id=?", (fid, doc_id))
        else:
            fid = doc["fabrica_id"]
            if not fid:
                raise RuntimeError("El documento no llegó a la fábrica: vuelve a subirlo")
        _estado(doc_id, "extrayendo", "La fábrica extrae el texto (OCR si está escaneado)")
        fabrica.esperar(fid)
        texto = fabrica.texto(fid)
        if not texto.strip():
            raise RuntimeError("La fábrica no encontró texto en el documento")
        _estado(doc_id, "dividiendo", "Dividiendo en capítulos")
        caps = dividir(texto)
        with bd.db() as c:
            borrar_capitulos(c, doc_id)
            for n, cap in enumerate(caps, 1):
                c.execute("INSERT INTO capitulos(doc_id,agente_id,orden,titulo,resumen,texto) VALUES(?,?,?,?,?,?)",
                          (doc_id, doc["agente_id"], n, cap["titulo"], _extracto(cap["texto"]), cap["texto"]))
            c.execute("UPDATE docs SET caracteres=? WHERE id=?", (len(texto), doc_id))
            _indexar(c, doc_id)   # ya se puede consultar mientras se simplifica
        _estado(doc_id, "resumiendo", f"Simplificando {len(caps)} capítulos")
        with bd.db() as c:
            filas = c.execute("SELECT id, titulo, texto FROM capitulos WHERE doc_id=? ORDER BY orden", (doc_id,)).fetchall()
        genericos = {f["id"] for f in filas if re.match(r"(Parte \d+|Documento)$", f["titulo"])}

        def uno(f):
            t, r, k, hecho = simplificar(f["titulo"], f["texto"])
            return f["id"], (t if f["id"] in genericos else f["titulo"]), r, k, hecho

        with ThreadPoolExecutor(4) as pool:
            res = list(pool.map(uno, filas[:MAX_RESUMIR]))
        with bd.db() as c:
            for cid, t, r, k, hecho in res:
                c.execute("UPDATE capitulos SET titulo=?, resumen=?, claves=?, simplificado=? WHERE id=?",
                          (t, r, k, int(hecho), cid))
            _indexar(c, doc_id)
        _estado(doc_id, "listo", f"{len(caps)} capítulos")
    except Exception as e:  # noqa: BLE001 — se enseña en el panel
        _estado(doc_id, "error", None, str(e)[:300])


def lanzar(doc_id, datos=None):
    threading.Thread(target=procesar, args=(doc_id, datos), daemon=True).start()


# ---- recuperar lo pertinente para una pregunta -----------------------------
def _consulta_fts(pregunta):
    palabras = []
    for p in re.findall(r"\w{3,}", pregunta.lower()):
        if p not in PARADAS and p not in palabras:
            palabras.append(p)
    return " OR ".join(f'"{p[:-2]}"*' if len(p) >= 6 else f'"{p}"' for p in palabras[:12])


def _plano(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def conocimiento(agente_id, pregunta, k=3, tope=5000):
    """→ (texto para el prompt, fuentes). Vacío si el agente no tiene pool o nada encaja."""
    with bd.db() as c:
        docs = c.execute("SELECT id, nombre, fabrica_id FROM docs WHERE agente_id=? AND ambito='pool' "
                         "AND estado IN ('listo','resumiendo')", (agente_id,)).fetchall()
        if not docs:
            return "", []
        puntos, pasaje = {}, {}
        q = _consulta_fts(pregunta)
        if q:
            for rango, r in enumerate(c.execute(
                    "SELECT cap_id FROM capfts WHERE capfts MATCH ? AND agente_id=? ORDER BY bm25(capfts,5.0,2.0,1.0) LIMIT 6",
                    (q, agente_id))):
                puntos[r["cap_id"]] = puntos.get(r["cap_id"], 0) + 1 / (60 + rango)
        por_fabrica = {d["fabrica_id"]: d["id"] for d in docs if d["fabrica_id"]}
        if por_fabrica and fabrica.configurada():
            try:
                hits = fabrica.buscar(pregunta, list(por_fabrica), 6)
            except fabrica.FabricaError:
                hits = []   # la búsqueda por texto sigue funcionando sin la semántica
            for rango, h in enumerate(hits):
                frag = _plano(h.get("texto") or "")
                medio = frag[20:100] if len(frag) > 100 else frag
                doc_local = por_fabrica.get(h.get("documento_id"))
                if not medio or not doc_local:
                    continue
                for cap in c.execute("SELECT id, texto FROM capitulos WHERE doc_id=?", (doc_local,)):
                    if medio in _plano(cap["texto"]):
                        puntos[cap["id"]] = puntos.get(cap["id"], 0) + 1 / (60 + rango)
                        pasaje.setdefault(cap["id"], h["texto"])
                        break
        mejores = sorted(puntos, key=puntos.get, reverse=True)[:k]
        bloques, fuentes = [], []
        for cid in mejores:
            cap = c.execute("SELECT c.*, d.nombre AS doc FROM capitulos c JOIN docs d ON d.id=c.doc_id WHERE c.id=?",
                            (cid,)).fetchone()
            extracto = (pasaje.get(cid) or cap["texto"])[:1100].strip()
            bloques.append(f"### {cap['doc']} · cap. {cap['orden']}: {cap['titulo']}\n"
                           f"Resumen: {cap['resumen']}\nPasaje: {extracto}")
            fuentes.append({"doc": cap["doc"], "capitulo": cap["orden"], "titulo": cap["titulo"]})
    return "\n\n".join(bloques)[:tope], fuentes


def contexto_chat(doc, pregunta, tope=TOPE_CHAT):
    """Texto de un documento adjunto a la pregunta: entero si cabe; si no, el principio y lo pertinente."""
    t = doc["texto"] or ""
    if len(t) <= tope:
        return t
    partes = [t[:2500]]
    try:
        partes += [h["texto"] for h in fabrica.buscar(pregunta, [doc["fabrica_id"]], 6)]
    except fabrica.FabricaError:
        pal = set(re.findall(r"\w{4,}", pregunta.lower())) - PARADAS
        trozos = [t[i:i + 1200] for i in range(2500, len(t), 1200)]
        trozos.sort(key=lambda x: -len(pal & set(re.findall(r"\w{4,}", x.lower()))))
        partes += trozos[:5]
    return "\n[…]\n".join(partes)[:tope]
