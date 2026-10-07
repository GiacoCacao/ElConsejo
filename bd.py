"""SQLite: paneles, conversación, documentos, capítulos y su índice de texto (FTS5)."""
import sqlite3
from contextlib import contextmanager

import config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS paneles(
  id TEXT PRIMARY KEY, nombre TEXT, descripcion TEXT, contexto TEXT, agentes TEXT, orden INTEGER);
CREATE TABLE IF NOT EXISTS mensajes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, panel_id TEXT, pregunta_id INTEGER, rol TEXT,
  agente_id TEXT, texto TEXT, imagenes TEXT, error INTEGER DEFAULT 0, ts REAL);
CREATE TABLE IF NOT EXISTS docs(
  id TEXT PRIMARY KEY, panel_id TEXT, agente_id TEXT, ambito TEXT, pregunta_id INTEGER,
  nombre TEXT, fabrica_id TEXT, estado TEXT, paso TEXT, error TEXT, caracteres INTEGER DEFAULT 0,
  texto TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS capitulos(
  id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT, agente_id TEXT, orden INTEGER,
  titulo TEXT, resumen TEXT, claves TEXT, texto TEXT, simplificado INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS consumo(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, panel_id TEXT, agente_id TEXT, pregunta_id INTEGER,
  tipo TEXT, modelo TEXT, entrada INTEGER, salida INTEGER, cache INTEGER, estimado INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS i_consumo_panel ON consumo(panel_id);
CREATE TABLE IF NOT EXISTS tarifas(
  modelo TEXT PRIMARY KEY, proveedor TEXT, contexto INTEGER, entrada REAL, cache REAL, salida REAL,
  entrada_punta REAL, cache_punta REAL, salida_punta REAL, franja TEXT);   -- USD por millón de tokens
CREATE TABLE IF NOT EXISTS sesiones(
  id INTEGER PRIMARY KEY AUTOINCREMENT, panel_id TEXT, numero INTEGER, asunto TEXT, estado TEXT,
  modo_debate TEXT, orden TEXT, anexos TEXT, abierta REAL, cerrada REAL, acta TEXT, acuerdo TEXT, resultado TEXT);
CREATE INDEX IF NOT EXISTS i_ses_panel ON sesiones(panel_id);
CREATE TABLE IF NOT EXISTS votaciones(
  id INTEGER PRIMARY KEY AUTOINCREMENT, sesion_id INTEGER, tipo TEXT, propuesta TEXT, alternativas TEXT,
  estado TEXT, intento INTEGER, resultado TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS votos(
  id INTEGER PRIMARY KEY AUTOINCREMENT, votacion_id INTEGER, agente_id TEXT, opcion TEXT, motivo TEXT,
  error INTEGER DEFAULT 0, ts REAL);
CREATE TABLE IF NOT EXISTS semillas(nombre TEXT PRIMARY KEY);   -- paneles de serie ya sembrados
CREATE INDEX IF NOT EXISTS i_cap_doc ON capitulos(doc_id);
CREATE INDEX IF NOT EXISTS i_cap_ag ON capitulos(agente_id);
CREATE INDEX IF NOT EXISTS i_docs_ag ON docs(agente_id);
CREATE VIRTUAL TABLE IF NOT EXISTS capfts USING fts5(
  titulo, resumen, texto, cap_id UNINDEXED, agente_id UNINDEXED,
  tokenize='unicode61 remove_diacritics 2');
"""
# columnas añadidas después de la primera versión
MIGRACIONES = [("mensajes", "ronda", "INTEGER DEFAULT 0"),
               ("mensajes", "adjuntos", "TEXT"),
               ("mensajes", "fuentes", "TEXT"),
               ("mensajes", "sesion_id", "INTEGER")]


@contextmanager
def db():
    c = sqlite3.connect(config.DB, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init():
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(ESQUEMA)
        for tabla, col, tipo in MIGRACIONES:
            if col not in {r["name"] for r in c.execute(f"PRAGMA table_info({tabla})")}:
                c.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")
        # reparación: las respuestas pertenecen a la sesión de su pregunta (versiones previas no lo guardaban)
        c.execute("UPDATE mensajes SET sesion_id=(SELECT q.sesion_id FROM mensajes q WHERE q.id=mensajes.pregunta_id) "
                  "WHERE rol='agent' AND sesion_id IS NULL AND (SELECT q.sesion_id FROM mensajes q WHERE q.id=mensajes.pregunta_id) IS NOT NULL")
        # consultas anteriores a las sesiones: una sesión cerrada (sin acta) por panel que las agrupa
        for (pid,) in c.execute("SELECT DISTINCT panel_id FROM mensajes WHERE sesion_id IS NULL").fetchall():
            t = c.execute("SELECT MIN(ts), MAX(ts) FROM mensajes WHERE panel_id=? AND sesion_id IS NULL", (pid,)).fetchone()
            n = c.execute("SELECT COALESCE(MAX(numero),0)+1 FROM sesiones WHERE panel_id=?", (pid,)).fetchone()[0]
            cur = c.execute("INSERT INTO sesiones(panel_id,numero,asunto,estado,modo_debate,orden,anexos,abierta,cerrada) "
                            "VALUES(?,?,?,?,?,?,?,?,?)", (pid, n, "Consultas anteriores a las sesiones", "cerrada",
                                                        "simultaneo", "[]", "[]", t[0], t[1]))
            c.execute("UPDATE mensajes SET sesion_id=? WHERE panel_id=? AND sesion_id IS NULL", (cur.lastrowid, pid))
        import consumo   # aquí para evitar el import circular
        consumo.sembrar(c)
        # un reinicio corta los hilos de procesado: que no queden «en curso» para siempre
        c.execute("UPDATE docs SET estado='error', error='Interrumpido por un reinicio; pulsa Reprocesar' "
                  "WHERE estado NOT IN ('listo','error')")
